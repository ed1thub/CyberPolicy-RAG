"""CyberPolicy-RAG — Streamlit frontend."""

import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Allow running from the repo root with `streamlit run frontend/streamlit_app.py`
sys.path.insert(0, str(Path(__file__).parent))

from api_client import ApiClient  # noqa: E402

_api = ApiClient()

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

_STATE_DEFAULTS: dict[str, Any] = {
    "token": None,
    "username": None,
    "role": None,
    "page": "Chat",
}


def _init_state() -> None:
    for key, default in _STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def _logout() -> None:
    for key, default in _STATE_DEFAULTS.items():
        st.session_state[key] = default
    st.rerun()


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------


def _show_login() -> None:
    st.title("CyberPolicy-RAG")
    st.subheader("Secure Policy Assistant")
    st.write("Log in to ask questions about cybersecurity policies.")

    if not _api.health():
        st.error(
            "Cannot reach backend at `http://127.0.0.1:8000`. "
            "Start it with `uvicorn backend.app.main:app --reload`."
        )

    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button(
                "Log in", type="primary", use_container_width=True
            )

        if submitted:
            if not username or not password:
                st.error("Enter username and password.")
                return

            token_data = _api.login(username, password)
            if token_data is None:
                st.error("Login failed. Check credentials or backend connection.")
                return

            token = token_data["access_token"]
            me = _api.get_me(token)
            if me is None:
                st.error("Authenticated but could not retrieve user profile.")
                return

            st.session_state.token = token
            st.session_state.username = me["username"]
            st.session_state.role = me["role"]
            st.session_state.page = "Chat"
            st.rerun()

    st.divider()
    with st.expander("Demo accounts"):
        st.markdown(
            "| Username | Password | Role |\n"
            "|---|---|---|\n"
            "| student1 | password123 | user |\n"
            "| analyst1 | password123 | security_analyst |\n"
            "| admin1 | password123 | admin |"
        )


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------


def _show_sidebar() -> None:
    with st.sidebar:
        st.title("CyberPolicy-RAG")
        st.write(f"**{st.session_state.username}**")
        st.caption(f"Role: `{st.session_state.role}`")
        st.divider()

        pages = ["Chat"]
        if st.session_state.role in ("security_analyst", "admin"):
            pages.append("Audit Logs")
        if st.session_state.role == "admin":
            pages.append("Admin Upload")

        selected = st.radio("Navigation", pages, key="nav_radio")
        st.session_state.page = selected

        st.divider()
        if st.button("Logout", use_container_width=True):
            _logout()


# ---------------------------------------------------------------------------
# Chat page
# ---------------------------------------------------------------------------

_CONFIDENCE_LABELS: dict[str, str] = {
    "high": "✅ High confidence",
    "medium": "⚠️ Medium confidence",
    "low": "⚠️ Low confidence",
    "none": "❌ No matching policy documents found",
    "blocked": "🚫 Request blocked",
}


def _show_chat() -> None:
    st.header("Policy Chat")
    st.caption(
        "Ask questions about cybersecurity policies. "
        "Answers are grounded in authorised documents only."
    )

    with st.form("chat_form", clear_on_submit=False):
        question = st.text_area(
            "Your question",
            height=120,
            max_chars=1000,
            placeholder="What does the password policy say about MFA?",
        )
        submitted = st.form_submit_button("Ask", type="primary")

    if not submitted or not question.strip():
        return

    with st.spinner("Retrieving answer from policy documents..."):
        result = _api.chat(question.strip(), st.session_state.token)

    if result is None:
        st.error("Could not reach the backend. Check it is running.")
        return

    # Detect auth errors (expired token etc.)
    if "detail" in result:
        detail = str(result.get("detail", "")).lower()
        if "not authenticated" in detail or "could not validate" in detail:
            st.warning("Session expired. Please log in again.")
            _logout()
        else:
            st.error(f"Error: {result['detail']}")
        return

    st.divider()

    answer: str = result.get("answer", "")
    confidence: str = result.get("confidence", "none")
    risk_flags: list[str] = result.get("risk_flags", [])
    sources: list[dict[str, Any]] = result.get("sources", [])

    # Answer display
    if confidence == "blocked":
        st.warning(f"**Request blocked**\n\n{answer}")
    elif confidence == "none":
        st.info(answer)
    else:
        st.markdown(f"**Answer**\n\n{answer}")

    # Risk flags
    if risk_flags:
        st.error(f"Risk flag: `{'`, `'.join(risk_flags)}`")

    # Confidence indicator
    st.caption(_CONFIDENCE_LABELS.get(confidence, confidence))

    # Source citations
    if sources:
        with st.expander(
            f"Sources — {len(sources)} document section{'s' if len(sources) != 1 else ''}"
        ):
            for i, source in enumerate(sources, 1):
                title = source.get("document_title", "Unknown")
                filename = source.get("filename", "")
                section = source.get("section_heading")
                page = source.get("page")

                st.markdown(f"**{i}. {title}**")
                if section:
                    st.write(f"Section: {section}")
                st.write(f"File: `{filename}`")
                if page:
                    st.write(f"Page: {page}")
                if i < len(sources):
                    st.divider()


# ---------------------------------------------------------------------------
# Audit logs page
# ---------------------------------------------------------------------------


def _show_audit_logs() -> None:
    st.header("Audit Logs")
    st.caption(
        "All chat requests are logged for accountability and incident review. "
        "Visible to security analysts and administrators only."
    )

    if st.button("Refresh", icon="🔄"):
        st.rerun()

    logs = _api.get_audit_logs(st.session_state.token)

    if logs is None:
        st.error(
            "Could not retrieve audit logs. "
            "Check backend connection or your permissions."
        )
        return

    if not logs:
        st.info("No audit log entries recorded yet.")
        return

    st.write(f"{len(logs)} log entr{'ies' if len(logs) != 1 else 'y'} found.")

    rows = []
    for log in logs:
        question_text = log.get("question") or ""
        truncated = question_text[:80] + ("…" if len(question_text) > 80 else "")
        rows.append(
            {
                "Username": log.get("username", ""),
                "Role": log.get("role", ""),
                "Question": truncated,
                "Status": log.get("answer_status", ""),
                "Risk flags": ", ".join(log.get("risk_flags") or []) or "—",
                "Documents used": ", ".join(log.get("documents_used") or []) or "—",
                "Timestamp": log.get("created_at", ""),
            }
        )

    st.dataframe(rows, use_container_width=True)


# ---------------------------------------------------------------------------
# Admin upload placeholder
# ---------------------------------------------------------------------------


def _show_admin_upload() -> None:
    st.header("Admin Document Upload")
    st.info(
        "Document upload will be available in a future release. "
        "Administrators will be able to upload `.md`, `.txt`, and `.pdf` "
        "policy files which are automatically chunked and indexed."
    )
    st.divider()
    st.write("**Planned upload requirements:**")
    st.markdown(
        "- Supported formats: `.md`, `.txt`, `.pdf`\n"
        "- Maximum file size: 5 MB per document\n"
        "- Sensitivity level must be selected at upload time\n"
        "- Admin role required — upload endpoint is not exposed to other roles\n"
        "- Uploaded documents are chunked and indexed immediately into ChromaDB"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="CyberPolicy-RAG",
        page_icon="🔒",
        layout="centered",
    )
    _init_state()

    if not _is_logged_in():
        _show_login()
        return

    _show_sidebar()

    page = st.session_state.page
    if page == "Chat":
        _show_chat()
    elif page == "Audit Logs":
        _show_audit_logs()
    elif page == "Admin Upload":
        _show_admin_upload()


if __name__ == "__main__":
    main()
