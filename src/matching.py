"""페북 광고 ↔ 네이버 마케팅분석 데이터 매칭.

매칭 전략 (네이버 동작에 맞춰 조정):
- nt_medium은 네이버가 도메인 따라 자동 변환 (traffic → traffic_b/_e/_s) → 매칭 키에서 제외
- 1차: (nt_detail, nt_keyword) 정확 매칭 → 광고별 고유 매출
- 2차: nt_detail만 매칭 + 광고비 비율 분배 (4-tuple 실패한 광고들끼리)
- 3차: 매칭 실패
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.mock_data import FacebookAd


@dataclass
class MatchedRow:
    """광고 + 매칭된 네이버 데이터."""
    ad: FacebookAd
    matched_key: tuple = ("", "", "")  # (source, medium, detail)
    revenue: float = 0.0
    conversion_count: int = 0
    naver_visits: int = 0
    matched: bool = False
    match_method: str = ""  # "exact" | "manual" | ""
    n_keyword_rows: int = 0  # 합산된 nt_keyword 행 수

    @property
    def nt_detail(self) -> str:
        return self.matched_key[2] if self.matched_key else self.ad.nt_detail

    @property
    def roas(self) -> float:
        return (self.revenue / self.ad.spend * 100) if self.ad.spend else 0.0

    @property
    def refund_amount(self) -> float:
        return 0.0


FACEBOOK_SOURCE_KEYWORDS = ("facebook", "fb")
EXCLUDED_SOURCE_KEYWORDS = ("revu", "nshoplive", "youtuber", "naver_connect")


def _is_facebook_source(source: str) -> bool:
    """nt_source가 페북 광고인지 판정.

    페북 외 채널(Revu 협찬, nshoplive, YouTuber, naver_connect 등)은 제외.
    """
    s = (source or "").lower().strip()
    if not s:
        return False
    if any(ex in s for ex in EXCLUDED_SOURCE_KEYWORDS):
        return False
    return any(fb in s for fb in FACEBOOK_SOURCE_KEYWORDS)


def _build_naver_lookups(naver_df: pd.DataFrame) -> tuple[dict[tuple, dict], dict[str, dict]]:
    """네이버 raw DF를 두 가지 인덱스로 빌드 (페북 매출만).

    Returns:
        - lookup_dk: (nt_detail, nt_keyword) → 합산 데이터 + nt_source/medium 샘플 보존
        - lookup_d:  nt_detail → 합산 데이터
    """
    lookup_dk: dict[tuple, dict] = {}
    lookup_d: dict[str, dict] = {}
    if naver_df.empty:
        return lookup_dk, lookup_d
    for _, row in naver_df.iterrows():
        source = str(row.get("nt_source", "")).strip()
        medium = str(row.get("nt_medium", "")).strip()
        detail = str(row.get("nt_detail", "")).strip()
        keyword = str(row.get("nt_keyword", "")).strip()
        revenue = float(row.get("결제금액", 0) or 0)
        conv = int(row.get("결제수", 0) or 0)
        visits = int(row.get("유입수", 0) or 0)

        if not detail:
            continue
        if not _is_facebook_source(source):
            # 페북 외 채널(Revu/nshoplive/YouTuber/naver_connect 등)은 제외
            continue

        dk_key = (detail, keyword)
        ex_dk = lookup_dk.get(dk_key, {
            "revenue": 0.0, "conversion_count": 0, "visits": 0, "n_rows": 0,
            "nt_sources": set(), "nt_mediums": set(),
        })
        ex_dk["revenue"] += revenue
        ex_dk["conversion_count"] += conv
        ex_dk["visits"] += visits
        ex_dk["n_rows"] += 1
        if source:
            ex_dk["nt_sources"].add(source)
        if medium:
            ex_dk["nt_mediums"].add(medium)
        lookup_dk[dk_key] = ex_dk

        ex_d = lookup_d.get(detail, {"revenue": 0.0, "conversion_count": 0, "visits": 0, "n_rows": 0})
        ex_d["revenue"] += revenue
        ex_d["conversion_count"] += conv
        ex_d["visits"] += visits
        ex_d["n_rows"] += 1
        lookup_d[detail] = ex_d
    return lookup_dk, lookup_d


def match_facebook_with_naver(
    ads: Iterable[FacebookAd],
    naver_df: pd.DataFrame,
    manual_overrides: dict[str, tuple] | None = None,
) -> tuple[list[MatchedRow], list[dict]]:
    """페북 광고를 네이버 데이터와 매칭.

    매칭 키: (nt_detail, nt_keyword) — nt_medium 무시 (네이버가 자동 변환).

    Returns:
        (매칭 결과 목록, 사용 안 된 네이버 (detail, keyword) 후보)
    """
    manual_overrides = manual_overrides or {}
    lookup_dk, lookup_d = _build_naver_lookups(naver_df)
    ads_list = list(ads)

    # 1차: (detail, keyword) 매칭으로 흡수된 키
    used_dk_keys: set[tuple] = set()
    matched_dk_results: dict[int, MatchedRow] = {}

    for idx, ad in enumerate(ads_list):
        if ad.nt_detail and ad.nt_keyword:
            dk = (ad.nt_detail, ad.nt_keyword)
            if dk in lookup_dk:
                data = lookup_dk[dk]
                matched_dk_results[idx] = MatchedRow(
                    ad=ad, matched_key=(ad.nt_source, ad.nt_medium, ad.nt_detail, ad.nt_keyword),
                    revenue=data["revenue"],
                    conversion_count=data["conversion_count"],
                    naver_visits=data["visits"],
                    matched=True, match_method="exact",
                    n_keyword_rows=data["n_rows"],
                )
                used_dk_keys.add(dk)

    # 2차: detail만 매칭하여 폴백 (4-tuple 안 된 광고들끼리 광고비 분배)
    leftover_spend_by_detail: dict[str, float] = defaultdict(float)
    for idx, ad in enumerate(ads_list):
        if idx in matched_dk_results:
            continue
        if ad.nt_detail:
            leftover_spend_by_detail[ad.nt_detail] += ad.spend

    # 1차에 사용된 데이터를 빼고 남은 detail 데이터
    used_per_detail: dict[str, dict] = defaultdict(lambda: {"revenue": 0.0, "conversion_count": 0, "visits": 0})
    for dk_key in used_dk_keys:
        d = lookup_dk[dk_key]
        detail = dk_key[0]
        used_per_detail[detail]["revenue"] += d["revenue"]
        used_per_detail[detail]["conversion_count"] += d["conversion_count"]
        used_per_detail[detail]["visits"] += d["visits"]

    used_details: set[str] = set()
    rows: list[MatchedRow] = []

    for idx, ad in enumerate(ads_list):
        # 1. 수동 매칭 (이름은 ad_name → key 매핑)
        if ad.ad_name in manual_overrides:
            key = manual_overrides[ad.ad_name]
            # key 는 (detail,) 또는 (detail, keyword) 등 다양 가능
            if isinstance(key, tuple) and len(key) >= 2 and key[:2][::-1] != key[:2]:
                # (detail, keyword) 형태
                dk = (key[-2], key[-1]) if len(key) >= 2 else None
            else:
                dk = None
            # 단순화: key를 (detail, keyword)로만 받음
            if isinstance(key, tuple) and len(key) == 2 and key in lookup_dk:
                data = lookup_dk[key]
                rows.append(MatchedRow(
                    ad=ad, matched_key=("", "", key[0], key[1]),
                    revenue=data["revenue"],
                    conversion_count=data["conversion_count"],
                    naver_visits=data["visits"],
                    matched=True, match_method="manual",
                    n_keyword_rows=data["n_rows"],
                ))
                used_dk_keys.add(key)
                continue

        # 2. 1차 (detail, keyword) 결과
        if idx in matched_dk_results:
            rows.append(matched_dk_results[idx])
            continue

        # 3. detail만 매칭 + 광고비 비율 분배
        if ad.nt_detail and ad.nt_detail in lookup_d:
            full = lookup_d[ad.nt_detail]
            used = used_per_detail.get(ad.nt_detail, {"revenue": 0.0, "conversion_count": 0, "visits": 0})
            remaining_revenue = full["revenue"] - used["revenue"]
            remaining_conv = full["conversion_count"] - used["conversion_count"]
            remaining_visits = full["visits"] - used["visits"]

            total_spend = leftover_spend_by_detail.get(ad.nt_detail, 0.0)
            ratio = (ad.spend / total_spend) if total_spend > 0 else 0.0
            rows.append(MatchedRow(
                ad=ad, matched_key=("", "", ad.nt_detail, ad.nt_keyword),
                revenue=max(0.0, remaining_revenue * ratio),
                conversion_count=max(0, int(round(remaining_conv * ratio))),
                naver_visits=max(0, int(round(remaining_visits * ratio))),
                matched=True, match_method="partial",
                n_keyword_rows=full["n_rows"],
            ))
            used_details.add(ad.nt_detail)
            continue

        # 4. 매칭 실패
        rows.append(MatchedRow(
            ad=ad, matched_key=("", "", ad.nt_detail, ad.nt_keyword),
            matched=False,
        ))

    # 사용 안 된 네이버 행 (수동 매칭 후보)
    # 매출 0건은 매칭 필요 없으므로 제외
    unmatched_naver = []
    for (detail, keyword), data in lookup_dk.items():
        if (detail, keyword) in used_dk_keys:
            continue
        if detail in used_details:
            continue  # 폴백으로 흡수됨
        if data["revenue"] <= 0:
            continue  # 매출 0건은 매칭 필요 없음
        unmatched_naver.append({
            "nt_source": ", ".join(sorted(data.get("nt_sources", set()))),
            "nt_medium": ", ".join(sorted(data.get("nt_mediums", set()))),
            "nt_detail": detail,
            "nt_keyword": keyword,
            "revenue": data["revenue"],
            "conversion_count": data["conversion_count"],
            "visits": data["visits"],
            "n_keyword_rows": data["n_rows"],
        })

    # 매출 큰 순으로 정렬 (찾기 쉽게)
    unmatched_naver.sort(key=lambda x: -x["revenue"])

    return rows, unmatched_naver


def matching_stats(rows: list[MatchedRow], unmatched_naver: list[dict]) -> dict:
    """매칭 통계."""
    total_ads = len(rows)
    matched_ads = sum(1 for r in rows if r.matched)
    matched_revenue = sum(r.revenue for r in rows if r.matched)
    unmatched_naver_revenue = sum(item["revenue"] for item in unmatched_naver)
    return {
        "total_ads": total_ads,
        "matched_ads": matched_ads,
        "match_rate": (matched_ads / total_ads * 100) if total_ads else 0.0,
        "matched_revenue": matched_revenue,
        "unmatched_naver_count": len(unmatched_naver),
        "unmatched_naver_revenue": unmatched_naver_revenue,
        "exact_count": sum(1 for r in rows if r.match_method == "exact"),
        "partial_count": sum(1 for r in rows if r.match_method == "partial"),
        "manual_count": sum(1 for r in rows if r.match_method == "manual"),
    }
