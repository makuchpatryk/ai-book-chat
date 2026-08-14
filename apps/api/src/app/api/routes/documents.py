"""Document upload and reads. Processing itself runs in the Celery worker."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import AppSettings, DbSession
from app.db.models import Document
from app.schemas.documents import DocumentDetail, DocumentRead, SectionRead
from app.services import documents as service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    response: Response,
    db: DbSession,
    settings: AppSettings,
    file: Annotated[UploadFile, File()],
) -> Document:
    document, created = await service.create_document(db, file, settings)
    if not created:
        # Same bytes as an existing document: hand back the row we already have
        # instead of an error the upload UI would have to branch on.
        response.status_code = status.HTTP_200_OK
    return document


@router.get("", response_model=list[DocumentRead])
async def list_documents(db: DbSession) -> list[Document]:
    return await service.list_documents(db)


@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(document_id: UUID, db: DbSession) -> DocumentDetail:
    found = await service.get_document_detail(db, document_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")

    document, chunk_count = found
    return DocumentDetail(
        **DocumentRead.model_validate(document).model_dump(),
        sections=[SectionRead.model_validate(section) for section in document.sections],
        chunk_count=chunk_count,
    )
