"""통합 대시보드 — 3채널(페북·GFA·네이버 검색광고) 한눈에.

- 사이드바: 보고일·집계일수·파일 업로드 (페북 매출 매칭용)
- 메인:
  - 통합 결과 요약 (3채널 합산: 광고비/매출/ROAS)
  - 채널별 결과 요약 (가로 9 KPI 카드)
  - 채널별 광고비 비중 (altair 세로 막대 3개)
"""

from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from src.aggregation import (
    aggregate_kpi,
    matched_rows_to_dataframe,
    merge_seven_day,
)
from src.facebook_api import fetch_facebook_ads
from src.formatting import apply_period_labels
from src.gfa_api import fetch_gfa_ads
from src.google_sheets import (
    append_channel_section,
    append_report,
    fetch_validity_history,
    get_latest_sheet_url,
)
from src.matching import match_facebook_with_naver
from src.naver_excel import parse_naver_marketing_excel
from src.naver_searchad_api import fetch_search_ads
from src.sidebar import render_sidebar
from src.validity import annotate_validity


# ────────────────────── 사이드바 ──────────────────────

sb = render_sidebar()
report_date = sb["report_date"]
report_dt = sb["report_dt"]
days = sb["days"]
start = sb["start"]
end = sb["end"]
weekday_label = sb["weekday_label"]
uploaded_current = sb["uploaded_current"]
generate_btn = sb["generate_btn"]


# ────────────────────── 메인 ──────────────────────

st.markdown(
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">광고 통합 오토파일럿</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")


# ────────────────────── 데이터 로드 ──────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _load_facebook_kpi(start_iso: str, end_iso: str, naver_excel_bytes: bytes | None, days_int: int):
    """페북 광고 + 마케팅분석 엑셀 매칭 → KPI dict 반환."""
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    ads = fetch_facebook_ads(s, e)
    if naver_excel_bytes:
        naver_df = parse_naver_marketing_excel(naver_excel_bytes)
    else:
        naver_df = pd.DataFrame(
            columns=["nt_source", "nt_medium", "nt_detail", "nt_keyword", "유입수", "결제수", "결제금액"]
        )
    rows, _ = match_facebook_with_naver(ads, naver_df, manual_overrides=None)
    df = matched_rows_to_dataframe(rows, days=days_int)
    return aggregate_kpi(df)


@st.cache_data(ttl=600, show_spinner=False)
def _load_search_kpi(start_iso: str, end_iso: str):
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    ads = fetch_search_ads(s, e)
    total_spend = sum(a.spend for a in ads)
    total_revenue = sum(a.revenue for a in ads)
    return {
        "total_spend": float(total_spend),
        "total_revenue": float(total_revenue),
        "roas": (total_revenue / total_spend * 100) if total_spend else 0.0,
        "n_groups": len(ads),
    }


@st.cache_data(ttl=600, show_spinner=False)
def _load_gfa_kpi(start_iso: str, end_iso: str):
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    ads = fetch_gfa_ads(s, e)
    total_spend = sum(a.spend for a in ads)
    total_revenue = sum(a.revenue for a in ads)
    return {
        "total_spend": float(total_spend),
        "total_revenue": float(total_revenue),
        "roas": (total_revenue / total_spend * 100) if total_spend else 0.0,
        "n_creatives": len(ads),
    }


def _kpi_card(col, label: str, value: str, threshold_roas: float | None = None, channel_roas: float | None = None):
    """KPI 카드 — ROAS 기준 분홍/파랑 배경."""
    if threshold_roas is not None and channel_roas is not None:
        bg = "#FCE7F3" if channel_roas >= threshold_roas else "#DBEAFE"
    else:
        bg = "#FAFAFA"
    col.markdown(
        f"""
        <div style="background:{bg}; border-radius:12px; padding:14px;">
            <div style="color:#666666; font-size:12px; margin-bottom:4px;">{label}</div>
            <div style="color:#111111; font-weight:700; font-size:18px;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_total_kpi(slot, fb_kpi: dict | None, gfa_kpi: dict | None, search_kpi: dict | None):
    """통합 KPI 카드 그리기 (None 채널은 0으로 처리)."""
    fb = fb_kpi or {"total_spend": 0, "total_revenue": 0}
    gfa = gfa_kpi or {"total_spend": 0, "total_revenue": 0}
    sa = search_kpi or {"total_spend": 0, "total_revenue": 0}
    total_spend = fb["total_spend"] + gfa["total_spend"] + sa["total_spend"]
    total_revenue = fb["total_revenue"] + gfa["total_revenue"] + sa["total_revenue"]
    total_roas = (total_revenue / total_spend * 100) if total_spend else 0.0
    bg = "#FCE7F3" if total_roas >= 100 else "#DBEAFE"
    with slot.container():
        st.markdown(
            f"""<style>[data-testid="stMetric"], .stMetric {{ background: {bg} !important; }}</style>""",
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("총 광고비", f"₩{total_spend:,.0f}")
            c2.metric("총 매출", f"₩{total_revenue:,.0f}")
            c3.metric("통합 ROAS", f"{total_roas:.0f}%")


def _render_channel_kpis(slot, fb_kpi: dict | None, gfa_kpi: dict | None, search_kpi: dict | None):
    """채널별 9 KPI 카드 그리기 (None은 — 표시)."""
    with slot.container():
        with st.container(border=True):
            cols = st.columns(9)
            # 페북 (100%)
            if fb_kpi is not None:
                _kpi_card(cols[0], "페북 광고비", f"₩{fb_kpi['total_spend']:,.0f}", 100, fb_kpi["roas"])
                _kpi_card(cols[1], "페북 매출", f"₩{fb_kpi['total_revenue']:,.0f}", 100, fb_kpi["roas"])
                _kpi_card(cols[2], "페북 ROAS", f"{fb_kpi['roas']:.0f}%", 100, fb_kpi["roas"])
            else:
                _kpi_card(cols[0], "페북 광고비", "—")
                _kpi_card(cols[1], "페북 매출", "—")
                _kpi_card(cols[2], "페북 ROAS", "—")
            # GFA (300%)
            if gfa_kpi is not None:
                _kpi_card(cols[3], "GFA 광고비", f"₩{gfa_kpi['total_spend']:,.0f}", 300, gfa_kpi["roas"])
                _kpi_card(cols[4], "GFA 매출", f"₩{gfa_kpi['total_revenue']:,.0f}", 300, gfa_kpi["roas"])
                _kpi_card(cols[5], "GFA ROAS", f"{gfa_kpi['roas']:.0f}%", 300, gfa_kpi["roas"])
            else:
                _kpi_card(cols[3], "GFA 광고비", "—")
                _kpi_card(cols[4], "GFA 매출", "—")
                _kpi_card(cols[5], "GFA ROAS", "—")
            # 검색 (300%)
            if search_kpi is not None:
                _kpi_card(cols[6], "검색 광고비", f"₩{search_kpi['total_spend']:,.0f}", 300, search_kpi["roas"])
                _kpi_card(cols[7], "검색 매출", f"₩{search_kpi['total_revenue']:,.0f}", 300, search_kpi["roas"])
                _kpi_card(cols[8], "검색 ROAS", f"{search_kpi['roas']:.0f}%", 300, search_kpi["roas"])
            else:
                _kpi_card(cols[6], "검색 광고비", "⏳ 로딩 중...")
                _kpi_card(cols[7], "검색 매출", "⏳ 로딩 중...")
                _kpi_card(cols[8], "검색 ROAS", "⏳ 로딩 중...")


if generate_btn or st.session_state.get("dashboard_loaded", False):
    st.session_state["dashboard_loaded"] = True

    # 페북은 마케팅분석 엑셀이 있어야 매출 매칭 가능 (없어도 광고비는 표시됨)
    naver_bytes = uploaded_current.getvalue() if uploaded_current is not None else None
    if naver_bytes is None:
        st.info("ℹ️ 페북 매출 매칭 없음 — 마케팅분석 엑셀을 업로드하면 페북 매출도 매칭됩니다. GFA·검색광고는 API 직접 조회 (엑셀 불필요).")

    # ───────── 자리 만들고 점진적으로 채워넣기 ─────────
    st.markdown("### 통합 결과 요약")
    total_kpi_slot = st.empty()
    _render_total_kpi(total_kpi_slot, None, None, None)

    st.markdown("### 채널별 결과 요약")
    channel_kpi_slot = st.empty()
    _render_channel_kpis(channel_kpi_slot, None, None, None)

    # 1. 페북 fetch (~5s)
    fb_kpi = None
    with st.spinner("페북 광고 처리 중..."):
        fb_kpi = _load_facebook_kpi(start.isoformat(), end.isoformat(), naver_bytes, int(days))
    _render_total_kpi(total_kpi_slot, fb_kpi, None, None)
    _render_channel_kpis(channel_kpi_slot, fb_kpi, None, None)

    # 2. GFA fetch (~5s)
    gfa_kpi = None
    with st.spinner("GFA 처리 중..."):
        gfa_kpi = _load_gfa_kpi(start.isoformat(), end.isoformat())
    _render_total_kpi(total_kpi_slot, fb_kpi, gfa_kpi, None)
    _render_channel_kpis(channel_kpi_slot, fb_kpi, gfa_kpi, None)

    # 3. 검색광고 fetch (~1~2분, 광고그룹마다 1콜)
    search_kpi = None
    with st.spinner("네이버 검색광고 처리 중 (광고그룹마다 1콜이라 1~2분 걸려요)..."):
        search_kpi = _load_search_kpi(start.isoformat(), end.isoformat())
    _render_total_kpi(total_kpi_slot, fb_kpi, gfa_kpi, search_kpi)
    _render_channel_kpis(channel_kpi_slot, fb_kpi, gfa_kpi, search_kpi)

    # ────────────────────── 채널별 광고비 비중 (altair 막대) ──────────────────────

    st.markdown("### 채널별 광고비 비중")

    chart_df = pd.DataFrame({
        "채널": ["페북", "GFA", "검색"],
        "광고비": [fb_kpi["total_spend"], gfa_kpi["total_spend"], search_kpi["total_spend"]],
    })

    bar = (
        alt.Chart(chart_df)
        .mark_bar(size=80, cornerRadius=6, color="#111111")
        .encode(
            x=alt.X("채널:N", title=None, axis=alt.Axis(labelFontSize=14, labelColor="#111111")),
            y=alt.Y(
                "광고비:Q",
                title="광고비 (KRW)",
                axis=alt.Axis(format=",.0f", labelColor="#666666", titleColor="#666666"),
            ),
            tooltip=[
                alt.Tooltip("채널:N"),
                alt.Tooltip("광고비:Q", format=",.0f", title="광고비 (₩)"),
            ],
        )
        .properties(height=300)
    )
    text = (
        alt.Chart(chart_df)
        .mark_text(
            align="center",
            baseline="bottom",
            dy=-6,
            fontSize=13,
            color="#111111",
            fontWeight=600,
        )
        .encode(
            x="채널:N",
            y="광고비:Q",
            text=alt.Text("광고비:Q", format=",.0f"),
        )
    )
    st.altair_chart(bar + text, use_container_width=True)

    # ────────────────────── 통합 시트 저장 ──────────────────────

    st.markdown("### 구글 시트 통합 저장")

    btn_save_col, btn_link_col = st.columns([3, 1])
    with btn_save_col:
        save_btn = st.button(
            "구글 시트 통합 저장 (3채널)",
            use_container_width=True,
            type="primary",
            key="save_integrated",
        )
    with btn_link_col:
        sheet_url = get_latest_sheet_url(report_dt)
        if sheet_url:
            st.link_button(
                "구글시트 바로가기",
                sheet_url,
                use_container_width=True,
            )

    if save_btn:
        with st.spinner("3채널 데이터 통합 저장 중..."):
            messages: list[str] = []
            ok_all = True

            # 1. 페북 — 기존 append_report (시트 새로 작성, 담당자 그룹 + 색상)
            try:
                fb_ads = fetch_facebook_ads(start, end)
                if naver_bytes:
                    fb_naver_df = parse_naver_marketing_excel(naver_bytes)
                else:
                    fb_naver_df = pd.DataFrame(
                        columns=["nt_source", "nt_medium", "nt_detail", "nt_keyword", "유입수", "결제수", "결제금액"]
                    )
                fb_rows, _ = match_facebook_with_naver(fb_ads, fb_naver_df, manual_overrides=None)
                fb_df = matched_rows_to_dataframe(fb_rows, days=int(days))

                # 유효 판정 + 7일 누적
                history = fetch_validity_history(report_dt, lookback_days=7)
                created_time_lookup = {r.ad.ad_name: getattr(r.ad, "created_time", None) for r in fb_rows}
                fb_df = annotate_validity(
                    fb_df,
                    history_lookup=history if history else None,
                    created_time_lookup=created_time_lookup,
                    report_date=report_dt,
                )
                fb_df = merge_seven_day(fb_df, history)
                fb_display_df = apply_period_labels(fb_df, int(days))

                from src.google_sheets import append_report as fb_append_report
                ok, msg = fb_append_report(fb_display_df, report_dt)
                messages.append(f"페북: {msg}")
                ok_all = ok_all and ok
            except Exception as e:
                messages.append(f"페북 저장 실패: {type(e).__name__}: {e}")
                ok_all = False

            # 2. GFA 섹션 추가
            try:
                gfa_ads = fetch_gfa_ads(start, end)
                if gfa_ads:
                    gfa_df = pd.DataFrame([
                        {
                            "캠페인": a.campaign_name,
                            "광고그룹": a.adgroup_name,
                            "소재명": a.creative_name,
                            "노출": a.impressions,
                            "클릭": a.clicks,
                            "CTR": round(a.ctr, 2),
                            f"{int(days)}일지출": int(a.spend),
                            f"{int(days)}일매출": int(a.revenue),
                            f"{int(days)}일전환수": a.conversion_count,
                            f"{int(days)}일ROAS": round(a.roas, 0),
                        }
                        for a in gfa_ads
                    ])
                    ok, msg = append_channel_section(report_dt, "GFA 성과형", gfa_df, color="green")
                    messages.append(f"GFA: {msg}")
                    ok_all = ok_all and ok
                else:
                    messages.append("GFA: 데이터 없음 (skip)")
            except Exception as e:
                messages.append(f"GFA 저장 실패: {type(e).__name__}: {e}")
                ok_all = False

            # 3. 검색광고 섹션 추가
            try:
                search_ads = fetch_search_ads(start, end)
                if search_ads:
                    search_df = pd.DataFrame([
                        {
                            "캠페인": a.campaign_name,
                            "광고그룹": a.adgroup_name,
                            "노출": a.impressions,
                            "클릭": a.clicks,
                            "CTR": round(a.ctr, 2),
                            "평균순위": round(a.avg_position, 1) if a.avg_position else 0,
                            f"{int(days)}일지출": int(a.spend),
                            f"{int(days)}일매출": int(a.revenue),
                            f"{int(days)}일전환수": a.conversion_count,
                            f"{int(days)}일ROAS": round(a.roas, 0),
                        }
                        for a in search_ads
                    ])
                    ok, msg = append_channel_section(report_dt, "네이버 검색광고", search_df, color="blue")
                    messages.append(f"검색광고: {msg}")
                    ok_all = ok_all and ok
                else:
                    messages.append("검색광고: 데이터 없음 (skip)")
            except Exception as e:
                messages.append(f"검색광고 저장 실패: {type(e).__name__}: {e}")
                ok_all = False

            st.session_state["integrated_save_result"] = (ok_all, messages)
            st.toast("3채널 저장 완료" if ok_all else "일부 실패 — 메시지 확인")
            st.rerun()

    if "integrated_save_result" in st.session_state:
        ok_all, messages = st.session_state["integrated_save_result"]
        if ok_all:
            st.success("\n".join(["**구글 시트 통합 저장 결과**:"] + [f"- {m}" for m in messages]))
        else:
            st.error("\n".join(["**일부 채널 저장 실패**:"] + [f"- {m}" for m in messages]))

else:
    st.info("사이드바에서 **마케팅분석 엑셀** 업로드(선택) + **보고서 생성** 버튼을 눌러주세요.")
