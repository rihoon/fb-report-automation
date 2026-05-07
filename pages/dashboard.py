"""통합 대시보드 — 3채널(페북·GFA·네이버검색) 한눈에.

현재는 placeholder. GFA·검색광고 API 모듈이 완성되면 실제 데이터로 교체.
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
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">광고 통합 오토파일럿</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")

st.markdown("### 통합 결과 요약")
st.info(
    "🚧 **개발 중** — 통합 대시보드는 GFA·네이버 검색광고 API 연동 완료 후 활성화됩니다.\n\n"
    "현재 페북광고 페이지는 정상 작동합니다. 사이드바에서 **페북광고**를 선택하세요."
)

# 임시 통합 KPI placeholder (mock)
with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    c1.metric("총 광고비", "—", help="3채널 합산 (API 연동 후 표시)")
    c2.metric("총 매출", "—", help="3채널 합산 (API 연동 후 표시)")
    c3.metric("통합 ROAS", "—", help="3채널 합산 (API 연동 후 표시)")

st.markdown("### 채널별 결과 요약")
with st.container(border=True):
    cols = st.columns(9)
    labels = [
        ("페북", "광고비"), ("페북", "매출"), ("페북", "ROAS"),
        ("GFA", "광고비"), ("GFA", "매출"), ("GFA", "ROAS"),
        ("검색", "광고비"), ("검색", "매출"), ("검색", "ROAS"),
    ]
    for col, (channel, kpi) in zip(cols, labels):
        col.metric(f"{channel} {kpi}", "—")

st.markdown("### 채널별 광고비 비중")
st.caption("API 연동 후 altair 세로 막대 차트로 표시됩니다.")
