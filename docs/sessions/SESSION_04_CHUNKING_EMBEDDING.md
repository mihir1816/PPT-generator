# Session 04 — Chunking & Embedding Pipeline

## Goal
Build the full indexing pipeline: Document → chunk (parent-document hierarchical) → embed (FastEmbed) → store in Qdrant. Define BM25S sparse index service (built on-demand at retrieval time, not during indexing). Wire into a Celery task that runs after document parsing. After this session, uploaded documents are automatically chunked, embedded, and searchable in Qdrant.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-03 complete
- `src/app/models/chunk.py` — Chunk model (has parent_content field)
- `src/app/models/document.py` — Document model (is_indexed, chunk_count)
- `src/app/services/crud.py` — create_chunks_bulk, update document
- `src/app/core/qdrant_client.py` — Qdrant connection
- `docs/CHUNKING_VECTORIZATION_RESEARCH.md` — full research

## Non-Negotiable Rules
- Parent-Document hierarchical chunking (NOT simple recursive — production choice)
- FastEmbed with `nomic-embed-text-v2-moe` (NOT sentence-transformers)
- Qdrant for dense vectors (NOT ChromaDB)
- BM25S for sparse search alongside dense
- Chunk size: 512 tokens (child), ~2048 tokens (parent)
- Overlap: 50 tokens
- Store parent_content in Chunk model for retrieval (return parent, search child)
- All indexing in Celery worker
- Qdrant collection created at startup if not exists

## Files to Create

### `services/chunking.py` — Chunking Service
```python
class ChunkingService:
    def chunk_document(self, markdown: str, metadata: dict) -> list[ChunkResult]:
        """
        Parent-Document hierarchical chunking:
        1. Split into PARENT chunks (~2048 tokens) using MarkdownHeaderTextSplitter
           - Split by h1/h2/h3 headers first (structure-aware)
        2. Split each parent into CHILD chunks (512 tokens, 50 overlap)
           using RecursiveCharacterTextSplitter
        3. Each child stores:
           - content: the child chunk text (used for embedding/search)
           - parent_content: the full parent chunk text (returned to LLM)
           - metadata: {headers, parent_index, child_index, page_num if available}
        """

@dataclass
class ChunkResult:
    content: str           # child chunk (512 tokens) — embedded & searched
    parent_content: str    # parent chunk (~2048 tokens) — returned to LLM
    metadata: dict         # headers, indices, source info
    token_count: int
```

Key: We SEARCH on child chunks (precise) but RETURN parent chunks (more context). This is the parent-document retrieval pattern.

### `services/embedding.py` — Embedding Service
```python
from fastembed import TextEmbedding

class EmbeddingService:
    def __init__(self):
        self.model = TextEmbedding("nomic-embed-text-v2-moe")
        self.dimension = 768  # nomic-embed-text-v2-moe output dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed list of texts. Returns list of vectors."""
        # FastEmbed handles batching internally
        return list(self.model.embed(texts))

    def embed_query(self, query: str) -> list[float]:
        """Embed single query. Prefix with 'search_query: '"""
        return list(self.model.query_embed(query))[0]
```
Initialize ONCE at startup, reuse.

### `services/vector_store.py` — Qdrant Integration
```python
class VectorStoreService:
    COLLECTION_NAME = "tcg_chunks"

    async def ensure_collection(self):
        """Create collection if not exists. Called at startup."""
        # vector size=768, distance=Cosine
        # Enable payload indexing on document_id, chunk_index

    async def upsert_chunks(self, chunks: list[dict]) -> list[str]:
        """
        Insert chunks into Qdrant.
        Each point:
          id: UUID string
          vector: embedding (768-dim)
          payload: {document_id, chunk_index, content, parent_content, metadata}
        Returns list of point IDs (stored as embedding_id in Chunk model)
        """

    async def search(self, query_vector: list[float], document_ids: list[str],
                     limit: int = 20) -> list[dict]:
        """Dense similarity search filtered by document_ids."""

    async def delete_by_document(self, document_id: str):
        """Delete all vectors for a document (for re-indexing)."""
```

### `services/sparse_index.py` — BM25S Sparse Index
```python
import bm25s

class SparseIndexService:
    """
    Builds BM25S indices ON-DEMAND at retrieval time from chunks in the DB.
    
    IMPORTANT: BM25S indices are NOT persisted or built during indexing.
    The Celery worker (indexing) and FastAPI server (retrieval) are separate
    processes with separate memory. Building an index in the worker would be
    invisible to the API server. Instead, we build a combined index at
    retrieval time from all chunks belonging to the deck's linked documents.
    
    For single-user mode, this is fast enough (~50ms for 1000 chunks).
    """

    def build_index_from_chunks(self, chunks: list[dict]) -> bm25s.BM25:
        """
        Build a COMBINED BM25 index from chunks across multiple documents.
        Input: [{chunk_index, content, document_id}, ...]
        Returns: fitted BM25 index.
        
        This is called at retrieval time, NOT during indexing.
        A single combined index avoids the multi-document fusion problem
        (separate indices have incompatible IDF statistics).
        """
        texts = [c["content"] for c in chunks]
        tokenized = bm25s.tokenize(texts, stopwords="en")
        index = bm25s.BM25()
        index.index(tokenized)
        return index

    def search(self, index: bm25s.BM25, query: str, 
               limit: int = 20) -> list[tuple[int, float]]:
        """BM25 search on a pre-built index. Returns list of (chunk_index, score)."""
        tokenized_query = bm25s.tokenize(query, stopwords="en")
        results, scores = index.retrieve(tokenized_query, k=min(limit, index.corpus_size))
        return list(zip(results[0].tolist(), scores[0].tolist()))
```
**Why on-demand instead of pre-built?**
1. Celery worker and API server are separate processes — in-memory indices are not shared.
2. A deck may link multiple documents. A single combined index produces correct IDF statistics across all documents (separate per-document indices would have incompatible scores).
3. For single-user mode, building from DB chunks is fast enough (~50ms for 1000 chunks).

### `tasks/indexing.py` — Celery Indexing Task
```python
@celery_app.task(bind=True, max_retries=2)
def index_document_task(self, document_id: str):
    """
    Full indexing pipeline:
    1. Fetch Document from DB
    2. Chunk: markdown_content → ChunkingService → list[ChunkResult]
    3. Embed: chunk contents → EmbeddingService → vectors
    4. Store in Qdrant: VectorStoreService.upsert_chunks()
    5. Save Chunks to DB (with embedding_id from Qdrant)
    6. Update Document: is_indexed=True, chunk_count=N
    7. Check wait gate for any deck linked to this document (see Session 06)
    
    NOTE: BM25S index is NOT built here. It is built on-demand at retrieval
    time in the API server process. See SparseIndexService.build_index_from_chunks().
    The chunks stored in DB (step 5) are the source for on-demand BM25.
    """
```

### Update `tasks/process_upload.py`
After creating Document, chain the indexing task:
```python
# At end of process_upload_task, after document is created:
index_document_task.delay(str(document.id))
```

### Update `main.py` startup
```python
# After existing startup checks:
# Ensure Qdrant collection exists
vector_store = VectorStoreService(qdrant_client)
await vector_store.ensure_collection()
```

## Flow
```
1. Create services/chunking.py
2. Create services/embedding.py
3. Create services/vector_store.py
4. Create services/sparse_index.py
5. Create tasks/indexing.py
6. Update tasks/process_upload.py to chain indexing
7. Update main.py startup to ensure Qdrant collection
8. Rebuild: docker compose up -d --build app celery-worker
9. Upload a doc → verify chunks in DB + Qdrant
```

## Verification
```bash
# 1. Rebuild
docker compose up -d --build app celery-worker

# 2. Upload a PDF and wait for processing + indexing
curl -X POST http://localhost:8200/api/upload -F "file=@sample.pdf"
# Wait 30s for parse + index

# 3. Check Document is indexed
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT id, title, is_indexed, chunk_count FROM documents;"
# Expected: is_indexed=true, chunk_count > 0

# 4. Check chunks in DB
docker compose exec postgres psql -U tcg_user -d teacher_content_gen \
  -c "SELECT chunk_index, token_count, char_length(content), char_length(parent_content) FROM chunks LIMIT 5;"
# Expected: rows with content shorter than parent_content

# 5. Check Qdrant has vectors
curl http://localhost:6333/collections/tcg_chunks
# Expected: points_count > 0

# 6. Test embedding service
docker compose exec app python -c "
from app.services.embedding import EmbeddingService
svc = EmbeddingService()
vec = svc.embed_query('What is photosynthesis?')
print(f'Vector dim: {len(vec)}')
assert len(vec) == 768
print('Embedding OK')
"

# 7. Test chunking
docker compose exec app python -c "
from app.services.chunking import ChunkingService
svc = ChunkingService()
md = '# Chapter 1\n\nSome text here.\n\n## Section 1.1\n\nMore detailed text about the topic.' * 20
chunks = svc.chunk_document(md, {})
print(f'Chunks: {len(chunks)}, First child len: {len(chunks[0].content)}, Parent len: {len(chunks[0].parent_content)}')
assert len(chunks) > 0
assert len(chunks[0].parent_content) >= len(chunks[0].content)
print('Chunking OK')
"

# 8. Celery logs clean
docker compose logs celery-worker --tail=30
# Expected: index_document_task succeeded
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 04 ✅, note Qdrant collection name `tcg_chunks`, next → Session 05
