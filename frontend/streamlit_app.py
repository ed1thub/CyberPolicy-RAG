"""CyberPolicy-RAG — Streamlit frontend."""

import sys
from pathlib import Path
from typing import Any

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from api_client import ApiClient  # noqa: E402

_api = ApiClient()

# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* Reduce top padding */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 0 !important;
}

/* Sidebar inner padding */
[data-testid="stSidebar"] > div:first-child {
    padding: 1.25rem 1rem 1rem;
}

/* Hide the nav radio label */
[data-testid="stSidebar"] [data-testid="stRadio"] > label:first-child {
    display: none;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 14px;
    font-weight: 500;
    padding: 5px 2px;
}

/* Chat input */
[data-testid="stChatInput"] textarea {
    font-family: 'Inter', sans-serif !important;
    font-size: 15px;
}

/* Form inputs */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    font-family: 'Inter', sans-serif !important;
    border-radius: 8px !important;
}

/* Primary button */
[data-testid="stFormSubmitButton"] button[kind="primary"],
.stButton button[kind="primary"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
}
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# HTML badge helpers
# ---------------------------------------------------------------------------

_CONFIDENCE_CONFIG: dict[str, tuple[str, str, str]] = {
    "high":    ("🟢", "#10b981", "High confidence"),
    "medium":  ("🟡", "#f59e0b", "Medium confidence"),
    "low":     ("🔴", "#ef4444", "Low confidence"),
    "none":    ("⭕", "#64748b", "No source found"),
    "blocked": ("🚫", "#ef4444", "Request blocked"),
}

_ROLE_CONFIG: dict[str, tuple[str, str]] = {
    "user":             ("#3b82f6", "User"),
    "security_analyst": ("#8b5cf6", "Security Analyst"),
    "admin":            ("#f59e0b", "Admin"),
}


def _badge(text: str, color: str, icon: str = "") -> str:
    prefix = f"{icon} " if icon else ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;'
        f'background:{color}22;color:{color};padding:3px 10px;'
        f'border-radius:20px;font-size:12px;font-weight:600;'
        f'border:1px solid {color}44;white-space:nowrap">'
        f'{prefix}{text}</span>'
    )


def _confidence_badge(confidence: str) -> str:
    icon, color, label = _CONFIDENCE_CONFIG.get(confidence, ("❓", "#64748b", confidence))
    return _badge(label, color, icon)


def _role_badge(role: str) -> str:
    color, label = _ROLE_CONFIG.get(role, ("#64748b", role.replace("_", " ").title()))
    return _badge(label, color)


def _risk_badge(flag: str) -> str:
    return (
        f'<span style="background:#ef444422;color:#ef4444;padding:2px 8px;'
        f'border-radius:4px;font-size:11px;font-weight:700;'
        f'border:1px solid #ef444444;font-family:monospace;letter-spacing:0.02em">'
        f'{flag}</span>'
    )


def _source_card(source: dict[str, Any]) -> str:
    title = source.get("document_title", "Unknown")
    filename = source.get("filename", "")
    section = source.get("section_heading") or ""
    page = source.get("page")
    page_text = f" · p.{page}" if page else ""
    section_html = (
        f'<div style="color:#94a3b8;font-size:12px;margin-top:2px">§ {section}</div>'
        if section
        else ""
    )
    return (
        f'<div style="padding:10px 12px;margin:6px 0;'
        f'background:rgba(59,130,246,0.07);'
        f'border-left:3px solid #3b82f6;border-radius:0 6px 6px 0">'
        f'<div style="font-weight:600;font-size:14px">{title}</div>'
        f'{section_html}'
        f'<div style="color:#475569;font-size:11px;margin-top:4px;font-family:monospace">'
        f'{filename}{page_text}</div></div>'
    )


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_STATE_DEFAULTS: dict[str, Any] = {
    "token":    None,
    "username": None,
    "role":     None,
    "page":     "Chat",
    "messages": [],
}


def _init_state() -> None:
    for key, default in _STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = (
                default if not isinstance(default, list) else []
            )


def _is_logged_in() -> bool:
    return bool(st.session_state.get("token"))


def _logout() -> None:
    for key, default in _STATE_DEFAULTS.items():
        st.session_state[key] = (
            default if not isinstance(default, list) else []
        )
    st.rerun()


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------

_DEMO_ACCOUNTS = (
    ("student1", "password123", "User"),
    ("analyst1", "password123", "Security Analyst"),
    ("admin1",   "password123", "Admin"),
)


def _show_login() -> None:
    _inject_css()

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown(
            """
            <div style="text-align:center;padding:3rem 0 1.75rem">
                <div style="font-size:52px;line-height:1">🔒</div>
                <h1 style="font-size:26px;font-weight:800;margin:0.75rem 0 0.25rem;
                           letter-spacing:-0.02em">CyberPolicy-RAG</h1>
                <p style="color:#64748b;font-size:14px;margin:0">
                    Secure AI-powered policy assistant
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not _api.health():
            st.error(
                "⚡ Backend unreachable at `http://127.0.0.1:8000`.  \n"
                "Run: `uvicorn backend.app.main:app --reload`"
            )

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="student1")
            password = st.text_input(
                "Password", type="password", placeholder="••••••••"
            )
            submitted = st.form_submit_button(
                "Sign in →", type="primary", use_container_width=True
            )

        if submitted:
            if not username or not password:
                st.error("Enter both username and password.")
                return

            with st.spinner("Signing in..."):
                token_data = _api.login(username, password)

            if token_data is None:
                st.error("Invalid credentials or backend unreachable.")
                return

            token = token_data["access_token"]
            me = _api.get_me(token)
            if me is None:
                st.error("Login succeeded but could not load user profile.")
                return

            st.session_state.token = token
            st.session_state.username = me["username"]
            st.session_state.role = me["role"]
            st.session_state.page = "Chat"
            st.session_state.messages = []
            st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        with st.expander("Demo accounts"):
            rows = "\n".join(
                f"| `{u}` | `{p}` | {r} |" for u, p, r in _DEMO_ACCOUNTS
            )
            st.markdown(f"| Username | Password | Role |\n|---|---|---|\n{rows}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

_PAGE_MAP: dict[str, str] = {
    "💬  Chat":         "Chat",
    "📋  Audit Logs":   "Audit Logs",
    "📤  Admin Upload": "Admin Upload",
}


def _show_sidebar() -> None:
    role = st.session_state.role or ""
    username = st.session_state.username or ""

    with st.sidebar:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;'
            'padding:0 0 1.5rem;font-weight:700;font-size:16px">'
            '<span style="font-size:20px">🔒</span> CyberPolicy-RAG</div>',
            unsafe_allow_html=True,
        )

        # User card
        st.markdown(
            f'<div style="background:rgba(255,255,255,0.06);border-radius:10px;'
            f'padding:12px 14px;margin-bottom:1.5rem;'
            f'border:1px solid rgba(255,255,255,0.08)">'
            f'<div style="font-weight:600;font-size:14px;margin-bottom:6px">'
            f'👤 {username}</div>'
            f'{_role_badge(role)}</div>',
            unsafe_allow_html=True,
        )

        # Navigation
        nav_options = ["💬  Chat"]
        if role in ("security_analyst", "admin"):
            nav_options.append("📋  Audit Logs")
        if role == "admin":
            nav_options.append("📤  Admin Upload")

        selected = st.radio(
            "nav", nav_options, key="nav_radio", label_visibility="collapsed"
        )
        st.session_state.page = _PAGE_MAP.get(selected, "Chat")

        st.divider()

        if (
            st.session_state.page == "Chat"
            and st.session_state.get("messages")
        ):
            if st.button("🗑️  Clear conversation", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        if st.button("Sign out", use_container_width=True):
            _logout()


# ---------------------------------------------------------------------------
# Chat page
# ---------------------------------------------------------------------------

_SUGGESTED: list[str] = [
    "What are the password complexity requirements?",
    "Is MFA mandatory for remote access?",
    "What is the incident response process for a data breach?",
    "How should confidential documents be handled?",
]


def _render_assistant_message(msg: dict[str, Any]) -> None:
    confidence: str = msg.get("confidence", "none")
    content: str = msg.get("content", "")
    sources: list[dict] = msg.get("sources", [])
    risk_flags: list[str] = msg.get("risk_flags", [])

    if risk_flags:
        flags_html = " ".join(_risk_badge(f) for f in risk_flags)
        st.markdown(f"⚠️ &nbsp;{flags_html}", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

    if confidence == "blocked":
        st.warning(content)
    elif confidence == "none":
        st.info(content)
    else:
        st.markdown(content)

    badge_html = _confidence_badge(confidence)
    st.markdown(
        f'<div style="margin-top:10px">{badge_html}</div>',
        unsafe_allow_html=True,
    )

    if sources:
        n = len(sources)
        with st.expander(
            f"📚 {n} source{'s' if n != 1 else ''}", expanded=False
        ):
            cards_html = "".join(_source_card(s) for s in sources)
            st.markdown(cards_html, unsafe_allow_html=True)


def _show_chat() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Empty state — welcome + suggested questions
    if not st.session_state.messages:
        st.markdown(
            """
            <div style="text-align:center;padding:3rem 1rem 1.5rem">
                <div style="font-size:42px;margin-bottom:12px">💬</div>
                <h2 style="font-size:22px;font-weight:700;margin:0 0 8px;
                           letter-spacing:-0.02em">Policy Chat</h2>
                <p style="color:#64748b;font-size:14px;max-width:480px;
                          margin:0 auto;line-height:1.6">
                    Ask any question about cybersecurity policies.
                    Answers are grounded in authorised documents only
                    and include source citations.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p style="text-align:center;color:#475569;font-size:13px;'
            'font-weight:500;margin-bottom:10px">Suggested questions</p>',
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, q in enumerate(_SUGGESTED):
            with cols[i % 2]:
                if st.button(q, key=f"suggest_{i}", use_container_width=True):
                    st.session_state["_prefill"] = q
                    st.rerun()

    # Render conversation history
    for msg in st.session_state.messages:
        avatar = "👤" if msg["role"] == "user" else "🔒"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                _render_assistant_message(msg)

    # Handle suggested-question prefill
    prefill: str = st.session_state.get("_prefill") or ""
    if "_prefill" in st.session_state:
        del st.session_state["_prefill"]

    question = st.chat_input("Ask about cybersecurity policies...")
    active_question = question or prefill
    if not active_question:
        return

    # Append and display user message
    st.session_state.messages.append({"role": "user", "content": active_question})
    with st.chat_message("user", avatar="👤"):
        st.markdown(active_question)

    # Fetch and display assistant response
    with st.chat_message("assistant", avatar="🔒"):
        with st.spinner("Searching policy documents..."):
            result = _api.chat(active_question, st.session_state.token)

        if result is None:
            st.error("Cannot reach backend. Check it is running.")
            return

        if "detail" in result:
            detail = str(result.get("detail", "")).lower()
            if "not authenticated" in detail or "could not validate" in detail:
                st.warning("Session expired — signing out.")
                _logout()
            else:
                st.error(f"Error: {result['detail']}")
            return

        assistant_msg: dict[str, Any] = {
            "role":       "assistant",
            "content":    result.get("answer", ""),
            "confidence": result.get("confidence", "none"),
            "sources":    result.get("sources", []),
            "risk_flags": result.get("risk_flags", []),
        }
        _render_assistant_message(assistant_msg)

    st.session_state.messages.append(assistant_msg)


# ---------------------------------------------------------------------------
# Audit logs page
# ---------------------------------------------------------------------------


def _show_audit_logs() -> None:
    st.markdown(
        '<h2 style="font-size:22px;font-weight:700;margin:0 0 4px;'
        'letter-spacing:-0.02em">Audit Logs</h2>'
        '<p style="color:#64748b;font-size:14px;margin:0 0 1.5rem">'
        "Every chat request is logged. Visible to Security Analysts and Admins.</p>",
        unsafe_allow_html=True,
    )

    c_left, c_right = st.columns([8, 1])
    with c_right:
        if st.button("↻", use_container_width=True, help="Refresh logs"):
            st.rerun()

    logs = _api.get_audit_logs(st.session_state.token)

    if logs is None:
        st.error("Could not retrieve logs. Check backend connection or permissions.")
        return

    if not logs:
        st.info("No audit entries recorded yet.")
        return

    # Summary metrics
    total     = len(logs)
    answered  = sum(1 for lg in logs if lg.get("answer_status") == "answered")
    blocked   = sum(1 for lg in logs if lg.get("answer_status") == "blocked")
    no_source = sum(1 for lg in logs if lg.get("answer_status") == "no_source")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total requests", total)
    m2.metric("Answered",       answered)
    m3.metric("Blocked",        blocked)
    m4.metric("No source",      no_source)

    st.markdown("<br>", unsafe_allow_html=True)

    rows = []
    for log in logs:
        q = log.get("question") or ""
        rows.append(
            {
                "Username":       log.get("username", ""),
                "Role":           log.get("role", ""),
                "Question":       q[:90] + ("…" if len(q) > 90 else ""),
                "Status":         log.get("answer_status", ""),
                "Risk flags":     ", ".join(log.get("risk_flags") or []) or "—",
                "Documents used": ", ".join(log.get("documents_used") or []) or "—",
                "Timestamp":      log.get("created_at", ""),
            }
        )

    st.dataframe(rows, use_container_width=True, height=420)


# ---------------------------------------------------------------------------
# Admin upload placeholder
# ---------------------------------------------------------------------------


_SENSITIVITY_LEVELS = ["public", "internal", "confidential", "restricted"]
_ALL_ROLES = ["user", "security_analyst", "admin"]
_SENSITIVITY_DEFAULT_ROLES: dict[str, list[str]] = {
    "public":       ["user", "security_analyst", "admin"],
    "internal":     ["user", "security_analyst", "admin"],
    "confidential": ["security_analyst", "admin"],
    "restricted":   ["admin"],
}


def _show_admin_upload() -> None:
    st.markdown(
        '<h2 style="font-size:22px;font-weight:700;margin:0 0 4px;'
        'letter-spacing:-0.02em">Document Upload</h2>'
        '<p style="color:#64748b;font-size:14px;margin:0 0 1.5rem">'
        "Admin-only. Upload policy documents for automatic chunking and indexing.</p>",
        unsafe_allow_html=True,
    )

    with st.form("upload_form", clear_on_submit=True):
        uploaded_file = st.file_uploader(
            "Policy document",
            type=["md", "txt", "pdf"],
            help="Supported formats: .md, .txt, .pdf — maximum 5 MB",
        )

        title = st.text_input(
            "Document title",
            placeholder="Password Policy",
            help="Leave blank to use the filename as the title.",
        )

        sensitivity_level = st.selectbox(
            "Sensitivity level",
            options=_SENSITIVITY_LEVELS,
            index=1,  # default: internal
        )

        default_roles = _SENSITIVITY_DEFAULT_ROLES.get(sensitivity_level or "internal", _ALL_ROLES)
        allowed_roles = st.multiselect(
            "Allowed roles",
            options=_ALL_ROLES,
            default=default_roles,
            help="Roles that may retrieve this document in chat.",
        )

        submitted = st.form_submit_button("Upload & index", type="primary")

    if not submitted:
        return

    if uploaded_file is None:
        st.error("Select a file to upload.")
        return

    if not allowed_roles:
        st.error("Select at least one allowed role.")
        return

    file_bytes = uploaded_file.read()
    allowed_roles_str = ",".join(allowed_roles)

    with st.spinner("Uploading and indexing document..."):
        result = _api.upload_document(
            file_bytes=file_bytes,
            filename=uploaded_file.name,
            title=title or "",
            sensitivity_level=sensitivity_level or "internal",
            allowed_roles=allowed_roles_str,
            token=st.session_state.token,
        )

    if result is None:
        st.error("Cannot reach the backend. Check it is running.")
        return

    if "detail" in result:
        st.error(f"Upload failed: {result['detail']}")
        return

    st.success(result.get("message", "Document uploaded successfully."))
    st.markdown(
        f"**ID:** {result.get('id')}  \n"
        f"**File:** `{result.get('filename')}`  \n"
        f"**Sensitivity:** `{result.get('sensitivity_level')}`  \n"
        f"**Chunks indexed:** {result.get('chunk_count')}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title="CyberPolicy-RAG",
        page_icon="🔒",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _init_state()

    if not _is_logged_in():
        _show_login()
        return

    _inject_css()
    _show_sidebar()

    page = st.session_state.get("page", "Chat")
    role = st.session_state.role or ""

    # Role-based guard (belt-and-suspenders — backend also enforces)
    if page == "Audit Logs" and role not in ("security_analyst", "admin"):
        page = "Chat"
    if page == "Admin Upload" and role != "admin":
        page = "Chat"

    if page == "Chat":
        _show_chat()
    elif page == "Audit Logs":
        _show_audit_logs()
    elif page == "Admin Upload":
        _show_admin_upload()


if __name__ == "__main__":
    main()
