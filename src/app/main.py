import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import text

from app.api.export import router as export_router
from app.api.feedback import router as feedback_router
from app.api.generate import router as generate_router
from app.api.syllabus import router as syllabus_router
from app.api.upload import router as upload_router
from app.config import get_settings
from app.core.database import async_engine
from app.core.minio_client import ensure_bucket, get_minio_client
from app.core.qdrant_client import get_qdrant
from app.core.redis_client import get_redis
from app.schemas.common import HealthResponse, SystemStatusResponse
from app.services.embedding import EmbeddingService
from app.services.exporter import PPTXExporter
from app.services.feedback import FeedbackService
from app.services.llm_client import LLMClient, LLMServiceError
from app.services.parsers.base import ParseError
from app.services.rag import RAGService
from app.services.reranker import RerankerService
from app.services.slide_generator import SlideGenerator
from app.services.slide_outline import SlideOutlineService
from app.services.sparse_index import SparseIndexService
from app.services.storage import StorageService
from app.services.syllabus import SyllabusService
from app.services.vector_store import VectorStoreService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("Postgres connection OK")

    redis_client = get_redis()
    await redis_client.ping()
    logger.info("Valkey (Redis) connection OK")

    qdrant_client = get_qdrant()
    await qdrant_client.get_collections()
    logger.info("Qdrant connection OK")

    minio_client = get_minio_client()
    await ensure_bucket(minio_client, settings.MINIO_BUCKET)
    logger.info("MinIO bucket '%s' ready", settings.MINIO_BUCKET)

    storage_service = StorageService(minio_client, settings.MINIO_BUCKET)

    embedding_service = EmbeddingService(
        model_name=settings.EMBEDDING_MODEL,
        dimension=settings.EMBEDDING_DIMENSION,
    )

    vector_store = VectorStoreService(
        qdrant_client, settings.QDRANT_COLLECTION, embedding_service.dimension
    )
    await vector_store.ensure_collection()

    sparse_index = SparseIndexService()

    llm_client = LLMClient(settings.LLM_BASE_URL, settings.LLM_MODEL)
    llm_healthy = await llm_client.health_check()
    if llm_healthy:
        logger.info("vLLM connection OK (model: %s)", settings.LLM_MODEL)
    else:
        logger.warning("vLLM not reachable at %s — LLM calls will fail until it's up", settings.LLM_BASE_URL)

    app.state.redis = redis_client
    app.state.qdrant = qdrant_client
    app.state.minio = minio_client
    app.state.storage_service = storage_service
    app.state.embedding_service = embedding_service
    app.state.vector_store = vector_store
    app.state.sparse_index = sparse_index
    syllabus_service = SyllabusService(llm_client)

    reranker = RerankerService()

    rag_service = RAGService(
        llm=llm_client,
        embedding=embedding_service,
        vector_store=vector_store,
        sparse=sparse_index,
        reranker=reranker,
    )

    slide_outline_service = SlideOutlineService(llm_client)
    slide_generator = SlideGenerator(llm_client, slide_outline_service)
    feedback_service = FeedbackService(llm_client, slide_generator, slide_outline_service)
    exporter = PPTXExporter()

    app.state.llm_client = llm_client
    app.state.syllabus_service = syllabus_service
    app.state.reranker = reranker
    app.state.rag_service = rag_service
    app.state.slide_outline_service = slide_outline_service
    app.state.slide_generator = slide_generator
    app.state.feedback_service = feedback_service
    app.state.exporter = exporter

    logger.info("All services connected — startup complete")
    yield

    # --- SHUTDOWN ---
    await async_engine.dispose()
    await redis_client.aclose()
    await qdrant_client.close()
    logger.info("Shutdown complete")


app = FastAPI(title="Teacher Content Generator", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(LLMServiceError)
async def llm_error_handler(_request: Request, exc: LLMServiceError) -> JSONResponse:
    logger.error("LLM service error: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "code": "llm_error"},
    )


@app.exception_handler(ParseError)
async def parse_error_handler(_request: Request, exc: ParseError) -> JSONResponse:
    logger.error("Parse error: %s", exc)
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": "parse_error"},
    )


@app.exception_handler(ValidationError)
async def validation_error_handler(_request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "code": "validation_error"},
    )


# ---------------------------------------------------------------------------
# Health & status endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)


@app.get("/api/status", response_model=SystemStatusResponse)
async def system_status() -> SystemStatusResponse:
    llm_ok = False
    qdrant_status = "error"
    valkey_status = "error"
    minio_status = "error"

    try:
        llm_ok = await app.state.llm_client.health_check()
    except Exception:
        pass

    try:
        await app.state.qdrant.get_collections()
        qdrant_status = "ok"
    except Exception:
        pass

    try:
        await app.state.redis.ping()
        valkey_status = "ok"
    except Exception:
        pass

    try:
        await asyncio.to_thread(app.state.minio.list_buckets)
        minio_status = "ok"
    except Exception:
        pass

    return SystemStatusResponse(
        llm_available=llm_ok,
        qdrant=qdrant_status,
        valkey=valkey_status,
        minio=minio_status,
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


app.include_router(upload_router)
app.include_router(syllabus_router)
app.include_router(generate_router)
app.include_router(feedback_router)
app.include_router(export_router)
