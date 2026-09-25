import logging

from flashrank import Ranker, RerankRequest

logger = logging.getLogger(__name__)


class RerankerService:
    def __init__(self, model_name: str = "ms-marco-MiniLM-L-12-v2"):
        logger.info("Loading reranker model: %s", model_name)
        self._ranker = Ranker(model_name=model_name)
        logger.info("Reranker model loaded")

    def rerank(
        self, query: str, passages: list[dict], top_k: int = 15
    ) -> list[dict]:
        if not passages:
            return []
        request = RerankRequest(query=query, passages=passages)
        results = self._ranker.rerank(request)
        return [
            {
                "id": r.get("id") if isinstance(r, dict) else getattr(r, "id", i),
                "text": r.get("text", "") if isinstance(r, dict) else getattr(r, "text", ""),
                "score": float(
                    r.get("score", 0.0) if isinstance(r, dict) else getattr(r, "score", 0.0)
                ),
            }
            for i, r in enumerate(results[:top_k])
        ]
