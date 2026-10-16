from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, EmbedderDep, LLMDep
from app.core.config import get_settings
from app.schemas.ask import AskRequest, AskResponse, CitationRead
from app.services import rag
from app.services.llm import LLMError, LLMNotConfiguredError, LLMUnavailableError
from app.services.search import UnknownPapersError

router = APIRouter(tags=["ask"])


@router.post(
    "/ask",
    responses={
        404: {"description": "One of the requested paper IDs does not exist"},
        502: {"description": "The language model failed"},
        503: {"description": "The embedding model or the language model is not available"},
    },
)
def ask(request: AskRequest, db: DbSession, embedder: EmbedderDep, llm: LLMDep) -> AskResponse:
    """Answer a question from the imported papers, citing the passages used."""
    try:
        result = rag.answer_question(
            db,
            embedder,
            llm,
            request.question,
            top_k=request.top_k,
            min_score=get_settings().rag_min_score,
            paper_ids=request.paper_ids,
        )
    except UnknownPapersError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (LLMNotConfiguredError, LLMUnavailableError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return AskResponse(
        answer=result.answer,
        abstained=result.abstained,
        abstention_reason=result.abstention_reason,
        citations=[
            CitationRead(
                number=citation.number,
                paper_id=citation.hit.paper_id,
                paper_title=citation.hit.paper_title,
                arxiv_id=citation.hit.arxiv_id,
                passage_id=citation.hit.passage_id,
                position=citation.hit.position,
                page=citation.hit.page,
                passage_text=citation.hit.text,
                score=round(citation.hit.score, 4),
            )
            for citation in result.citations
        ],
        best_score=None if result.best_score is None else round(result.best_score, 4),
    )
