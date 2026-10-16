from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Leading/trailing whitespace is stripped first, so "   " counts as empty.
QueryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class SearchRequest(BaseModel):
    query: QueryText = Field(examples=["How does the model use attention?"])
    limit: int = Field(default=5, ge=1, le=50)
    # Empty list = search all indexed papers.
    paper_ids: list[int] = Field(default_factory=list, max_length=100)


class SearchResult(BaseModel):
    paper_id: int
    title: str
    arxiv_id: str
    passage_id: int
    position: int
    page: int | None
    text: str
    score: float  # cosine similarity, -1..1, higher = more similar


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
