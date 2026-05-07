"""네이버 검색광고 OpenAPI 연동 모듈.

공식 문서: https://naver.github.io/searchad-apidoc/

인증: HMAC-SHA256 시그니처 (헤더에 X-Timestamp/X-API-KEY/X-Customer/X-Signature 포함)

데이터 흐름:
1. /ncc/campaigns → 캠페인 목록
2. /ncc/adgroups → 광고그룹 목록
3. /ncc/keywords → 키워드 목록
4. /stats → 키워드별 성과 데이터 (광고비/노출/클릭/전환/매출)

Mock 모드: 시크릿이 없거나 USE_MOCK=True면 가짜 데이터 반환.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import requests


SEARCHAD_BASE_URL = "https://api.searchad.naver.com"


# ────────────────────── 데이터 모델 ──────────────────────


@dataclass
class SearchAd:
    """검색광고 키워드 단위 성과 데이터."""

    customer_id: str
    campaign_id: str
    campaign_name: str
    adgroup_id: str
    adgroup_name: str
    keyword_id: str
    keyword: str
    keyword_type: str = "일반"           # "브랜드" | "일반" | "쇼핑"
    status: str = "ELIGIBLE"             # "ELIGIBLE" | "INELIGIBLE" | "PAUSED" | "DELETED"
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0                    # 광고비 (₩)
    revenue: float = 0.0                 # 매출 (₩) — API 자체 제공
    conversions: int = 0                 # 전환수
    ctr: float = 0.0                     # 클릭률 (%) — API 또는 클릭/노출로 계산
    avg_position: float = 0.0            # 평균노출순위
    date_start: datetime = field(default_factory=datetime.now)
    date_stop: datetime = field(default_factory=datetime.now)

    @property
    def roas(self) -> float:
        """ROAS (%) — 매출 / 광고비 * 100."""
        return (self.revenue / self.cost * 100) if self.cost else 0.0


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
) -> list[SearchAd]:
    """네이버 검색광고 키워드 단위 성과 데이터 조회.

    Args:
        start_date: 조회 시작일 (KST).
        end_date: 조회 종료일 (KST, 포함).
        use_mock: True면 mock 데이터 반환 (개발/테스트).

    Returns:
        SearchAd 리스트 (키워드 단위, 기간 내 활동한 키워드만).
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
) -> list[SearchAd]:
    """네이버 검색광고 OpenAPI 실제 호출.

    1. 캠페인 목록 조회
    2. 각 캠페인의 광고그룹 목록 조회
    3. 각 광고그룹의 키워드 목록 조회
    4. 키워드별 성과 데이터 조회 (StatReport)
    """
    results: list[SearchAd] = []

    # 1. 캠페인 목록
    campaigns = _fetch_campaigns(api_key, secret_key, customer_id)

    # 캠페인별 ID/이름 매핑
    campaign_lookup = {c["nccCampaignId"]: c.get("name", "") for c in campaigns}

    # 2. 광고그룹 목록
    adgroups = _fetch_adgroups(api_key, secret_key, customer_id)
    adgroup_lookup = {
        a["nccAdgroupId"]: {
            "name": a.get("name", ""),
            "campaign_id": a.get("nccCampaignId", ""),
        }
        for a in adgroups
    }

    # 3. 키워드 목록
    keywords = _fetch_keywords(api_key, secret_key, customer_id)

    # 4. 키워드별 성과 데이터 조회 (배치)
    keyword_ids = [k["nccKeywordId"] for k in keywords]
    stats_lookup = _fetch_stats(
        api_key, secret_key, customer_id,
        ids=keyword_ids,
        id_type="id",  # 키워드 ID 단위
        start_date=start_date,
        end_date=end_date,
    )

    # 5. 조립
    for kw in keywords:
        kw_id = kw.get("nccKeywordId", "")
        adgroup_id = kw.get("nccAdgroupId", "")
        adgroup_info = adgroup_lookup.get(adgroup_id, {})
        campaign_id = adgroup_info.get("campaign_id", "")
        stat = stats_lookup.get(kw_id, {})

        impressions = int(stat.get("impCnt", 0) or 0)
        clicks = int(stat.get("clkCnt", 0) or 0)
        ctr = (clicks / impressions * 100) if impressions else 0.0

        results.append(
            SearchAd(
                customer_id=customer_id,
                campaign_id=campaign_id,
                campaign_name=campaign_lookup.get(campaign_id, ""),
                adgroup_id=adgroup_id,
                adgroup_name=adgroup_info.get("name", ""),
                keyword_id=kw_id,
                keyword=kw.get("keyword", ""),
                keyword_type=kw.get("type", "일반"),
                status=kw.get("status", "ELIGIBLE"),
                impressions=impressions,
                clicks=clicks,
                cost=float(stat.get("salesAmt", 0) or 0),  # ⚠️ 필드명 확인 필요
                revenue=float(stat.get("convAmt", 0) or 0),  # ⚠️ 필드명 확인 필요
                conversions=int(stat.get("ccnt", 0) or 0),  # ⚠️ 필드명 확인 필요
                ctr=round(ctr, 2),
                avg_position=float(stat.get("avgRnk", 0) or 0),  # ⚠️ 필드명 확인 필요
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
        return r.json() if isinstance(r.json(), list) else []
    except Exception:
        return []


def _fetch_adgroups(api_key: str, secret_key: str, customer_id: str) -> list[dict]:
    """광고그룹 목록 조회."""
    uri = "/ncc/adgroups"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)
    try:
        r = requests.get(f"{SEARCHAD_BASE_URL}{uri}", headers=headers, timeout=30)
        r.raise_for_status()
        return r.json() if isinstance(r.json(), list) else []
    except Exception:
        return []


def _fetch_keywords(api_key: str, secret_key: str, customer_id: str) -> list[dict]:
    """키워드 목록 조회."""
    uri = "/ncc/keywords"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)
    try:
        r = requests.get(f"{SEARCHAD_BASE_URL}{uri}", headers=headers, timeout=30)
        r.raise_for_status()
        return r.json() if isinstance(r.json(), list) else []
    except Exception:
        return []


def _fetch_stats(
    api_key: str,
    secret_key: str,
    customer_id: str,
    ids: list[str],
    id_type: str,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, dict]:
    """ID(키워드/광고그룹/캠페인) 단위 성과 데이터 조회.

    Args:
        ids: 조회할 ID 목록
        id_type: "id" (개별 ID 단위)
        start_date, end_date: 조회 기간

    Returns:
        {id: stat_dict} 형태로 반환
    """
    if not ids:
        return {}

    uri = "/stats"
    headers = _build_headers("GET", uri, api_key, secret_key, customer_id)

    # API 한도 고려해 1000개씩 배치 호출
    result: dict[str, dict] = {}
    BATCH_SIZE = 1000
    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i:i + BATCH_SIZE]
        params = {
            "ids": ",".join(batch_ids),
            "fields": '["impCnt","clkCnt","salesAmt","ccnt","convAmt","avgRnk","ctr","cpc"]',
            "timeRange": f'{{"since":"{start_date.strftime("%Y-%m-%d")}","until":"{end_date.strftime("%Y-%m-%d")}"}}',
        }
        try:
            r = requests.get(f"{SEARCHAD_BASE_URL}{uri}", headers=headers, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            # data 구조: { "data": [ {"id": "kwd_xxx", "impCnt": 100, ...}, ... ] }
            for row in data.get("data", []) if isinstance(data, dict) else []:
                _id = row.get("id")
                if _id:
                    result[_id] = row
        except Exception:
            continue
    return result


# ────────────────────── Mock 데이터 (개발/테스트용) ──────────────────────


_MOCK_KEYWORDS = [
    "다이어리", "오늘쓰임", "회사생활 다이어리", "이야기다이어리",
    "다다일력", "오늘기억다이어리", "초등플래너", "회사다이어리",
    "주간노트", "스터디플래너", "데일리플래너", "직장인다이어리",
    "리훈다이어리", "리훈오늘쓰임", "2026다이어리", "겨울방학플래너",
    "리훈노트", "감성노트", "원노트", "연간계획노트",
]
_MOCK_CAMPAIGNS = [
    "01.브랜드_리훈", "02.다이어리_시즌", "03.플래너_상시", "04.노트_상시",
]
_MOCK_TYPES = ["브랜드", "일반", "일반", "일반"]


def generate_mock_search_ads(start_date: datetime, end_date: datetime) -> list[SearchAd]:
    """개발/테스트용 mock 검색광고 데이터 생성."""
    rng = random.Random(start_date.toordinal())  # seed로 재현 가능
    ads: list[SearchAd] = []
    for i, kw in enumerate(_MOCK_KEYWORDS):
        camp_idx = i % len(_MOCK_CAMPAIGNS)
        impressions = rng.randint(50, 5000)
        clicks = rng.randint(1, max(2, impressions // 20))
        cost = clicks * rng.randint(50, 800)  # CPC 50~800원
        # 매출은 광고비의 0~5배 (다양성)
        revenue_multiplier = rng.choice([0, 0.5, 1.2, 2.0, 3.5, 5.0])
        revenue = cost * revenue_multiplier
        conversions = int(clicks * rng.uniform(0, 0.15))
        ctr = (clicks / impressions * 100) if impressions else 0.0
        ads.append(SearchAd(
            customer_id="MOCK",
            campaign_id=f"cmp_{camp_idx}",
            campaign_name=_MOCK_CAMPAIGNS[camp_idx],
            adgroup_id=f"grp_{i // 3}",
            adgroup_name=f"광고그룹 {i // 3 + 1}",
            keyword_id=f"kwd_{i:04d}",
            keyword=kw,
            keyword_type=_MOCK_TYPES[camp_idx],
            status="ELIGIBLE" if rng.random() > 0.1 else "PAUSED",
            impressions=impressions,
            clicks=clicks,
            cost=round(cost, 0),
            revenue=round(revenue, 0),
            conversions=conversions,
            ctr=round(ctr, 2),
            avg_position=round(rng.uniform(1.0, 10.0), 1),
            date_start=start_date,
            date_stop=end_date,
        ))
    return ads


# ────────────────────── DataFrame 변환 헬퍼 ──────────────────────


def search_ads_to_dataframe(ads: Iterable[SearchAd], days: int = 1):
    """SearchAd 리스트를 DataFrame으로 변환 (검색광고 페이지 표시용).

    Args:
        ads: SearchAd 리스트.
        days: 집계 일수 — 1일지출 계산용 (현재는 사용 안 함, 추후 확장)

    Returns:
        pandas.DataFrame
    """
    import pandas as pd

    records = []
    for ad in ads:
        records.append({
            "캠페인명": ad.campaign_name,
            "광고그룹": ad.adgroup_name,
            "키워드": ad.keyword,
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
