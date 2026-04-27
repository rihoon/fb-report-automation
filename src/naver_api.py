"""네이버 커머스 API 연동.

Mock 모드: 시크릿이 없거나 use_mock=True면 Mock 데이터 반환.
실제 모드: 커머스 API로 주문 조회.

API 명세:
- 인증: POST /external/v1/oauth2/token (bcrypt + base64 서명)
- 주문 조회: GET /external/v1/pay-order/seller/product-orders
- 클레임: GET /external/v1/pay-order/seller/claims

서명 방식 (네이버 공식):
    1. message = client_id + "_" + timestamp(ms)
    2. hashed = bcrypt.hashpw(message, salt=client_secret)
    3. signature = base64(hashed)
"""

from __future__ import annotations

import base64
import time
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import bcrypt
import requests


NAVER_API_BASE = "https://api.commerce.naver.com"


def fetch_naver_orders(
    start_date: datetime,
    end_date: datetime,
    use_mock: bool = False,
    facebook_ads_for_mock: list | None = None,
) -> list:
    """네이버 스마트스토어 주문 조회."""
    if use_mock:
        return _fetch_mock(facebook_ads_for_mock)

    try:
        import streamlit as st
        cfg = st.secrets.get("naver", {})
        client_id = cfg.get("CLIENT_ID")
        client_secret = cfg.get("CLIENT_SECRET")
    except (ImportError, AttributeError, KeyError):
        return _fetch_mock(facebook_ads_for_mock)

    if not client_id or not client_secret:
        return _fetch_mock(facebook_ads_for_mock)

    return _fetch_real(start_date, end_date, client_id, client_secret)


_last_debug: dict = {"calls": [], "response_samples": []}


def get_last_debug_info() -> dict:
    """마지막 API 호출 진단 정보."""
    return _last_debug


def _fetch_real(
    start_date: datetime,
    end_date: datetime,
    client_id: str,
    client_secret: str,
) -> list:
    """실제 네이버 커머스 API 호출. 2단계:
    1) /last-changed-statuses 로 변경 주문 ID 목록 조회 (24h 청크)
    2) /query 로 상세 정보 일괄 조회 (300건 청크)

    네이버 제약:
    - lastChangedFrom~To 범위는 24시간 이내여야 함 → 일별로 쪼개서 호출
    """
    from src.mock_data import NaverOrder

    _last_debug["calls"] = []
    _last_debug["response_samples"] = []

    token = _get_oauth_token(client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1) 변경된 주문 ID 조회 - 24시간 단위로 쪼개서 호출
    list_url = f"{NAVER_API_BASE}/external/v1/pay-order/seller/product-orders/last-changed-statuses"
    all_product_order_ids: set[str] = set()

    # 진단: 여러 상태값을 시도해서 어느 것이 데이터를 주는지 확인
    status_types_to_try = ["PAYED", "PAY_WAITING", "DISPATCHED", "PURCHASE_DECIDED", "DELIVERED"]

    for chunk_start, chunk_end in _split_into_24h(start_date, end_date):
        chunk_total_ids = 0
        per_status_counts = {}

        for status_type in status_types_to_try:
            list_params = {
                "lastChangedFrom": chunk_start.strftime("%Y-%m-%dT%H:%M:%S.000+09:00"),
                "lastChangedTo": chunk_end.strftime("%Y-%m-%dT%H:%M:%S.000+09:00"),
                "lastChangedType": status_type,
            }
            list_resp = requests.get(list_url, headers=headers, params=list_params, timeout=30)
            if not list_resp.ok:
                # 상태값이 잘못된 경우는 패스 (다음 상태 시도)
                per_status_counts[status_type] = f"err {list_resp.status_code}"
                continue

            raw_json = list_resp.json()
            list_data = raw_json.get("data", {}) or {}
            statuses = (
                list_data.get("lastChangeStatuses", [])
                if isinstance(list_data, dict)
                else (list_data if isinstance(list_data, list) else [])
            )
            ids_in_status = 0
            for item in statuses:
                pid = item.get("productOrderId") if isinstance(item, dict) else None
                if pid:
                    all_product_order_ids.add(pid)
                    ids_in_status += 1
            per_status_counts[status_type] = ids_in_status
            chunk_total_ids += ids_in_status

            # 첫 번째 비어있는 응답 샘플 저장 (디버깅용)
            if ids_in_status == 0 and not _last_debug["response_samples"]:
                _last_debug["response_samples"].append({
                    "status_type": status_type,
                    "from": chunk_start.isoformat(),
                    "to": chunk_end.isoformat(),
                    "raw_response": raw_json,
                })

        _last_debug["calls"].append({
            "from": chunk_start.isoformat(),
            "to": chunk_end.isoformat(),
            "total_unique_ids": chunk_total_ids,
            "per_status": per_status_counts,
        })

    if not all_product_order_ids:
        return []

    # 2) 상세 일괄 조회 (300건씩)
    detail_url = f"{NAVER_API_BASE}/external/v1/pay-order/seller/product-orders/query"
    orders: list[NaverOrder] = []
    sample_saved = False
    for chunk in _chunked(sorted(all_product_order_ids), 300):
        body = {"productOrderIds": chunk}
        detail_resp = requests.post(detail_url, headers=headers, json=body, timeout=30)
        if not detail_resp.ok:
            raise requests.HTTPError(
                f"네이버 주문 상세 조회 실패 ({detail_resp.status_code}): {detail_resp.text}",
                response=detail_resp,
            )
        detail_data = detail_resp.json().get("data", []) or []

        # 첫 1건 샘플 저장 (UTM 필드 어디 있는지 디버깅용)
        if detail_data and not sample_saved:
            _last_debug["order_sample"] = detail_data[0]
            sample_saved = True

        for item in detail_data:
            orders.append(_parse_order_item(item))

    return orders


def _split_into_24h(start: datetime, end: datetime):
    """기간을 24시간 청크로 분할 (네이버 API 제약)."""
    current = start
    while current < end:
        chunk_end = min(current + timedelta(hours=24) - timedelta(seconds=1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(seconds=1)


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _parse_order_item(item: dict):
    """네이버 주문 상세 응답 1건을 NaverOrder로 변환.

    응답 구조 (nested):
    {
        "productOrder": {
            "productOrderId": "...",
            "productName": "...",
            "totalPaymentAmount": ...,
            "claimStatus": ...,
        },
        "order": {
            "orderId": "...",
            "paymentDate": "...",
            "orderDate": "...",
        }
    }
    """
    from src.mock_data import NaverOrder

    product_order = item.get("productOrder", item) or {}
    order_info = item.get("order", {}) or {}

    order_id = product_order.get("productOrderId") or order_info.get("orderId", "")
    product_name = product_order.get("productName", "")
    amount = float(product_order.get("totalPaymentAmount", 0) or 0)

    order_at_str = order_info.get("paymentDate") or order_info.get("orderDate")
    if order_at_str:
        try:
            order_at = datetime.fromisoformat(order_at_str.replace("Z", "+00:00"))
        except ValueError:
            order_at = datetime.now()
    else:
        order_at = datetime.now()

    # UTM 추출 (referrer/유입경로가 있다면)
    utm_source = utm_campaign = utm_content = None
    landing_url = (
        product_order.get("inflowPath")
        or order_info.get("inflowPath")
        or order_info.get("referer")
        or ""
    )
    if landing_url:
        utm_source, utm_campaign, utm_content = _extract_utm(landing_url)

    # 환불 여부 (claimStatus 또는 productOrderStatus)
    claim_status = product_order.get("claimStatus", "") or ""
    order_status = product_order.get("productOrderStatus", "") or ""
    is_refunded = (
        "REFUND" in claim_status.upper()
        or "CANCEL" in order_status.upper()
    )
    refund_amount = amount if is_refunded else 0.0

    return NaverOrder(
        order_id=str(order_id),
        product_name=product_name,
        amount=amount,
        order_at=order_at,
        utm_source=utm_source,
        utm_campaign=utm_campaign,
        utm_content=utm_content,
        refund_amount=refund_amount,
        is_refunded=is_refunded,
    )


def _extract_utm(url: str) -> tuple[str | None, str | None, str | None]:
    """URL에서 UTM 파라미터 추출."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        return (
            qs.get("utm_source", [None])[0],
            qs.get("utm_campaign", [None])[0],
            qs.get("utm_content", [None])[0],
        )
    except Exception:
        return None, None, None


_token_cache: dict = {"token": None, "expires_at": 0}


def _generate_signature(client_id: str, client_secret: str, timestamp_ms: int) -> str:
    """네이버 커머스 API 서명 생성.

    공식 가이드:
        message = f"{client_id}_{timestamp_ms}"
        hashed  = bcrypt.hashpw(message.encode(), salt=client_secret.encode())
        sign    = base64(hashed)
    """
    message = f"{client_id}_{timestamp_ms}".encode("utf-8")
    hashed = bcrypt.hashpw(message, client_secret.encode("utf-8"))
    return base64.b64encode(hashed).decode("utf-8")


def _get_oauth_token(client_id: str, client_secret: str) -> str:
    """네이버 커머스 OAuth 토큰 (캐시)."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    timestamp_ms = int(now * 1000)
    signature = _generate_signature(client_id, client_secret, timestamp_ms)

    url = f"{NAVER_API_BASE}/external/v1/oauth2/token"
    payload = {
        "client_id": client_id,
        "timestamp": str(timestamp_ms),
        "client_secret_sign": signature,
        "grant_type": "client_credentials",
        "type": "SELF",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(url, data=payload, headers=headers, timeout=10)
    if not resp.ok:
        # 응답 본문도 함께 표출 → 디버깅 용이
        raise requests.HTTPError(
            f"네이버 인증 실패 ({resp.status_code}): {resp.text}",
            response=resp,
        )
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
    return _token_cache["token"]


def _fetch_mock(facebook_ads_for_mock: list | None = None) -> list:
    """Mock 데이터로 fallback."""
    from src.mock_data import generate_facebook_ads, generate_naver_orders
    if not facebook_ads_for_mock:
        facebook_ads_for_mock = generate_facebook_ads(n_ads=60, seed=7)
    return generate_naver_orders(facebook_ads_for_mock, seed=107)
