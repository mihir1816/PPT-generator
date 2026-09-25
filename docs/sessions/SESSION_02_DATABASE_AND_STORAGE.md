# Session 02 — Database Models & Storage Layer

## Goal
Create all PostgreSQL tables (SQLAlchemy ORM), run Alembic migrations, build MinIO storage service, and async CRUD helpers. After this session, DB has all tables and files can be uploaded/downloaded via MinIO.

## Read First
- `docs/sessions/SESSION_TRACKER.md` — confirm Session 01 complete
- `src/app/config.py` — DB/MinIO settings
- `src/app/core/database.py` — engine + session factory
- `src/app/core/minio_client.py` — MinIO client
- `src/app/schemas/` — all Pydantic schemas (mirror to DB models)

## Non-Negotiable Rules
- Async SQLAlchemy 2.0 (mapped_column, DeclarativeBase)
- Every model: `id` (UUID PK), `created_at`, `updated_at` with `server_default=func.now()`
- Foreign keys with `ondelete="CASCADE"` where parent deletion cascades
- Alembic migrations must be auto-generatable
- MinIO ops wrapped with `asyncio.to_thread()` (SDK is sync)
- No business logic in models — pure data

## Models to Create

### `models/base.py`
Base class + TimestampMixin (created_at, updated_at)

### `models/upload.py` — Upload
```
id: UUID PK
filename: str
source_type: str (pdf/plain_text/web_url/pptx/docx/image_ocr)
mime_type: str | None
file_size: int | None
minio_key: str
status: str (pending/processing/completed/failed)
error_message: str | None
metadata_json: JSON | None
```

### `models/document.py` — Document
```
id: UUID PK
upload_id: UUID FK → Upload (CASCADE)
title: str | None
source_type: str
raw_text: Text
content_blocks: JSON (list of ContentBlock dicts)
markdown_content: Text
chunk_count: int = 0
is_indexed: bool = False
```

### `models/chunk.py` — Chunk
```
id: UUID PK
document_id: UUID FK → Document (CASCADE)
chunk_index: int
content: Text
parent_content: Text | None (for parent-doc chunking — stores larger parent chunk)
metadata_json: JSON
embedding_id: str | None (Qdrant point ID)
token_count: int
UniqueConstraint: (document_id, chunk_index)
```

### `models/deck.py` — Deck
```
id: UUID PK
teacher_query: Text
preferences_json: JSON (TeacherPreferences)
syllabus_json: JSON | None (TopicSyllabus — approved)
syllabus_status: str (pending/generating/feedback/approved)
status: str — uses DeckStatus enum from schemas/common.py (pending/generating_syllabus/syllabus_review/waiting_for_indexing/ready_for_retrieval/retrieving/retrieval_complete/generating_outline/outline_ready/generating_slides/completed/failed)
outline_json: JSON | None (list of SlideOutline)
retrieval_json: JSON | None (RetrievalResult — persisted, NOT in Redis with TTL)
document_map: Text | None
version: int = 0
```
**Why `retrieval_json` in DB instead of Redis?**: Retrieval results are needed throughout the feedback lifecycle (hours/days). A Redis TTL would expire mid-workflow. DB storage ensures retrieval data survives restarts and long review sessions.

Relationships: slides, feedback_rounds, deck_documents

### `models/deck_document.py` — DeckDocument (M2M)
```
id: UUID PK
deck_id: UUID FK → Deck (CASCADE)
document_id: UUID FK → Document (CASCADE)
UniqueConstraint: (deck_id, document_id)
```

### `models/slide.py` — Slide
```
id: UUID PK
deck_id: UUID FK → Deck (CASCADE)
slide_id: str (e.g. "slide_1")
position: int
title: str
body: Text
bullet_points: JSON
table_data: JSON | None
speaker_notes: Text = ""
layout_hint: str = "bullet"
outline_version: int
Index: (deck_id, position)
```

### `models/feedback.py` — FeedbackRound
```
id: UUID PK
deck_id: UUID FK → Deck (CASCADE)
round_number: int
feedback_type: str (syllabus/per_slide/whole_deck/structural)
raw_feedback: Text
parsed_actions_json: JSON
affected_slide_ids: JSON
outline_snapshot_json: JSON (outline BEFORE changes — for undo)
slides_snapshot_json: JSON (full slide data BEFORE changes — for undo)
syllabus_snapshot_json: JSON | None (syllabus BEFORE changes — for syllabus feedback undo)
```
**Why `slides_snapshot_json`?**: The Slide model has no version history. When slides are regenerated, old content is overwritten. Without snapshots, undo cannot restore previous slide content. This stores `[{slide_id, title, body, bullet_points, ...}]` for all affected slides before modification.

### `models/__init__.py`
Import all models so Alembic sees them.

## Storage Service — `services/storage.py`
```python
class StorageService:
    upload_file(file: UploadFile, key: str) -> str
    upload_bytes(data: bytes, key: str, content_type: str) -> str
    download_file(key: str) -> bytes
    get_presigned_url(key: str, expires: int = 3600) -> str
    delete_file(key: str) -> None
    generate_key(upload_id: str, filename: str) -> str
        # returns "uploads/{upload_id}/{filename}"
```
All methods use `asyncio.to_thread()` for async.

## CRUD Helpers — `services/crud.py`
Async functions for each model:
```
create_upload, get_upload, update_upload_status
create_document, get_document, get_documents_by_upload
create_chunks_bulk, get_chunks_by_document, get_chunks_by_ids
create_deck, get_deck, update_deck_status, update_deck_syllabus, update_deck_outline
link_deck_document, get_deck_documents
create_slide, create_slides_bulk, get_slides_by_deck, update_slide, delete_slides_by_deck
create_feedback_round, get_feedback_rounds_by_deck, get_last_feedback_round
update_deck_retrieval, get_deck_retrieval
```

## Alembic
- Update `alembic/env.py`: import Base, set target_metadata, use sync_database_url
- Generate: `alembic revision --autogenerate -m "initial_tables"`
- Run: `alembic upgrade head`

## Flow
```
1. Create models/base.py
2. Create all model files
3. Update models/__init__.py
4. Update alembic/env.py
5. Create services/storage.py
6. Create services/crud.py
7. Generate + run migration
8. Test
```

## Verification
```bash
# 1. Run migration
docker compose exec app alembic upgrade head
# Expected: no errors

# 2. Tables exist
docker compose exec postgres psql -U tcg_user -d teacher_content_gen -c "\dt"
# Expected: uploads, documents, chunks, decks, deck_documents, slides, feedback_rounds

# 3. CRUD test
docker compose exec app python -c "
import asyncio
from app.core.database import async_session
from app.services.crud import create_upload, get_upload
async def test():
    async with async_session() as db:
        u = await create_upload(db, filename='test.pdf', source_type='pdf', minio_key='test/test.pdf')
        await db.commit()
        fetched = await get_upload(db, u.id)
        assert fetched.filename == 'test.pdf'
        print(f'CRUD OK: {fetched.id}')
asyncio.run(test())
"

# 4. MinIO test
docker compose exec app python -c "
import asyncio
from app.services.storage import StorageService
from app.core.minio_client import get_minio_client
from app.config import get_settings
async def test():
    s = get_settings()
    svc = StorageService(get_minio_client(s), s.MINIO_BUCKET)
    await svc.upload_bytes(b'hello', 'test/verify.txt', 'text/plain')
    data = await svc.download_file('test/verify.txt')
    assert data == b'hello'
    await svc.delete_file('test/verify.txt')
    print('MinIO OK')
asyncio.run(test())
"

# 5. No pending migrations
docker compose exec app alembic check
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 02 ✅, list files, next → Session 03
