"""네이버 검색광고 OpenAPI 연동 모듈 (광고그룹 단위).

공식 문서: https://naver.github.io/searchad-apidoc/

인증: HMAC-SHA256 시그니처 (헤더에 X-Timestamp/X-API-KEY/X-Customer/X-Signature 포함)

데이터 흐름 (광고그룹 단위):
1. /ncc/campaigns → 캠페인 목록
2. /ncc/adgroups → 광고그룹 목록 (캠페인별)
3. /stats?id={adgroup_id} → 광고그룹별 일별 성과 데이터
4. 일별 데이터를 기간 합계로 합산

⚠️ /stats 는 단일 ID(`id`)만 받음 — 광고그룹마다 1콜
키워드 단위 fetch는 v2에서 추가 예정.

응답 필드명 (실측 확인됨):
- salesAmt = 광고비 (₩)
- convAmt = 매출 = 전환금액 (₩)
- ccnt = 전환수
- impCnt = 노출수
- clkCnt = 클릭수
- avgRnk = 평균순위

Mock 모드: 시크릿이 없거나 use_mock=True면 가짜 데이터 반환.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import requests


SEARCHAD_BASE_URL = "https://api.searchad.naver.com"


# ────────────────────── 데이터 모델 ──────────────────────


@dataclass
class SearchAdGroup:
    """검색광고 광고그룹 단위 성과 데이터."""

    customer_id: str
    campaign_id: str
    campaign_name: str
    adgroup_id: str
    adgroup_name: str
    status: str = "ELIGIBLE"             # ELIGIBLE / INELIGIBLE / PAUSED / DELETED
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0                    # 광고비 (₩) — salesAmt
    revenue: float = 0.0                 # 매출 (₩) — convAmt
    conversions: int = 0                 # 전환수 — ccnt
    ctr: float = 0.0                     # 클릭률 (%) — 클릭/노출
    avg_position: float = 0.0            # 평균노출순위 — avgRnk
    date_start: datetime = field(default_factory=datetime.now)
    date_stop: datetime = field(default_factory=datetime.now)

    @property
    def roas(self) -> float:
        """ROAS (%) — 매출 / 광고비 * 100."""
        return (self.revenue / self.cost * 100) if self.cost else 0.0


# 호환을 위한 타입 별칭 (이전에 SearchAd로 import한 코드 보호)
SearchAd = SearchAdGroup


# ────────────────────── 인증 헬퍼 ──────────────────────


def _generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    """네이버 검색광고 OpenAPI HMAC-SHA256 시그니처 생성.

    Args:
        timestamp: 밀리초 단위 epoch 문자열 (예: "1614784800000")
        method: HTTP 메서드 (대문자, 예: "GET")
        uri: 호출 URI (쿼리스트링 제외, 예: "/ncc/campaigns")
        secret_key: 발급받은 비밀키 (base64)

    Returns:
        Base64 인코딩된 시그니처 문자열.
    """
    message = f"{timestamp}.{method.upper()}.{uri}"
    digest = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_headers(method: str, uri: str, api_key: str, secret_key: str, customer_id: str) -> dict:
    """네이버 검색광고 OpenAPI 호출용 인증 헤더 생성."""
    timestamp = str(int(time.time() * 1000))
    signature = _generate_signature(timestamp, method, uri, secret_key)
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": signature,
    }


# ────────────────────── 메인 fetch 함수 ──────────────────────


def fetch_search_ads(
    start_date: datetime,
    end_date: datetime,
    use_mock: bool = False,
) -> list[SearchAdGroup]:
    """네이버 검색광고 광고그룹 단위 성과 데이터 조회.

    Args:
        start_date: 조회 시작일 (KST).
        end_date: 조회 종료일 (KST, 포함).
        use_mock: True면 mock 데이터 반환.

    Returns:
        SearchAdGroup 리스트 (광고그룹 단위, 기간 합산).
    """
    if use_mock:
        return generate_mock_search_ads(start_date, end_date)

    try:
        import streamlit as st
        cfg = st.secrets.get("naver_searchad", {})
        api_key = cfg.get("API_KEY")
        secret_key = cfg.get("SECRET_KEY")
        customer_id = cfg.get("CUSTOMER_ID")
    except (ImportError, AttributeError, KeyError):
        return generate_mock_search_ads(start_date, end_date)

    if not all([api_key, secret_key, customer_id]):
        return generate_mock_search_ads(start_date, end_date)

    return _fetch_real(start_date, end_date, api_key, secret_key, str(customer_id))


# ────────────────────── 실제 API 호출 ──────────────────────


def _fetch_real(
    start_date: datetime,
    end_date: datetime,
    api_key: str,
    secret_key: str,
    customer_id: str,
) -> list[SearchAdGroup]:
    """네이버 검색광고 OpenAPI 실제 호출 — 광고그룹 단위 합산.

    1. 캠페인 목록 조회 (/ncc/campaigns)
    2. 캠페인별 광고그룹 목록 조회 (/ncc/adgroups?nccCampaignId=...)
    3. 광고그룹별 stats 조회 (/stats?id=...) — 일별 데이터 → 기간 합산
    """
    # 1. 캠페인 목록
    campaigns = _fetch_campaigns(api_key, secret_key, customer_id)
    if not campaigns:
        return []
    campaign_lookup = {c["nccCampaignId"]: c.get("name", "") for c in campaigns}

    # 2. 캠페인별 광고그룹 (모두 모음)
    adgroups: list[dict] = []
    for camp in campaigns:
        adgroups.extend(
            _fetch_adgroups(api_key, secret_key, customer_id, camp["nccCampaignId"])
        )

    # 3. 광고그룹별 stats — N콜 (광고그룹 수만큼)
    results: list[SearchAdGroup] = []
    for ag in adgroups:
        ag_id = ag.get("nccAdgroupId", "")
        stat = _fetch_adgroup_stats(api_key, secret_key, customer_id, ag_id, start_date, end_date)

        # 응답이 비어있으면 0으로 (기간에 활동 없는 광고그룹)
        impressions = stat.get("impCnt", 0)
        clicks = stat.get("clkCnt", 0)
        ctr = (clicks / impressions * 100) if impressions else 0.0

        # 광고그룹 status는 광고그룹 자체 status (ELIGIBLE 등) — userLock으로도 추정 가능
        # ncc/adgroups 응답에 status 필드 없으면 'ELIGIBLE' 기본
        status_raw = ag.get("status") or ("PAUSED" if ag.get("userLock") else "ELIGIBLE")

        results.append(
            SearchAdGroup(
                customer_id=customer_id,
                campaign_id=ag.get("nccCampaignId", ""),
                campaign_name=campaign_lookup.get(ag.get("nccCampaignId", ""), ""),
                adgroup_id=ag_id,
                adgroup_name=ag.get("name", ""),
                status=status_raw,
                impressions=impressions,
                clicks=clicks,
                cost=float(stat.get("salesAmt", 0)),
                revenue=float(stat.get("convAmt", 0)),
                conversions=int(stat.get("ccnt", 0)),
                ctr=round(ctr, 2),
                avg_position=float(stat.get("avgRnk", 0)),
                date_start=start_date,
                date_stop=end_date,
            )
        )
    return results


def _fetch_campaigns(api_key: str, secret_key: str, customer_id: str) -> list[dict]:
    """캠페인 목록 조회."""
    uri = "/ncc/campaigns"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)
    try:
        r = requests.get(f"{SEARCHAD_BASE_URL}{uri}", headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_adgroups(api_key: str, secret_key: str, customer_id: str, campaign_id: str) -> list[dict]:
    """캠페인별 광고그룹 목록 조회."""
    uri = "/ncc/adgroups"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)
    try:
        r = requests.get(
            f"{SEARCHAD_BASE_URL}{uri}",
            params={"nccCampaignId": campaign_id},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


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
                {"dateStart": "2026-04-30", "impCnt": 1238, "clkCnt": 67,
                 "salesAmt": 10829, "convAmt": 453300, "ccnt": 30, "avgRnk": 2.0},
                ...
            ]
        }

    Returns:
        합산된 dict: {"impCnt", "clkCnt", "salesAmt", "convAmt", "ccnt", "avgRnk"}
    """
    if not adgroup_id:
        return {}
    uri = "/stats"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)
    fields_json = json.dumps(["impCnt", "clkCnt", "salesAmt", "convAmt", "ccnt", "avgRnk"])
    time_range_json = json.dumps({
        "since": start_date.strftime("%Y-%m-%d"),
        "until": end_date.strftime("%Y-%m-%d"),
    })
    try:
        r = requests.get(
            f"{SEARCHAD_BASE_URL}{uri}",
            params={"id": adgroup_id, "fields": fields_json, "timeRange": time_range_json},
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        rows = payload.get("data", []) if isinstance(payload, dict) else []
        # 일별 데이터를 합산 (avgRnk는 가중평균, 나머지는 단순 합)
        total_imp = total_clk = total_conv = 0
        total_cost = total_revenue = 0.0
        weighted_rnk_sum = 0.0
        for row in rows:
            imp = int(row.get("impCnt", 0) or 0)
            clk = int(row.get("clkCnt", 0) or 0)
            total_imp += imp
            total_clk += clk
            total_conv += int(row.get("ccnt", 0) or 0)
            total_cost += float(row.get("salesAmt", 0) or 0)
            total_revenue += float(row.get("convAmt", 0) or 0)
            # avgRnk는 노출 가중평균 (간단 근사)
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


# ────────────────────── Mock 데이터 (개발/테스트용) ──────────────────────


_MOCK_CAMPAIGNS = [
    "01.브랜드_리훈", "02.다이어리_시즌", "03.플래너_상시", "04.노트_상시",
]
_MOCK_GROUPS_PER_CAMP = [
    ["브랜드_핵심", "브랜드_연관"],
    ["겨울다이어리", "신년다이어리", "이야기다이어리"],
    ["주간플래너", "초등플래너"],
    ["감성노트", "원노트"],
]


def generate_mock_search_ads(start_date: datetime, end_date: datetime) -> list[SearchAdGroup]:
    """개발/테스트용 mock 검색광고 광고그룹 데이터 생성."""
    rng = random.Random(start_date.toordinal())
    groups: list[SearchAdGroup] = []
    grp_idx = 0
    for camp_idx, camp_name in enumerate(_MOCK_CAMPAIGNS):
        for group_name in _MOCK_GROUPS_PER_CAMP[camp_idx]:
            impressions = rng.randint(500, 50000)
            clicks = rng.randint(20, max(30, impressions // 30))
            cost = clicks * rng.randint(50, 800)
            revenue_multiplier = rng.choice([0.5, 1.5, 3.0, 5.0, 8.0])  # 검색광고는 ROAS 보통 높음
            revenue = cost * revenue_multiplier
            conversions = int(clicks * rng.uniform(0.05, 0.20))
            ctr = (clicks / impressions * 100) if impressions else 0.0
            groups.append(SearchAdGroup(
                customer_id="MOCK",
                campaign_id=f"cmp_{camp_idx}",
                campaign_name=camp_name,
                adgroup_id=f"grp_{grp_idx:04d}",
                adgroup_name=group_name,
                status="ELIGIBLE" if rng.random() > 0.1 else "PAUSED",
                impressions=impressions,
                clicks=clicks,
                cost=round(cost, 0),
                revenue=round(revenue, 0),
                conversions=conversions,
                ctr=round(ctr, 2),
                avg_position=round(rng.uniform(1.0, 5.0), 1),
                date_start=start_date,
                date_stop=end_date,
            ))
            grp_idx += 1
    return groups


# ────────────────────── DataFrame 변환 헬퍼 ──────────────────────


def search_ads_to_dataframe(ads: Iterable[SearchAdGroup], days: int = 1):
    """SearchAdGroup 리스트를 DataFrame으로 변환 (검색광고 페이지 표시용)."""
    import pandas as pd

    records = []
    for ad in ads:
        records.append({
            "캠페인명": ad.campaign_name,
            "광고그룹": ad.adgroup_name,
            "노출": ad.impressions,
            "클릭": ad.clicks,
            "CTR": ad.ctr,
            "평균순위": ad.avg_position,
            "지출": round(ad.cost, 0),
            "매출": round(ad.revenue, 0),
            "전환수": ad.conversions,
            "ROAS": round(ad.roas, 0),
        })
    return pd.DataFrame(records)
