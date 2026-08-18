"""Wire shapes for the search endpoint."""

from uuid import UUID

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=100)
    min_score: int | None = Field(default=None, ge=0, le=10)


class SearchResultRead(BaseModel):
    chunk_id: UUID
    content: str
    page_start: int
    page_end: int
    section_title: str | None
    score: int | None
    distance: float


class SearchResponse(BaseModel):
    results: list[SearchResultRead]
    grounded: bool
    reranked: bool
    reason: str | None
    candidate_count: int
