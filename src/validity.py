"""유효 O/X/— 자동 판정 + 사유 표기.

판정 룰 (우선순위 순):
1. 광고 등록 < 7일       → "—" / "데이터 부족"
2. 7일 매출 = 0          → "X" / "7일 매출 0"
3. 7일 ROAS<80% & 최근 ROAS≥100% → "O" / "최근 성과 좋음"
4. 7일 ROAS<80% & 최근 ROAS<100% → "X" / "7일 전환 80%미만"
5. 7일 ROAS ≥ 80%        → "O" / ""

데이터 소스:
- 광고 등록일: 페북 API created_time
- 7일 매출/ROAS: 구글 시트 누적 보고서에서 합산
- 최근 보고기간 ROAS: 현재 보고서의 ROAS 컬럼
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def evaluate_validity(
    history_7d_revenue: float,
    history_7d_roas: float,
    current_roas: float,
    created_time: datetime | None,
    report_date: datetime,
) -> tuple[str, str]:
    """광고 1건의 유효성 판정.

    Args:
        history_7d_revenue: 최근 7일 누적 매출 (원).
        history_7d_roas: 최근 7일 누적 ROAS (%).
        current_roas: 현재 보고서 기간 ROAS (%).
        created_time: 광고 등록일 (없으면 None).
        report_date: 보고일.

    Returns:
        (status, reason) — status ∈ {"O", "X", "—"}
    """
    # 1. 광고 등록 < 7일 → "-" / 데이터 부족
    if created_time is not None:
        days_since_created = (report_date - created_time).days
        if days_since_created < 7:
            return "—", "데이터 부족"

    # created_time을 못 받았으면 (None) → 이력 자체로 판정 (보수적으로 7일 매출 0이면 X 등)
    # 단, 시트에도 이력이 없으면 "-" / "데이터 부족"으로 보호
    if created_time is None and history_7d_revenue == 0 and history_7d_roas == 0:
        return "—", "데이터 부족"

    # 2. 7일 매출 0 → 무조건 X
    if history_7d_revenue <= 0:
        return "X", "7일 매출 0"

    # 3. 7일 ROAS<80% & 최근 ROAS≥100% → O
    if history_7d_roas < 80 and current_roas >= 100:
        return "O", "최근 성과 좋음"

    # 4. 7일 ROAS<80% & 최근 ROAS<100% → X
    if history_7d_roas < 80 and current_roas < 100:
        return "X", "7일 전환 80%미만"

    # 5. Default — 7일 ROAS≥80% → O
    return "O", ""


def annotate_validity(
    df: pd.DataFrame,
    history_lookup: dict[str, dict] | None = None,
    created_time_lookup: dict[str, datetime | None] | None = None,
    report_date: datetime | None = None,
) -> pd.DataFrame:
    """DataFrame에 유효 / 사유 컬럼 추가.

    Args:
        df: aggregation 결과 DataFrame ("광고이름", "ROAS" 컬럼 필수).
        history_lookup: {광고이름: {"7d_revenue", "7d_spend", "7d_roas", "has_enough_history"}}.
        created_time_lookup: {광고이름: datetime | None}.
        report_date: 보고일 (기본값: 오늘).
    """
    df = df.copy()
    if report_date is None:
        report_date = datetime.now()

    statuses: list[str] = []
    reasons: list[str] = []

    for _, row in df.iterrows():
        ad_name = row["광고이름"]
        h = (history_lookup or {}).get(ad_name, {})
        history_7d_revenue = float(h.get("7d_revenue", 0) or 0)
        history_7d_roas = float(h.get("7d_roas", 0) or 0)
        current_roas = float(row.get("ROAS") or 0)
        created_time = (created_time_lookup or {}).get(ad_name)

        status, reason = evaluate_validity(
            history_7d_revenue=history_7d_revenue,
            history_7d_roas=history_7d_roas,
            current_roas=current_roas,
            created_time=created_time,
            report_date=report_date,
        )
        statuses.append(status)
        reasons.append(reason)

    df["유효"] = statuses
    df["유효사유"] = reasons
    return df
