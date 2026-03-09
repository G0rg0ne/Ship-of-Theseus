"""
Embedding service for entity and community summary vectorization.

Uses OpenAI text-embedding-3-small to produce vectors for:
- Entity Identity Cards (label + description) — powers Local Search
- Community summaries — powers Global Search

Vectors are stored in Neo4j Vector Index.
"""
from typing import Any, Dict, List

from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.logger import logger

# Max texts per OpenAI embedding request (API limit is higher; batching for safety)
_EMBEDDING_BATCH_SIZE = 100


def entity_to_embed_text(node: Dict[str, Any]) -> str:
    """
    Build the text to embed for an entity (Identity Card: label + description).

    Uses node label and optional description from properties.
    """
    label = node.get("label") or node.get("id") or ""
    description = (
        node.get("description")
        or (node.get("properties") or {}).get("description")
        or ""
    )
    if description:
        return f"{label}: {description}".strip()
    return label


class EmbeddingService:
    """Batch embedding via OpenAI embeddings API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = model or getattr(
            settings, "EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self._embeddings: OpenAIEmbeddings | None = None
        self._dimension: int | None = None

    def _get_embeddings(self) -> OpenAIEmbeddings:
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                model=self._model,
                openai_api_key=self._api_key or "",
            )
        return self._embeddings

    def get_embedding_dimension(self) -> int:
        """
        Return the embedding vector dimension for the configured model.

        The dimension is determined once by probing a single embedding call and
        then cached for subsequent uses.
        """
        if self._dimension is not None:
            return self._dimension

        embeddings_client = self._get_embeddings()
        # Use a small probe text to avoid unnecessary token usage.
        vector = embeddings_client.embed_query("dimension probe")
        dim = len(vector)
        self._dimension = dim
        logger.info(
            "Resolved embedding dimension",
            model=self._model,
            dimensions=dim,
        )
        return dim

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts. Batches in chunks of _EMBEDDING_BATCH_SIZE.

        Returns a list of vectors (lists of floats) in the same order as texts.
        Empty or whitespace-only texts are embedded as a zero-vector placeholder
        if needed for index alignment; OpenAI may reject empty strings.
        """
        if not texts:
            return []
        # Replace empty/whitespace with a placeholder so we get a valid vector per slot
        normalized = [t.strip() if t and t.strip() else "(no text)" for t in texts]
        embeddings_client = self._get_embeddings()
        result: List[List[float]] = []
        for i in range(0, len(normalized), _EMBEDDING_BATCH_SIZE):
            batch = normalized[i : i + _EMBEDDING_BATCH_SIZE]
            vectors = embeddings_client.embed_documents(batch)
            result.extend(vectors)
        logger.debug(
            "Embedded texts",
            total=len(texts),
            batches=(len(texts) + _EMBEDDING_BATCH_SIZE - 1) // _EMBEDDING_BATCH_SIZE,
        )
        return result

    def embed_entities(
        self, nodes: List[Dict[str, Any]]
    ) -> Dict[str, List[float]]:
        """
        Embed each entity node by Identity Card (label + description).

        Returns a dict mapping node id -> embedding vector.
        """
        if not nodes:
            return {}
        ids = []
        texts = []
        for n in nodes:
            nid = n.get("id") or n.get("label") or ""
            if nid:
                ids.append(nid)
                texts.append(entity_to_embed_text(n))
        vectors = self.embed_texts(texts)
        return dict(zip(ids, vectors))
