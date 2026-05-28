"""네이버 GFA(성과형) 광고 API 연동.

Mock 모드: 시크릿이 없거나 use_mock=True면 Mock 데이터 반환.
실제 모드: HMAC-SHA256 시그니처 인증으로 GFA 통계 보고서 조회.

GFA API 인증 방식 (네이버 광고 시스템 표준):
- 헤더:
    - X-Timestamp: 현재 시간 ms epoch
    - X-API-KEY: 발급받은 액세스 라이선스 키
    - X-Customer: 광고주 고객 ID
    - X-Signature: HMAC-SHA256(secret_key, message) → base64
- 서명 메시지: f"{timestamp}.{HTTP_METHOD}.{URI_PATH}"
  (URI는 query string 제외, 항상 path만)

GFA API endpoint는 키 발급 후 공식 문서에 맞춰 조정 필요.
현재는 표준 패턴으로 구현 + endpoint placeholder.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import datetime
from typing import Any

import requests


# GFA API 베이스 URL — 검색광고와 동일 도메인 (실측 검증됨)
GFA_API_BASE = "https://api.searchad.naver.com"

# 발견된 endpoint:
# - /ad-accounts: GET → 계정 목록 (adPlatformType="GFA"인 항목 자동 검출)
# - /stat-reports: POST → 통계 (정확한 schema는 공식 문서 필요, 11001 에러 반환 중)
GFA_AD_ACCOUNTS_PATH = "/ad-accounts"
GFA_STATS_PATH = "/stat-reports"

# 메타데이터 endpoint placeholder — 실제 path 미확정 (TODO: 공식 문서)
GFA_CAMPAIGNS_PATH = "/gfa/v1/campaigns"
GFA_ADGROUPS_PATH = "/gfa/v1/adgroups"
GFA_CREATIVES_PATH = "/gfa/v1/creatives"


def fetch_gfa_ads(
    start_date: datetime,
    end_date: datetime,
    use_mock: bool = False,
) -> list:
    """GFA 성과형 광고 보고서 조회.

    데이터 출처는 get_last_data_source() 로 확인 가능:
        "real"        → 실 API 정상
        "real_empty"  → 실 API 호출 OK이지만 데이터 없음
        "real_error"  → 실 API 호출 실패 (에러 발생)
        "mock"        → use_mock=True 또는 키 없음 → 가짜 데이터

    Args:
        start_date: 조회 시작일 (포함).
        end_date: 조회 종료일 (포함).
        use_mock: True면 강제로 Mock 데이터 사용.

    Returns:
        GFAAd 리스트 (real 실패 시 빈 리스트, mock 안 떨어짐).
    """
    global _data_source
    if use_mock:
        _data_source = "mock"
        return _fetch_mock(start_date, end_date)

    try:
        import streamlit as st
        cfg = st.secrets.get("naver_gfa", {})
        access_key = cfg.get("ACCESS_KEY")
        secret_key = cfg.get("SECRET_KEY")
        customer_id = cfg.get("CUSTOMER_ID")
    except (ImportError, AttributeError, KeyError):
        _data_source = "mock"
        _last_debug["errors"].append("Streamlit secrets 접근 실패")
        return _fetch_mock(start_date, end_date)

    if not all([access_key, secret_key, customer_id]):
        _data_source = "mock"
        _last_debug["errors"].append("[naver_gfa] 시크릿 미설정 → mock 사용")
        return _fetch_mock(start_date, end_date)

    return _fetch_real(start_date, end_date, access_key, secret_key, customer_id)


# ────────────────────── 진단 정보 ──────────────────────

_last_debug: dict = {"calls": [], "errors": [], "samples": []}
_data_source: str = "unknown"


def get_last_debug_info() -> dict:
    """마지막 API 호출 진단 정보 (개발/디버깅용)."""
    return _last_debug


def get_data_source() -> str:
    """마지막 호출의 데이터 출처: real / real_empty / real_error / mock / unknown."""
    return _data_source


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


# ────────────────────── GFA adAccountNo 자동 검출 ──────────────────────

def discover_gfa_ad_account(
    access_key: str,
    secret_key: str,
    customer_id: str,
) -> int | None:
    """master customer 아래의 모든 광고계정 중 adPlatformType="GFA"인 계정 번호 반환.

    실측 응답 예시:
        {"content": [
            {"adAccountNo": 1720164, "adAccount": {"adPlatformType": "SA", ...}},
            {"adAccountNo": 8489,    "adAccount": {"adPlatformType": "GFA", ...}}
        ]}

    Returns:
        adAccountNo (int) — GFA 계정 번호. 없으면 None.
    """
    try:
        accounts = _api_get(GFA_AD_ACCOUNTS_PATH, access_key, secret_key, customer_id)
        if not isinstance(accounts, list):
            return None
        for acc in accounts:
            ad_account = acc.get("adAccount", {}) if isinstance(acc, dict) else {}
            if ad_account.get("adPlatformType") == "GFA":
                no = acc.get("adAccountNo") or ad_account.get("no")
                if no is not None:
                    return int(no)
        return None
    except Exception as e:
        _last_debug["errors"].append(f"discover_gfa_ad_account: {type(e).__name__}: {e}")
        return None


# ────────────────────── 실제 API 호출 ──────────────────────

def _fetch_real(
    start_date: datetime,
    end_date: datetime,
    access_key: str,
    secret_key: str,
    customer_id: str,
) -> list:
    """실제 GFA API 호출.

    실패 시 Mock fallback 안 함 — 빈 리스트 반환 (data_source="real_error" 또는 "real_empty").
    """
    global _data_source
    from src.mock_data import GFAAd

    _last_debug["calls"] = []
    _last_debug["errors"] = []
    _last_debug["discovered_ad_account"] = None

    # 0. GFA adAccountNo 자동 검출 (master customer 아래 GFA 계정)
    ad_account_no = discover_gfa_ad_account(access_key, secret_key, customer_id)
    _last_debug["discovered_ad_account"] = ad_account_no
    if ad_account_no is None:
        _last_debug["errors"].append("GFA 계정 못 찾음 (adPlatformType=GFA 없음)")
        _data_source = "real_error"
        return []

    # reportTp 변형 — GFA 전용 / 전환 전용 보고서 타입을 순서대로 시도
    # 광고비가 0이어도 전환은 잡혀야 함 → 전환 전용 reportTp 우선 시도
    REPORT_TP_VARIANTS = [
        "AD_DETAIL",          # 기본 (광고비 포함)
        "AD",                 # 광고 단위
        "AD_CONVERSION",      # 전환 전용 (광고비 0이어도 데이터 있을 가능성)
        "AD_DETAIL_CONVERSION",
        "AD_OVERVIEW",
    ]

    try:
        results: list[GFAAd] = []
        from datetime import timedelta

        successful_tp: str | None = None
        for offset in range((end_date - start_date).days + 1):
            day = start_date + timedelta(days=offset)
            day_str = day.strftime("%Y-%m-%d")

            day_rows: list[dict] = []
            # 변형 reportTp 순회 — 첫 BUILT 응답 사용
            for tp in REPORT_TP_VARIANTS:
                rows = _fetch_report_for_date(
                    day_str, access_key, secret_key, customer_id, ad_account_no,
                    report_tp=tp,
                )
                if rows:  # 데이터 있으면 멈춤
                    day_rows = rows
                    if successful_tp is None:
                        successful_tp = tp
                        _last_debug.setdefault("info", []).append(
                            f"✅ 작동한 reportTp: {tp}"
                        )
                    break

            for r in day_rows:
                results.append(_row_to_gfa_ad(r, day, day))

        if not results:
            _last_debug["errors"].append(
                f"모든 reportTp 변형({REPORT_TP_VARIANTS}) 시도했으나 데이터 0건"
            )
            _data_source = "real_empty"
            return []
        _data_source = "real"
        return results
    except Exception as e:
        _last_debug["errors"].append(f"_fetch_real: {type(e).__name__}: {e}")
        _data_source = "real_error"
        return []


# 이하는 placeholder (활성화되지 않음 — TODO: GFA 메타 endpoint 확정 후 사용)
def _fetch_real_old(
    start_date: datetime,
    end_date: datetime,
    access_key: str,
    secret_key: str,
    customer_id: str,
) -> list:
    """기존 메타 조회 흐름 (placeholder, 호출되지 않음)."""
    from src.mock_data import GFAAd
    try:
        # 1. 캠페인 / 광고그룹 / 소재 메타 조회 (TODO: GFA 전용 path 미확정)
        campaigns = _api_get(GFA_CAMPAIGNS_PATH, access_key, secret_key, customer_id)
        adgroups = _api_get(GFA_ADGROUPS_PATH, access_key, secret_key, customer_id)
        creatives = _api_get(GFA_CREATIVES_PATH, access_key, secret_key, customer_id)

        # 인덱스 빌드
        campaign_by_id = {str(c.get("id", c.get("campaignId", ""))): c for c in (campaigns or [])}
        adgroup_by_id = {str(a.get("id", a.get("adgroupId", ""))): a for a in (adgroups or [])}

        # 2. 통계 보고서 조회 — creative IDs + 날짜 범위
        creative_ids = [str(cr.get("id", cr.get("creativeId", ""))) for cr in (creatives or [])]
        if not creative_ids:
            _last_debug["errors"].append("creatives 메타 비어있음")
            return _fetch_mock(start_date, end_date)

        stats_payload = {
            "ids": creative_ids,
            "fields": ["impressions", "clicks", "cost", "conversions", "salesAmount"],
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
        }
        stats = _api_post(GFA_STATS_PATH, stats_payload, access_key, secret_key, customer_id)
        stats_by_creative = {str(s.get("id", s.get("creativeId", ""))): s for s in (stats or [])}

        # 3. 메타 + 통계 결합
        results: list[GFAAd] = []
        for cr in creatives:
            cid = str(cr.get("id", cr.get("creativeId", "")))
            stat = stats_by_creative.get(cid, {})
            ag_id = str(cr.get("adgroupId", ""))
            ag = adgroup_by_id.get(ag_id, {})
            cp_id = str(ag.get("campaignId", ""))
            cp = campaign_by_id.get(cp_id, {})

            results.append(GFAAd(
                campaign_name=cp.get("name", ""),
                adgroup_name=ag.get("name", ""),
                creative_name=cr.get("name", ""),
                impressions=int(stat.get("impressions", 0) or 0),
                clicks=int(stat.get("clicks", 0) or 0),
                spend=float(stat.get("cost", 0) or 0),
                conversion_count=int(stat.get("conversions", 0) or 0),
                revenue=float(stat.get("salesAmount", 0) or 0),
                date_start=start_date,
                date_stop=end_date,
                delivery_status=cr.get("status", "active").lower(),
            ))
        return results

    except Exception as e:
        _last_debug["errors"].append(f"{type(e).__name__}: {e}")
        # 실패 시 Mock fallback (앱 멈추지 않게)
        return _fetch_mock(start_date, end_date)


# ────────────────────── 비동기 보고서 잡 흐름 ──────────────────────

def _fetch_report_for_date(
    statDt: str,
    access_key: str,
    secret_key: str,
    customer_id: str,
    ad_account_no: int,
    report_tp: str = "AD_DETAIL",
    max_polls: int = 30,
    poll_interval: float = 2.0,
) -> list:
    """비동기 보고서 잡 생성 → 폴링 → 다운로드 → 파싱.

    실측 검증된 흐름 (네이버 광고 시스템 표준):
    1. POST /stat-reports {"reportTp": "AD_DETAIL", "statDt": "YYYY-MM-DD"}
       → {"reportJobId": ..., "status": "REGIST"}
    2. GET /stat-reports/{id} 폴링 → status BUILT 까지
    3. status BUILT 시 downloadUrl 받아 데이터 다운로드 (TSV)
    4. TSV 파싱 → 행 리스트 반환

    status NONE이면 빈 리스트 (해당 날짜 데이터 없음).

    Args:
        statDt: "YYYY-MM-DD" (KST 기준, API가 UTC로 변환)
        ad_account_no: GFA adAccountNo (옵션 — 잡 페이로드에 포함)
        report_tp: "AD_DETAIL" 또는 "AD"
    """
    payload = {
        "reportTp": report_tp,
        "statDt": statDt,
        "adAccountNo": ad_account_no,  # GFA 계정 명시
    }
    code, body = _raw_call("/stat-reports", "POST", access_key, secret_key, customer_id, body=payload)
    if code != 200:
        _last_debug["errors"].append(f"잡 생성 실패 {code}: {body[:200]}")
        return []
    job = _parse_json(body)
    job_id = job.get("reportJobId")
    if not job_id:
        return []

    # 2. 폴링
    import time as _time
    for i in range(max_polls):
        _time.sleep(poll_interval)
        code, body = _raw_call(f"/stat-reports/{job_id}", "GET", access_key, secret_key, customer_id)
        if code != 200:
            _last_debug["errors"].append(f"폴링 실패 {code}")
            return []
        j = _parse_json(body)
        status = j.get("status")
        if status == "BUILT":
            download_url = j.get("downloadUrl", "")
            if not download_url:
                return []
            return _download_and_parse_tsv(download_url, access_key, secret_key, customer_id)
        if status in ("NONE", "FAILED"):
            # NONE = 데이터 없음 (정상 응답)
            return []
    _last_debug["errors"].append(f"폴링 타임아웃 (job_id={job_id})")
    return []


def _raw_call(uri, method, access_key, secret_key, customer_id, body=None):
    """저수준 HTTP 호출 (raw 응답 반환)."""
    headers = _build_auth_headers(access_key, secret_key, customer_id, method, uri.split("?")[0])
    url = f"{GFA_API_BASE}{uri}"
    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=30)
        _last_debug["calls"].append({"method": method, "uri": uri, "status": r.status_code})
        return r.status_code, r.text
    except Exception as e:
        _last_debug["errors"].append(f"_raw_call {uri}: {type(e).__name__}: {e}")
        return None, ""


def _parse_json(text: str) -> dict:
    import json as _json
    try:
        return _json.loads(text)
    except Exception:
        return {}


def _download_and_parse_tsv(
    download_url: str,
    access_key: str,
    secret_key: str,
    customer_id: str,
) -> list:
    """downloadUrl 호출 → TSV 파싱 → 딕셔너리 행 리스트 반환.

    헤더 + 데이터 행 구조. 첫 줄을 컬럼명으로, 나머지를 데이터로.
    """
    from urllib.parse import urlparse
    p = urlparse(download_url)
    sig_path = p.path
    headers = _build_auth_headers(access_key, secret_key, customer_id, "GET", sig_path)
    try:
        r = requests.get(download_url, headers=headers, timeout=60)
        if not r.ok:
            _last_debug["errors"].append(f"다운로드 실패 {r.status_code}")
            return []
        text = r.text
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return []
        header = lines[0].split("\t")
        rows = []
        for line in lines[1:]:
            cells = line.split("\t")
            row = {header[i]: cells[i] for i in range(min(len(header), len(cells)))}
            rows.append(row)
        # 진단: 첫 행 샘플 보존
        if rows:
            _last_debug["samples"] = rows[:3]
        return rows
    except Exception as e:
        _last_debug["errors"].append(f"다운로드/파싱 실패: {type(e).__name__}: {e}")
        return []


def _row_to_gfa_ad(row: dict, date_start: datetime, date_stop: datetime):
    """파싱된 행 → GFAAd 변환.

    실제 컬럼명은 BUILT 보고서 다운로드 후 _last_debug["samples"]로 확인.
    현재는 광고 시스템 표준 필드명 추측.
    """
    from src.mock_data import GFAAd
    return GFAAd(
        campaign_name=str(row.get("Campaign Name") or row.get("campaignName") or row.get("캠페인명") or ""),
        adgroup_name=str(row.get("Ad Group Name") or row.get("adgroupName") or row.get("광고그룹명") or ""),
        creative_name=str(row.get("Ad Name") or row.get("Creative") or row.get("creativeName") or row.get("소재명") or ""),
        impressions=int(float(row.get("Impressions") or row.get("impressions") or row.get("노출수") or 0)),
        clicks=int(float(row.get("Clicks") or row.get("clicks") or row.get("클릭수") or 0)),
        spend=float(row.get("Cost") or row.get("cost") or row.get("salesAmt") or row.get("광고비") or 0),
        conversion_count=int(float(row.get("Conversions") or row.get("ccnt") or row.get("전환수") or 0)),
        revenue=float(row.get("Conversion Sales") or row.get("convAmt") or row.get("전환매출") or 0),
        date_start=date_start,
        date_stop=date_stop,
        delivery_status="active",
    )


def _api_get(
    uri_path: str,
    access_key: str,
    secret_key: str,
    customer_id: str,
    params: dict | None = None,
) -> Any:
    """GFA API GET 요청 (인증 헤더 포함)."""
    url = f"{GFA_API_BASE}{uri_path}"
    headers = _build_auth_headers(access_key, secret_key, customer_id, "GET", uri_path)
    resp = requests.get(url, headers=headers, params=params or {}, timeout=30)
    _last_debug["calls"].append({
        "method": "GET",
        "uri": uri_path,
        "status": resp.status_code,
    })
    if not resp.ok:
        raise requests.HTTPError(
            f"GFA GET {uri_path} 실패 ({resp.status_code}): {resp.text[:200]}",
            response=resp,
        )
    data = resp.json()
    # 응답 구조: 보통 {"content": [...]} (GFA), {"data": [...]} 또는 [...] 그대로
    if isinstance(data, dict):
        return data.get("content", data.get("data", data.get("items", [])))
    return data


def _api_post(
    uri_path: str,
    payload: dict,
    access_key: str,
    secret_key: str,
    customer_id: str,
) -> Any:
    """GFA API POST 요청 (인증 헤더 + JSON body)."""
    url = f"{GFA_API_BASE}{uri_path}"
    headers = _build_auth_headers(access_key, secret_key, customer_id, "POST", uri_path)
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    _last_debug["calls"].append({
        "method": "POST",
        "uri": uri_path,
        "status": resp.status_code,
    })
    if not resp.ok:
        raise requests.HTTPError(
            f"GFA POST {uri_path} 실패 ({resp.status_code}): {resp.text[:200]}",
            response=resp,
        )
    data = resp.json()
    if isinstance(data, dict):
        return data.get("data", data.get("items", []))
    return data


# ────────────────────── Mock fallback ──────────────────────

def _fetch_mock(start_date: datetime, end_date: datetime) -> list:
    """Mock GFA 데이터 — 키 없을 때 또는 개발 시."""
    from src.mock_data import generate_gfa_ads
    period_days = max(1, (end_date - start_date).days + 1)
    return generate_gfa_ads(
        n_ads=25,
        period_days=period_days,
        ref_date=end_date,
        seed=2026,
    )
