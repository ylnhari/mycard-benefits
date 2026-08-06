"""HTTP adapter for public deterministic Q&A."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mycard_benefits.catalog import CatalogLoadError, load_catalog

from .engine import MAX_QUERY_LENGTH, answer


class Question(BaseModel):
    query: str = Field(min_length=1, max_length=MAX_QUERY_LENGTH)


def create_qa_router(catalog_dir: Path) -> APIRouter:
    router = APIRouter(prefix="/api/v1/qa", tags=["qa"])

    @router.post("")
    def ask(payload: Question) -> dict[str, object]:
        try:
            catalog = load_catalog(catalog_dir)
        except CatalogLoadError:
            raise HTTPException(status_code=503, detail="Catalog unavailable") from None
        try:
            return answer(catalog, payload.query)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid question") from None

    return router
