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

    if re.search(r"how\s+often|how\s+frequent", question_lower) and "access" in question_lower:
        match = re.search(
            r"access\s+must\s+be\s+reviewed\s+at\s+least\s+every\s+(\d+\s+days)",
            context,
            flags=re.IGNORECASE,
        )
        if match:
            return f"At least every {match.group(1)}."

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

    # "Can X data include Y?" — check negative list
    can_include_m = re.search(
        r"can\s+(?:public|internal|confidential|restricted)\s+data\s+include\s+(.+?)[\?.]?$",
        question_lower,
    )
    if can_include_m:
        level_m = re.search(
            r"can\s+(public|internal|confidential|restricted)\s+data\s+include",
            question_lower,
        )
        orig_m = re.search(
            r"can\s+(?:public|internal|confidential|restricted)\s+data\s+include\s+(.+?)[\?.]?$",
            question,
            re.IGNORECASE,
        )
        if level_m and orig_m:
            level_cap = level_m.group(1).capitalize()
            item_lower = can_include_m.group(1).strip()
            item_display = orig_m.group(1).strip()
            if re.search(
                rf"must\s+not\s+include[^.]*?{re.escape(item_lower)}",
                _preprocess_context(context),
                re.IGNORECASE | re.DOTALL,
            ):
                return f"No. {level_cap} data must not include {item_display}."

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
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        score = sum(1 for kw in keywords if kw in candidate.lower())
        if score:
            scored.append((score, candidate))

    if not scored:
        return None

    # Higher score first; for equal scores prefer longer (more complete answer)
    scored.sort(key=lambda item: (-item[0], -len(item[1])))
    best_score, best_candidate = scored[0]
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
    preprocessed = _preprocess_context(context)
    candidates: list[str] = []

    paras = [p.strip() for p in re.split(r"\n\s*\n", preprocessed) if p.strip()]

    # Bi-paragraph combined candidates (captures multi-sentence definitions)
    for i in range(len(paras) - 1):
        p1, p2 = paras[i], paras[i + 1]
        if re.match(r"^\s*[-*•]", p1) or re.match(r"^\s*[-*•]", p2):
            continue
        c1, c2 = _clean_text(p1), _clean_text(p2)
        if (
            c1
            and c2
            and len(c1.split()) >= 5
            and not _is_low_value_line(c1)
            and not _is_low_value_line(c2)
        ):
            combined = f"{c1} {c2}"
            if len(combined.split()) >= 8 and len(combined) <= 500:
                candidates.append(combined)

    # Line-level candidates
    for line in preprocessed.splitlines():
        cleaned = _clean_text(line)
        if cleaned and not _is_low_value_line(cleaned) and len(cleaned.split()) >= 5 and len(cleaned) <= 260:
            candidates.append(cleaned)

    # Sentence-level candidates — split per paragraph to avoid heading+sentence gluing
    for para in paras:
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            cleaned = _clean_text(sentence)
            if cleaned and not _is_low_value_line(cleaned) and len(cleaned.split()) >= 5 and len(cleaned) <= 260:
                candidates.append(cleaned)

    return candidates


def _preprocess_context(context: str) -> str:
    """Strip heading markers and expand 'intro:\n\n- item' blocks into sentences."""
    # Strip ## heading markers to plain text
    lines = []
    for line in context.split("\n"):
        m = re.match(r"^#{1,6}\s+(.+)$", line.rstrip())
        lines.append(m.group(1) if m else line)
    text = "\n".join(lines)

    # Expand colon+list blocks: "Foo may be stored in:\n\n- A\n- B" → "Foo may be stored in a, b."
    def _join_list(m: re.Match) -> str:
        intro = m.group(1).strip().rstrip(":")
        items = re.findall(r"^\s*[-*•]\s*(.+)", m.group(2), re.MULTILINE)
        clean_items = []
        for item in items:
            item = item.strip().replace("**", "").replace("`", "").rstrip(".")
            if item:
                clean_items.append(item[0].lower() + item[1:])
        if not clean_items:
            return m.group(0)
        if len(clean_items) == 1:
            joined = clean_items[0]
        elif len(clean_items) == 2:
            joined = f"{clean_items[0]} and {clean_items[1]}"
        else:
            joined = ", ".join(clean_items[:-1]) + ", and " + clean_items[-1]
        return f"{intro} {joined}."

    text = re.sub(
        r"([^\n]+:)\s*\n+\s*((?:\s*[-*•][^\n]+\n?)+)",
        _join_list,
        text,
    )
    return text


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
