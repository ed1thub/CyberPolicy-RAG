"""LLM provider abstraction with a mock default for local development."""

import re
from collections.abc import Sequence
from typing import Protocol

from backend.app.config import settings

NO_SOURCE_ANSWER = (
    "I could not find this information in the authorised policy documents."
)
POLICY_NOT_SPECIFIED_ANSWER = "The policy does not specify this."
POLICY_ASSISTANT_SYSTEM_PROMPT = (
    "You are a cybersecurity policy assistant. Use only the uploaded policy "
    "documents to answer user questions. Answer in a short, direct, and "
    "specific way. Do not include unrelated policy details. Prefer 1-3 "
    "sentences. If the policy lists multiple items, summarise only the "
    "relevant items briefly. If the answer is not found in the policy context, "
    "say: 'The policy does not specify this.'"
)

_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "can",
    "do",
    "does",
    "document",
    "employees",
    "for",
    "how",
    "if",
    "in",
    "is",
    "it",
    "must",
    "of",
    "policy",
    "quickly",
    "required",
    "should",
    "the",
    "they",
    "this",
    "to",
    "users",
    "what",
    "when",
    "which",
    "with",
}


class LLMProvider(Protocol):
    """Minimal interface accepted by RagService."""

    def generate(self, question: str, context_chunks: Sequence[str]) -> str:
        """Generate an answer given a question and retrieved context chunks."""
        ...


class MockLLM:
    """
    Default LLM for local development.

    Extracts a concise answer from retrieved policy context without calling any
    external API. This allows the full RAG pipeline to run in tests and local
    dev without an OpenAI key or a running Ollama instance.
    """

    def __init__(
        self,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        self.system_prompt = POLICY_ASSISTANT_SYSTEM_PROMPT
        self.max_output_tokens = max_output_tokens or settings.llm_max_output_tokens
        self.temperature = (
            temperature if temperature is not None else settings.llm_temperature
        )

    def generate(self, question: str, context_chunks: Sequence[str]) -> str:
        if not context_chunks:
            return NO_SOURCE_ANSWER

        combined_context = "\n\n".join(context_chunks)
        answer = _answer_known_policy_question(question, combined_context)
        if answer is None:
            answer = _extract_relevant_answer(question, combined_context)
        if answer is None:
            return POLICY_NOT_SPECIFIED_ANSWER
        return _limit_answer(answer, self.max_output_tokens)


def _answer_known_policy_question(question: str, context: str) -> str | None:
    """Return concise answers for common policy facts in the local demo corpus."""
    question_lower = question.lower()

    if "password" in question_lower and any(
        term in question_lower for term in ("length", "characters", "long")
    ):
        match = re.search(
            r"(?:be\s+)?at\s+least\s+(\d+)\s+characters(?:\s+long)?",
            context,
            flags=re.IGNORECASE,
        ) or re.search(
            r"minimum\s+length\s+(?:of\s+)?(\d+)\s+characters",
            context,
            flags=re.IGNORECASE,
        )
        if match:
            return f"Passwords must be at least {match.group(1)} characters long."

    if "sensitivity level" in question_lower or "classification" in question_lower:
        for pattern in (
            r"\*\*Classification:\*\*\s*([^\n\r]+)",
            r"\bClassification:\s*([^\n\r]+)",
            r"\bsensitivity[_\s-]*level:\s*([^\n\r]+)",
        ):
            match = re.search(pattern, context, flags=re.IGNORECASE)
            if match:
                return _ensure_period(_clean_text(match.group(1)))

    if (
        "critical" in question_lower
        and "vulnerab" in question_lower
        and any(term in question_lower for term in ("fix", "remediat", "resolved"))
    ):
        match = re.search(
            r"\|\s*Critical\s*\|\s*Within\s+(\d+)\s+days\s*\|",
            context,
            flags=re.IGNORECASE,
        ) or re.search(
            r"critical\s+vulnerabilities?.{0,80}?within\s+(\d+)\s+days",
            context,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match:
            return (
                f"Critical vulnerabilities must be remediated within "
                f"{match.group(1)} days."
            )

    if "phishing" in question_lower and any(
        term in question_lower for term in ("email", "report", "receive")
    ):
        if re.search(
            r"report\s+suspected\s+phishing\s+emails?\s+to\s+the\s+IT\s+or\s+Security\s+Team\s+immediately",
            context,
            flags=re.IGNORECASE,
        ):
            return "They must report it to the IT or Security Team immediately."

    if (
        ("public ai" in question_lower or "ai tools" in question_lower)
        and any(term in question_lower for term in ("restricted", "confidential"))
    ):
        if re.search(
            r"must\s+not\s+enter\s+.*?\bconfidential\b.*?\brestricted\b.*?public\s+AI\s+tools\s+unless\s+approved",
            context,
            flags=re.IGNORECASE | re.DOTALL,
        ) or re.search(
            r"must\s+not\s+enter\s+.*?\brestricted\b.*?\bconfidential\b.*?public\s+AI\s+tools\s+unless\s+approved",
            context,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return (
                "No. Users must not enter restricted or confidential information "
                "into public AI tools unless approved."
            )

    return None


def _extract_relevant_answer(question: str, context: str) -> str | None:
    keywords = _question_keywords(question)
    if not keywords:
        return None

    candidates = _context_candidates(context)
    scored_candidates: list[tuple[int, str]] = []
    for candidate in candidates:
        candidate_lower = candidate.lower()
        score = sum(1 for keyword in keywords if keyword in candidate_lower)
        if score:
            scored_candidates.append((score, candidate))

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda item: (-item[0], len(item[1])))
    best_score, best_candidate = scored_candidates[0]
    minimum_score = 1 if len(keywords) <= 2 else 2
    if best_score < minimum_score:
        return None
    return _ensure_period(best_candidate)


def _question_keywords(question: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    keywords = {word for word in words if len(word) > 2 and word not in _STOP_WORDS}
    if "mfa" in keywords:
        keywords.update({"multi", "factor", "authentication"})
    return keywords


def _context_candidates(context: str) -> list[str]:
    candidates: list[str] = []
    for line in context.splitlines():
        cleaned = _clean_text(line)
        if not cleaned or _is_low_value_line(cleaned):
            continue
        if len(cleaned) <= 260:
            candidates.append(cleaned)

    sentences = re.split(r"(?<=[.!?])\s+", _clean_text(context))
    for sentence in sentences:
        cleaned = _clean_text(sentence)
        if cleaned and len(cleaned) <= 260 and not _is_low_value_line(cleaned):
            candidates.append(cleaned)

    return candidates


def _clean_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[*\-\d.\s]+", "", cleaned)
    cleaned = cleaned.replace("**", "").replace("`", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" |")
    if "|" in cleaned:
        cells = [cell.strip() for cell in cleaned.split("|") if cell.strip()]
        cleaned = " ".join(cells)
    return cleaned.strip()


def _is_low_value_line(text: str) -> bool:
    lower = text.lower()
    return (
        lower.startswith("#")
        or lower.startswith("version:")
        or lower.startswith("effective date:")
        or lower.startswith("review date:")
        or lower.startswith("owner:")
        or set(text) <= {"-", ":", " "}
    )


def _ensure_period(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    return stripped if stripped[-1] in ".?!" else f"{stripped}."


def _limit_answer(answer: str, max_output_tokens: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    concise = " ".join(sentence for sentence in sentences[:3] if sentence).strip()
    words = concise.split()
    if len(words) <= max_output_tokens:
        return concise
    return _ensure_period(" ".join(words[:max_output_tokens]).rstrip(",;:"))
