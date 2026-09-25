import logging

from fastembed import TextEmbedding

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str = "nomic-embed-text-v2-moe", dimension: int = 768):
        self._model_name = model_name
        self._dimension = dimension
        logger.info("Loading embedding model: %s", model_name)
        self._model = TextEmbedding(model_name)
        logger.info("Embedding model loaded (dimension=%d)", dimension)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [embedding.tolist() for embedding in self._model.embed(texts)]

    def embed_query(self, query: str) -> list[float]:
        embeddings = list(self._model.query_embed(query))
        return embeddings[0].tolist()
