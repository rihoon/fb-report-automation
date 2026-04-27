"""네이버 마케팅분석 엑셀 파서.

스마트스토어센터 → 데이터분석 → 마케팅분석 → 사용자정의채널 → 다운로드
받은 엑셀 파일에서 nt_detail별 결제금액·결제수를 추출.
"""

from __future__ import annotations

import io

import pandas as pd


# 우리가 사용할 핵심 컬럼 (네이버 엑셀 기준)
REQUIRED_COLUMNS = {
    "nt_source",
    "nt_medium",
    "nt_detail",
    "nt_keyword",
    "유입수",
    "결제수",
    "결제금액",
}

# 별칭 매핑 (혹시 엑셀 헤더가 약간 다를 수 있어서)
COLUMN_ALIASES = {
    "결제금액": ["결제금액", "결제금액(마지막클릭)"],
    "결제수": ["결제수", "결제수(마지막클릭)"],
    "유입수": ["유입수", "방문수"],
}


def parse_naver_marketing_excel(file_or_bytes) -> pd.DataFrame:
    """네이버 마케팅분석 엑셀을 DataFrame으로 변환.

    Args:
        file_or_bytes: 파일 경로 / file-like / bytes

    Returns:
        nt_detail별로 집계된 DataFrame.
        컬럼: [nt_source, nt_medium, nt_detail, nt_keyword, 유입수, 결제수, 결제금액, 채널속성_list]
    """
    if isinstance(file_or_bytes, (bytes, bytearray)):
        file_or_bytes = io.BytesIO(file_or_bytes)

    df = pd.read_excel(file_or_bytes, sheet_name=0, engine="openpyxl")

    # 컬럼 정규화
    df = df.rename(columns={c: c.strip() for c in df.columns})

    # nt_detail 없는 행은 제거 (광고 단위가 아닌 합계 행 등)
    df = df.dropna(subset=["nt_detail"])
    df["nt_detail"] = df["nt_detail"].astype(str).str.strip()
    df = df[df["nt_detail"].str.len() > 0]

    # 숫자 컬럼 캐스팅
    for col in ("유입수", "결제수", "결제금액"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def aggregate_by_nt_detail(df: pd.DataFrame) -> pd.DataFrame:
    """nt_detail별로 합산 (모바일+PC, nt_keyword 무관)."""
    if df.empty:
        return pd.DataFrame(columns=["nt_detail", "유입수", "결제수", "결제금액"])

    agg = df.groupby("nt_detail", as_index=False).agg({
        "유입수": "sum",
        "결제수": "sum",
        "결제금액": "sum",
    })
    return agg


def find_naver_row(naver_agg: pd.DataFrame, nt_detail: str) -> dict | None:
    """nt_detail로 네이버 데이터 1건 찾기."""
    if naver_agg.empty or not nt_detail:
        return None
    matched = naver_agg[naver_agg["nt_detail"].str.strip() == nt_detail.strip()]
    if matched.empty:
        return None
    row = matched.iloc[0]
    return {
        "nt_detail": row["nt_detail"],
        "유입수": float(row.get("유입수", 0)),
        "결제수": int(row.get("결제수", 0)),
        "결제금액": float(row.get("결제금액", 0)),
    }
