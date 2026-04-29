"""단일 비밀번호 보호."""

from __future__ import annotations

import hmac

import streamlit as st


def check_password() -> bool:
    """비번 검증. 통과하면 True 반환, 아니면 입력 폼 렌더 후 False."""
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("### 🔒 페북성과보고서 자동화")
    st.caption("접근하려면 비밀번호를 입력하세요.")

    # st.form으로 감싸면 Enter 키 입력 시 자동 제출됨
    with st.form("login_form", clear_on_submit=False, border=False):
        password = st.text_input(
            "비밀번호", type="password", key="pw_input", label_visibility="collapsed"
        )
        submit = st.form_submit_button("입장", use_container_width=True)

    if submit:
        expected = st.secrets.get("APP_PASSWORD", "")
        if not expected:
            st.error("관리자: APP_PASSWORD가 설정되지 않았습니다. .streamlit/secrets.toml 확인 바랍니다.")
            return False
        if hmac.compare_digest(password, expected):
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("비밀번호가 일치하지 않습니다.")
    return False
