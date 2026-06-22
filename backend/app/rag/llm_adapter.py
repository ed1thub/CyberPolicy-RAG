"""LLM provider abstraction with a mock default for local development."""

from collections.abc import Sequence
from typing import Protocol

NO_SOURCE_ANSWER = (
    "I could not find this information in the authorised policy documents."
)


class LLMProvider(Protocol):
    """Minimal interface accepted by RagService."""

    def generate(self, question: str, context_chunks: Sequence[str]) -> str:
        """Generate an answer given a question and retrieved context chunks."""
        ...


class MockLLM:
    """
    Default LLM for local development.

    Returns the retrieved context directly without calling any external API.
    This allows the full RAG pipeline to run in tests and local dev without
    an OpenAI key or a running Ollama instance.
    """

    def generate(self, question: str, context_chunks: Sequence[str]) -> str:
        if not context_chunks:
            return NO_SOURCE_ANSWER
        combined = "\n\n---\n\n".join(context_chunks)
        return f"Based on the authorised policy documents:\n\n{combined}"
