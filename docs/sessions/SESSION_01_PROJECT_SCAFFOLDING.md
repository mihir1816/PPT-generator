# Session 01 — Project Scaffolding & Docker Infrastructure

## Goal
Create the full project skeleton, Docker Compose with all services, shared Pydantic schemas, config, and Dockerfile. After this session, `docker compose up` boots all infra and FastAPI responds on `/health`.

## Read First
- `docs/sessions/PROJECT_OVERVIEW.md` — full architecture and tech stack
- `docs/sessions/SESSION_TRACKER.md` — current state

## Non-Negotiable Rules
- ALL code inside `teacher-content-gen/` directory
- Python 3.12+, `pyproject.toml` (no setup.py)
- `src/` layout: `teacher-content-gen/src/app/`
- Every service in Docker — no bare-metal
- `.env.example` with every variable documented
- No hardcoded values — all config from environment
- Type hints on every function
- Pydantic v2 for all schemas

## What to Build

### 1. `docker-compose.yml` — 8 services

**postgres**: `postgres:16-alpine`, port `5433:5432`, volume `tcg_pgdata`, healthcheck `pg_isready`

**valkey**: `valkey/valkey:8-alpine`, port `6380:6379`, volume `tcg_redisdata`, healthcheck `valkey-cli ping`. BSD-3 licensed (Redis 7.4+ is SSPL, not OSI open source). Valkey is the Linux Foundation Redis fork — fully API-compatible, drop-in replacement.

**qdrant**: `qdrant/qdrant:v1.14.0`, ports `6333:6333` + `6334:6334`, volume `tcg_qdrantdata`, healthcheck `curl http://localhost:6333/healthz`

**minio**: `minio/minio:latest`, ports `9000:9000` + `9001:9001`, volume `tcg_miniodata`, command `server /data --console-address ":9001"`, healthcheck curl

**vllm**: `vllm/vllm-openai:latest`, port `8100:8000`, GPU required, args: `--model Qwen/Qwen3-30B-A3B-AWQ --quantization awq --max-model-len 16384 --gpu-memory-utilization 0.90 --trust-remote-code --dtype half`, volume `tcg_vllm_cache:/root/.cache/huggingface`. Use Docker Compose `profiles: [gpu]` so devs without GPU can skip it.

**app**: build from `./Dockerfile`, port `8200:8000`, depends on postgres+valkey+qdrant+minio, command `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`, mount `./src` for hot reload

**celery-worker**: same Dockerfile, command `celery -A app.core.celery_app worker --loglevel=info --concurrency=4 --autoscale=4,1`, depends on valkey+postgres+qdrant+minio, no port. Autoscale: 4 max / 1 min workers (handles burst uploads without idle waste).

**frontend**: build from `./frontend/Dockerfile`, port `3000:3000`, depends on app (placeholder — built in Session 13)

### 2. `Dockerfile`
```
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl libgl1-mesa-glx libglib2.0-0 \
    poppler-utils libmagic1 tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
ENV PYTHONPATH=/app/src
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3. `pyproject.toml`
Dependencies (all with current versions):
```
fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, psycopg2-binary,
alembic, redis[hiredis], celery, qdrant-client, minio, pydantic-settings,
pdfplumber, docling, python-pptx, python-docx, trafilatura,
pytesseract, Pillow, python-magic, fastembed, bm25s, flashrank,
openai, httpx, sse-starlette, python-multipart
```

### 4. `src/app/config.py` — Pydantic BaseSettings
```python
class Settings(BaseSettings):
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_NAME: str = "teacher_content_gen"
    DB_USER: str = "tcg_user"
    DB_PASSWORD: str
    REDIS_HOST: str = "valkey"
    REDIS_PORT: int = 6379
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    MINIO_HOST: str = "minio"
    MINIO_PORT: int = 9000
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "tcg-uploads"
    LLM_BASE_URL: str = "http://vllm:8000/v1"
    LLM_MODEL: str = "Qwen/Qwen3-30B-A3B-AWQ"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7
    CELERY_BROKER_URL: str = "redis://valkey:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://valkey:6379/1"
    MAX_UPLOAD_SIZE_MB: int = 50
    LLM_TIMEOUT: int = 120
    LLM_JSON_RETRIES: int = 1
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def database_url(self) -> str: ...       # postgresql+asyncpg://...
    @property
    def sync_database_url(self) -> str: ...  # postgresql+psycopg2://...
    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
```

### 5. Shared Schemas (Pydantic v2)

**`schemas/document.py`**: SourceType (PDF/PLAIN_TEXT/WEB_URL/PPTX/DOCX/IMAGE_OCR), ContentType (HEADING/PARAGRAPH/BULLET_LIST/NUMBERED_LIST/TABLE/IMAGE_DESCRIPTION/CODE_BLOCK/QUOTE), ContentBlock, ProcessedDocument (with `to_markdown()` method)

**`schemas/syllabus.py`**: SyllabusTopic (title, subtopics list, depth_hint, notes), TopicSyllabus (title, topics list, audience_level, estimated_slides), SyllabusFeedback (action: add/remove/expand/reorder/modify, target_topic, instruction)

**`schemas/deck.py`**: SlideType, SlideStatus, SlideOutline, SlideContent, TeacherPreferences (audience_level, tone: formal/creative, content_mode: grounded/mixed, slide_count_hint, additional_instructions), DeckState

**`schemas/common.py`**: TaskStatus enum (pending/processing/completed/failed), DeckStatus enum (pending/generating_syllabus/syllabus_review/waiting_for_indexing/ready_for_retrieval/retrieving/retrieval_complete/generating_outline/outline_ready/generating_slides/completed/failed), UploadResponse, GenerationStatus, ErrorResponse

**Note**: `DeckStatus` is the SINGLE SOURCE OF TRUTH for all deck state transitions. Every session that changes deck status MUST use values from this enum.

### 6. Core Clients (thin wrappers in `core/`)

**`core/database.py`**: async engine (`create_async_engine`), `AsyncSession` factory, `get_db()` dependency, sync engine + session for Celery

**`core/redis_client.py`**: `redis.asyncio` client, `get_redis()` singleton

**`core/qdrant_client.py`**: `AsyncQdrantClient`, `get_qdrant()` singleton

**`core/minio_client.py`**: `minio.Minio` client, `ensure_bucket()` at startup

**`core/celery_app.py`**: Celery app instance, broker/backend from settings, autodiscover `app.tasks`

### 7. `main.py`
```python
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP:
    # Test DB, Redis, Qdrant connections
    # Ensure MinIO bucket exists
    # Ensure Qdrant collection exists
    # Initialize singleton services (EmbeddingService, RerankerService, LLMClient)
    # Store in app.state for DI access
    # Log: all services connected
    yield
    # SHUTDOWN:
    # Close DB engine, Redis connections

app = FastAPI(title="Teacher Content Generator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health(): return {"status": "ok", "version": "0.1.0"}
```

### 7b. Dependency Injection Foundation (`deps.py`)
Set up DI from the start so all sessions use `Depends()` consistently:
```python
from app.config import get_settings

def get_llm_client(request: Request) -> LLMClient:
    return request.app.state.llm_client

def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service

def get_storage_service(request: Request) -> StorageService:
    return request.app.state.storage_service

# Add more as services are created in later sessions.
# Each session adds its service's DI factory here.
```
All subsequent sessions MUST use `Depends()` to access services in endpoints — never direct instantiation.

### 8. Alembic init
- `alembic.ini` pointing to `alembic/` directory
- `alembic/env.py` configured with `Base.metadata` and `sync_database_url`
- Empty `alembic/versions/` directory

### 9. `.env.example`, `.dockerignore`

## Flow
```
1. Create teacher-content-gen/ directory
2. Write pyproject.toml
3. Write Dockerfile + .dockerignore
4. Write docker-compose.yml (all 8 services)
5. Write .env.example → copy to .env
6. Write config.py
7. Write all schema files (including DeckStatus enum in common.py)
8. Write all core client files
9. Write main.py (with lifespan, CORS)
10. Write deps.py (DI foundation)
11. Write alembic.ini + alembic/env.py
12. Create empty __init__.py in all packages
```

## Verification
```bash
cd teacher-content-gen

# 1. Start infra (skip vllm if no GPU)
docker compose up -d postgres valkey qdrant minio
docker compose up -d --build app

# 2. All containers healthy
docker compose ps
# Expected: postgres, valkey, qdrant, minio, app — "healthy"

# 3. Health endpoint
curl http://localhost:8200/health
# Expected: {"status":"ok","version":"0.1.0"}

# 4. MinIO console loads
# http://localhost:9001 — login minioadmin/minioadmin123, bucket "tcg-uploads" exists

# 5. Qdrant dashboard loads
# http://localhost:6333/dashboard

# 6. Schemas import cleanly
docker compose exec app python -c "
from app.schemas.document import ProcessedDocument
from app.schemas.deck import DeckState
from app.schemas.syllabus import TopicSyllabus
print('All schemas OK')
"

# 7. Celery worker starts
docker compose up -d celery-worker
docker compose logs celery-worker --tail=20
# Expected: "ready" with no import errors
```

## On Completion
Update `SESSION_TRACKER.md`: mark Session 01 ✅, list files, set next → Session 02
