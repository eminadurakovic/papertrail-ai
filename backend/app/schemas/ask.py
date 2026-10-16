from pydantic import BaseModel, Field

from app.schemas.search import QueryText


class AskRequest(BaseModel):
    question: QueryText = Field(examples=["What limitation does the method identify?"])
    # Empty list = use all indexed papers.
    paper_ids: list[int] = Field(default_factory=list, max_length=100)
    top_k: int = Field(default=5, ge=1, le=10)


class CitationRead(BaseModel):
    number: int  # matches [number] in the answer text
    paper_id: int
    paper_title: str
    arxiv_id: str
    passage_id: int
    position: int
    page: int | None
    passage_text: str
    score: float


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    # no_relevant_passages | model_insufficient_evidence | no_valid_citations
    abstention_reason: str | None
    citations: list[CitationRead]
    best_score: float | None  # highest retrieval score among the searched passages
