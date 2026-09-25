"""FastAPI dependency-injection factories.

Every endpoint accesses services via `Depends()` from this module — never by
direct instantiation. Services are created once in `main.py`'s lifespan and
stored on `app.state`; each factory here just reads them back off the request.
"""

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from app.services.embedding import EmbeddingService
    from app.services.exporter import PPTXExporter
    from app.services.feedback import FeedbackService
    from app.services.llm_client import LLMClient
    from app.services.rag import RAGService
    from app.services.reranker import RerankerService
    from app.services.slide_generator import SlideGenerator
    from app.services.slide_outline import SlideOutlineService
    from app.services.sparse_index import SparseIndexService
    from app.services.storage import StorageService
    from app.services.syllabus import SyllabusService
    from app.services.vector_store import VectorStoreService


def get_llm_client(request: Request) -> "LLMClient":
    return request.app.state.llm_client


def get_embedding_service(request: Request) -> "EmbeddingService":
    return request.app.state.embedding_service


def get_storage_service(request: Request) -> "StorageService":
    return request.app.state.storage_service


def get_vector_store(request: Request) -> "VectorStoreService":
    return request.app.state.vector_store


def get_sparse_index(request: Request) -> "SparseIndexService":
    return request.app.state.sparse_index


def get_reranker(request: Request) -> "RerankerService":
    return request.app.state.reranker


def get_syllabus_service(request: Request) -> "SyllabusService":
    return request.app.state.syllabus_service


def get_rag_service(request: Request) -> "RAGService":
    return request.app.state.rag_service


def get_slide_outline_service(request: Request) -> "SlideOutlineService":
    return request.app.state.slide_outline_service


def get_slide_generator(request: Request) -> "SlideGenerator":
    return request.app.state.slide_generator


def get_feedback_service(request: Request) -> "FeedbackService":
    return request.app.state.feedback_service


def get_exporter(request: Request) -> "PPTXExporter":
    return request.app.state.exporter
