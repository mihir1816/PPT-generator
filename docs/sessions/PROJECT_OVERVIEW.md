# Teacher Content Generator — Complete Project Overview

## What This Is
A product that generates PowerPoint presentations from uploaded documents. Teachers upload content (PDF, PPTX, DOCX, URLs, images), provide instructions, and the system generates a complete slide deck with iterative feedback at two stages.

## The 9-Stage Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: USER INPUT                                             │
│   Upload docs (PDF/PPTX/DOCX/URL/Image)                        │
│   Choose: Tone (Formal / Creative)                              │
│   Choose: Content (Grounded / Mixed)                            │
│   Choose: Level (Beginner / Intermediate / Advanced)            │
│   Write: Description text                                       │
│   Optional: Provide outline text                                │
└──────────────────────┬──────────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────────┐   ┌──────────────────────────┐
│ STAGE 2A: BACKGROUND│   │ STAGE 2B: FOREGROUND     │
│ Parse → Chunk →     │   │ LLM generates Topic      │
│ Embed → Store in    │   │ Syllabus from description │
│ Qdrant + BM25S      │   │ + outline (if given)      │
│ (Celery worker)     │   │                           │
└────────┬────────────┘   └────────────┬──────────────┘
         │                             │
         │                             ▼
         │                  ┌──────────────────────────┐
         │                  │ STAGE 3: FEEDBACK LOOP #1│
         │                  │ User reviews syllabus    │
         │                  │ Add/remove/reorder topics│
         │                  │ Loop until approved      │
         │                  └────────────┬─────────────┘
         │                               │
         ▼                               ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 4: WAIT GATE                                   │
│ Both must complete: vectorization ✓ + syllabus ✓     │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 5: RAG RETRIEVAL                               │
│ Syllabus topics → multiple queries → embed →         │
│ Qdrant dense search + BM25S sparse → RRF fusion →   │
│ FlashRank rerank → collected chunks per topic        │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 6: SLIDE OUTLINE                               │
│ LLM takes syllabus + retrieved chunks + preferences  │
│ → maps topics to slides (split tables, layout hints) │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 7: SLIDE CONTENT GENERATION                    │
│ Per slide: outline entry + chunks → LLM → JSON       │
│ Streamed via SSE to frontend (slide by slide)        │
│ Grounded: only doc content | Mixed: LLM fills gaps   │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 8: FEEDBACK LOOP #2                            │
│ User reviews slides → expand/add/remove/edit         │
│ Parse feedback → update outline → regen ONLY affected│
│ Loop until finalized                                 │
└──────────────────────┬──────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────┐
│ STAGE 9: EXPORT                                      │
│ python-pptx generates PPTX → MinIO → user downloads │
└─────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology | License | Why |
|-----------|-----------|---------|-----|
| **LLM** | Qwen3-30B-A3B Q4 (AWQ) | Apache 2.0 | MoE, 3.3B active, 70B quality, ~17GB VRAM |
| **LLM Inference** | vLLM (Docker) | Apache 2.0 | OpenAI-compatible API, continuous batching |
| **Embedding** | nomic-embed-text-v2-moe via FastEmbed | Apache 2.0 | MoE embedding, 4x faster than sentence-transformers |
| **Vector DB** | Qdrant | Apache 2.0 | Native hybrid search, 4ms latency |
| **Sparse Search** | BM25S | MIT | 500x faster than rank-bm25 |
| **Reranker** | FlashRank | Apache 2.0 | 4MB, zero torch deps, CPU-only |
| **Chunking** | Parent-Document Hierarchical | MIT | langchain-text-splitters, 512 token chunks |
| **Backend** | FastAPI | MIT | Async, SSE support, auto docs |
| **Task Queue** | Celery + Valkey | BSD / BSD | Async document processing (Valkey = BSD-3 Redis fork by Linux Foundation) |
| **Database** | PostgreSQL 16 | PostgreSQL License | SQLAlchemy 2.0 + Alembic |
| **File Storage** | MinIO | AGPL (self-host OK) | S3-compatible, Docker |
| **Streaming** | SSE (Server-Sent Events) | — | Slide-by-slide to frontend |
| **Frontend** | React + Vite + TailwindCSS | MIT | SPA with real-time updates |
| **Export** | python-pptx | MIT | PowerPoint generation |
| **PDF Parser** | pdfplumber + Docling | MIT | Tables + complex layouts |
| **PPTX Parser** | python-pptx | MIT | Slide content extraction |
| **DOCX Parser** | python-docx | MIT | Word document extraction |
| **Web Parser** | trafilatura | Apache 2.0 | Article extraction |
| **OCR** | Tesseract + pytesseract | Apache 2.0 | Scanned documents (lightweight, ~50MB vs PaddleOCR's ~3GB) |
| **Containers** | Docker Compose | Apache 2.0 | All services containerized |

## Directory Structure

```
teacher-content-gen/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── .dockerignore
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py                  # FastAPI entry + lifespan
│       ├── deps.py                  # FastAPI Depends() factories
│       ├── config.py                # Pydantic BaseSettings
│       ├── schemas/                 # Pydantic v2 models
│       │   ├── document.py          # ProcessedDocument, ContentBlock
│       │   ├── deck.py              # DeckState, SlideOutline, SlideContent
│       │   ├── syllabus.py          # TopicSyllabus, SyllabusTopic
│       │   └── common.py            # StatusEnum, responses
│       ├── models/                  # SQLAlchemy ORM
│       │   ├── base.py
│       │   ├── upload.py
│       │   ├── document.py
│       │   ├── chunk.py
│       │   ├── deck.py
│       │   ├── deck_document.py
│       │   ├── slide.py
│       │   └── feedback.py
│       ├── services/                # Business logic
│       │   ├── storage.py           # MinIO wrapper
│       │   ├── crud.py              # DB CRUD helpers
│       │   ├── llm_client.py        # vLLM OpenAI client
│       │   ├── prompt_templates.py  # All LLM prompts
│       │   ├── syllabus.py          # Topic syllabus gen + feedback
│       │   ├── rag.py               # Retrieval pipeline
│       │   ├── slide_outline.py     # Slide outline generation
│       │   ├── slide_generator.py   # Content generation + streaming
│       │   ├── feedback.py          # Feedback loop #2 logic
│       │   ├── exporter.py          # PPTX export
│       │   └── parsers/
│       │       ├── __init__.py
│       │       ├── base.py
│       │       ├── router.py
│       │       ├── pdf_parser.py
│       │       ├── text_parser.py
│       │       ├── docx_parser.py
│       │       ├── web_parser.py
│       │       ├── pptx_parser.py
│       │       └── ocr_parser.py
│       ├── api/                     # FastAPI routers
│       │   ├── upload.py
│       │   ├── syllabus.py
│       │   ├── generate.py
│       │   ├── feedback.py
│       │   └── export.py
│       ├── tasks/                   # Celery tasks
│       │   ├── process_upload.py
│       │   └── indexing.py
│       └── core/                    # Infrastructure clients
│           ├── database.py
│           ├── redis_client.py
│           ├── qdrant_client.py
│           ├── minio_client.py
│           └── celery_app.py
├── frontend/                        # React SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   └── Dockerfile
└── tests/
```

## Docker Services & Ports

| Service | Image | Port (Host) | Purpose |
|---------|-------|-------------|---------|
| postgres | postgres:16-alpine | 5433 | Main database |
| valkey | valkey/valkey:8-alpine | 6380 | Celery broker + cache (BSD-3 Redis fork) |
| qdrant | qdrant/qdrant:v1.14.0 | 6333, 6334 | Vector database |
| minio | minio/minio:latest | 9000, 9001 | File storage |
| vllm | vllm/vllm-openai:latest | 8100 | LLM inference (GPU) |
| app | Custom (Dockerfile) | 8200 | FastAPI backend |
| celery-worker | Same as app | — | Async task processing |
| frontend | Custom (frontend/Dockerfile) | 3000 | React UI |

## Non-Negotiable Rules
1. ALL libraries FREE and open-source (MIT / Apache 2.0 / BSD)
2. LLM: Qwen3-30B-A3B Q4 (AWQ) only
3. If user provides outline → LLM STRICTLY follows it
4. Feedback Loop #1 on syllabus BEFORE content generation
5. Feedback Loop #2 on slides → only regenerate AFFECTED slides
6. No web search (deferred)
7. No concurrent user optimization (single user now)
8. Production-quality modular code
9. Everything in Docker
10. No PyMuPDF (AGPL), No Surya (GPL), No PaddleOCR (too heavy ~3GB) — license-safe and lightweight only
11. Grounded mode = ONLY doc content | Mixed = LLM fills gaps, not entire slides
12. No hardcoded values — all config from environment

## Session Plan
14 sessions total. Each completable in 1 AI agent prompt.
See individual SESSION_XX_*.md files for details.
