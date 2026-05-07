"""GFA 성과형 광고 상세 페이지 (소재 단위)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.gfa_api import fetch_gfa_ads
from src.sidebar import render_sidebar


# ────────────────────── 사이드바 ──────────────────────

sb = render_sidebar()
report_date = sb["report_date"]
report_dt = sb["report_dt"]
days = sb["days"]
start = sb["start"]
end = sb["end"]
weekday_label = sb["weekday_label"]
generate_btn = sb["generate_btn"]


# ────────────────────── 메인 ──────────────────────

st.markdown(
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">GFA 성과형 광고</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")


# ────────────────────── 데이터 로드 ──────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _load_gfa_ads(start_iso: str, end_iso: str):
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    return fetch_gfa_ads(s, e)


if generate_btn or st.session_state.get("gfa_report_loaded", False):
    st.session_state["gfa_report_loaded"] = True

    with st.spinner("GFA 성과형 광고 데이터 처리 중..."):
        ads = _load_gfa_ads(start.isoformat(), end.isoformat())

    if not ads:
        st.warning("GFA 데이터가 없습니다. 시크릿(`[naver_gfa]`)을 확인하세요.")
        st.stop()

    # ────────── KPI 집계 ──────────
    total_spend = sum(a.spend for a in ads)
    total_revenue = sum(a.revenue for a in ads)
    total_conversions = sum(a.conversion_count for a in ads)
    total_impressions = sum(a.impressions for a in ads)
    total_clicks = sum(a.clicks for a in ads)
    roas = (total_revenue / total_spend * 100) if total_spend else 0.0
    ctr = (total_clicks / total_impressions * 100) if total_impressions else 0.0

    # ROAS 임계값 300% 기준 색상
    st.markdown("### 결과 요약")
    _metric_bg = "#FCE7F3" if roas >= 300 else "#DBEAFE"
    st.markdown(
        f"""
        <style>
        [data-testid="stMetric"], .stMetric {{
            background: {_metric_bg} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("총 광고비", f"₩{total_spend:,.0f}")
        c2.metric("총 매출", f"₩{total_revenue:,.0f}")
        c3.metric("ROAS", f"{roas:.0f}%")
        c4.metric("전환수", f"{total_conversions:,}")
        c5.metric("소재 수", f"{len(ads):,}")

        info_cols = st.columns(2)
        info_cols[0].info(f"노출: **{total_impressions:,}** / 클릭: **{total_clicks:,}** (CTR: {ctr:.2f}%)")
        info_cols[1].info(f"평균 ROAS: **{roas:.0f}%** (300% 이상 시 분홍 카드)")

    # ────────── 소재별 상세 표 ──────────
    st.markdown("### 광고소재별 상세")

    df = pd.DataFrame([
        {
            "캠페인": a.campaign_name,
            "광고그룹": a.adgroup_name,
            "소재명": a.creative_name,
            "노출": a.impressions,
            "클릭": a.clicks,
            "CTR": f"{a.ctr:.2f}%",
            f"{days}일지출": int(a.spend),
            f"{days}일매출": int(a.revenue),
            f"{days}일전환수": a.conversion_count,
            f"{days}일ROAS": f"{a.roas:.0f}%",
        }
        for a in ads
    ])

    st.dataframe(
        df,
        use_container_width=True,
        height=500,
        hide_index=True,
        column_config={
            f"{days}일지출": st.column_config.NumberColumn(format="₩%d"),
            f"{days}일매출": st.column_config.NumberColumn(format="₩%d"),
            f"{days}일전환수": st.column_config.NumberColumn(format="%d"),
            "노출": st.column_config.NumberColumn(format="%d"),
            "클릭": st.column_config.NumberColumn(format="%d"),
        },
    )

else:
    st.info("사이드바에서 **보고서 생성** 버튼을 눌러주세요.")
