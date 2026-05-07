"""광고 통합 오토파일럿 — Streamlit 멀티페이지 entry point.

페이지 구조:
- 통합 대시보드 (홈) — 3채널 한눈에
- 페북광고 — 기존 v1.0 기능 그대로
- GFA 성과형 — 신규 (개발 중)
- 네이버 검색광고 — 신규 (개발 중)

전역 설정 (페이지 config + CSS + 인증)은 모두 이 파일에서.
페이지별 로직은 pages/ 폴더의 각 파일에서.
"""

from __future__ import annotations

import streamlit as st

from src.auth import check_password


# ────────────────────── 페이지 설정 ──────────────────────

st.set_page_config(
    page_title="광고 통합 오토파일럿",
    page_icon="assets/icon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ────────────────────── 글로벌 CSS (모든 페이지) ──────────────────────

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
    /* 사이드바와 메인 영역 상단 정렬 */
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
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] h3:first-child {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    /* 메인 영역 섹션 헤더 — 20px */
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
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h3,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        font-size: 20px !important;
        font-weight: 700 !important;
    }
    /* 사이드바 보고일(date_input) 테두리 */
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
    /* 사이드바 캡션 폰트 사이즈 축소 */
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
    /* 사이드바 file_uploader — 흰 박스/설명 제거 */
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
    /* 알림 박스 — 중립 회색, 테두리 없음 */
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
    /* KPI 카드 */
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


# ────────────────────── 인증 (모든 페이지 공통) ──────────────────────

if not check_password():
    st.stop()


# ────────────────────── 페이지 네비게이션 ──────────────────────

dashboard_page = st.Page(
    "pages/dashboard.py",
    title="통합 대시보드",
    default=True,
)
facebook_page = st.Page(
    "pages/facebook.py",
    title="페북광고",
)
gfa_page = st.Page(
    "pages/gfa.py",
    title="GFA 성과형",
)
search_ad_page = st.Page(
    "pages/search_ad.py",
    title="네이버 검색광고",
)

pg = st.navigation(
    [dashboard_page, facebook_page, gfa_page, search_ad_page],
)
pg.run()
