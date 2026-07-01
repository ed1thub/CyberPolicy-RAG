"""Tests for T08: RAG service security, citations, and response structure."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.app.documents.chunker import DocumentChunk
from backend.app.rag.llm_adapter import (
    NO_SOURCE_ANSWER,
    POLICY_ASSISTANT_SYSTEM_PROMPT,
    POLICY_NOT_SPECIFIED_ANSWER,
    MockLLM,
)
from backend.app.rag.retriever import Retriever
from backend.app.rag.rag_service import RagService
from backend.app.rag.vector_store import SearchResult, VectorStore


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


class PolicyExampleEmbeddings:
    """Deterministic embeddings for concise-answer regression examples."""

    _KEYWORDS = (
        "password",
        "sensitivity",
        "classification",
        "critical",
        "vulnerabilities",
        "phishing",
        "email",
        "restricted",
        "confidential",
        "public",
        "ai",
        "tools",
        "general",
    )

    def _embed(self, text: str) -> list[float]:
        lower = text.lower()
        values = [float(lower.count(keyword)) for keyword in self._KEYWORDS]
        if not any(values):
            values[-1] = 1.0
        return values

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

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


class OrderedResultStore:
    """Return results in a fixed bad order so retriever reranking is testable."""

    def __init__(self, results: list[SearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, list[str], int]] = []

    def search(
        self,
        query: str,
        allowed_sensitivity_levels: list[str],
        top_k: int = 5,
    ) -> list[SearchResult]:
        self.calls.append((query, list(allowed_sensitivity_levels), top_k))
        return self.results[:top_k]


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


@pytest.fixture
def policy_example_service(tmp_path: Path) -> RagService:
    store = VectorStore(
        chroma_path=tmp_path / "examples-chroma",
        embedding_provider=PolicyExampleEmbeddings(),
    )
    store.add_chunks(
        [
            make_chunk(
                "novacore_password_001",
                "## Password Requirements\n\nPasswords must:\n\n"
                "* Be at least 12 characters long.\n"
                "* Contain uppercase letters, lowercase letters, numbers, "
                "and symbols where supported.",
                "internal",
                "user,security_analyst,admin",
                "Password Requirements",
            ),
            make_chunk(
                "novacore_classification_001",
                "**Classification:** Internal Use Only\n\n"
                "Document sensitivity level for this policy.",
                "internal",
                "user,security_analyst,admin",
                "Document Control",
            ),
            make_chunk(
                "novacore_vuln_001",
                "## Vulnerability Management Policy\n\n"
                "| Severity | Required Remediation Time |\n"
                "| -------- | ------------------------: |\n"
                "| Critical | Within 7 days |\n"
                "| High | Within 14 days |",
                "internal",
                "user,security_analyst,admin",
                "Remediation Timeframes",
            ),
            make_chunk(
                "novacore_phishing_001",
                "## Email and Phishing Security Policy\n\n"
                "Users must report suspected phishing emails to the IT or "
                "Security Team immediately.",
                "internal",
                "user,security_analyst,admin",
                "Email and Phishing Security Policy",
            ),
            make_chunk(
                "novacore_ai_001",
                "## Artificial Intelligence and Automated Tools Policy\n\n"
                "Users must not enter confidential, restricted, customer, "
                "employee, legal, financial, source code, or security-sensitive "
                "information into public AI tools unless approved.",
                "internal",
                "user,security_analyst,admin",
                "Artificial Intelligence and Automated Tools Policy",
            ),
        ]
    )
    return RagService(vector_store=store, llm=MockLLM())


# ---------------------------------------------------------------------------
# MockLLM unit tests
# ---------------------------------------------------------------------------


def test_mock_llm_returns_no_source_answer_for_empty_context() -> None:
    llm = MockLLM()
    result = llm.generate("What is the policy?", [])
    assert result == NO_SOURCE_ANSWER


def test_mock_llm_uses_concise_policy_assistant_prompt() -> None:
    llm = MockLLM()

    assert llm.system_prompt == POLICY_ASSISTANT_SYSTEM_PROMPT
    assert "Answer in a short, direct, and specific way" in llm.system_prompt
    assert "Prefer 1-3 sentences" in llm.system_prompt


def test_mock_llm_returns_concise_context_answer() -> None:
    llm = MockLLM()
    result = llm.generate(
        "What is the required password length?",
        ["Passwords must be at least 12 characters long. Extra details apply."],
    )

    assert result == "Passwords must be at least 12 characters long."


def test_mock_llm_returns_policy_not_specified_for_irrelevant_context() -> None:
    llm = MockLLM()
    result = llm.generate(
        "What is the quantum computing policy?",
        ["Passwords must be at least 12 characters long."],
    )

    assert result == POLICY_NOT_SPECIFIED_ANSWER


def test_rag_policy_not_specified_has_no_sources_or_confidence(
    seeded_store: VectorStore,
) -> None:
    service = RagService(vector_store=seeded_store, llm=MockLLM())

    response = service.answer("What is the quantum computing policy?", "user")

    assert response.answer == POLICY_NOT_SPECIFIED_ANSWER
    assert response.sources == []
    assert response.confidence == "none"


def test_retriever_oversamples_then_reranks_by_question_terms() -> None:
    irrelevant = SearchResult(
        chunk_id="general_001",
        text="General acceptable use requirements apply to all staff.",
        metadata={"sensitivity_level": "internal"},
        distance=0.1,
    )
    relevant = SearchResult(
        chunk_id="password_001",
        text="Passwords must be at least 12 characters long.",
        metadata={
            "sensitivity_level": "internal",
            "section_heading": "Password Requirements",
        },
        distance=0.9,
    )
    store = OrderedResultStore(
        [
            irrelevant,
            relevant,
            SearchResult(
                chunk_id="other_001",
                text="Email accounts must use MFA.",
                metadata={"sensitivity_level": "internal"},
                distance=0.2,
            ),
            SearchResult(
                chunk_id="other_002",
                text="Backups must be tested monthly.",
                metadata={"sensitivity_level": "internal"},
                distance=0.3,
            ),
        ]
    )
    retriever = Retriever(store)  # type: ignore[arg-type]

    results = retriever.retrieve_for_role(
        "What is the required password length?",
        "user",
        top_k=1,
    )

    assert store.calls[0][2] == 4
    assert [result.chunk_id for result in results] == ["password_001"]


@pytest.mark.parametrize(
    ("question", "expected_answer"),
    [
        (
            "What is the required password length?",
            "Passwords must be at least 12 characters long.",
        ),
        ("Which sensitivity level is this document?", "Internal."),
        (
            "How quickly must critical vulnerabilities be fixed?",
            "Critical vulnerabilities must be remediated within 7 days.",
        ),
        (
            "What should users do if they receive a suspicious phishing email?",
            "They must report it to the IT or Security Team immediately.",
        ),
        (
            "Can employees upload restricted data to public AI tools?",
            "No. Users must not enter restricted or confidential information "
            "into public AI tools unless approved.",
        ),
    ],
)
def test_rag_answers_policy_examples_concisely(
    policy_example_service: RagService,
    question: str,
    expected_answer: str,
) -> None:
    response = policy_example_service.answer(question, "user")

    assert response.answer == expected_answer
    assert response.confidence == "high"
    assert response.sources
    assert len(response.answer.split()) <= 20


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


# ---------------------------------------------------------------------------
# Routing accuracy: 7 production-scenario tests
# ---------------------------------------------------------------------------

_INTERNAL_DEFINITION_TEXT = (
    "3. Definition of Internal Data\n\n"
    "Internal data is information intended only for use inside the organisation.\n\n"
    "It may be shared with authorised employees and approved contractors, "
    "but it must not be published publicly without approval."
)

_CONFIDENTIAL_ACCESS_TEXT = (
    "6. Access Control Requirements\n\n"
    "Access to Confidential data must follow least privilege.\n\n"
    "Requirements include:\n\n"
    "- Access must be approved by the data owner.\n"
    "- Access must be reviewed at least every 90 days.\n"
    "- Multi-factor authentication must be used where available.\n"
    "- Shared accounts must not be used.\n"
    "- Access must be removed immediately when no longer needed.\n"
    "- Privileged access must be logged and reviewed."
)

_RESTRICTED_ACCESS_TEXT = (
    "6. Access Control Requirements\n\n"
    "Access to Restricted data must follow strict least privilege.\n\n"
    "Requirements include:\n\n"
    "- Access must be approved by the data owner and Security Team.\n"
    "- Multi-factor authentication is mandatory.\n"
    "- Access must be reviewed at least every 30 days.\n"
    "- Emergency access must be logged and reviewed.\n"
    "- Access must be removed immediately when no longer required."
)

_CONFIDENTIAL_EXAMPLES_TEXT = (
    "4. Examples of Confidential Data\n\n"
    "Examples include:\n\n"
    "- Customer names and contact details.\n"
    "- Employee records.\n"
    "- Payroll information.\n"
    "- Business contracts.\n"
    "- Internal financial documents.\n"
    "- Source code.\n"
    "- Security architecture documents.\n"
    "- Internal audit reports.\n"
    "- Vendor security reviews.\n"
    "- Non-public product plans.\n"
    "- Legal correspondence.\n"
    "- Customer support records."
)

_RESTRICTED_EXAMPLES_TEXT = (
    "4. Examples of Restricted Data\n\n"
    "Examples include:\n\n"
    "- Passwords.\n"
    "- Multi-factor authentication recovery codes.\n"
    "- API keys.\n"
    "- Private encryption keys.\n"
    "- SSH private keys.\n"
    "- Database credentials.\n"
    "- Cloud administrator credentials.\n"
    "- Payment card data.\n"
    "- Highly sensitive personal information.\n"
    "- Security incident evidence.\n"
    "- Vulnerability exploit details.\n"
    "- Malware samples.\n"
    "- Legal investigation files.\n"
    "- Backup encryption keys.\n"
    "- Production environment secrets."
)

_PUBLIC_STORAGE_TEXT = (
    "7. Storage Requirements\n\n"
    "Public data may be stored in:\n\n"
    "- Public websites.\n"
    "- Approved content management systems.\n"
    "- Marketing platforms.\n"
    "- Public document repositories.\n"
    "- Official social media platforms.\n\n"
    "Even though Public data has low sensitivity, it must still be "
    "protected from unauthorised modification."
)

_PUBLIC_RULES_TEXT = (
    "5. Public Data Rules\n\n"
    "Public data may be:\n\n"
    "- Published on the company website.\n"
    "- Shared on official social media accounts.\n"
    "- Sent to customers or partners.\n\n"
    "Public data must not include:\n\n"
    "- Passwords.\n"
    "- API keys.\n"
    "- Private keys.\n"
    "- Customer records.\n"
    "- Employee personal records."
)


def _make_routing_chunk(
    chunk_id: str,
    text: str,
    sensitivity_level: str,
    allowed_roles: str,
    section_heading: str,
    document_title: str,
    filename: str,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        text=text,
        document_title=document_title,
        filename=filename,
        sensitivity_level=sensitivity_level,
        allowed_roles=allowed_roles,
        section_heading=section_heading,
        page=None,
    )


class RoutingEmbeddings:
    """Deterministic embeddings for routing tests — returns a stable nonzero vector."""

    def _embed(self, text: str) -> list[float]:
        words = text.lower().split()
        kw = [
            "definition", "examples", "storage", "access", "control",
            "rules", "api", "keys", "source", "code", "public", "restricted",
            "confidential", "internal", "password",
        ]
        vals = [float(words.count(k)) for k in kw]
        if not any(vals):
            vals[-1] = 1.0
        return vals

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.fixture
def routing_service(tmp_path: Path) -> RagService:
    store = VectorStore(
        chroma_path=tmp_path / "routing-chroma",
        embedding_provider=RoutingEmbeddings(),
    )
    chunks = [
        _make_routing_chunk(
            "internal_def_001", _INTERNAL_DEFINITION_TEXT, "internal",
            "user,security_analyst,admin",
            "3. Definition of Internal Data",
            "Internal Data Handling Policy", "internal-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "conf_access_001", _CONFIDENTIAL_ACCESS_TEXT, "confidential",
            "security_analyst,admin",
            "6. Access Control Requirements",
            "Confidential Data Handling Policy", "confidential-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "restr_access_001", _RESTRICTED_ACCESS_TEXT, "restricted",
            "admin",
            "6. Access Control Requirements",
            "Restricted Data Handling Policy", "restricted-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "conf_examples_001", _CONFIDENTIAL_EXAMPLES_TEXT, "confidential",
            "security_analyst,admin",
            "4. Examples of Confidential Data",
            "Confidential Data Handling Policy", "confidential-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "restr_examples_001", _RESTRICTED_EXAMPLES_TEXT, "restricted",
            "admin",
            "4. Examples of Restricted Data",
            "Restricted Data Handling Policy", "restricted-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "public_storage_001", _PUBLIC_STORAGE_TEXT, "public",
            "user,security_analyst,admin",
            "7. Storage Requirements",
            "Public Data Handling Policy", "public-data-handling-policy.md",
        ),
        _make_routing_chunk(
            "public_rules_001", _PUBLIC_RULES_TEXT, "public",
            "user,security_analyst,admin",
            "5. Public Data Rules",
            "Public Data Handling Policy", "public-data-handling-policy.md",
        ),
    ]
    store.add_chunks(chunks)
    return RagService(vector_store=store, llm=MockLLM())


def test_what_is_internal_data(routing_service: RagService) -> None:
    response = routing_service.answer("What is Internal data?", "user")
    assert response.answer == (
        "Internal data is information intended only for use inside the organisation."
    )
    assert response.confidence == "high"
    assert any("Definition" in (s.section_heading or "") for s in response.sources)


def test_confidential_access_review_frequency(routing_service: RagService) -> None:
    response = routing_service.answer(
        "How often must Confidential data access be reviewed?", "admin"
    )
    assert response.answer == (
        "Confidential data access must be reviewed at least every 90 days."
    )
    assert response.confidence == "high"
    assert any("Access Control" in (s.section_heading or "") for s in response.sources)


def test_restricted_access_review_frequency(routing_service: RagService) -> None:
    response = routing_service.answer(
        "How often must Restricted data access be reviewed?", "admin"
    )
    assert response.answer == (
        "Restricted data access must be reviewed at least every 30 days."
    )
    assert response.confidence == "high"
    assert any("Access Control" in (s.section_heading or "") for s in response.sources)


def test_source_code_sensitivity_level(routing_service: RagService) -> None:
    response = routing_service.answer("What sensitivity level is source code?", "admin")
    assert response.answer == "source code is Confidential."
    assert response.confidence == "high"
    assert any("Examples" in (s.section_heading or "") for s in response.sources)


def test_api_keys_sensitivity_level(routing_service: RagService) -> None:
    response = routing_service.answer("What sensitivity level are API keys?", "admin")
    assert response.answer == "API keys are Restricted."
    assert response.confidence == "high"
    assert any("Examples" in (s.section_heading or "") for s in response.sources)


def test_public_storage_locations(routing_service: RagService) -> None:
    response = routing_service.answer("Where can Public data be stored?", "user")
    assert response.answer == (
        "Public data may be stored in public websites, approved content management "
        "systems, marketing platforms, public document repositories, and official "
        "social media platforms."
    )
    assert response.confidence == "high"
    assert any("Storage" in (s.section_heading or "") for s in response.sources)


def test_can_public_data_include_api_keys(routing_service: RagService) -> None:
    response = routing_service.answer("Can Public data include API keys?", "user")
    assert response.answer == "No. Public data must not include API keys."
    assert response.confidence == "high"
    assert any("Public Data" in (s.section_heading or "") or "Rules" in (s.section_heading or "") for s in response.sources)


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
