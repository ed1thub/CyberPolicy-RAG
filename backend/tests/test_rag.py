"""Tests for T08: RAG service security, citations, and response structure."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.app.documents.chunker import DocumentChunk
from backend.app.rag.llm_adapter import NO_SOURCE_ANSWER, MockLLM
from backend.app.rag.rag_service import RagService
from backend.app.rag.vector_store import VectorStore


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class KeywordEmbeddings:
    """Deterministic embeddings keyed on fixed keywords — no model download needed."""

    _KEYWORDS = ("password", "incident", "restricted", "general")

    def _embed(self, text: str) -> list[float]:
        lower = text.lower()
        values = [float(lower.count(kw)) for kw in self._KEYWORDS]
        if not any(values):
            values[-1] = 1.0
        return values

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class SpyLLM:
    """Records every generate() call so tests can verify LLM is not called when it shouldn't be."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def generate(self, question: str, context_chunks: Sequence[str]) -> str:
        self.calls.append((question, list(context_chunks)))
        return f"SpyLLM answer for: {question}"

    @property
    def call_count(self) -> int:
        return len(self.calls)


def make_chunk(
    chunk_id: str,
    text: str,
    sensitivity_level: str,
    allowed_roles: str,
    section: str = "Security Requirements",
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        text=text,
        document_title=f"{sensitivity_level.title()} Policy",
        filename=f"{sensitivity_level}_policy.md",
        sensitivity_level=sensitivity_level,
        allowed_roles=allowed_roles,
        section_heading=section,
        page=None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_store(tmp_path: Path) -> VectorStore:
    """Vector store with one chunk at each sensitivity level."""
    store = VectorStore(
        chroma_path=tmp_path / "chroma",
        embedding_provider=KeywordEmbeddings(),
    )
    store.add_chunks(
        [
            make_chunk(
                "public_001",
                "General acceptable use requirements apply to all staff.",
                "public",
                "user,security_analyst,admin",
            ),
            make_chunk(
                "internal_001",
                "Password accounts require multi-factor authentication.",
                "internal",
                "user,security_analyst,admin",
            ),
            make_chunk(
                "confidential_001",
                "Incident responders must preserve breach evidence and contain the incident.",
                "confidential",
                "security_analyst,admin",
            ),
            make_chunk(
                "restricted_001",
                "Restricted administrator recovery procedures are classified.",
                "restricted",
                "admin",
            ),
        ]
    )
    return store


@pytest.fixture
def rag_service(seeded_store: VectorStore) -> RagService:
    return RagService(vector_store=seeded_store, llm=MockLLM())


# ---------------------------------------------------------------------------
# MockLLM unit tests
# ---------------------------------------------------------------------------


def test_mock_llm_returns_no_source_answer_for_empty_context() -> None:
    llm = MockLLM()
    result = llm.generate("What is the policy?", [])
    assert result == NO_SOURCE_ANSWER


def test_mock_llm_includes_context_in_answer() -> None:
    llm = MockLLM()
    result = llm.generate("What is the policy?", ["chunk one", "chunk two"])
    assert "chunk one" in result
    assert "chunk two" in result


# ---------------------------------------------------------------------------
# User role: can access public and internal
# ---------------------------------------------------------------------------


def test_user_gets_answer_for_public_content(rag_service: RagService) -> None:
    response = rag_service.answer("general acceptable use requirements", "user")
    assert response.answer != NO_SOURCE_ANSWER
    assert len(response.sources) > 0


def test_user_gets_answer_for_internal_content(rag_service: RagService) -> None:
    response = rag_service.answer("password multi-factor authentication", "user")
    assert response.answer != NO_SOURCE_ANSWER
    assert len(response.sources) > 0


def test_user_sources_never_include_confidential_chunks(rag_service: RagService) -> None:
    """Even when asking about confidential topics, returned sources stay public/internal."""
    response = rag_service.answer("incident breach evidence", "user")
    for source in response.sources:
        assert source.filename not in {"confidential_policy.md", "restricted_policy.md"}, (
            f"User received an unauthorised source: {source.filename}"
        )


def test_user_sources_never_include_restricted_chunks(rag_service: RagService) -> None:
    response = rag_service.answer("restricted administrator recovery", "user")
    for source in response.sources:
        assert source.filename != "restricted_policy.md", (
            f"User received a restricted source: {source.filename}"
        )


# ---------------------------------------------------------------------------
# Security analyst role: can access confidential, not restricted
# ---------------------------------------------------------------------------


def test_security_analyst_can_access_confidential_content(
    rag_service: RagService,
) -> None:
    response = rag_service.answer("incident breach evidence", "security_analyst")
    assert response.answer != NO_SOURCE_ANSWER
    assert len(response.sources) > 0


def test_security_analyst_sources_never_include_restricted_chunks(
    rag_service: RagService,
) -> None:
    response = rag_service.answer("restricted administrator recovery", "security_analyst")
    for source in response.sources:
        assert source.filename != "restricted_policy.md", (
            f"security_analyst received a restricted source: {source.filename}"
        )


# ---------------------------------------------------------------------------
# Admin role: can access all levels
# ---------------------------------------------------------------------------


def test_admin_can_access_restricted_content(rag_service: RagService) -> None:
    response = rag_service.answer("restricted administrator recovery", "admin")
    assert response.answer != NO_SOURCE_ANSWER
    assert len(response.sources) > 0


def test_admin_can_access_confidential_content(rag_service: RagService) -> None:
    response = rag_service.answer("incident breach evidence", "admin")
    assert response.answer != NO_SOURCE_ANSWER
    assert len(response.sources) > 0


# ---------------------------------------------------------------------------
# Unknown role: denied entirely
# ---------------------------------------------------------------------------


def test_unknown_role_returns_no_source_response(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "unknown_role")
    assert response.answer == NO_SOURCE_ANSWER
    assert response.sources == []
    assert response.confidence == "none"


def test_guest_role_returns_no_source_response(rag_service: RagService) -> None:
    response = rag_service.answer("general policy", "guest")
    assert response.answer == NO_SOURCE_ANSWER
    assert response.confidence == "none"


# ---------------------------------------------------------------------------
# No matching content
# ---------------------------------------------------------------------------


def test_empty_store_returns_no_source_response() -> None:
    import chromadb

    empty_store = VectorStore(
        chroma_path=None,
        embedding_provider=KeywordEmbeddings(),
        client=chromadb.EphemeralClient(),
    )
    service = RagService(vector_store=empty_store, llm=MockLLM())
    response = service.answer("quantum computing policy", "admin")
    assert response.answer == NO_SOURCE_ANSWER
    assert response.sources == []
    assert response.confidence == "none"


# ---------------------------------------------------------------------------
# Security invariant: LLM is never called for unauthorised requests
# ---------------------------------------------------------------------------


def test_llm_not_called_for_unknown_role(seeded_store: VectorStore) -> None:
    spy = SpyLLM()
    service = RagService(vector_store=seeded_store, llm=spy)
    service.answer("password requirements", "unknown_role")
    assert spy.call_count == 0


def test_llm_not_called_when_store_is_empty() -> None:
    import chromadb

    empty_store = VectorStore(
        chroma_path=None,
        embedding_provider=KeywordEmbeddings(),
        client=chromadb.EphemeralClient(),
    )
    spy = SpyLLM()
    service = RagService(vector_store=empty_store, llm=spy)
    service.answer("any policy question", "admin")
    assert spy.call_count == 0


def test_llm_receives_only_authorised_context(seeded_store: VectorStore) -> None:
    spy = SpyLLM()
    service = RagService(vector_store=seeded_store, llm=spy)
    # User can only see public + internal
    service.answer("general password requirements", "user")
    assert spy.call_count == 1
    _, context_chunks = spy.calls[0]
    combined = " ".join(context_chunks).lower()
    assert "incident" not in combined
    assert "restricted administrator" not in combined


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


def test_response_has_answer_field(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert isinstance(response.answer, str)
    assert len(response.answer) > 0


def test_response_has_sources_list(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert isinstance(response.sources, list)


def test_response_has_risk_flags_list(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert isinstance(response.risk_flags, list)


def test_response_has_valid_confidence_value(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert response.confidence in {"high", "medium", "low", "none", "blocked"}


def test_sources_have_required_fields(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert len(response.sources) > 0
    for source in response.sources:
        assert hasattr(source, "document_title")
        assert hasattr(source, "filename")
        assert hasattr(source, "section_heading")
        assert hasattr(source, "page")


def test_answer_with_sources_has_confidence_high(rag_service: RagService) -> None:
    response = rag_service.answer("password requirements", "user")
    assert len(response.sources) > 0
    assert response.confidence == "high"


def test_no_source_response_has_confidence_none() -> None:
    import chromadb

    empty_store = VectorStore(
        chroma_path=None,
        embedding_provider=KeywordEmbeddings(),
        client=chromadb.EphemeralClient(),
    )
    service = RagService(vector_store=empty_store, llm=MockLLM())
    response = service.answer("any question", "admin")
    assert response.confidence == "none"


def test_sources_deduplicated_per_document_section(tmp_path: Path) -> None:
    """Two chunks from the same document and section produce one citation."""
    store = VectorStore(
        chroma_path=tmp_path / "chroma",
        embedding_provider=KeywordEmbeddings(),
    )
    store.add_chunks(
        [
            make_chunk(
                "pwd_001",
                "Password policy chunk one about passwords.",
                "internal",
                "user,security_analyst,admin",
                "Password Requirements",
            ),
            make_chunk(
                "pwd_002",
                "Password policy chunk two about passwords.",
                "internal",
                "user,security_analyst,admin",
                "Password Requirements",
            ),
        ]
    )
    service = RagService(vector_store=store, llm=MockLLM())
    response = service.answer("password requirements", "user")
    citation_keys = [
        (s.document_title, s.filename, s.section_heading) for s in response.sources
    ]
    assert len(citation_keys) == len(set(citation_keys)), "Duplicate citations found"
