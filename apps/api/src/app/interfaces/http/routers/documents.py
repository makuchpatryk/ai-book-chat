"""Document management endpoints (thin layer)."""

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.application.usecases.documents.delete_document import DeleteDocument
from app.application.usecases.documents.get_cover import GetCover
from app.application.usecases.documents.get_document_detail import GetDocumentDetail
from app.application.usecases.documents.list_documents import ListDocuments
from app.application.usecases.documents.request_overview import RequestOverview
from app.application.usecases.documents.retry_document import RetryDocument
from app.application.usecases.documents.upload_document import UploadDocument
from app.interfaces.http.composition import (
    get_delete_document,
    get_get_cover,
    get_get_document_detail,
    get_list_documents,
    get_request_overview,
    get_retry_document,
    get_upload_document,
)
from app.interfaces.http.schemas.documents import (
    DescriptionSection,
    DocumentDetail,
    DocumentRead,
    SectionRead,
)

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_CHUNK_BYTES = 64 * 1024


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    use_case: UploadDocument = Depends(get_upload_document),
) -> DocumentRead:
    """Upload a document for processing. A duplicate upload is a 409 (see errors.py)."""

    async def read_chunks() -> AsyncGenerator[bytes, None]:
        while chunk := await file.read(UPLOAD_CHUNK_BYTES):
            yield chunk

    document = await use_case.execute(file.filename or "", read_chunks())
    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    use_case: ListDocuments = Depends(get_list_documents),
) -> list[DocumentRead]:
    """List all documents."""
    documents = await use_case.execute()
    return [DocumentRead.model_validate(doc) for doc in documents]


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    use_case: GetDocumentDetail = Depends(get_get_document_detail),
) -> DocumentDetail:
    """Get document with sections."""
    result = await use_case.execute(document_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    document, sections, chunk_count = result
    doc_read = DocumentRead.model_validate(document)
    section_reads = [SectionRead.model_validate(s) for s in sections]

    return DocumentDetail(
        **doc_read.model_dump(),
        sections=section_reads,
        description_sections=[
            DescriptionSection(**s) for s in document.description_sections
        ],
        chunk_count=chunk_count,
    )


@router.post("/{document_id}/retry", response_model=DocumentRead, status_code=status.HTTP_200_OK)
async def retry_document(
    document_id: UUID,
    use_case: RetryDocument = Depends(get_retry_document),
) -> DocumentRead:
    """Retry ingestion of a document. Domain errors map to 404/409 in errors.py."""
    document = await use_case.execute(document_id)
    return DocumentRead.model_validate(document)


@router.get("/{document_id}/cover", status_code=status.HTTP_200_OK)
async def get_document_cover(
    document_id: UUID,
    use_case: GetCover = Depends(get_get_cover),
) -> Response:
    """Get document cover image."""
    cover_bytes, mime_type = await use_case.execute(document_id)
    return Response(
        content=cover_bytes,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post(
    "/{document_id}/overview/regenerate",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_overview(
    document_id: UUID,
    request_uc: RequestOverview = Depends(get_request_overview),
    detail_uc: GetDocumentDetail = Depends(get_get_document_detail),
) -> DocumentRead:
    """Request overview regeneration for a document."""
    await request_uc.execute(document_id)
    result = await detail_uc.execute(document_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    document, _, _ = result
    return DocumentRead.model_validate(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    use_case: DeleteDocument = Depends(get_delete_document),
) -> None:
    """Delete a document."""
    success = await use_case.execute(document_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
