"""Tests for local embeddings and sensitivity-filtered ChromaDB retrieval."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from backend.app.documents.chunker import DocumentChunk
from backend.app.rag.embeddings import MODEL_NAME, SentenceTransformerEmbeddings
from backend.app.rag.vector_store import COLLECTION_NAME, VectorStore


class KeywordEmbeddings:
    """Deterministic local embeddings that require no model download."""

    keywords = ("password", "incident", "restricted", "general")

    def __init__(self) -> None:
        self.query_calls = 0

    def _embed(self, text: str) -> list[float]:
        lowered = text.lower()
        values = [float(lowered.count(keyword)) for keyword in self.keywords]
        if not any(values):
            values[-1] = 1.0
        return values

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._embed(text)


def make_chunk(
    chunk_id: str,
    text: str,
    sensitivity_level: str,
    allowed_roles: str,
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        text=text,
        document_title=f"{sensitivity_level.title()} Policy",
        filename=f"{sensitivity_level}_policy.md",
        sensitivity_level=sensitivity_level,
        allowed_roles=allowed_roles,
        section_heading="Security Requirements",
        page=None,
    )


@pytest.fixture
def embedding_provider() -> KeywordEmbeddings:
    return KeywordEmbeddings()


@pytest.fixture
def vector_store(
    tmp_path: Path,
    embedding_provider: KeywordEmbeddings,
) -> VectorStore:
    return VectorStore(
        chroma_path=tmp_path / "chroma",
        embedding_provider=embedding_provider,
    )


@pytest.fixture
def policy_chunks() -> list[DocumentChunk]:
    return [
        make_chunk(
            "acceptable_use_001",
            "General acceptable use requirements for all staff.",
            "public",
            "user,security_analyst,admin",
        ),
        make_chunk(
            "password_policy_001",
            "Password accounts require multi-factor authentication.",
            "internal",
            "user,security_analyst,admin",
        ),
        make_chunk(
            "incident_response_001",
            "Incident responders must preserve breach evidence.",
            "confidential",
            "security_analyst,admin",
        ),
        make_chunk(
            "restricted_admin_001",
            "Restricted administrator recovery procedures.",
            "restricted",
            "admin",
        ),
    ]


def test_sentence_transformer_uses_required_model(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded_models: list[str] = []

    class FakeModel:
        def __init__(self, model_name: str) -> None:
            loaded_models.append(model_name)

        def encode(self, texts: list[str], **_: object) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr("sentence_transformers.SentenceTransformer", FakeModel)
    embeddings = SentenceTransformerEmbeddings()

    assert embeddings.embed_query("test") == [1.0, 0.0]
    assert loaded_models == [MODEL_NAME]
    assert MODEL_NAME == "all-MiniLM-L6-v2"


def test_chunks_are_inserted_with_text_embeddings_and_metadata(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
) -> None:
    vector_store.add_chunks(policy_chunks)

    stored = vector_store.collection.get(
        include=["documents", "embeddings", "metadatas"]
    )

    assert vector_store.collection.name == COLLECTION_NAME
    assert set(stored["ids"]) == {chunk.chunk_id for chunk in policy_chunks}
    assert len(stored["documents"]) == len(policy_chunks)
    assert len(stored["embeddings"]) == len(policy_chunks)
    for metadata in stored["metadatas"]:
        assert set(metadata) == {
            "document_title",
            "filename",
            "sensitivity_level",
            "allowed_roles",
            "section_heading",
            "page",
            "chunk_id",
        }
        assert isinstance(metadata["allowed_roles"], str)


def test_chunks_persist_across_vector_store_instances(
    tmp_path: Path,
    policy_chunks: list[DocumentChunk],
) -> None:
    chroma_path = tmp_path / "persistent-chroma"
    first_store = VectorStore(chroma_path, KeywordEmbeddings())
    first_store.add_chunks(policy_chunks)

    reopened_store = VectorStore(chroma_path, KeywordEmbeddings())

    assert reopened_store.collection.count() == len(policy_chunks)


def test_search_returns_relevant_results(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
) -> None:
    vector_store.add_chunks(policy_chunks)

    results = vector_store.search(
        "What are the password requirements?",
        ["public", "internal", "confidential", "restricted"],
        top_k=2,
    )

    assert results
    assert results[0].chunk_id == "password_policy_001"
    assert "multi-factor" in results[0].text


def test_search_respects_sensitivity_filters(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
) -> None:
    vector_store.add_chunks(policy_chunks)

    results = vector_store.search("incident breach", ["confidential"])

    assert [result.chunk_id for result in results] == ["incident_response_001"]
    assert all(result.metadata["sensitivity_level"] == "confidential" for result in results)


def test_restricted_chunks_require_explicit_restricted_access(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
) -> None:
    vector_store.add_chunks(policy_chunks)

    unauthorised_results = vector_store.search(
        "restricted administrator procedures",
        ["public", "internal", "confidential"],
    )
    authorised_results = vector_store.search(
        "restricted administrator procedures",
        ["restricted"],
    )

    assert "restricted_admin_001" not in {
        result.chunk_id for result in unauthorised_results
    }
    assert [result.chunk_id for result in authorised_results] == [
        "restricted_admin_001"
    ]


def test_empty_allowed_sensitivity_levels_returns_no_results_without_querying(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
    embedding_provider: KeywordEmbeddings,
) -> None:
    vector_store.add_chunks(policy_chunks)

    assert vector_store.search("restricted procedures", []) == []
    assert embedding_provider.query_calls == 0


def test_reset_collection_removes_all_chunks(
    vector_store: VectorStore,
    policy_chunks: list[DocumentChunk],
) -> None:
    vector_store.add_chunks(policy_chunks)

    vector_store.reset_collection()

    assert vector_store.collection.name == COLLECTION_NAME
    assert vector_store.collection.count() == 0


def test_unknown_allowed_sensitivity_is_rejected(vector_store: VectorStore) -> None:
    with pytest.raises(ValueError, match="Unknown sensitivity levels"):
        vector_store.search("policy", ["top_secret"])
