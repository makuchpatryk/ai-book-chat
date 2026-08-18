"""Wire shapes for chat endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class SourceRead(BaseModel):
    chunk_id: UUID
    page_start: int
    page_end: int
    score: int | None
    section_title: str | None
    snippet: str


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str  # "user" | "assistant"
    content: str
    grounded: bool | None
    truncated: bool
    sources: list[SourceRead] = []


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: str


# SSE event payload models
class SourcesEventData(BaseModel):
    chunk_id: str
    page_start: int
    page_end: int
    score: int | None
    section_title: str | None
    snippet: str


class SourcesPayload(BaseModel):
    results: list[SourcesEventData]
    pages: list[int]


class TokenPayload(BaseModel):
    text: str


class DonePayload(BaseModel):
    message_id: str
    grounded: bool
    truncated: bool


class ErrorPayload(BaseModel):
    detail: str
