from collections.abc import Generator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.arxiv import ArxivClient
from app.services.embeddings import Embedder, EmbeddingModelUnavailableError, OnnxEmbedder
from app.services.llm import LLMClient
from app.services.ollama import OllamaClient
from app.services.pdf import PdfDownloader

USER_AGENT = "papertrail-ai/0.1 (local portfolio project)"


def _http_client(timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout_seconds, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )


def get_arxiv_client() -> Generator[ArxivClient, None, None]:
    settings = get_settings()
    with _http_client(settings.arxiv_timeout_seconds) as http_client:
        yield ArxivClient(http_client, settings.arxiv_api_url)


def get_pdf_downloader() -> Generator[PdfDownloader, None, None]:
    settings = get_settings()
    with _http_client(settings.pdf_timeout_seconds) as http_client:
        yield PdfDownloader(http_client, settings.pdf_max_bytes)


@lru_cache(maxsize=1)
def _load_embedder(model_dir: Path, batch_size: int) -> OnnxEmbedder:
    # Loading the model takes a moment, so do it once per process and reuse it.
    return OnnxEmbedder(model_dir, batch_size=batch_size)


def get_embedder() -> Embedder:
    settings = get_settings()
    try:
        return _load_embedder(settings.embedding_model_dir, settings.embedding_batch_size)
    except EmbeddingModelUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def get_llm() -> Generator[LLMClient | None, None, None]:
    """The configured language model, or None if answer generation is disabled."""
    settings = get_settings()
    if settings.llm_provider == "none":
        yield None
        return
    # Local server: no User-Agent or redirects needed, just a generous timeout.
    with httpx.Client(timeout=settings.llm_timeout_seconds) as http_client:
        yield OllamaClient(http_client, settings.ollama_url, settings.ollama_model)


# Route parameter types resolved by FastAPI's dependency injection.
DbSession = Annotated[Session, Depends(get_db)]
ArxivDep = Annotated[ArxivClient, Depends(get_arxiv_client)]
DownloaderDep = Annotated[PdfDownloader, Depends(get_pdf_downloader)]
EmbedderDep = Annotated[Embedder, Depends(get_embedder)]
LLMDep = Annotated[LLMClient | None, Depends(get_llm)]
