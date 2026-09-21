"""Wire shapes for the documents endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.values.overview import OverviewStatus
from app.infrastructure.db.models import DocumentStatus


class DescriptionSection(BaseModel):
    """A section of the document description."""

    heading: str
    body: str


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
    author: str | None = None
    summary: str | None = None
    language: str | None = None
    doc_type: str | None = None
    topics: list[str] = []
    overview_status: OverviewStatus | None = None
    has_cover: bool = False
    embedded_chunks: int | None = None
    total_chunks: int | None = None


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    order_index: int
    start_page: int
    end_page: int


class DocumentDetail(DocumentRead):
    sections: list[SectionRead]
    description_sections: list[DescriptionSection] = []
    chunk_count: int
