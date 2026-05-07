"""모든 페이지가 공유하는 사이드바.

날짜 설정(보고일·집계일수) + 파일 업로드 + 보고서 생성 버튼.
state는 st.session_state로 페이지 간 공유.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from src.aggregation import get_collection_period


def render_sidebar() -> dict[str, Any]:
    """공통 사이드바 렌더링.

    Returns:
        {
            "report_date": date,
            "report_dt": datetime,
            "days": int,
            "start": datetime,
            "end": datetime,
            "weekday_label": str,
            "uploaded_current": UploadedFile | None,
            "generate_btn": bool,
        }
    """
    # ────── 날짜 설정 ──────
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

    # ────── 파일 업로드 ──────
    st.sidebar.markdown("### 파일 업로드")

    uploaded_current = st.sidebar.file_uploader(
        "**집계 기간 엑셀**", type=["xlsx"], key="upload_current",
    )
    st.sidebar.caption(
        "* 엑셀 파일은 500MB까지 업로드 가능\n"
        "* 스스 관리자센터 → 데이터분석 → 마케팅분석 → 사용자정의채널 → 상세보기 → 다운로드\n"
        "* 지난 주 데이터는 구글시트 누적탭에서 자동 조회됩니다.\n"
        "* ※ 페북 매출 매칭에만 사용 (GFA·검색광고는 API에서 직접 조회)"
    )

    st.sidebar.divider()

    generate_btn = st.sidebar.button(
        "보고서 생성", use_container_width=True, type="primary", key="generate_btn"
    )

    # session_state에도 저장 (페이지 간 공유)
    state = {
        "report_date": report_date,
        "report_dt": report_dt,
        "days": int(days),
        "start": start,
        "end": end,
        "weekday_label": weekday_label,
        "uploaded_current": uploaded_current,
        "generate_btn": generate_btn,
    }
    st.session_state["sidebar_state"] = state
    return state
