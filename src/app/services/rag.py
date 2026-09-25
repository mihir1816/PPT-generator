import asyncio
import hashlib
import logging
import uuid as uuid_mod
from dataclasses import asdict, dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.syllabus import TopicSyllabus
from app.services import crud
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.prompt_templates import (
    QUERY_GENERATION_SYSTEM,
    QUERY_GENERATION_USER,
)
from app.services.reranker import RerankerService
from app.services.sparse_index import SparseIndexService
from app.services.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

RRF_K = 60
DENSE_LIMIT = 20
SPARSE_LIMIT = 20
RERANK_TOP_K = 10
FULL_COVERAGE_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScoredChunk:
    chunk_id: str
    content: str
    parent_content: str
    score: float
    metadata: dict = field(default_factory=dict)
    source_query: str = ""


@dataclass
class TopicChunks:
    topic_title: str
    chunks: list[ScoredChunk]
    coverage: str


@dataclass
class RetrievalResult:
    topic_chunks: list[TopicChunks]
    total_chunks: int
    queries_generated: int
    gaps: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pydantic models for LLM query generation response
# ---------------------------------------------------------------------------


class TopicQueryItem(BaseModel):
    topic: str
    search_queries: list[str] = Field(default_factory=list)


class QueryGenerationResponse(BaseModel):
    queries: list[TopicQueryItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# RAG Service
# ---------------------------------------------------------------------------


class RAGService:
    def __init__(
        self,
        llm: LLMClient,
        embedding: EmbeddingService,
        vector_store: VectorStoreService,
        sparse: SparseIndexService,
        reranker: RerankerService,
    ):
        self._llm = llm
        self._embedding = embedding
        self._vector_store = vector_store
        self._sparse = sparse
        self._reranker = reranker

    # ------------------------------------------------------------------
    # Public: full Stage 5 pipeline
    # ------------------------------------------------------------------

    async def retrieve_for_deck(
        self,
        syllabus: TopicSyllabus,
        document_ids: list[str],
        content_mode: str,
        db: AsyncSession,
    ) -> RetrievalResult:
        doc_uuids = [uuid_mod.UUID(d) for d in document_ids]
        db_chunks = await crud.get_chunks_by_documents(db, doc_uuids)

        if not db_chunks:
            logger.warning("No chunks found for documents %s", document_ids)
            return self._empty_result(syllabus)

        all_chunks = [
            {
                "db_id": str(c.id),
                "document_id": str(c.document_id),
                "chunk_index": c.chunk_index,
                "content": c.content,
                "parent_content": c.parent_content or c.content,
                "metadata": c.metadata_json or {},
                "embedding_id": c.embedding_id,
            }
            for c in db_chunks
        ]

        bm25_index = await asyncio.to_thread(
            self._sparse.build_index_from_chunks, all_chunks,
        )
        logger.info("Built BM25S index with %d chunks", len(all_chunks))

        topic_queries = await self.generate_queries(syllabus)
        total_queries = sum(len(qs) for qs in topic_queries.values())
        logger.info(
            "Generated %d queries for %d topics",
            total_queries,
            len(topic_queries),
        )

        topic_chunks_list: list[TopicChunks] = []
        gaps: list[str] = []
        total_unique = 0

        for topic in syllabus.topics:
            queries = topic_queries.get(topic.title)
            if not queries:
                queries = self._fallback_queries(topic)

            seen: dict[str, ScoredChunk] = {}

            for query in queries:
                try:
                    query_vector = await asyncio.to_thread(
                        self._embedding.embed_query, query,
                    )
                except Exception:
                    logger.warning("Embedding failed for query: %s", query, exc_info=True)
                    continue

                fused = await self._hybrid_search_single(
                    query, query_vector, document_ids, bm25_index, all_chunks,
                )

                for sc in fused:
                    key = hashlib.md5(
                        sc.parent_content.encode("utf-8", errors="replace")
                    ).hexdigest()
                    if key not in seen or sc.score > seen[key].score:
                        seen[key] = sc

            unique_chunks = list(seen.values())

            if unique_chunks:
                rerank_query = topic.title
                if topic.subtopics:
                    rerank_query += ": " + ", ".join(topic.subtopics[:5])
                unique_chunks = await asyncio.to_thread(
                    self._rerank_chunks, rerank_query, unique_chunks,
                )

            coverage = self._assess_coverage(len(unique_chunks))
            if coverage == "none":
                gaps.append(topic.title)
            elif coverage == "partial" and content_mode == "mixed":
                gaps.append(topic.title)

            total_unique += len(unique_chunks)
            topic_chunks_list.append(
                TopicChunks(
                    topic_title=topic.title,
                    chunks=unique_chunks,
                    coverage=coverage,
                )
            )

        logger.info(
            "Retrieval complete: %d unique chunks across %d topics, %d gaps",
            total_unique,
            len(topic_chunks_list),
            len(gaps),
        )

        return RetrievalResult(
            topic_chunks=topic_chunks_list,
            total_chunks=total_unique,
            queries_generated=total_queries,
            gaps=gaps,
        )

    # ------------------------------------------------------------------
    # Query generation
    # ------------------------------------------------------------------

    async def generate_queries(
        self, syllabus: TopicSyllabus
    ) -> dict[str, list[str]]:
        try:
            result = await self._llm.generate_json(
                QUERY_GENERATION_SYSTEM,
                QUERY_GENERATION_USER.format(
                    syllabus_json=syllabus.model_dump_json(indent=2),
                ),
                response_model=QueryGenerationResponse,
            )
            topic_queries: dict[str, list[str]] = {}
            for item in result.queries:
                if item.search_queries:
                    topic_queries[item.topic] = item.search_queries
            return topic_queries
        except LLMServiceError:
            logger.warning(
                "LLM query generation failed; falling back to topic titles",
                exc_info=True,
            )
            return {
                t.title: self._fallback_queries(t)
                for t in syllabus.topics
            }

    # ------------------------------------------------------------------
    # Hybrid search (single query)
    # ------------------------------------------------------------------

    async def _hybrid_search_single(
        self,
        query: str,
        query_vector: list[float],
        document_ids: list[str],
        bm25_index,
        all_chunks: list[dict],
    ) -> list[ScoredChunk]:
        dense_ranked = await self._dense_search(
            query, query_vector, document_ids
        )
        sparse_ranked = await asyncio.to_thread(
            self._sparse_search, query, bm25_index, all_chunks,
        )
        return self._rrf_fusion(dense_ranked, sparse_ranked)

    async def _dense_search(
        self,
        query: str,
        query_vector: list[float],
        document_ids: list[str],
    ) -> list[tuple[str, ScoredChunk]]:
        results = await self._vector_store.search(
            query_vector, document_ids, limit=DENSE_LIMIT,
        )
        ranked: list[tuple[str, ScoredChunk]] = []
        for hit in results:
            key = f"{hit['document_id']}:{hit['chunk_index']}"
            ranked.append((
                key,
                ScoredChunk(
                    chunk_id=hit["id"],
                    content=hit.get("content", ""),
                    parent_content=hit.get("parent_content", hit.get("content", "")),
                    score=hit["score"],
                    metadata=hit.get("metadata", {}),
                    source_query=query,
                ),
            ))
        return ranked

    def _sparse_search(
        self,
        query: str,
        bm25_index,
        all_chunks: list[dict],
    ) -> list[tuple[str, ScoredChunk]]:
        sparse_raw = self._sparse.search(bm25_index, query, limit=SPARSE_LIMIT)
        ranked: list[tuple[str, ScoredChunk]] = []
        for idx, score in sparse_raw:
            if not (0 <= idx < len(all_chunks)):
                continue
            chunk = all_chunks[idx]
            key = f"{chunk['document_id']}:{chunk['chunk_index']}"
            ranked.append((
                key,
                ScoredChunk(
                    chunk_id=chunk.get("embedding_id") or chunk["db_id"],
                    content=chunk["content"],
                    parent_content=chunk["parent_content"],
                    score=score,
                    metadata=chunk["metadata"],
                    source_query=query,
                ),
            ))
        return ranked

    # ------------------------------------------------------------------
    # RRF fusion
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_fusion(
        dense_ranked: list[tuple[str, ScoredChunk]],
        sparse_ranked: list[tuple[str, ScoredChunk]],
        k: int = RRF_K,
    ) -> list[ScoredChunk]:
        scores: dict[str, float] = {}
        chunk_map: dict[str, ScoredChunk] = {}

        for rank, (key, sc) in enumerate(dense_ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in chunk_map:
                chunk_map[key] = sc

        for rank, (key, sc) in enumerate(sparse_ranked, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in chunk_map:
                chunk_map[key] = sc

        sorted_keys = sorted(scores, key=scores.__getitem__, reverse=True)

        result: list[ScoredChunk] = []
        for key in sorted_keys:
            sc = chunk_map[key]
            sc.score = scores[key]
            result.append(sc)
        return result

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

    def _rerank_chunks(
        self,
        query: str,
        chunks: list[ScoredChunk],
        top_k: int = RERANK_TOP_K,
    ) -> list[ScoredChunk]:
        if not chunks:
            return []

        passages = [
            {"id": str(i), "text": c.content}
            for i, c in enumerate(chunks)
        ]

        reranked = self._reranker.rerank(query, passages, top_k=top_k)

        result: list[ScoredChunk] = []
        for item in reranked:
            try:
                idx = int(item["id"])
            except (ValueError, TypeError):
                logger.debug("Reranker returned non-integer id: %s", item.get("id"))
                continue
            if 0 <= idx < len(chunks):
                sc = chunks[idx]
                sc.score = item["score"]
                result.append(sc)

        if not result and chunks:
            logger.warning(
                "Reranker returned no usable results for query '%s'; "
                "falling back to pre-rerank order (%d chunks)",
                query[:80], len(chunks),
            )
            return chunks[:top_k]

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _assess_coverage(chunk_count: int) -> str:
        if chunk_count >= FULL_COVERAGE_THRESHOLD:
            return "full"
        if chunk_count > 0:
            return "partial"
        return "none"

    @staticmethod
    def _fallback_queries(topic) -> list[str]:
        queries = [topic.title]
        for sub in topic.subtopics[:2]:
            queries.append(f"{topic.title} {sub}")
        return queries

    @staticmethod
    def _empty_result(syllabus: TopicSyllabus) -> RetrievalResult:
        return RetrievalResult(
            topic_chunks=[
                TopicChunks(topic_title=t.title, chunks=[], coverage="none")
                for t in syllabus.topics
            ],
            total_chunks=0,
            queries_generated=0,
            gaps=[t.title for t in syllabus.topics],
        )
