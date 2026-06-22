"""Tests for deterministic role-based document access control."""

import pytest

from backend.app.security.access_control import (
    can_access_document,
    get_allowed_sensitivity_levels,
)


def test_user_allowed_sensitivity_levels() -> None:
    assert get_allowed_sensitivity_levels("user") == ["public", "internal"]


@pytest.mark.parametrize("sensitivity_level", ["public", "internal"])
def test_user_can_access_public_and_internal(sensitivity_level: str) -> None:
    assert can_access_document("user", sensitivity_level) is True


@pytest.mark.parametrize("sensitivity_level", ["confidential", "restricted"])
def test_user_cannot_access_confidential_or_restricted(sensitivity_level: str) -> None:
    assert can_access_document("user", sensitivity_level) is False


def test_security_analyst_allowed_sensitivity_levels() -> None:
    assert get_allowed_sensitivity_levels("security_analyst") == [
        "public",
        "internal",
        "confidential",
    ]


@pytest.mark.parametrize(
    "sensitivity_level",
    ["public", "internal", "confidential"],
)
def test_security_analyst_can_access_allowed_levels(sensitivity_level: str) -> None:
    assert can_access_document("security_analyst", sensitivity_level) is True


def test_security_analyst_cannot_access_restricted() -> None:
    assert can_access_document("security_analyst", "restricted") is False


@pytest.mark.parametrize(
    "sensitivity_level",
    ["public", "internal", "confidential", "restricted"],
)
def test_admin_can_access_all_valid_levels(sensitivity_level: str) -> None:
    assert can_access_document("admin", sensitivity_level) is True


def test_unknown_role_gets_no_access() -> None:
    assert get_allowed_sensitivity_levels("unknown") == []
    assert can_access_document("unknown", "public") is False


@pytest.mark.parametrize("role", ["user", "security_analyst", "admin", "unknown"])
def test_unknown_sensitivity_level_is_denied(role: str) -> None:
    assert can_access_document(role, "top_secret") is False
