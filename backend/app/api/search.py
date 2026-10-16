from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, EmbedderDep
from app.schemas.search import SearchRequest, SearchResponse, SearchResult
from app.services import search as search_service

router = APIRouter(tags=["search"])


@router.post(
    "/search",
    responses={
        404: {"description": "One of the requested paper IDs does not exist"},
        503: {"description": "The embedding model is not available"},
    },
)
def search(request: SearchRequest, db: DbSession, embedder: EmbedderDep) -> SearchResponse:
    """Return the passages most similar in meaning to the query (no generated answer)."""
    try:
        hits = search_service.semantic_search(
            db, embedder, request.query, limit=request.limit, paper_ids=request.paper_ids
        )
    except search_service.UnknownPapersError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return SearchResponse(
        query=request.query,
        results=[
            SearchResult(
                paper_id=hit.paper_id,
                title=hit.paper_title,
                arxiv_id=hit.arxiv_id,
                passage_id=hit.passage_id,
                position=hit.position,
                page=hit.page,
                text=hit.text,
                score=round(hit.score, 4),
            )
            for hit in hits
        ],
    )
