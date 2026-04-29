"""유효 O/X 자동 판정 + 사유 표기.

판정 룰:
- 7일간 ROAS < 80% → X ("7일간 전환율80%미만")
- 7일치 데이터 부족 → "러닝중" (판정 보류, 머신러닝 단계)
- 그 외 → O

판정 데이터: 구글 시트 누적_보고서에서 최근 7일치 합산
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.matching import MatchedRow


def evaluate_validity(
    ad_name: str,
    history_7d_roas: float,
    has_enough_history: bool,
    history_7d_spend: float = 0.0,
) -> tuple[str, str]:
    """광고 1건의 유효성 판정.

    Args:
        history_7d_roas: 최근 7일 ROAS (%).
        has_enough_history: 7일치 데이터가 충분히 누적됐는지.
        history_7d_spend: 최근 7일 광고비 (데이터 부족 판정용).

    Returns:
        (status, reason) — status ∈ {"O", "X", "러닝중"}
    """
    if not has_enough_history:
        # 7일 누적 광고비도 0이면 "데이터 부족" (시트에 이력 자체가 없음)
        if history_7d_spend <= 0:
            return "러닝중", "데이터 부족"
        return "러닝중", "머신러닝 단계"
    if history_7d_roas < 80:
        return "X", "7일간 전환율80%미만"
    return "O", ""


def annotate_validity(
    df: pd.DataFrame,
    history_lookup: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """DataFrame에 유효 / 사유 컬럼 추가.

    Args:
        df: aggregation의 결과 DataFrame.
        history_lookup: {광고이름: {"7d_revenue": ..., "7d_spend": ..., "7d_roas": ..., "has_enough_history": ...}}
                        없으면 모든 행을 "데이터 부족"으로 처리.
    """
    df = df.copy()
    statuses: list[str] = []
    reasons: list[str] = []

    for _, row in df.iterrows():
        ad_name = row["광고이름"]
        if history_lookup and ad_name in history_lookup:
            h = history_lookup[ad_name]
            status, reason = evaluate_validity(
                ad_name,
                h.get("7d_roas", 0),
                h.get("has_enough_history", False),
                h.get("7d_spend", 0),
            )
        else:
            # 누적 시트에 이력 자체가 없음 → 데이터 부족
            status, reason = "러닝중", "데이터 부족"
        statuses.append(status)
        reasons.append(reason)

    df["유효"] = statuses
    df["유효사유"] = reasons
    return df
