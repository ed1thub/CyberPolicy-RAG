"""Tests for the Streamlit redirect shim that replaces the old frontend."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"
TARGET_URL = "http://localhost:8000"


def test_shim_renders_without_exceptions() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    assert len(at.exception) == 0


def test_shim_shows_redirect_button() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    button_labels = [b.label for b in at.button]
    assert "Auto-open in browser" in button_labels


def test_shim_info_contains_target_url() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=10)
    at.run()
    info_values = [i.value for i in at.info]
    assert any(TARGET_URL in v for v in info_values)
