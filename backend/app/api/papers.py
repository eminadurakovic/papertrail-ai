from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import ArxivDep, DbSession, DownloaderDep, EmbedderDep
from app.core.config import get_settings
from app.models import Paper
from app.schemas.paper import (
    ImportPaperRequest,
    ImportPaperResponse,
    IndexPaperResponse,
    PaperDetail,
    PaperSummary,
    PassageRead,
    ProcessPaperResponse,
)
from app.services import indexing, ingestion, processing
from app.services import papers as paper_service
from app.services.arxiv import (
    ArxivPaperNotFoundError,
    ArxivResponseError,
    ArxivUnavailableError,
    InvalidArxivIdError,
)
from app.services.embeddings import EmbeddingError
from app.services.pdf import PdfDownloadError, PdfUnavailableError, UnprocessableDocumentError

router = APIRouter(prefix="/papers", tags=["papers"])

# Each known failure maps to one HTTP status. The exception message is user-friendly;
# stack traces only go to the server log.
ErrorTable = dict[type[Exception], int]

IMPORT_ERRORS: ErrorTable = {
    InvalidArxivIdError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ArxivPaperNotFoundError: status.HTTP_404_NOT_FOUND,
    ArxivResponseError: status.HTTP_502_BAD_GATEWAY,
    ArxivUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    ingestion.IngestionDatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}

PROCESS_ERRORS: ErrorTable = {
    processing.PaperNotFoundError: status.HTTP_404_NOT_FOUND,
    UnprocessableDocumentError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    PdfDownloadError: status.HTTP_502_BAD_GATEWAY,
    PdfUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    processing.ProcessingDatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}

INDEX_ERRORS: ErrorTable = {
    processing.PaperNotFoundError: status.HTTP_404_NOT_FOUND,
    indexing.NotProcessedError: status.HTTP_409_CONFLICT,
    EmbeddingError: status.HTTP_500_INTERNAL_SERVER_ERROR,
    indexing.IndexingDatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def _paper_detail(db: DbSession, paper: Paper) -> PaperDetail:
    count = paper_service.passage_counts(db, [paper.id]).get(paper.id, 0)
    return PaperDetail.model_validate(paper).model_copy(update={"passage_count": count})


def _to_http_error(exc: Exception, table: ErrorTable) -> HTTPException:
    status_code = next(code for error_type, code in table.items() if isinstance(exc, error_type))
    return HTTPException(status_code=status_code, detail=str(exc))


@router.get("")
def list_papers(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PaperSummary]:
    papers = paper_service.list_papers(db, limit=limit, offset=offset)
    counts = paper_service.passage_counts(db, [paper.id for paper in papers])
    return [
        PaperSummary.model_validate(paper).model_copy(
            update={"passage_count": counts.get(paper.id, 0)}
        )
        for paper in papers
    ]


@router.post(
    "/import",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Paper was already imported; the stored paper is returned"},
        404: {"description": "No such paper on arXiv"},
        422: {"description": "Invalid arXiv ID"},
        502: {"description": "arXiv returned an unusable response"},
        503: {"description": "arXiv could not be reached"},
    },
)
def import_paper(
    request: ImportPaperRequest, response: Response, db: DbSession, arxiv: ArxivDep
) -> ImportPaperResponse:
    """Import a paper's metadata from arXiv. Importing the same paper again is a no-op."""
    try:
        result = ingestion.import_paper(db, request.arxiv_id, arxiv)
    except tuple(IMPORT_ERRORS) as exc:
        raise _to_http_error(exc, IMPORT_ERRORS) from exc

    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ImportPaperResponse(created=result.created, paper=_paper_detail(db, result.paper))


@router.get("/{paper_id}")
def get_paper(paper_id: int, db: DbSession) -> PaperDetail:
    paper = paper_service.get_paper(db, paper_id)
    if paper is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return _paper_detail(db, paper)


@router.post(
    "/{paper_id}/process",
    responses={
        404: {"description": "Paper not found"},
        422: {"description": "The PDF could not be used (not a PDF, too large, no text)"},
        502: {"description": "The PDF server returned an unexpected response"},
        503: {"description": "The PDF could not be downloaded right now"},
    },
)
def process_paper(paper_id: int, db: DbSession, downloader: DownloaderDep) -> ProcessPaperResponse:
    """Download the paper's PDF, extract its text and (re)build its passages."""
    settings = get_settings()
    try:
        result = processing.process_paper(
            db,
            paper_id,
            downloader,
            chunk_size=settings.chunk_size_words,
            chunk_overlap=settings.chunk_overlap_words,
        )
    except tuple(PROCESS_ERRORS) as exc:
        raise _to_http_error(exc, PROCESS_ERRORS) from exc

    return ProcessPaperResponse(
        paper_id=result.paper.id,
        ingestion_status=result.paper.ingestion_status,
        page_count=result.page_count,
        extracted_characters=result.extracted_characters,
        passage_count=result.passage_count,
    )


@router.post(
    "/{paper_id}/index",
    responses={
        404: {"description": "Paper not found"},
        409: {"description": "The paper has not been processed yet"},
        503: {"description": "The embedding model is not available"},
    },
)
def index_paper(paper_id: int, db: DbSession, embedder: EmbedderDep) -> IndexPaperResponse:
    """Compute and store an embedding for every passage of the paper. Safe to repeat."""
    try:
        result = indexing.index_paper(db, paper_id, embedder)
    except tuple(INDEX_ERRORS) as exc:
        raise _to_http_error(exc, INDEX_ERRORS) from exc

    return IndexPaperResponse(
        paper_id=result.paper.id,
        ingestion_status=result.paper.ingestion_status,
        indexed_passages=result.indexed_passages,
        embedding_dimension=result.dimension,
        embedding_model=result.model_name,
    )


@router.get("/{paper_id}/passages")
def list_passages(paper_id: int, db: DbSession) -> list[PassageRead]:
    """All passages of a paper in order. Empty if the paper has not been processed yet."""
    if paper_service.get_paper(db, paper_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found")
    return [PassageRead.model_validate(p) for p in paper_service.list_passages(db, paper_id)]
