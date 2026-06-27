"""Deterministic output guard for generated chat answers.

This guard is intentionally simple and rule-based. It is a final safety layer
that checks generated answers before they are returned to the user. It does not
replace authentication, RBAC, prompt guarding, or authorised retrieval.
"""

from dataclasses import dataclass, field
import re

BLOCKED_OUTPUT_ANSWER = (
    "The generated response was blocked because it may contain sensitive information."
)
UNSAFE_OUTPUT_FLAG = "unsafe_output_blocked"


@dataclass(frozen=True)
class OutputGuardResult:
    """Result of checking a generated answer."""

    allowed: bool
    answer: str
    risk_flags: list[str] = field(default_factory=list)
    confidence: str | None = None


_API_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bghp_[0-9A-Za-z_]{20,}\b"),
    re.compile(r"\bsk-[0-9A-Za-z][0-9A-Za-z_-]{16,}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
)

_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:api[_ -]?key|access[_ -]?token|secret[_ -]?key|client[_ -]?secret)"
    r"\s*[:=]\s*['\"]?[0-9A-Za-z_\-./+=]{12,}['\"]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_PASSWORD_LINE_PATTERN = re.compile(
    r"^\s*(?:password|passwd|pwd|passphrase|db_password|admin_password)"
    r"\s*[:=]\s*['\"]?\S.{5,}['\"]?\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_SYSTEM_OR_HIDDEN_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsystem prompt\s*:", re.IGNORECASE),
    re.compile(r"\bdeveloper message\s*:", re.IGNORECASE),
    re.compile(r"\bthe system instructions are\b", re.IGNORECASE),
    re.compile(r"\byou are chatgpt\b", re.IGNORECASE),
    re.compile(r"\byou are an ai assistant\b", re.IGNORECASE),
    re.compile(r"\bhidden instructions\s*:", re.IGNORECASE),
    re.compile(r"\binternal instructions\s*:", re.IGNORECASE),
    re.compile(r"\bconfidential instructions\s*:", re.IGNORECASE),
)

_DOCUMENT_DUMP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfull document dump\b", re.IGNORECASE),
    re.compile(r"\bentire document follows\b", re.IGNORECASE),
    re.compile(r"\bverbatim document\b", re.IGNORECASE),
    re.compile(r"\bcomplete document contents\b", re.IGNORECASE),
    re.compile(
        r"\b(?:begin|start) (?:full )?document\b.*\b(?:end|finish) "
        r"(?:full )?document\b",
        re.IGNORECASE | re.DOTALL,
    ),
)


def check_output(answer: str) -> OutputGuardResult:
    """Return a blocked result if a generated answer looks unsafe."""
    if _contains_unsafe_output(answer):
        return OutputGuardResult(
            allowed=False,
            answer=BLOCKED_OUTPUT_ANSWER,
            risk_flags=[UNSAFE_OUTPUT_FLAG],
            confidence="blocked",
        )

    return OutputGuardResult(allowed=True, answer=answer)


def _contains_unsafe_output(answer: str) -> bool:
    """Check for basic sensitive-output warning signs."""
    return (
        _contains_api_key_style_string(answer)
        or _SECRET_ASSIGNMENT_PATTERN.search(answer) is not None
        or _PASSWORD_LINE_PATTERN.search(answer) is not None
        or _matches_any(answer, _SYSTEM_OR_HIDDEN_LEAK_PATTERNS)
        or _matches_any(answer, _DOCUMENT_DUMP_PATTERNS)
    )


def _contains_api_key_style_string(answer: str) -> bool:
    """Detect common API-key/token shapes."""
    return _matches_any(answer, _API_KEY_PATTERNS)


def _matches_any(answer: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """Return True when any compiled pattern matches the answer."""
    return any(pattern.search(answer) for pattern in patterns)
