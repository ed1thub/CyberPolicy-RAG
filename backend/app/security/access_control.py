"""Deterministic role-based access control for policy documents."""

VALID_SENSITIVITY_LEVELS = frozenset(
    {"public", "internal", "confidential", "restricted"}
)

_ROLE_SENSITIVITY_LEVELS = {
    "user": ("public", "internal"),
    "security_analyst": ("public", "internal", "confidential"),
    "admin": ("public", "internal", "confidential", "restricted"),
}


def get_allowed_sensitivity_levels(role: str) -> list[str]:
    """Return the sensitivity levels allowed for a role, denying unknown roles."""
    return list(_ROLE_SENSITIVITY_LEVELS.get(role, ()))


def can_access_document(role: str, sensitivity_level: str) -> bool:
    """Return whether a role may access a valid document sensitivity level."""
    if sensitivity_level not in VALID_SENSITIVITY_LEVELS:
        return False
    return sensitivity_level in _ROLE_SENSITIVITY_LEVELS.get(role, ())
