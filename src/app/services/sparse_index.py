import logging

import bm25s

logger = logging.getLogger(__name__)


class SparseIndexService:
    """Builds BM25S indices on-demand at retrieval time from DB chunks.

    Indices are NOT persisted or built during indexing. The Celery worker
    (indexing) and FastAPI server (retrieval) are separate processes with
    separate memory. A combined index across all documents linked to a
    deck produces correct IDF statistics; per-document indices would have
    incompatible scores.
    """

    def build_index_from_chunks(self, chunks: list[dict]) -> bm25s.BM25:
        texts = [c["content"] for c in chunks]
        tokenized = bm25s.tokenize(texts, stopwords="en")
        index = bm25s.BM25()
        index.index(tokenized)
        return index

    def search(
        self,
        index: bm25s.BM25,
        query: str,
        limit: int = 20,
    ) -> list[tuple[int, float]]:
        if index.corpus_size == 0:
            return []
        tokenized_query = bm25s.tokenize(query, stopwords="en")
        k = min(limit, index.corpus_size)
        try:
            results, scores = index.retrieve(tokenized_query, k=k)
        except Exception:
            logger.debug("BM25 search returned no results for query", exc_info=True)
            return []
        return list(zip(results[0].tolist(), scores[0].tolist()))
