"""Search over a document's embedded chunks (thin layer)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.usecases.search.search_document import SearchDocument
from app.interfaces.http.composition import get_search_document
from app.interfaces.http.schemas.search import SearchRequest, SearchResponse, SearchResultRead

router = APIRouter(prefix="/documents", tags=["search"])


@router.post("/{document_id}/search", response_model=SearchResponse)
async def search(
    document_id: UUID,
    request: SearchRequest,
    use_case: SearchDocument = Depends(get_search_document),
) -> SearchResponse:
    """Search a document's embedded chunks."""
    try:
        outcome = await use_case.execute(
            document_id, request.query, top_k=request.top_k, min_score=request.min_score
        )

        # Convert scored chunks to SearchResultRead
        results = [
            SearchResultRead(
                chunk_id=scored.chunk.chunk_id,
                content=scored.chunk.content,
                page_start=scored.chunk.page_start,
                page_end=scored.chunk.page_end,
                section_title=scored.chunk.section_title,
                score=scored.score,
                distance=scored.chunk.distance,
            )
            for scored in outcome.scored_chunks
        ]

        return SearchResponse(
            results=results,
            grounded=outcome.grounded,
            reranked=True,  # assume reranker was used (would need to track this)
            reason=outcome.reason if not outcome.grounded else None,
            candidate_count=len(outcome.scored_chunks),
        )
    except Exception as e:
        from app.domain.errors import DocumentNotFound, DocumentNotReady
        if isinstance(e, DocumentNotFound):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
        if isinstance(e, DocumentNotReady):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="document not ready for search"
            )
        raise
