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
GRAY_BG = "#F5F5F5"
GRAY_TEXT = "#999999"

PERCENT_COLUMNS = ("ROAS", "7일ROAS", "작년대비", "지난주대비", "작년ROAS")

MONEY_COLUMNS_FIXED = ("1일지출", "7일지출", "7일매출", "환불액", "작년매출", "지난주매출", "CPC", "CPM")
INT_COLUMNS = ("도달", "클릭", "노출", "전환수", "유입수")


def is_money_column(col_name: str) -> bool:
    """돈 단위 컬럼 판정 (동적 N일지출/N일매출도 인식)."""
    name = str(col_name)
    if name in MONEY_COLUMNS_FIXED:
        return True
    return name.endswith("지출") or name.endswith("매출")


def is_percent_column(col_name: str) -> bool:
    """퍼센트 컬럼 판정 (동적 N일ROAS도 인식)."""
    name = str(col_name)
    if name in PERCENT_COLUMNS:
        return True
    return name.endswith("ROAS")


def make_period_labels(days: int) -> dict[str, str]:
    """기간 기준 컬럼 라벨 생성.

    예: 3 → {'지출': '3일지출', '매출': '3일매출', 'ROAS': '3일ROAS', '전환수': '3일전환수', '유입수': '3일유입수'}
    """
    return {
        "지출": f"{days}일지출",
        "매출": f"{days}일매출",
        "ROAS": f"{days}일ROAS",
        "전환수": f"{days}일전환수",
        "유입수": f"{days}일유입수",
    }


def apply_period_labels(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """내부 컬럼명을 동적 N일 라벨로 변경 (지출/매출/ROAS/전환수/유입수)."""
    return df.rename(columns=make_period_labels(days))


def display_column_order(days: int) -> tuple[str, ...]:
    """기간 라벨 반영된 컬럼 순서.

    사용자 요청 순서:
    ... 도달/클릭/노출/CPC/CPM/CTR
    → 1일지출 → N일지출 → N일매출 → N일전환수 → N일유입수 → N일ROAS
    → 7일지출 → 7일매출 → 7일ROAS
    → 유효 → 유효사유
    → 환불액 → 작년/지난주 비교 → nt_source/medium
    """
    labels = make_period_labels(days)
    return (
        "담당자", "캠페인명", "광고세트", "광고이름",
        "nt_detail", "nt_keyword", "매칭방식",
        "게재상태",
        "도달", "클릭", "노출", "CPC", "CPM", "CTR",
        # N일 데이터 (사용자 요청 순서)
        "1일지출",
        labels["지출"], labels["매출"],
        labels["전환수"], labels["유입수"], labels["ROAS"],
        # 7일 데이터
        "7일지출", "7일매출", "7일ROAS",
        # 유효 판정
        "유효", "유효사유",
        # 판정 (광고 매니저 최종 판정/코멘트 — 시트에서 직접 입력)
        "판정",
        # 보조
        "환불액",
        "지난주매출", "지난주대비",
        "작년매출", "작년ROAS", "작년대비",
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
        elif is_percent_column(col):
            fmt[col] = _safe_pct
        elif col in INT_COLUMNS or col.endswith("전환수") or col.endswith("유입수"):
            fmt[col] = _safe_int_count
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
    pct_cols = [c for c in df.columns if is_percent_column(c)]

    # 1) format 먼저
    styler = df.style.format(fmt, na_rep="")

    # 2) coloring
    if pct_cols:
        styler = styler.map(_color_pct, subset=pct_cols)
    if "유효" in df.columns:
        styler = styler.apply(_gray_invalid, axis=1)

    return styler
