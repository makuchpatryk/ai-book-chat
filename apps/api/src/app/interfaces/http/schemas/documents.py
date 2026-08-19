"""Wire shapes for the documents endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.infrastructure.db.models import DocumentStatus


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    title: str
    status: DocumentStatus
    page_count: int | None
    # Populated only on FAILED; it is the whole point of the failed state.
    error_message: str | None
    created_at: datetime


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    order_index: int
    start_page: int
    end_page: int


class DocumentDetail(DocumentRead):
    sections: list[SectionRead]
    chunk_count: int
