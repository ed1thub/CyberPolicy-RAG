"""Role-aware retriever that enforces access control before vector search."""

from backend.app.rag.vector_store import SearchResult, VectorStore
from backend.app.security.access_control import get_allowed_sensitivity_levels


class Retriever:
    """Combines access control with vector store search.

    Access control is applied first: the retriever determines the allowed
    sensitivity levels for the given role and passes them to the vector store
    as a hard filter. The vector store never returns chunks outside those levels.
    Unknown roles receive an empty allowed list and therefore no results.
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store

    def retrieve_for_role(
        self,
        question: str,
        role: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Return only chunks the role is authorised to read.

        Steps:
        1. Determine allowed sensitivity levels for role (deny-by-default).
        2. Return empty list immediately if role has no allowed levels.
        3. Pass allowed levels as a hard filter to vector store search.
        """
        allowed_levels = get_allowed_sensitivity_levels(role)
        if not allowed_levels:
            return []
        return self._vector_store.search(question, allowed_levels, top_k=top_k)
