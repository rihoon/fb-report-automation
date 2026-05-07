"""네이버 검색광고 상세 페이지 — placeholder.

Fork B에서 네이버 검색광고 API 연동 완료되면 활성화.
"""

from __future__ import annotations

import streamlit as st

from src.sidebar import render_sidebar


# ────────────────────── 사이드바 ──────────────────────
sb = render_sidebar()
report_date = sb["report_date"]
weekday_label = sb["weekday_label"]
days = sb["days"]


# ────────────────────── 메인 ──────────────────────

st.markdown(
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">네이버 검색광고</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")

st.info(
    "🚧 **개발 중** — 네이버 검색광고 페이지는 API 연동 완료 후 활성화됩니다.\n\n"
    "예정 컬럼: 캠페인 / 광고그룹 / 키워드 / 노출 / 클릭 / CTR / 평균순위 / N일지출 / N일매출 / N일전환수 / N일ROAS"
)
