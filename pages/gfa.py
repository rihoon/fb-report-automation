"""GFA 성과형 광고 상세 페이지 (소재 단위)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.gfa_api import fetch_gfa_ads, get_data_source, get_last_debug_info
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

    src = get_data_source()
    dbg = get_last_debug_info()
    ad_account = dbg.get("discovered_ad_account", "N/A")

    # API 데이터가 없으면 안내 + 수동 입력 옵션 제공
    if not ads:
        last_err = dbg.get("errors", ["에러 없음"])[-1] if dbg.get("errors") else "에러 없음"
        if src == "mock":
            st.warning("⚠️ **시크릿 미설정** — `[naver_gfa]` 섹션이 secrets.toml 에 없거나 비어있습니다.")
        elif src == "real_empty":
            st.info(
                f"ℹ️ **GFA API 호출 정상** (adAccountNo: `{ad_account}`) — 데이터 0건.\n\n"
                f"이 기간에 광고 운영되지 않았거나, /stat-reports schema 미확정. "
                f"GFA 대시보드에서 직접 확인한 값을 아래에 입력하시면 표시됩니다."
            )
        elif src == "real_error":
            st.error(f"❌ **GFA API 호출 실패** — {last_err}\n\nadAccountNo: `{ad_account}`")

    # ────────── KPI 집계 (API 데이터) ──────────
    api_spend = sum(a.spend for a in ads)
    api_revenue = sum(a.revenue for a in ads)
    api_conversions = sum(a.conversion_count for a in ads)
    api_impressions = sum(a.impressions for a in ads)
    api_clicks = sum(a.clicks for a in ads)

    # ────────── 수동 입력 (API 비었을 때 + 사용자가 GFA 대시보드 값 입력) ──────────
    manual_key = f"gfa_manual_{report_date.strftime('%Y%m%d')}_{days}"
    if not ads:
        with st.expander("✏️ GFA 대시보드 값 직접 입력", expanded=True):
            st.caption("API가 데이터를 못 가져올 때 사용. 보고일별로 저장됨.")
            m_cols = st.columns(4)
            manual_spend = m_cols[0].number_input("광고비 (₩)", min_value=0, value=int(st.session_state.get(f"{manual_key}_spend", 0)), step=1000)
            manual_revenue = m_cols[1].number_input("전환매출 (₩)", min_value=0, value=int(st.session_state.get(f"{manual_key}_revenue", 0)), step=1000)
            manual_conversions = m_cols[2].number_input("전환수", min_value=0, value=int(st.session_state.get(f"{manual_key}_conv", 0)), step=1)
            manual_impressions = m_cols[3].number_input("노출", min_value=0, value=int(st.session_state.get(f"{manual_key}_imp", 0)), step=1)
            manual_clicks = st.number_input("클릭", min_value=0, value=int(st.session_state.get(f"{manual_key}_clk", 0)), step=1)
            st.session_state[f"{manual_key}_spend"] = manual_spend
            st.session_state[f"{manual_key}_revenue"] = manual_revenue
            st.session_state[f"{manual_key}_conv"] = manual_conversions
            st.session_state[f"{manual_key}_imp"] = manual_impressions
            st.session_state[f"{manual_key}_clk"] = manual_clicks
    else:
        manual_spend = manual_revenue = manual_conversions = manual_impressions = manual_clicks = 0

    # ────────── 최종 KPI (API + 수동 합산) ──────────
    total_spend = api_spend + manual_spend
    total_revenue = api_revenue + manual_revenue
    total_conversions = api_conversions + manual_conversions
    total_impressions = api_impressions + manual_impressions
    total_clicks = api_clicks + manual_clicks
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

    # ────────── 소재별 상세 표 (API 데이터 있을 때만) ──────────
    if ads:
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
        st.caption("💡 광고소재별 상세는 API 데이터가 있을 때만 표시됩니다. 위는 수동 입력 합산.")

else:
    st.info("사이드바에서 **보고서 생성** 버튼을 눌러주세요.")
