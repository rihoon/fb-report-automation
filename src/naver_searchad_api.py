"""네이버 검색광고 OpenAPI 연동.

Mock 모드: 시크릿이 없거나 use_mock=True면 Mock 데이터 반환.
실제 모드: HMAC-SHA256 시그니처 인증으로 검색광고 보고서 조회.

검색광고 API 인증 방식 (네이버 광고 시스템 표준):
- 헤더:
    - X-Timestamp: 현재 시간 ms epoch
    - X-API-KEY: 발급받은 액세스 라이선스 키
    - X-Customer: 광고주 고객 ID
    - X-Signature: HMAC-SHA256(secret_key, message) → base64
- 서명 메시지: f"{timestamp}.{HTTP_METHOD}.{URI_PATH}"
  (URI는 query string 제외, 항상 path만)

엔드포인트 (실 API 검증 완료):
- GET /ncc/campaigns                        → 캠페인 목록
- GET /ncc/adgroups?nccCampaignId={id}      → 광고그룹 목록
- GET /stats?id={adgroup_id}&fields=...     → 광고그룹별 일별 stats

성과 필드 (실 API 응답에서 확정):
- salesAmt = 광고비 (₩)
- convAmt  = 매출 = 전환금액 (₩)
- ccnt     = 전환수
- impCnt   = 노출수
- clkCnt   = 클릭수
- avgRnk   = 평균노출순위

⚠️ /stats는 단일 ID(`id`)만 받음 → 광고그룹마다 1콜.
키워드 단위 fetch는 v2에서 추가 예정.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any

import requests


# 검색광고 API 베이스 URL
SEARCHAD_API_BASE = "https://api.searchad.naver.com"

# 엔드포인트 path (실 API 검증 완료)
SEARCHAD_CAMPAIGNS_PATH = "/ncc/campaigns"
SEARCHAD_ADGROUPS_PATH = "/ncc/adgroups"
SEARCHAD_STATS_PATH = "/stats"


def fetch_search_ads(
    start_date: datetime,
    end_date: datetime,
    use_mock: bool = False,
) -> list:
    """네이버 검색광고 보고서 조회 (광고그룹 단위).

    Args:
        start_date: 조회 시작일 (포함).
        end_date: 조회 종료일 (포함).
        use_mock: True면 Mock 데이터 사용 (개발/테스트).

    Returns:
        SearchAd 리스트 (광고그룹 단위, 기간 합산).
    """
    if use_mock:
        return _fetch_mock(start_date, end_date)

    try:
        import streamlit as st
        cfg = st.secrets.get("naver_searchad", {})
        api_key = cfg.get("API_KEY")
        secret_key = cfg.get("SECRET_KEY")
        customer_id = cfg.get("CUSTOMER_ID")
    except (ImportError, AttributeError, KeyError):
        return _fetch_mock(start_date, end_date)

    if not all([api_key, secret_key, customer_id]):
        return _fetch_mock(start_date, end_date)

    return _fetch_real(start_date, end_date, api_key, secret_key, str(customer_id))


# ────────────────────── 진단 정보 ──────────────────────

_last_debug: dict = {"calls": [], "errors": [], "samples": []}


def get_last_debug_info() -> dict:
    """마지막 API 호출 진단 정보 (개발/디버깅용)."""
    return _last_debug


# ────────────────────── 인증 (HMAC-SHA256) ──────────────────────

def _generate_signature(
    secret_key: str,
    timestamp_ms: int,
    method: str,
    uri_path: str,
) -> str:
    """네이버 광고 시스템 표준 HMAC-SHA256 서명 생성.

    message = f"{timestamp_ms}.{METHOD_UPPER}.{URI_PATH}"
    sign    = HMAC-SHA256(secret_key, message) → base64
    """
    message = f"{timestamp_ms}.{method.upper()}.{uri_path}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_auth_headers(
    access_key: str,
    secret_key: str,
    customer_id: str,
    method: str,
    uri_path: str,
) -> dict[str, str]:
    """인증 헤더 4종 빌드."""
    timestamp_ms = int(time.time() * 1000)
    signature = _generate_signature(secret_key, timestamp_ms, method, uri_path)
    return {
        "X-Timestamp": str(timestamp_ms),
        "X-API-KEY": access_key,
        "X-Customer": str(customer_id),
        "X-Signature": signature,
        "Content-Type": "application/json; charset=UTF-8",
    }


# ────────────────────── 실제 API 호출 ──────────────────────

def _fetch_real(
    start_date: datetime,
    end_date: datetime,
    api_key: str,
    secret_key: str,
    customer_id: str,
) -> list:
    """실제 네이버 검색광고 API 호출.

    동작 흐름:
    1. 캠페인 목록 조회 (GET /ncc/campaigns)
    2. 캠페인별 광고그룹 목록 조회 (GET /ncc/adgroups?nccCampaignId=...)
    3. 광고그룹별 stats 조회 (GET /stats?id=...) — 일별 데이터 → 기간 합산
    4. 메타 + 통계 결합 → SearchAd 리스트 반환

    실패하거나 응답 비면 Mock fallback.
    """
    from src.mock_data import SearchAd

    _last_debug["calls"] = []
    _last_debug["errors"] = []

    try:
        # 1. 캠페인 메타 조회
        campaigns = _api_get(SEARCHAD_CAMPAIGNS_PATH, api_key, secret_key, customer_id)
        if not campaigns:
            _last_debug["errors"].append("캠페인 메타 비어있음")
            return _fetch_mock(start_date, end_date)
        campaign_lookup = {c["nccCampaignId"]: c.get("name", "") for c in campaigns}

        # 2. 캠페인별 광고그룹 모두 모음
        adgroups: list[dict] = []
        for camp in campaigns:
            ags = _api_get(
                SEARCHAD_ADGROUPS_PATH, api_key, secret_key, customer_id,
                params={"nccCampaignId": camp["nccCampaignId"]},
            )
            adgroups.extend(ags or [])

        if not adgroups:
            _last_debug["errors"].append("광고그룹 메타 비어있음")
            return _fetch_mock(start_date, end_date)

        # 3. 광고그룹별 stats 조회 + 메타 결합
        results: list[SearchAd] = []
        for ag in adgroups:
            ag_id = ag.get("nccAdgroupId", "")
            stat = _fetch_adgroup_stats(
                api_key, secret_key, customer_id,
                adgroup_id=ag_id,
                start_date=start_date,
                end_date=end_date,
            )

            impressions = int(stat.get("impCnt", 0) or 0)
            clicks = int(stat.get("clkCnt", 0) or 0)
            # 광고그룹 status는 응답에 없을 수 있어 userLock 으로 추정
            status_raw = ag.get("status") or ("paused" if ag.get("userLock") else "active")

            results.append(SearchAd(
                campaign_name=campaign_lookup.get(ag.get("nccCampaignId", ""), ""),
                adgroup_name=ag.get("name", ""),
                impressions=impressions,
                clicks=clicks,
                spend=float(stat.get("salesAmt", 0) or 0),
                conversion_count=int(stat.get("ccnt", 0) or 0),
                revenue=float(stat.get("convAmt", 0) or 0),
                avg_position=float(stat.get("avgRnk", 0) or 0),
                date_start=start_date,
                date_stop=end_date,
                delivery_status=str(status_raw).lower(),
            ))
        return results

    except Exception as e:
        _last_debug["errors"].append(f"{type(e).__name__}: {e}")
        return _fetch_mock(start_date, end_date)


def _api_get(
    uri_path: str,
    api_key: str,
    secret_key: str,
    customer_id: str,
    params: dict | None = None,
) -> Any:
    """검색광고 API GET 요청 (인증 헤더 포함)."""
    url = f"{SEARCHAD_API_BASE}{uri_path}"
    headers = _build_auth_headers(api_key, secret_key, customer_id, "GET", uri_path)
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    _last_debug["calls"].append({
        "method": "GET",
        "uri": uri_path,
        "status": resp.status_code,
    })
    if not resp.ok:
        raise requests.HTTPError(
            f"검색광고 GET {uri_path} 실패 ({resp.status_code}): {resp.text[:200]}",
            response=resp,
        )
    data = resp.json()
    if isinstance(data, dict):
        return data.get("data", data.get("items", []))
    return data


def _fetch_adgroup_stats(
    api_key: str,
    secret_key: str,
    customer_id: str,
    adgroup_id: str,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """광고그룹 단위 일별 stats 조회 → 기간 합산.

    응답 구조:
        {
            "summary": {...},
            "data": [
                {"dateStart": "...", "impCnt": ..., "clkCnt": ...,
                 "salesAmt": ..., "convAmt": ..., "ccnt": ..., "avgRnk": ...},
                ...일별 row...
            ]
        }

    Returns:
        합산된 dict: {"impCnt", "clkCnt", "salesAmt", "convAmt", "ccnt", "avgRnk"}
    """
    if not adgroup_id:
        return {}

    headers = _build_auth_headers(api_key, secret_key, customer_id, "GET", SEARCHAD_STATS_PATH)
    fields_json = json.dumps(["impCnt", "clkCnt", "salesAmt", "convAmt", "ccnt", "avgRnk"])
    time_range_json = json.dumps({
        "since": start_date.strftime("%Y-%m-%d"),
        "until": end_date.strftime("%Y-%m-%d"),
    })
    try:
        resp = requests.get(
            f"{SEARCHAD_API_BASE}{SEARCHAD_STATS_PATH}",
            params={"id": adgroup_id, "fields": fields_json, "timeRange": time_range_json},
            headers=headers,
            timeout=30,
        )
        _last_debug["calls"].append({
            "method": "GET",
            "uri": SEARCHAD_STATS_PATH,
            "status": resp.status_code,
            "id": adgroup_id,
        })
        if not resp.ok:
            return {}
        payload = resp.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else []

        # 일별 데이터 합산 — avgRnk 는 노출 가중평균
        total_imp = total_clk = total_conv = 0
        total_cost = total_revenue = 0.0
        weighted_rnk_sum = 0.0
        for row in rows:
            imp = int(row.get("impCnt", 0) or 0)
            total_imp += imp
            total_clk += int(row.get("clkCnt", 0) or 0)
            total_conv += int(row.get("ccnt", 0) or 0)
            total_cost += float(row.get("salesAmt", 0) or 0)
            total_revenue += float(row.get("convAmt", 0) or 0)
            weighted_rnk_sum += float(row.get("avgRnk", 0) or 0) * imp
        avg_rnk = (weighted_rnk_sum / total_imp) if total_imp else 0.0
        return {
            "impCnt": total_imp,
            "clkCnt": total_clk,
            "ccnt": total_conv,
            "salesAmt": total_cost,
            "convAmt": total_revenue,
            "avgRnk": round(avg_rnk, 2),
        }
    except Exception:
        return {}


# ────────────────────── Mock fallback ──────────────────────

def _fetch_mock(start_date: datetime, end_date: datetime) -> list:
    """Mock 검색광고 데이터 — 키 없을 때 또는 개발 시."""
    from src.mock_data import generate_search_ads
    period_days = max(1, (end_date - start_date).days + 1)
    return generate_search_ads(
        n_ads=20,
        period_days=period_days,
        ref_date=end_date,
        seed=2026,
    )
