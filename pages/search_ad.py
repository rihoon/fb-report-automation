"""네이버 검색광고 상세 페이지 (광고그룹 단위)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.naver_searchad_api import fetch_search_ads, get_data_source, get_last_debug_info
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
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">네이버 검색광고</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")


# ────────────────────── 데이터 로드 ──────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _load_search_ads(start_iso: str, end_iso: str):
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    return fetch_search_ads(s, e)


if generate_btn or st.session_state.get("search_report_loaded", False):
    st.session_state["search_report_loaded"] = True

    with st.spinner("네이버 검색광고 데이터 처리 중... (광고그룹마다 1콜이라 시간이 좀 걸려요)"):
        ads = _load_search_ads(start.isoformat(), end.isoformat())

    if not ads:
        src = get_data_source()
        dbg = get_last_debug_info()
        last_err = dbg.get("errors", ["알 수 없음"])[-1] if dbg.get("errors") else "에러 없음"

        if src == "mock":
            st.warning("⚠️ **시크릿 미설정** — `[naver_searchad]` 섹션이 secrets.toml 에 없거나 비어있습니다.")
        elif src == "real_empty":
            st.info(f"ℹ️ **검색광고 API 호출은 정상**이지만 데이터가 0건입니다. (이 기간에 광고 활동 없을 수도)\n\n마지막 진단: {last_err}")
        elif src == "real_error":
            st.error(f"❌ **검색광고 API 호출 실패** — {last_err}")
        else:
            st.warning(f"검색광고 데이터 없음 (출처: `{src}`)")
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
        c5.metric("광고그룹 수", f"{len(ads):,}")

        info_cols = st.columns(2)
        info_cols[0].info(f"노출: **{total_impressions:,}** / 클릭: **{total_clicks:,}** (CTR: {ctr:.2f}%)")
        info_cols[1].info(f"평균 ROAS: **{roas:.0f}%** (300% 이상 시 분홍 카드)")

    # ────────── 광고그룹별 상세 표 ──────────
    st.markdown("### 광고그룹별 상세")

    df = pd.DataFrame([
        {
            "캠페인": a.campaign_name,
            "광고그룹": a.adgroup_name,
            "노출": a.impressions,
            "클릭": a.clicks,
            "CTR": f"{a.ctr:.2f}%",
            "평균순위": f"{a.avg_position:.1f}" if a.avg_position else "-",
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
