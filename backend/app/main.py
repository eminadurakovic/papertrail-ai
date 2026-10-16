import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.ask import router as ask_router
from app.api.health import router as health_router
from app.api.info import router as info_router
from app.api.papers import router as papers_router
from app.api.search import router as search_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def database_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A database failure that no route handled itself (e.g. while listing papers)."""
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The database is unavailable. Try again later."},
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: a JSON body instead of a plain-text page, and no internals in it."""
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s"
    )

    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.include_router(health_router)
    app.include_router(info_router)
    app.include_router(papers_router)
    app.include_router(search_router)
    app.include_router(ask_router)
    return app


app = create_app()
