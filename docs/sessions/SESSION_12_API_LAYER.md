# Session 12 — FastAPI Complete API Layer

## Goal
Consolidate all endpoints into a clean, documented API. Add missing endpoints, error handling, CORS, request validation, and proper dependency injection. Wire the full end-to-end flow so the frontend has a single coherent API surface. After this session, every user action has a corresponding API endpoint.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Sessions 01-11 complete
- `src/app/api/` — all existing router files (upload, syllabus, generate, feedback, export)
- `src/app/main.py` — current app setup
- `docs/sessions/PROJECT_OVERVIEW.md` — the 9-stage flow

## Non-Negotiable Rules
- All endpoints follow REST conventions
- Every endpoint has proper error responses (4xx/5xx with ErrorResponse)
- CORS enabled for frontend origin (localhost:3000)
- Request validation via Pydantic models (not raw dicts)
- Dependency injection for services (FastAPI Depends)
- API prefix: `/api/` for all endpoints
- Health check at root: `/health`
- Auto-generated OpenAPI docs at `/docs`
- No auth for now (single user) but structure for future auth middleware

## Complete Endpoint Map

### Upload & Documents (`api/upload.py` — already exists, verify/fix)
```
POST   /api/upload              Upload file (PDF/PPTX/DOCX/image)
POST   /api/upload-url          Submit URL for parsing
GET    /api/upload/{id}         Upload status + document_id
GET    /api/documents           List all documents
GET    /api/documents/{id}      Document detail (title, source, blocks, indexed status)
DELETE /api/documents/{id}      Delete document + chunks + vectors
```

### Syllabus (`api/syllabus.py` — already exists, verify/fix)
```
POST   /api/decks                        Create deck + generate syllabus
GET    /api/decks                        List all decks
GET    /api/decks/{id}                   Deck detail (status, syllabus, slide count)
POST   /api/decks/{id}/syllabus-feedback Send syllabus feedback
POST   /api/decks/{id}/syllabus-approve  Approve syllabus
DELETE /api/decks/{id}                   Delete deck + all slides + feedback
```

### Generation (`api/generate.py` — already exists, verify/fix)
```
POST   /api/decks/{id}/retrieve         Trigger RAG retrieval
POST   /api/decks/{id}/generate-outline  Generate slide outline
POST   /api/decks/{id}/generate-slides   Generate slide content (SSE stream)
GET    /api/decks/{id}/slides            Get all slides (non-streaming)
GET    /api/decks/{id}/slides/{slide_id} Get single slide
```

### Feedback (`api/feedback.py` — already exists, verify/fix)
```
POST   /api/decks/{id}/slide-feedback   Send slide feedback (SSE stream response)
POST   /api/decks/{id}/undo             Undo last feedback round
GET    /api/decks/{id}/feedback-history  List all feedback rounds
```

### Export (`api/export.py` — already exists, verify/fix)
```
POST   /api/decks/{id}/export           Generate PPTX + return download URL
GET    /api/decks/{id}/export/download   Direct file download
```

### System
```
GET    /health                          App + service health
GET    /api/status                      System status (LLM available, Qdrant status)
```

## What to Build / Fix

### 1. Verify Dependency Injection Setup
DI was set up in Session 01 (`deps.py`) and extended by each subsequent session.
Verify ALL services have DI factories in `deps.py`:
```python
# These should already exist from earlier sessions:
get_llm_client, get_embedding_service, get_vector_store,
get_sparse_index, get_reranker, get_storage,
get_syllabus_service, get_rag_service, get_slide_generator,
get_feedback_service, get_exporter
```
Audit all endpoints to confirm they use `Depends()` — no direct instantiation.
Services initialized ONCE at startup (lifespan), stored in `app.state`.

### 2. Error Handling
```python
# Global exception handlers in main.py:
@app.exception_handler(LLMServiceError)
@app.exception_handler(ParseError)
@app.exception_handler(ValidationError)

# Each returns ErrorResponse with appropriate status code
```

### 3. CORS
Already configured in Session 01's `main.py` lifespan using `settings.CORS_ORIGINS`.
Verify it is working correctly with the frontend origin.

### 4. Request/Response Models
Ensure every endpoint has typed request and response models:
```python
class CreateDeckRequest(BaseModel):
    document_ids: list[UUID]
    description: str
    outline: str | None = None
    preferences: TeacherPreferences

class DeckResponse(BaseModel):
    deck_id: UUID
    status: str
    syllabus: TopicSyllabus | None
    slide_count: int
    version: int
    created_at: datetime
```

### 5. Lifespan
Already set up in Session 01 using `@asynccontextmanager async def lifespan()`.
Verify all services are initialized in lifespan and stored in `app.state`.

### 6. Missing Endpoints
Add any endpoints not yet created:
- `GET /api/documents` (list all)
- `DELETE /api/documents/{id}` (full cleanup — see below)
- `GET /api/decks` (list all)
- `DELETE /api/decks/{id}` (full cleanup — see below)
- `GET /api/decks/{id}/slides/{slide_id}` (single slide)
- `GET /api/decks/{id}/feedback-history`
- `GET /api/status`

### 6b. Document Deletion Cleanup (CRITICAL)
`DELETE /api/documents/{id}` must clean up ALL associated data, not just DB rows:
```python
async def delete_document(document_id: UUID, db, vector_store, storage):
    """
    Full cleanup sequence:
    1. Delete vectors from Qdrant: vector_store.delete_by_document(document_id)
    2. Delete file from MinIO: storage.delete_file(document.minio_key)  (via upload)
    3. DB CASCADE handles: chunks, deck_documents rows
    4. Delete Document row from DB
    
    Without steps 1-2, deleting a document leaves orphaned vectors in Qdrant
    and orphaned files in MinIO that consume storage indefinitely.
    """
```

### 6c. Deck Deletion Cleanup
`DELETE /api/decks/{id}` must also clean up exported PPTX from MinIO:
```python
async def delete_deck(deck_id: UUID, db, storage):
    """
    1. Delete exported PPTX from MinIO: storage.delete_file(f"exports/{deck_id}/...")
    2. DB CASCADE handles: slides, feedback_rounds, deck_documents
    3. Delete Deck row from DB
    """
```

## Flow
```
1. Create deps.py with all service dependency factories
2. Refactor main.py to use lifespan + DI
3. Add missing endpoints to existing routers
4. Add request/response Pydantic models for every endpoint
5. Add global error handlers
6. Add CORS middleware
7. Test every endpoint end-to-end
8. Verify OpenAPI docs render at /docs
```

## Verification
```bash
# 1. OpenAPI docs load
curl http://localhost:8200/docs
# Expected: Swagger UI HTML (open in browser to inspect)

# 2. All endpoints listed
curl http://localhost:8200/openapi.json | python -m json.tool | grep '"path"'
# Expected: all endpoints from the map above

# 3. Health check
curl http://localhost:8200/health
# Expected: {"status":"ok","version":"0.1.0"}

# 4. System status
curl http://localhost:8200/api/status
# Expected: {"llm_available": true/false, "qdrant": "ok", "valkey": "ok", "minio": "ok"}

# 5. CORS headers
curl -I -X OPTIONS http://localhost:8200/api/decks \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST"
# Expected: Access-Control-Allow-Origin: http://localhost:3000

# 6. Error handling
curl http://localhost:8200/api/decks/00000000-0000-0000-0000-000000000000
# Expected: {"detail":"Deck not found","code":"not_found"} with 404 status

# 7. List endpoints
curl http://localhost:8200/api/documents
curl http://localhost:8200/api/decks
# Expected: [] or list of items

# 8. Full flow test (manual walkthrough)
# Upload → check status → create deck → syllabus feedback → approve →
# retrieve → outline → generate slides → slide feedback → export → download
# Verify each step returns expected responses
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 12 ✅, note all endpoints working, next → Session 13
