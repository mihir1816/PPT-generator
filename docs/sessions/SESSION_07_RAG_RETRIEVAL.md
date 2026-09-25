# Session 07 — RAG Retrieval Engine

## Goal
Build the complete retrieval pipeline: approved syllabus → multi-query generation → hybrid search (dense + BM25) → RRF fusion → FlashRank reranking → collected chunks per topic. After this session, given a deck with approved syllabus and indexed documents, the system retrieves all relevant content.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-06 complete
- `src/app/services/vector_store.py` — Qdrant search
- `src/app/services/sparse_index.py` — BM25S search
- `src/app/services/embedding.py` — query embedding
- `src/app/services/llm_client.py` — for query generation
- `src/app/services/prompt_templates.py` — QUERY_GENERATION template
- `src/app/schemas/syllabus.py` — TopicSyllabus
- `docs/RAG_ARCHITECTURE_RESEARCH.md` — hybrid search, RRF, reranking
- `docs/CHUNKING_VECTORIZATION_RESEARCH.md` — retrieval section

## Non-Negotiable Rules
- Multi-query: generate 2-3 search queries per syllabus topic
- Hybrid: BOTH dense (Qdrant) AND sparse (BM25S) for every query
- Fusion: Reciprocal Rank Fusion (RRF) with k=60
- Rerank: FlashRank on fused results
- Return PARENT chunks (not child chunks) — parent has more context
- Filter search by document_ids linked to the deck
- Deduplicate chunks across queries (same parent_content = same chunk)
- Grounded mode: only retrieved content | Mixed mode: flag gaps for LLM to fill

## Files to Create

### `services/rag.py` — RAG Retrieval Service
```python
class RAGService:
    def __init__(self, llm: LLMClient, embedding: EmbeddingService,
                 vector_store: VectorStoreService, sparse: SparseIndexService):
        ...

    async def retrieve_for_deck(self, syllabus: TopicSyllabus,
                                 document_ids: list[str],
                                 content_mode: str,
                                 db: AsyncSession) -> RetrievalResult:
        """
        Full Stage 5 pipeline:
        0. Load all chunks for linked documents from DB
        1. Build COMBINED BM25S index on-the-fly from loaded chunks
           (on-demand — avoids process boundary issue with Celery worker)
        2. generate_queries(syllabus) → dict[topic, list[query]]
        3. For each query:
           a. Dense search: embed query → Qdrant search (filtered by doc_ids)
           b. Sparse search: BM25S search on the COMBINED index
           c. RRF fusion of dense + sparse results
        4. Deduplicate across all queries (by parent chunk content hash)
        5. Rerank all unique chunks with FlashRank
        6. Group chunks by syllabus topic
        7. Return RetrievalResult
        """

    async def generate_queries(self, syllabus: TopicSyllabus) -> dict[str, list[str]]:
        """
        LLM generates 2-3 search queries per topic.
        Uses QUERY_GENERATION prompt template.
        Returns: {topic_title: [query1, query2, query3]}
        """

    async def hybrid_search_single(self, query: str, query_vector: list[float],
                                    document_ids: list[str], bm25_index: bm25s.BM25,
                                    all_chunks: list[dict],
                                    limit: int = 20) -> list[ScoredChunk]:
        """
        Single query hybrid search:
        1. Dense: Qdrant similarity search filtered by document_ids → list of (chunk, score)
        2. Sparse: BM25S search on pre-built COMBINED index → list of (chunk, score)
           (single combined index, NOT per-document — avoids IDF mismatch)
        3. RRF fusion → combined ranked list
        """

    def rrf_fusion(self, dense_results: list, sparse_results: list,
                   k: int = 60) -> list[ScoredChunk]:
        """
        Reciprocal Rank Fusion:
        For each chunk across both lists:
          rrf_score = sum(1 / (k + rank_in_list)) for each list containing it
        Sort by rrf_score descending.
        """

    def rerank(self, query: str, chunks: list[ScoredChunk],
               top_k: int = 15) -> list[ScoredChunk]:
        """
        FlashRank reranking.
        Takes query + candidate chunks → re-scores → returns top_k.
        """

@dataclass
class ScoredChunk:
    chunk_id: str
    content: str           # child chunk (what was searched)
    parent_content: str    # parent chunk (what gets returned to LLM)
    score: float
    metadata: dict
    source_query: str      # which query found this

@dataclass
class TopicChunks:
    topic_title: str
    chunks: list[ScoredChunk]
    coverage: str          # "full" | "partial" | "none"

@dataclass
class RetrievalResult:
    topic_chunks: list[TopicChunks]
    total_chunks: int
    queries_generated: int
    gaps: list[str]        # topics with no/low coverage (for mixed mode)
```

### `services/reranker.py` — FlashRank Wrapper
```python
from flashrank import Ranker, RerankRequest

class RerankerService:
    def __init__(self):
        self.ranker = Ranker()  # loads default model (~4MB)

    def rerank(self, query: str, passages: list[dict], top_k: int = 15) -> list[dict]:
        """
        Rerank passages for a query.
        Input: [{"id": ..., "text": ...}, ...]
        Output: sorted by relevance, top_k
        """
        request = RerankRequest(query=query, passages=passages)
        results = self.ranker.rerank(request)
        return results[:top_k]
```
Initialize once at startup.

### `api/generate.py` — Retrieval Trigger Endpoint
```
POST /api/decks/{deck_id}/retrieve
    Precondition: deck status must be "ready_for_retrieval" (wait gate passed)
    Flow:
      1. Load deck (syllabus, document_ids, preferences)
      2. Call rag_service.retrieve_for_deck()
      3. Store RetrievalResult in Deck.retrieval_json (DB — NOT Redis)
         Why DB? Redis TTL would expire during long feedback sessions.
         Retrieval data is needed for hours/days during the feedback lifecycle.
      4. Update deck status → "retrieval_complete"
      5. Return { status, total_chunks, coverage_summary, gaps }
```

## Flow
```
1. Create services/reranker.py
2. Create services/rag.py
3. Create api/generate.py (retrieval trigger endpoint)
4. Add FlashRank to pyproject.toml if not present
5. Initialize RerankerService in main.py startup
6. Register generate router in main.py
7. Test full retrieval pipeline
```

## Verification
```bash
# Prerequisites: deck with approved syllabus + indexed documents (from Sessions 03-06)

# 1. Trigger retrieval
curl -X POST http://localhost:8200/api/decks/<deck_id>/retrieve
# Expected: { "status": "retrieval_complete", "total_chunks": N, "coverage_summary": {...} }
# N should be > 0

# 2. Check queries were generated
# (visible in response or logs)
docker compose logs app --tail=30 | grep "queries"
# Expected: "Generated X queries for Y topics"

# 3. Test hybrid search directly
docker compose exec app python -c "
import asyncio
from app.services.rag import RAGService
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.sparse_index import SparseIndexService
from app.services.reranker import RerankerService
from app.services.llm_client import LLMClient
from app.config import get_settings

async def test():
    s = get_settings()
    emb = EmbeddingService()
    vec = emb.embed_query('What is machine learning?')
    print(f'Query vector dim: {len(vec)}')
    # If you have Qdrant with data:
    from app.core.qdrant_client import get_qdrant
    vs = VectorStoreService(await get_qdrant())
    results = await vs.search(vec, document_ids=['<doc_id>'], limit=5)
    print(f'Dense results: {len(results)}')
    print('Hybrid search OK')
asyncio.run(test())
"

# 4. Test reranker
docker compose exec app python -c "
from app.services.reranker import RerankerService
svc = RerankerService()
results = svc.rerank('machine learning', [
    {'id': '1', 'text': 'ML is a subset of AI that learns from data'},
    {'id': '2', 'text': 'The weather today is sunny'},
    {'id': '3', 'text': 'Deep learning uses neural networks for ML tasks'}
])
print(f'Top result: {results[0][\"id\"]}')
assert results[0]['id'] in ('1', '3')
print('Reranker OK')
"

# 5. Test RRF fusion
docker compose exec app python -c "
from app.services.rag import RAGService
fused = RAGService.rrf_fusion(
    dense_results=[('a', 1), ('b', 2), ('c', 3)],
    sparse_results=[('b', 1), ('d', 2), ('a', 3)],
    k=60
)
print(f'Fused order: {[c[0] for c in fused]}')
# 'b' should be first (appears in both lists at good ranks)
print('RRF OK')
"
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 07 ✅, note retrieval pipeline working, next → Session 08
