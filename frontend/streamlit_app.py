"""Frontend entry-point shim — opens the FastAPI-served HTML UI."""

from __future__ import annotations

import webbrowser

import streamlit as st

URL = "http://localhost:8000"

st.set_page_config(page_title="CyberPolicy-RAG", page_icon="🛡️")
st.title("🛡️ CyberPolicy-RAG")
st.info(
    f"The frontend is now served by FastAPI at **{URL}**\n\n"
    "Make sure `uvicorn backend.app.main:app --reload` is running, "
    "then open the link below."
)
st.link_button("Open CyberPolicy-RAG →", URL, use_container_width=True)

if st.button("Auto-open in browser"):
    webbrowser.open(URL)
