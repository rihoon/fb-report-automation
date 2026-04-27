"""작년 동기 / 지난주 비교 로직.

작년 비교는 **같은 주차** (요일 기준).
지난주 비교는 단순 7일 전.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def get_same_week_last_year(report_date: datetime) -> datetime:
    """작년 같은 주차의 같은 요일 산출.

    예: 2026-04-27 (월) → 2025-04-28 (월)
    ISO 주차 기준으로 같은 주의 같은 요일을 찾음.
    """
    year_ago = report_date - timedelta(days=365)
    target_weekday = report_date.weekday()
    diff = (target_weekday - year_ago.weekday()) % 7
    if diff > 3:
        diff -= 7
    return year_ago + timedelta(days=diff)


def get_last_week(report_date: datetime) -> datetime:
    """지난주 같은 요일 (단순 7일 전)."""
    return report_date - timedelta(days=7)


def merge_comparison(
    current_df: pd.DataFrame,
    last_year_df: pd.DataFrame | None = None,
    last_week_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """현재 보고서에 작년·지난주 매출 컬럼 추가.

    매칭 키: 광고이름 (utm_content == ad_name).
    같은 광고가 작년에 없으면 NaN 처리.
    """
    df = current_df.copy()

    if last_year_df is not None and not last_year_df.empty:
        ly = last_year_df[["광고이름", "매출", "ROAS"]].rename(
            columns={"매출": "작년매출", "ROAS": "작년ROAS"}
        )
        df = df.merge(ly, on="광고이름", how="left")
        df["작년대비"] = (df["매출"] / df["작년매출"] * 100).round(0)
    else:
        df["작년매출"] = pd.NA
        df["작년ROAS"] = pd.NA
        df["작년대비"] = pd.NA

    if last_week_df is not None and not last_week_df.empty:
        lw = last_week_df[["광고이름", "매출"]].rename(columns={"매출": "지난주매출"})
        df = df.merge(lw, on="광고이름", how="left")
        df["지난주대비"] = (df["매출"] / df["지난주매출"] * 100).round(0)
    else:
        df["지난주매출"] = pd.NA
        df["지난주대비"] = pd.NA

    return df


def compute_kpi_deltas(current_kpi: dict, last_year_kpi: dict | None) -> dict:
    """KPI 카드용 작년 대비 증감률."""
    if not last_year_kpi:
        return {key: None for key in ["spend", "revenue", "roas", "conversion"]}

    def pct(current: float, last: float) -> float | None:
        if last == 0:
            return None
        return round((current - last) / last * 100, 1)

    return {
        "spend": pct(current_kpi["total_spend"], last_year_kpi["total_spend"]),
        "revenue": pct(current_kpi["total_revenue"], last_year_kpi["total_revenue"]),
        "roas": pct(current_kpi["roas"], last_year_kpi["roas"]),
        "conversion": pct(current_kpi["conversion_count"], last_year_kpi["conversion_count"]),
    }
