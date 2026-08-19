"""Document management endpoints (thin layer)."""

import hashlib
from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.application.usecases.documents.delete_document import DeleteDocument
from app.application.usecases.documents.get_document_detail import GetDocumentDetail
from app.application.usecases.documents.list_documents import ListDocuments
from app.application.usecases.documents.retry_document import RetryDocument
from app.application.usecases.documents.upload_document import UploadDocument
from app.domain.errors import DocumentNotFound
from app.interfaces.http.composition import (
    get_delete_document,
    get_get_document_detail,
    get_list_documents,
    get_retry_document,
    get_upload_document,
)
from app.interfaces.http.schemas.documents import DocumentDetail, DocumentRead, SectionRead

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    response: Response,
    file: Annotated[UploadFile, File()],
    use_case: UploadDocument = Depends(get_upload_document),
) -> DocumentRead:
    """Upload a document for processing."""
    # Read all chunks and compute hash
    chunks = []
    sha256_hash = hashlib.sha256()

    while True:
        chunk = await file.read(8192)
        if not chunk:
            break
        chunks.append(chunk)
        sha256_hash.update(chunk)

    content_hash = sha256_hash.hexdigest()

    async def chunk_generator() -> AsyncGenerator[bytes, None]:
        for chunk in chunks:
            yield chunk

    try:
        document = await use_case.execute(file.filename or "", content_hash, chunk_generator())
        return DocumentRead.model_validate(document)
    except Exception as e:
        # DuplicateUpload returns 200 with existing doc
        from app.domain.errors import DuplicateUpload
        if isinstance(e, DuplicateUpload):
            response.status_code = status.HTTP_200_OK
            # Re-run to get the existing document
            document = await use_case.execute(file.filename or "", content_hash, chunk_generator())
            return DocumentRead.model_validate(document)
        raise


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

    document, sections = result
    doc_read = DocumentRead.model_validate(document)
    section_reads = [SectionRead.model_validate(s) for s in sections]

    return DocumentDetail(
        **doc_read.model_dump(),
        sections=section_reads,
        chunk_count=len(sections),  # placeholder
    )


@router.post("/{document_id}/retry", response_model=DocumentRead, status_code=status.HTTP_200_OK)
async def retry_document(
    document_id: UUID,
    use_case: RetryDocument = Depends(get_retry_document),
) -> DocumentRead:
    """Retry ingestion of a document."""
    try:
        document = await use_case.execute(document_id)
        return DocumentRead.model_validate(document)
    except DocumentNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    use_case: DeleteDocument = Depends(get_delete_document),
) -> None:
    """Delete a document."""
    success = await use_case.execute(document_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
