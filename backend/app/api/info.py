from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.embeddings import OnnxEmbedder

router = APIRouter(tags=["health"])


class InfoResponse(BaseModel):
    """Non-secret configuration, shown on the frontend's About page."""

    app_name: str
    version: str
    embedding_model: str
    embedding_dimension: int
    llm_provider: str
    llm_model: str | None
    rag_min_score: float
    chunk_size_words: int
    chunk_overlap_words: int


@router.get("/info")
def info() -> InfoResponse:
    settings = get_settings()
    return InfoResponse(
        app_name=settings.app_name,
        version="0.1.0",
        embedding_model=OnnxEmbedder.model_name,
        embedding_dimension=OnnxEmbedder.dimension,
        llm_provider=settings.llm_provider,
        llm_model=settings.ollama_model if settings.llm_provider == "ollama" else None,
        rag_min_score=settings.rag_min_score,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
    )
