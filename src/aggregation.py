"""광고별·담당자별 성과 집계."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd

from src.matching import MatchedRow


def matched_rows_to_dataframe(rows: Iterable[MatchedRow]) -> pd.DataFrame:
    """매칭 결과를 DataFrame으로 변환 (기본 컬럼)."""
    records = []
    method_label = {"exact": "정확", "partial": "분배", "manual": "수동", "": "❌"}
    for row in rows:
        ad = row.ad
        # FB Insights time_range는 inclusive (since~until 양 끝일 모두 포함) → +1
        period_days = max(1, (ad.date_stop - ad.date_start).days + 1)
        records.append({
            "담당자": ad.owner,
            "캠페인명": ad.campaign_name,
            "광고세트": ad.adset_name,
            "광고이름": ad.ad_name,
            "nt_source": ad.nt_source,
            "nt_medium": ad.nt_medium,
            "nt_detail": row.nt_detail,
            "nt_keyword": ad.nt_keyword,
            "매칭방식": method_label.get(row.match_method, row.match_method),
            "게재상태": ad.delivery_status,
            "도달": ad.reach,
            "클릭": ad.clicks,
            "노출": ad.impressions,
            "CPC": round(ad.cpc, 0),
            "CPM": round(ad.cpm, 0),
            "CTR": round(ad.ctr, 2),
            "지출": round(ad.spend, 0),
            "1일지출": round(ad.spend / period_days, 0),
            "매출": round(row.revenue, 0),
            "ROAS": round(row.roas, 0),
            "전환수": row.conversion_count,
            "유입수": row.naver_visits,
            "환불액": round(row.refund_amount, 0),
            "메모": "",  # 광고 매니저 코멘트용 — 시트에서 직접 입력
        })
    return pd.DataFrame(records)


def get_collection_period(report_date: datetime) -> tuple[datetime, datetime, int]:
    """보고일 기준 집계 기간 산출. **보고일 당일은 제외** (전날까지의 데이터만).

    - 월요일 → 금·토·일 (3일)
    - 수요일 → 월·화 (2일)
    - 금요일 → 수·목 (2일)
    - 그 외 요일 → 전일 1일 (fallback)

    Returns:
        (시작일 00:00, 종료일 23:59, 일수)
    """
    weekday = report_date.weekday()  # 월=0, 화=1, ..., 일=6

    if weekday == 0:  # 월요일 → 금·토·일
        days = 3
    elif weekday == 2:  # 수요일 → 월·화
        days = 2
    elif weekday == 4:  # 금요일 → 수·목
        days = 2
    else:
        days = 1

    # 보고일 전날 23:59:59 까지
    end_day = report_date - timedelta(days=1)
    end = datetime(end_day.year, end_day.month, end_day.day, 23, 59, 59)
    # 시작일 00:00:00
    start_day = end_day - timedelta(days=days - 1)
    start = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0)
    return start, end, days


def get_seven_day_window(report_date: datetime) -> tuple[datetime, datetime]:
    """7일 ROAS 계산용 윈도우 (보고일 기준 최근 7일)."""
    end = datetime(report_date.year, report_date.month, report_date.day, 23, 59, 59)
    start = end - timedelta(days=7)
    return start, end


def merge_seven_day(df: pd.DataFrame, history_lookup: dict[str, dict] | None) -> pd.DataFrame:
    """광고이름 기준으로 7일 누적 광고비/매출/ROAS 컬럼 추가.

    history_lookup 데이터는 구글 시트 누적 보고서에서 산출됨 (fetch_validity_history).
    """
    df = df.copy()
    spends: list = []
    revenues: list = []
    roases: list = []
    for ad_name in df["광고이름"]:
        h = (history_lookup or {}).get(ad_name, {})
        spend = float(h.get("7d_spend", 0) or 0)
        revenue = float(h.get("7d_revenue", 0) or 0)
        roas = float(h.get("7d_roas", 0) or 0)
        spends.append(round(spend, 0) if spend else pd.NA)
        revenues.append(round(revenue, 0) if revenue else pd.NA)
        roases.append(round(roas, 0) if spend > 0 else pd.NA)
    df["7일지출"] = spends
    df["7일매출"] = revenues
    df["7일ROAS"] = roases
    return df


def aggregate_kpi(df: pd.DataFrame) -> dict:
    """전체 KPI 4종 집계."""
    if df.empty:
        return {
            "total_spend": 0.0,
            "total_revenue": 0.0,
            "roas": 0.0,
            "conversion_count": 0,
        }
    total_spend = float(df["지출"].sum())
    total_revenue = float(df["매출"].sum())
    return {
        "total_spend": total_spend,
        "total_revenue": total_revenue,
        "roas": (total_revenue / total_spend * 100) if total_spend else 0.0,
        "conversion_count": int(df["전환수"].sum()),
    }


def aggregate_by_owner(df: pd.DataFrame) -> pd.DataFrame:
    """담당자별 합계."""
    if df.empty:
        return pd.DataFrame()
    grouped = df.groupby("담당자", as_index=False).agg({
        "지출": "sum",
        "매출": "sum",
        "전환수": "sum",
        "클릭": "sum",
        "노출": "sum",
    })
    grouped["ROAS"] = (grouped["매출"] / grouped["지출"] * 100).round(0)
    grouped["CTR"] = (grouped["클릭"] / grouped["노출"] * 100).round(2)
    return grouped
