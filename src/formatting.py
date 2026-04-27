"""조건부 서식: ROAS·작년 대비·지난주 대비 셀 색상 + 숫자 포맷.

규칙:
- ≥ 100% → 분홍 배경 (#FCE7F3) + 분홍 텍스트 (#BE185D)
- < 100% → 푸른 배경 (#DBEAFE) + 푸른 텍스트 (#1E40AF)
- 유효 X → 회색 처리

포맷 적용 주의:
- Pandas Styler.format()은 단일 호출로 dict 전체를 넘겨야 Streamlit이 안정적으로 적용함.
- styling은 .format() **이후**에 적용해야 함.
"""

from __future__ import annotations

import pandas as pd


PINK_BG = "#FCE7F3"
PINK_TEXT = "#BE185D"
BLUE_BG = "#DBEAFE"
BLUE_TEXT = "#1E40AF"
GRAY_BG = "#F3F4F6"
GRAY_TEXT = "#9CA3AF"

PERCENT_COLUMNS = ("ROAS", "작년대비", "지난주대비", "작년ROAS")

MONEY_COLUMNS_FIXED = ("1일지출", "환불액", "작년매출", "지난주매출", "CPC", "CPM")
INT_COLUMNS = ("도달", "클릭", "노출", "전환수")


def is_money_column(col_name: str) -> bool:
    """돈 단위 컬럼 판정 (동적 N일지출/N일매출도 인식)."""
    name = str(col_name)
    if name in MONEY_COLUMNS_FIXED:
        return True
    return name.endswith("지출") or name.endswith("매출")


def make_period_labels(days: int) -> tuple[str, str]:
    """기간 기준 컬럼 라벨 생성. 예: 3 → ('3일지출', '3일매출')."""
    return f"{days}일지출", f"{days}일매출"


def apply_period_labels(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """내부 컬럼명(지출/매출)을 동적 라벨로 변경."""
    spend_label, revenue_label = make_period_labels(days)
    return df.rename(columns={"지출": spend_label, "매출": revenue_label})


def display_column_order(days: int) -> tuple[str, ...]:
    """기간 라벨 반영된 컬럼 순서."""
    spend_label, revenue_label = make_period_labels(days)
    return (
        "담당자", "캠페인명", "광고세트", "광고이름",
        "nt_detail", "nt_keyword", "매칭방식",
        "게재상태",
        "도달", "클릭", "노출", "CPC", "CPM", "CTR",
        "1일지출", spend_label,
        revenue_label, "ROAS", "전환수", "환불액",
        "지난주매출", "지난주대비",
        "작년매출", "작년ROAS", "작년대비",
        "유효", "유효사유",
        "nt_source", "nt_medium",  # 끝에 (참고용)
    )


def _color_pct(val) -> str:
    """100% 기준 분홍/푸른 배경."""
    if pd.isna(val):
        return ""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v >= 100:
        return f"background-color: {PINK_BG}; color: {PINK_TEXT}; font-weight: 600;"
    return f"background-color: {BLUE_BG}; color: {BLUE_TEXT}; font-weight: 600;"


def _gray_invalid(row: pd.Series) -> list[str]:
    """유효 X 행은 회색 처리."""
    if "유효" in row.index and row["유효"] == "X":
        return [f"background-color: {GRAY_BG}; color: {GRAY_TEXT};"] * len(row)
    return [""] * len(row)


def _safe_int_money(x):
    if pd.isna(x):
        return ""
    try:
        v = float(x)
        if not (v == v) or v in (float("inf"), float("-inf")):
            return "-"
        return f"₩{int(v):,}"
    except (ValueError, OverflowError, TypeError):
        return "-"


def _safe_int_count(x):
    if pd.isna(x):
        return ""
    try:
        v = float(x)
        if not (v == v) or v in (float("inf"), float("-inf")):
            return "-"
        return f"{int(v):,}"
    except (ValueError, OverflowError, TypeError):
        return "-"


def _safe_pct(x):
    if pd.isna(x):
        return "-"
    try:
        v = float(x)
        if not (v == v):  # NaN
            return "-"
        if v == float("inf"):
            return "∞%"
        if v == float("-inf"):
            return "-∞%"
        return f"{int(v):,}%"
    except (ValueError, OverflowError, TypeError):
        return "-"


def _safe_ctr(x):
    if pd.isna(x):
        return ""
    try:
        v = float(x)
        if not (v == v) or v in (float("inf"), float("-inf")):
            return "-"
        return f"{v:.2f}%"
    except (ValueError, OverflowError, TypeError):
        return "-"


def _build_format_dict(df: pd.DataFrame) -> dict:
    """모든 숫자 컬럼 포맷을 단일 dict로 모음."""
    fmt: dict = {}
    for col in df.columns:
        if is_money_column(col):
            fmt[col] = _safe_int_money
    for col in INT_COLUMNS:
        if col in df.columns:
            fmt[col] = _safe_int_count
    for col in PERCENT_COLUMNS:
        if col in df.columns:
            fmt[col] = _safe_pct
    if "CTR" in df.columns:
        fmt["CTR"] = _safe_ctr
    return fmt


def reorder_columns(df: pd.DataFrame, days: int | None = None) -> pd.DataFrame:
    """보고서 표시용 컬럼 순서 정렬."""
    if df.empty:
        return df
    order = display_column_order(days) if days else display_column_order(0)
    ordered = [c for c in order if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]


def style_dataframe(df: pd.DataFrame, days: int | None = None):
    """Streamlit 표시용 Styler 반환."""
    if df.empty:
        return df

    df = reorder_columns(df, days)
    fmt = _build_format_dict(df)
    pct_cols = [c for c in PERCENT_COLUMNS if c in df.columns]

    # 1) format 먼저
    styler = df.style.format(fmt, na_rep="")

    # 2) coloring
    if pct_cols:
        styler = styler.map(_color_pct, subset=pct_cols)
    if "유효" in df.columns:
        styler = styler.apply(_gray_invalid, axis=1)

    return styler
