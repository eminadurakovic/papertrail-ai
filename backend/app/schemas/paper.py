"""API schemas for papers."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.paper import PaperStatus


class AuthorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class PaperSummary(BaseModel):
    """Compact representation used in lists."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    arxiv_id: str
    title: str
    published_date: date
    ingestion_status: PaperStatus
    authors: list[AuthorRead]
    passage_count: int = 0  # filled in by the API from a separate count query


class PaperDetail(PaperSummary):
    """Full representation of a single paper."""

    abstract: str
    source_url: str
    pdf_url: str
    processing_error: str | None
    created_at: datetime
    updated_at: datetime


class PassageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    text: str
    page: int | None
    section: str | None


class IndexPaperResponse(BaseModel):
    paper_id: int
    ingestion_status: PaperStatus
    indexed_passages: int
    embedding_dimension: int
    embedding_model: str


class ProcessPaperResponse(BaseModel):
    paper_id: int
    ingestion_status: PaperStatus
    page_count: int
    extracted_characters: int
    passage_count: int


class ImportPaperRequest(BaseModel):
    arxiv_id: str = Field(min_length=1, max_length=100, examples=["1706.03762"])


class ImportPaperResponse(BaseModel):
    created: bool  # False if the paper was already imported
    paper: PaperDetail
