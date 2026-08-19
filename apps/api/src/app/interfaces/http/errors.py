"""Exception handlers mapping domain/application errors to HTTP responses."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.domain.errors import (
    ConversationNotFound,
    DocumentAlreadyProcessed,
    DocumentNotFound,
    DocumentNotReady,
    DocumentStillProcessing,
    DuplicateUpload,
    FileTooLarge,
    NotAPdf,
    SourceFileMissing,
    UnsupportedFileType,
)


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for domain errors."""

    @app.exception_handler(DocumentNotFound)
    async def handle_document_not_found(request: Request, exc: DocumentNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "document not found"},
        )

    @app.exception_handler(ConversationNotFound)
    async def handle_conversation_not_found(request: Request, exc: ConversationNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "conversation not found"},
        )

    @app.exception_handler(DocumentNotReady)
    async def handle_document_not_ready(request: Request, exc: DocumentNotReady) -> JSONResponse:
        detail = f"document not ready for {exc.activity}"
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": detail},
        )

    @app.exception_handler(DocumentAlreadyProcessed)
    async def handle_document_already_processed(request: Request, exc: DocumentAlreadyProcessed) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "document is already processed"},
        )

    @app.exception_handler(DocumentStillProcessing)
    async def handle_document_still_processing(request: Request, exc: DocumentStillProcessing) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "document is still processing"},
        )

    @app.exception_handler(DuplicateUpload)
    async def handle_duplicate_upload(request: Request, exc: DuplicateUpload) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "duplicate upload; document already processed"},
        )

    @app.exception_handler(SourceFileMissing)
    async def handle_source_file_missing(request: Request, exc: SourceFileMissing) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "original file is missing; re-upload it"},
        )

    @app.exception_handler(UnsupportedFileType)
    async def handle_unsupported_file_type(request: Request, exc: UnsupportedFileType) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content={"detail": "only PDF files are supported"},
        )

    @app.exception_handler(FileTooLarge)
    async def handle_file_too_large(request: Request, exc: FileTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": f"file exceeds the {exc.max_mb} MB limit"},
        )

    @app.exception_handler(NotAPdf)
    async def handle_not_a_pdf(request: Request, exc: NotAPdf) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": "file is not a valid PDF (missing %PDF- header)"},
        )
