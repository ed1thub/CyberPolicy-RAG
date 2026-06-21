"""Sentence-transformer embeddings used by the policy vector store."""

from collections.abc import Sequence
from typing import Any, Protocol

MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingProvider(Protocol):
    """Small interface accepted by the vector store and test doubles."""

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document text for storage."""

    def embed_query(self, text: str) -> list[float]:
        """Embed one search query."""


class SentenceTransformerEmbeddings:
    """Generate local embeddings with the configured sentence transformer."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    def _get_model(self) -> Any:
        """Load the model on first use so importing the app never downloads it."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Return a normalised embedding for every supplied document."""
        if not texts:
            return []

        encoded = self._get_model().encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Return one normalised query embedding."""
        return self.embed_documents([text])[0]
