"""페북성과보고서 자동화 — Streamlit 메인 앱.

매칭 방식:
- 페북 광고 link_url에서 nt_detail 추출
- 네이버 마케팅분석 엑셀(다운로드 후 업로드)에서 nt_detail별 결제금액 매칭
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from src.aggregation import (
    aggregate_by_owner,
    aggregate_kpi,
    get_collection_period,
    matched_rows_to_dataframe,
    merge_seven_day,
)
from src.auth import check_password
from src.comparison import (
    compute_kpi_deltas,
    get_last_week,
    get_same_week_last_year,
    merge_comparison,
)
from src.facebook_api import fetch_facebook_ads, get_link_url_debug
from src.formatting import apply_period_labels, style_dataframe
from src.export import export_to_excel
from src.google_sheets import (
    append_report,
    fetch_report_from_sheet,
    fetch_validity_history,
    get_latest_sheet_url,
    get_sheet_id,
    log_manual_match,
)
from src.matching import match_facebook_with_naver, matching_stats
from src.mock_data import generate_mock_naver_excel_df
from src.naver_excel import parse_naver_marketing_excel
from src.validity import annotate_validity


# ────────────────────── 페이지 설정 ──────────────────────

st.set_page_config(
    page_title="페북 성과보고서 오토파일럿",
    page_icon="assets/icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css');

    html, body, [class*="css"],
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"],
    [data-testid="stMetricLabel"],
    [data-testid="stDataFrame"], [data-testid="stDataFrame"] *,
    [data-testid="stTable"], [data-testid="stTable"] *,
    input, button, textarea, select,
    .stMarkdown, .stMarkdown * {
        font-family: 'Pretendard Variable', 'Pretendard', -apple-system, BlinkMacSystemFont, "Noto Sans KR", system-ui, sans-serif !important;
        -webkit-font-smoothing: antialiased !important;
        -moz-osx-font-smoothing: grayscale !important;
        text-rendering: optimizeLegibility !important;
        font-feature-settings: 'tnum' on !important;
    }
    /* 사이드바와 메인 영역 상단 정렬 (날짜 설정 ↔ 페북성과보고서 자동화 같은 높이) */
    .main .block-container {
        padding-top: 2.5rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        padding-top: 2.5rem !important;
    }
    .main .block-container h1:first-child,
    .main .block-container > div:first-child h1 {
        margin-top: 0 !important;
        padding-top: 0 !important;
        line-height: 1.2;
    }
    /* 사이드바 헤더(날짜 설정 / 파일 업로드) — 20px 섹션 헤더 */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] h3 {
        font-size: 20px !important;
        font-weight: 700 !important;
        color: #111111 !important;
        line-height: 1.3 !important;
    }
    /* 첫 헤더는 메인 타이틀과 상단선 맞추기 */
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] h3:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    /* 메인 영역 섹션 헤더(결과 요약, 담당자별 요약, 광고별 상세) — 20px */
    .main .block-container h3,
    [data-testid="stMain"] h3,
    [data-testid="stMainBlockContainer"] h3,
    [data-testid="stMarkdown"] h3,
    [data-testid="stMarkdownContainer"] h3 {
        font-size: 20px !important;
        font-weight: 700 !important;
        color: #111111 !important;
        line-height: 1.3 !important;
    }
    /* 사이드바 안의 [data-testid="stMarkdown"] 으로 들어간 h3에는 사이드바 규칙 우선 */
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h3,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        font-size: 20px !important;
        font-weight: 700 !important;
    }
    /* 사이드바 입력창 테두리 — 보고일(date_input) */
    section[data-testid="stSidebar"] [data-testid="stDateInput"] [data-baseweb="input"] {
        border: 1px solid #E5E7EB !important;
        border-radius: 8px !important;
    }
    /* 사이드바 집계 일수(number_input) — 입력+버튼 통합 테두리 */
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] [data-baseweb="input"] {
        border: none !important;
        background: transparent !important;
    }
    section[data-testid="stSidebar"] [data-testid="stNumberInput"] > div:not([data-testid="stWidgetLabel"]):not(label) {
        border: 1px solid #E5E7EB !important;
        border-radius: 8px !important;
        overflow: hidden;
    }
    /* 사이드바 캡션(설명 텍스트) 폰트 사이즈/행간 축소 — 여러 셀렉터 fallback */
    section[data-testid="stSidebar"] [data-testid="stCaption"],
    section[data-testid="stSidebar"] [data-testid="stCaption"] *,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] *,
    section[data-testid="stSidebar"] small,
    section[data-testid="stSidebar"] small * {
        font-size: 11px !important;
        line-height: 1.4 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaption"] ul,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] ul,
    section[data-testid="stSidebar"] small ul {
        margin: 0 !important;
        padding-left: 1rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stCaption"] li,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] li,
    section[data-testid="stSidebar"] small li {
        margin: 0 !important;
        padding: 0 !important;
    }
    /* 사이드바 집계 기간 엑셀(file_uploader) — 흰 박스/설명 제거, Browse 버튼만 풀 너비 */
    section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"],
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzone"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
        min-height: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"],
    section[data-testid="stSidebar"] [data-testid="stFileUploadDropzoneInstructions"] {
        display: none !important;
    }
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        width: 100% !important;
    }
    /* 알림(st.info / st.warning) 박스 — 파란/노란 톤 → 중립 회색, 테두리 없음 */
    [data-testid="stAlert"],
    [data-testid="stAlertContentInfo"],
    [data-testid="stAlertContentWarning"],
    [data-testid="stNotification"],
    [role="alert"] {
        background-color: #F0F0F0 !important;
        border: none !important;
        box-shadow: none !important;
        border-radius: 8px !important;
        color: #111111 !important;
    }
    [data-testid="stAlert"] *,
    [data-testid="stNotification"] *,
    [role="alert"] * {
        color: #111111 !important;
    }
    .stMetric { background: #FAFAFA; border-radius: 12px; padding: 16px; }
    .stMetric label { color: #666666 !important; font-size: 13px !important; }
    .stMetric [data-testid="stMetricValue"] {
        color: #111111 !important;
        font-weight: 700 !important;
        font-size: 1.5rem !important;
    }
    div[data-testid="stMetricDelta"] { font-weight: 600; font-size: 12px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ────────────────────── 인증 ──────────────────────

if not check_password():
    st.stop()


# ────────────────────── 사이드바 ──────────────────────

st.sidebar.markdown("### 날짜 설정")

today = date.today()
report_date = st.sidebar.date_input("**보고일**", value=today, format="YYYY-MM-DD")
report_dt = datetime.combine(report_date, datetime.min.time())

# 요일별 자동 집계 일수 (월=3, 수=2, 금=2, 그 외=1)
auto_start, auto_end, auto_days = get_collection_period(report_dt)
weekday_label = ["월", "화", "수", "목", "금", "토", "일"][report_dt.weekday()]

# 집계 일수 직접 변경 가능 (연휴 등)
days = st.sidebar.number_input(
    f"**집계 일수** (자동: {auto_days}일)",
    min_value=1,
    max_value=14,
    value=int(auto_days),
    step=1,
    help="기본값은 요일 기준 자동 산출. 연휴나 특수 케이스에선 직접 변경하세요.",
)

# days가 변경되면 종료일 고정(보고일 전날 23:59:59), 시작일만 재계산
end = auto_end
start_day = end - timedelta(days=int(days) - 1)
start = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0)

# 자동값과 다르면 표시 강조
caption_label = f"**{weekday_label}요일** 기준"
if int(days) != int(auto_days):
    caption_label += f" (자동 {auto_days}일 → 직접 {days}일로 변경)"
st.sidebar.caption(
    f"{caption_label}: {start.strftime('%m/%d')} ~ {end.strftime('%m/%d')} ({days}일)"
)

st.sidebar.divider()

# 지난주/작년 비교는 추후 누적 데이터 쌓인 후 활성화
compare_last_week = False
compare_last_year = False

# 담당자 필터 제거 — 광고별 상세 표에 담당자 탭이 있어 충분
selected_owners: list[str] = []  # 빈 리스트 = 전체 표시

st.sidebar.markdown("### 파일 업로드")

uploaded_current = st.sidebar.file_uploader(
    "**집계 기간 엑셀**", type=["xlsx"], key="upload_current",
)
st.sidebar.caption(
    "* 엑셀 파일은 500MB까지 업로드 가능\n"
    "* 스스 관리자센터 → 데이터분석 → 마케팅분석 → 사용자정의채널 → 상세보기 → 다운로드\n"
    "* 지난 주 데이터는 구글시트 누적탭에서 자동 조회됩니다."
)

st.sidebar.divider()

# Mock 토글 제거 — 실제 데이터 모드 고정
use_mock = False

generate_btn = st.sidebar.button("보고서 생성", use_container_width=True, type="primary")


# ────────────────────── 메인 영역 ──────────────────────

st.markdown(
    '<h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; color: #111111;">페북 성과보고서 오토파일럿</h1>',
    unsafe_allow_html=True,
)
st.caption(f"보고일: **{report_date.strftime('%Y년 %m월 %d일')} ({weekday_label})** | 집계 {days}일치")


# ────────────────────── 데이터 로드 ──────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _load_facebook(start_iso: str, end_iso: str, use_mock: bool):
    s = datetime.fromisoformat(start_iso)
    e = datetime.fromisoformat(end_iso)
    return fetch_facebook_ads(s, e, use_mock=use_mock)


def _load_naver_data(uploaded_file, use_mock: bool, fb_ads_for_mock=None):
    """네이버 마케팅분석 데이터 로드 (raw, full tuple 매칭용).

    - use_mock=True: mock 생성
    - 업로드된 파일 있음: 파싱
    - 둘 다 없음: 빈 DF
    """
    if use_mock:
        return generate_mock_naver_excel_df(fb_ads_for_mock or [])
    if uploaded_file is None:
        return pd.DataFrame(columns=["nt_source", "nt_medium", "nt_detail", "nt_keyword", "유입수", "결제수", "결제금액"])
    return parse_naver_marketing_excel(uploaded_file.getvalue())


def _build_report(ads_list, naver_agg, days, manual_overrides=None):
    rows, unmatched_naver = match_facebook_with_naver(ads_list, naver_agg, manual_overrides=manual_overrides)
    df = matched_rows_to_dataframe(rows, days=days)
    return df, unmatched_naver, rows


if generate_btn or st.session_state.get("report_loaded", False):
    st.session_state["report_loaded"] = True

    # 실제 모드인데 엑셀 없음 → 안내
    if not use_mock and uploaded_current is None:
        st.warning("사이드바에서 **마케팅분석 엑셀**을 업로드해주세요.")
        st.stop()

    with st.spinner("페북 + 네이버 데이터 처리 중..."):
        # 현재 기간
        ads = _load_facebook(start.isoformat(), end.isoformat(), use_mock)
        naver_agg = _load_naver_data(uploaded_current, use_mock, fb_ads_for_mock=ads)
        manual_overrides = st.session_state.get("manual_overrides", {})
        current_df, unmatched_naver, rows_for_stats = _build_report(ads, naver_agg, int(days), manual_overrides)

        # 작년 동기 — 구글 시트 누적 탭에서 자동 조회
        last_year_df = pd.DataFrame()
        last_year_kpi = None
        if compare_last_year:
            ly_report_date = get_same_week_last_year(report_dt)
            last_year_df = fetch_report_from_sheet(ly_report_date)
            if not last_year_df.empty:
                last_year_kpi = aggregate_kpi(last_year_df)

        # 지난주 — 구글 시트 누적 탭에서 자동 조회
        last_week_df = pd.DataFrame()
        if compare_last_week:
            lw_report_date = get_last_week(report_dt)
            last_week_df = fetch_report_from_sheet(lw_report_date)

    # 비교 컬럼 추가
    merged_df = merge_comparison(current_df, last_year_df, last_week_df)

    # 유효 판정 — 구글 시트 누적 데이터(7일) + 페북 API created_time
    history = fetch_validity_history(report_dt, lookback_days=7) if not use_mock else {}
    # 옛 캐시(created_time 필드 없음) 호환 — getattr로 안전 fallback
    created_time_lookup = {r.ad.ad_name: getattr(r.ad, "created_time", None) for r in rows_for_stats}
    merged_df = annotate_validity(
        merged_df,
        history_lookup=history if history else None,
        created_time_lookup=created_time_lookup,
        report_date=report_dt,
    )

    # 7일 누적 컬럼 (7일지출/7일매출/7일ROAS) 추가 — 같은 history_lookup 사용
    merged_df = merge_seven_day(merged_df, history)

    if selected_owners:
        merged_df = merged_df[merged_df["담당자"].isin(selected_owners)]

    display_df = apply_period_labels(merged_df, int(days))

    # ────────────────────── KPI 카드 ──────────────────────

    kpi = aggregate_kpi(merged_df)
    deltas = compute_kpi_deltas(kpi, last_year_kpi)

    # 꺼진 광고 매출 (현재 활성 페북 광고에 매칭 안 된 페북 채널 매출)
    ghost_revenue = sum(item["revenue"] for item in unmatched_naver)
    ghost_count = sum(item["conversion_count"] for item in unmatched_naver)

    st.markdown("### 결과 요약")
    # ROAS 기준 카드 배경: ≥100% 옅은 핑크 / <100% 옅은 파랑
    _roas = float(kpi.get("roas", 0) or 0)
    _metric_bg = "#FCE7F3" if _roas >= 100 else "#DBEAFE"
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
        c1.metric(
            "총 광고비",
            f"₩{kpi['total_spend']:,.0f}",
            delta=f"{deltas['spend']:+.1f}% (작년)" if deltas["spend"] is not None else None,
            delta_color="inverse",
        )
        c2.metric(
            "총 매출",
            f"₩{kpi['total_revenue']:,.0f}",
            delta=f"{deltas['revenue']:+.1f}% (작년)" if deltas["revenue"] is not None else None,
        )
        c3.metric(
            "ROAS",
            f"{kpi['roas']:.0f}%",
            delta=f"{deltas['roas']:+.1f}% (작년)" if deltas["roas"] is not None else None,
        )
        c4.metric(
            "전환수",
            f"{kpi['conversion_count']:,}",
            delta=f"{deltas['conversion']:+.1f}% (작년)" if deltas["conversion"] is not None else None,
        )
        c5.metric(
            "꺼진 광고 매출",
            f"₩{ghost_revenue:,.0f}",
            delta=f"{ghost_count}건" if ghost_count else None,
            delta_color="off",
            help="현재 활성 페북 광고에 매칭 안 됐지만 페북 출처(facebook)인 매출. 보통 꺼진 광고의 지연 전환.",
        )

        # ────────────────────── 매칭 통계 ──────────────────────
        stats = matching_stats(rows_for_stats, unmatched_naver)
        info_cols = st.columns(2)
        info_cols[0].info(
            f"매칭률: **{stats['match_rate']:.1f}%** ({stats['matched_ads']:,}/{stats['total_ads']:,} 광고)"
        )
        info_cols[1].info(f"매칭 매출: **₩{stats['matched_revenue']:,.0f}**")

    # 담당자별 요약
    st.markdown("### 담당자별 요약")
    owner_summary = aggregate_by_owner(merged_df)
    if not owner_summary.empty:
        owner_display = owner_summary.rename(columns={"지출": "광고비"})
        owner_display = owner_display[["담당자", "광고비", "매출", "ROAS", "전환수", "클릭", "노출", "CTR"]].copy()
        # 천 단위 콤마로 미리 포맷 (Streamlit NumberColumn이 콤마 미지원)
        owner_display["광고비"] = owner_display["광고비"].apply(lambda x: f"₩{int(x):,}")
        owner_display["매출"] = owner_display["매출"].apply(lambda x: f"₩{int(x):,}")
        owner_display["ROAS"] = owner_display["ROAS"].apply(lambda x: f"{int(x):,}%" if pd.notna(x) else "-")
        owner_display["전환수"] = owner_display["전환수"].apply(lambda x: f"{int(x):,}")
        owner_display["클릭"] = owner_display["클릭"].apply(lambda x: f"{int(x):,}")
        owner_display["노출"] = owner_display["노출"].apply(lambda x: f"{int(x):,}")
        owner_display["CTR"] = owner_display["CTR"].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "-")
        st.dataframe(owner_display, use_container_width=True, hide_index=True)
    else:
        st.info("담당자별 집계 데이터가 없습니다.")

    if compare_last_year and last_year_df.empty:
        st.warning("작년 동기 데이터가 없습니다. 사이드바에서 작년 엑셀도 업로드하면 비교가 가능해요.")
    if compare_last_week and last_week_df.empty:
        st.warning("지난주 데이터가 없습니다. 사이드바에서 지난주 엑셀도 업로드하면 비교가 가능해요.")

    # 매칭률 0%면 페북 URL 진단 정보 표시
    if not use_mock and stats["match_rate"] == 0 and stats["total_ads"] > 0:
        debug = get_link_url_debug()
        with st.expander("페북 광고 URL 진단 (매칭률 0%일 때)", expanded=True):
            st.caption("페북 광고에서 link_url 가져오기 + nt_detail 추출 결과")
            errors = debug.get("errors", [])
            if errors:
                st.error(f"URL 조회 에러 {len(errors)}건. 첫 3건:")
                for e in errors[:3]:
                    st.code(e)
            samples = debug.get("samples", [])
            if samples:
                st.write("**광고별 첫 5건 샘플:**")
                for s in samples:
                    st.json(s)
            else:
                st.warning("샘플이 비어있어요. 페북 API 권한이나 ad_id 문제일 수 있어요.")

    # ────────────────────── 광고별 상세 표 ──────────────────────

    st.markdown("### 광고별 상세")

    # 시트 저장 + 바로가기 버튼 (광고별 상세 헤더 바로 아래)
    _btn_save, _btn_link = st.columns([3, 1])
    with _btn_save:
        if st.button("구글 시트 누적 저장", use_container_width=True, type="primary", key="save_sheet_top"):
            with st.spinner("구글 시트에 저장 중..."):
                try:
                    ok, msg = append_report(display_df, report_dt)
                except Exception as e:
                    ok, msg = False, f"예외 발생: {type(e).__name__}: {e}"
            st.session_state["sheet_save_result"] = (ok, msg)
            st.toast(msg)
            st.rerun()
    with _btn_link:
        # 가장 최근 MMDD 탭 URL — 보고일 시트 우선, 없으면 최신 MMDD 시트
        _sheet_url = get_latest_sheet_url(report_dt)
        if _sheet_url:
            st.link_button(
                "구글시트 바로가기",
                _sheet_url,
                use_container_width=True,
            )

    # 저장 결과 영구 표시
    if "sheet_save_result" in st.session_state:
        _ok, _msg = st.session_state["sheet_save_result"]
        if _ok:
            st.success(f"구글 시트: {_msg}")
        else:
            st.error(f"구글 시트 저장 실패: {_msg}")

    available_owners = sorted(display_df["담당자"].unique())
    if available_owners:
        tabs = st.tabs(["전체"] + [str(o) for o in available_owners])
        with tabs[0]:
            st.dataframe(style_dataframe(display_df, days=days), use_container_width=True, height=500)
        for i, owner in enumerate(available_owners, start=1):
            with tabs[i]:
                owner_df = display_df[display_df["담당자"] == owner]
                st.dataframe(style_dataframe(owner_df, days=days), use_container_width=True, height=500)
    else:
        st.info("표시할 데이터가 없습니다.")

    # ────────────────────── 매칭 진단 (페북 ↔ 네이버 파라미터 비교) ──────────────────────

    # 매칭 실패한 페북 광고 (매칭은 됐지만 매출 0인 건 제외 — 그건 그냥 매출 없는 광고)
    failed_fb_rows = [r for r in rows_for_stats if not r.matched]
    if failed_fb_rows or unmatched_naver:
        with st.expander(
            f"매칭 진단 — 파라미터 비교 (페북 매칭 실패 {len(failed_fb_rows)}건 / 매출 있는 미매칭 네이버 {len(unmatched_naver)}건)",
            expanded=False,
        ):
            tab_fb, tab_nv = st.tabs(["페북 (매칭 실패)", "네이버 (페북에 없는 매출)"])

            with tab_fb:
                if failed_fb_rows:
                    fb_diag = pd.DataFrame([
                        {
                            "광고이름": r.ad.ad_name,
                            "담당자": r.ad.owner,
                            "nt_source": r.ad.nt_source,
                            "nt_medium": r.ad.nt_medium,
                            "nt_detail": r.ad.nt_detail,
                            "nt_keyword": r.ad.nt_keyword,
                            "지출": r.ad.spend,
                            "랜딩 URL": r.ad.link_url or "(URL 없음)",
                        }
                        for r in failed_fb_rows
                    ])
                    st.dataframe(
                        fb_diag,
                        use_container_width=True,
                        height=300,
                        column_config={
                            "랜딩 URL": st.column_config.LinkColumn("랜딩 URL", width="large"),
                            "지출": st.column_config.NumberColumn(format="₩%d"),
                        },
                    )
                else:
                    st.info("매칭 실패한 페북 광고 없음")

            with tab_nv:
                if unmatched_naver:
                    nv_diag = pd.DataFrame(unmatched_naver)
                    nv_diag = nv_diag[["nt_source", "nt_medium", "nt_detail", "nt_keyword", "revenue", "conversion_count", "visits"]]
                    nv_diag.columns = ["nt_source", "nt_medium", "nt_detail", "nt_keyword", "결제금액", "결제수", "유입수"]
                    st.dataframe(nv_diag, use_container_width=True, height=300)
                else:
                    st.info("매칭 안 된 네이버 매출 없음")

    # ────────────────────── 매칭 안 된 nt_detail (수동 매칭) ──────────────────────

    if unmatched_naver:
        with st.expander(
            f"매칭 안 된 네이버 행 {len(unmatched_naver)}건 — 수동 매칭",
            expanded=False,
        ):
            st.caption(
                "페북 광고와 매칭되지 못한 네이버 매출입니다. "
                "아래 페북 광고 목록(URL/파라미터)을 보고 어떤 광고에 합칠지 선택하세요."
            )

            # 1. 페북 광고 전체 참고 표 (URL/파라미터 포함)
            st.markdown("**페북 광고 32개 전체 (참고용 — URL/파라미터 비교)**")
            fb_reference_df = pd.DataFrame([
                {
                    "광고이름": r.ad.ad_name,
                    "담당자": r.ad.owner,
                    "nt_source": r.ad.nt_source,
                    "nt_medium": r.ad.nt_medium,
                    "nt_detail": r.ad.nt_detail,
                    "nt_keyword": r.ad.nt_keyword,
                    "지출": r.ad.spend,
                    "현재매출": r.revenue,
                    "랜딩 URL": r.ad.link_url or "(URL 없음)",
                }
                for r in rows_for_stats
            ])
            st.dataframe(
                fb_reference_df,
                use_container_width=True,
                height=250,
                column_config={
                    "랜딩 URL": st.column_config.LinkColumn("랜딩 URL", width="medium"),
                    "지출": st.column_config.NumberColumn(format="₩%d"),
                    "현재매출": st.column_config.NumberColumn(format="₩%d"),
                },
            )

            st.divider()

            # 2. 매칭 안 된 네이버 행 + 드롭다운
            st.markdown("**매칭 작업**")
            ad_options = ["(매칭 안 함)"] + [
                f"{r.ad.ad_name}  |  {r.ad.nt_detail}/{r.ad.nt_keyword}"
                for r in sorted(rows_for_stats, key=lambda x: x.ad.ad_name)
            ]
            new_overrides = dict(st.session_state.get("manual_overrides", {}))

            # 헤더
            h1, h2, h3, h4, h5, h6, h7 = st.columns([1.5, 1.5, 2, 1.2, 1.5, 1, 3])
            h1.markdown("**nt_source**")
            h2.markdown("**nt_medium**")
            h3.markdown("**nt_detail**")
            h4.markdown("**nt_keyword**")
            h5.markdown("**결제금액**")
            h6.markdown("**결제수**")
            h7.markdown("**매칭할 광고 (광고이름 | nt_detail/nt_keyword)**")

            for idx, item in enumerate(unmatched_naver):
                c1, c2, c3, c4, c5, c6, c7 = st.columns([1.5, 1.5, 2, 1.2, 1.5, 1, 3])
                c1.text(item["nt_source"] or "-")
                c2.text(item["nt_medium"] or "-")
                c3.text(item["nt_detail"] or "-")
                c4.text(item["nt_keyword"] or "-")
                c5.text(f"₩{item['revenue']:,.0f}")
                c6.text(f"{item['conversion_count']}")
                key_id = f"match_nt_{idx}_{item['nt_detail']}_{item['nt_keyword']}"
                selected = c7.selectbox(
                    "매칭할 광고",
                    ad_options,
                    key=key_id,
                    label_visibility="collapsed",
                )
                if selected != "(매칭 안 함)":
                    # "광고이름 | nt_detail/nt_keyword" 에서 광고이름만 추출
                    selected_ad_name = selected.split("  |  ")[0].strip()
                    new_overrides[selected_ad_name] = (item["nt_detail"], item["nt_keyword"])

            if st.button("수동 매칭 적용", key="apply_manual_match"):
                st.session_state["manual_overrides"] = new_overrides
                for ad_name, key in new_overrides.items():
                    log_manual_match("/".join(key), ad_name, user="user", reason="수동 매칭")
                st.success(f"{len(new_overrides)}건 매칭 적용됨. 새로고침하면 반영됩니다.")
                st.rerun()

else:
    st.info("사이드바에서 **마케팅분석 엑셀 업로드** + **보고서 생성** 버튼을 눌러주세요.")
