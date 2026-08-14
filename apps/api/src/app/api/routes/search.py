"""Search over a document's embedded chunks."""

from copy import deepcopy
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AppSettings, DbSession
from app.db.models import DocumentStatus
from app.retrieval.pipeline import search as search_pipeline
from app.schemas.search import SearchRequest, SearchResponse, SearchResultRead
from app.services import documents as service

router = APIRouter(prefix="/documents", tags=["search"])


@router.post("/{document_id}/search", response_model=SearchResponse)
async def search(
    document_id: UUID,
    request: SearchRequest,
    db: DbSession,
    settings: AppSettings,
) -> SearchResponse:
    """Search a document's embedded chunks."""
    document = await service.get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    if document.status != DocumentStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="document not ready for search"
        )

    # Override settings with request parameters if provided
    search_settings = settings
    if request.top_k is not None or request.min_score is not None:
        search_settings = deepcopy(settings)
        if request.top_k is not None:
            search_settings.retrieval_top_k = request.top_k
        if request.min_score is not None:
            search_settings.rerank_min_score = request.min_score

    outcome = await search_pipeline(db, document_id, request.query, search_settings)

    return SearchResponse(
        results=[
            SearchResultRead(
                chunk_id=candidate.chunk.id,
                content=candidate.chunk.content,
                page_start=candidate.chunk.page_start,
                page_end=candidate.chunk.page_end,
                section_title=candidate.section_title,
                score=score,
                distance=candidate.distance,
            )
            for candidate, score in outcome.results
        ],
        grounded=outcome.grounded,
        reranked=outcome.reranked,
        reason=outcome.reason,
        candidate_count=outcome.candidate_count,
    )
