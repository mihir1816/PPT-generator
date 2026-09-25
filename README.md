# PPT Generator (Teacher Content Gen)

Generates PowerPoint presentations from uploaded documents using RAG + LLM.

## Features

- Multi-format document ingestion (PDF, DOCX, TXT)
- Hybrid search with dense vector embeddings and BM25 reranking
- Presentation structure generation with LLM integration
- Custom presentation slide styling and automated PPTX export
- FastAPI backend with Celery background task processing
- Modern React/Vite frontend interface

## Tech Stack

- **Backend**: FastAPI, Celery, SQLAlchemy, Alembic, PostgreSQL, Valkey / Redis, Qdrant, MinIO
- **Frontend**: React, Vite, TailwindCSS
- **ML / AI**: OpenAI / vLLM, FastEmbed, FlashRank, LangChain splitters

## Setup

1. Copy `.env.example` to `.env` and fill in necessary credentials:
   ```bash
   cp .env.example .env
   ```

2. Start the core services:
   ```bash
   docker compose up -d
   ```

3. Install Python dependencies:
   ```bash
   pip install -e .
   ```

4. Run database migrations:
   ```bash
   alembic upgrade head
   ```

5. Run the frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
