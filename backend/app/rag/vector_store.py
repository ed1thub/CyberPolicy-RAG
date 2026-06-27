"""Persistent ChromaDB storage with sensitivity-filtered policy retrieval."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

from backend.app.config import settings
from backend.app.documents.chunker import DocumentChunk
from backend.app.rag.embeddings import EmbeddingProvider, SentenceTransformerEmbeddings

COLLECTION_NAME = "policy_chunks"
VALID_SENSITIVITY_LEVELS = frozenset(
    {"public", "internal", "confidential", "restricted"}
)
REQUIRED_METADATA_FIELDS = frozenset(
    {
        "document_title",
        "filename",
        "sensitivity_level",
        "allowed_roles",
        "section_heading",
        "page",
        "chunk_id",
    }
)


@dataclass(frozen=True)
class SearchResult:
    """One authorised chunk returned by a vector search."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None


class VectorStore:
    """Store policy chunks and retrieve only explicitly allowed sensitivities."""

    def __init__(
        self,
        chroma_path: str | Path | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        client: Any | None = None,
    ) -> None:
        path = Path(chroma_path if chroma_path is not None else settings.chroma_path)
        self.embedding_provider = embedding_provider or SentenceTransformerEmbeddings()
        self.client = client or chromadb.PersistentClient(path=str(path))
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self) -> Any:
        return self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: Sequence[DocumentChunk]) -> None:
        """Embed and upsert chunks with complete scalar metadata."""
        if not chunks:
            return

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Chunk IDs must be unique within an insert batch")

        documents = [chunk.text for chunk in chunks]
        metadatas = [self._normalise_metadata(chunk) for chunk in chunks]
        embeddings = self.embedding_provider.embed_documents(documents)

        if len(embeddings) != len(chunks):
            raise ValueError("Embedding provider returned an unexpected number of vectors")

        self.collection.upsert(
            ids=chunk_ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(
        self,
        query: str,
        allowed_sensitivity_levels: Sequence[str],
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search only chunks whose sensitivity is explicitly authorised."""
        allowed_levels = set(allowed_sensitivity_levels)
        unknown_levels = allowed_levels - VALID_SENSITIVITY_LEVELS
        if unknown_levels:
            raise ValueError(f"Unknown sensitivity levels: {sorted(unknown_levels)}")
        if not allowed_levels or top_k <= 0:
            return []

        result_count = min(top_k, self.collection.count())
        if result_count == 0:
            return []

        ordered_levels = sorted(allowed_levels)
        where_filter: dict[str, Any]
        if len(ordered_levels) == 1:
            where_filter = {"sensitivity_level": ordered_levels[0]}
        else:
            where_filter = {"sensitivity_level": {"$in": ordered_levels}}

        response = self.collection.query(
            query_embeddings=[self.embedding_provider.embed_query(query)],
            n_results=result_count,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        return self._authorised_results(response, allowed_levels)

    def _authorised_results(
        self,
        response: dict[str, Any],
        allowed_levels: set[str],
    ) -> list[SearchResult]:
        """Convert Chroma output and defensively enforce the access boundary."""
        ids = (response.get("ids") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        results: list[SearchResult] = []
        for chunk_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            if metadata["sensitivity_level"] not in allowed_levels:
                continue
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=document,
                    metadata=dict(metadata),
                    distance=float(distance) if distance is not None else None,
                )
            )
        return results

    def delete_by_filename(self, filename: str) -> int:
        """Delete all chunks whose metadata filename matches. Returns count deleted."""
        result = self.collection.get(where={"filename": filename}, include=[])
        ids = result.get("ids") or []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def reset_collection(self) -> None:
        """Delete all stored policy chunks and recreate the collection."""
        self.client.delete_collection(name=COLLECTION_NAME)
        self.collection = self._get_or_create_collection()

    @staticmethod
    def _normalise_metadata(chunk: DocumentChunk) -> dict[str, Any]:
        metadata = chunk.to_metadata()
        missing_fields = REQUIRED_METADATA_FIELDS - metadata.keys()
        if missing_fields:
            raise ValueError(f"Chunk metadata is missing fields: {sorted(missing_fields)}")
        if metadata["sensitivity_level"] not in VALID_SENSITIVITY_LEVELS:
            raise ValueError(
                f"Unknown sensitivity level: {metadata['sensitivity_level']}"
            )

        allowed_roles = metadata["allowed_roles"]
        if isinstance(allowed_roles, (list, tuple, set, frozenset)):
            metadata["allowed_roles"] = ",".join(str(role) for role in allowed_roles)
        else:
            metadata["allowed_roles"] = str(allowed_roles)
        return metadata
