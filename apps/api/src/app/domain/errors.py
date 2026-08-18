"""Domain-level errors."""


class DomainError(Exception):
    """Base class for domain errors."""

    pass


class DocumentNotFound(DomainError):
    """Document does not exist."""

    pass


class ConversationNotFound(DomainError):
    """Conversation does not exist."""

    pass


class DocumentNotReady(DomainError):
    """Document is not in READY status and cannot be used."""

    def __init__(self, activity: str):
        self.activity = activity
        super().__init__(f"document not ready for {activity}")


class DocumentAlreadyProcessed(DomainError):
    """Document has already been processed."""

    pass


class DocumentStillProcessing(DomainError):
    """Document is still being processed."""

    pass


class SourceFileMissing(DomainError):
    """Original uploaded file is missing."""

    pass


class UnsupportedFileType(DomainError):
    """File type is not supported."""

    pass


class FileTooLarge(DomainError):
    """File exceeds size limit."""

    def __init__(self, max_mb: int):
        self.max_mb = max_mb
        super().__init__(f"file exceeds the {max_mb} MB limit")


class NotAPdf(DomainError):
    """File is not a valid PDF."""

    pass


class DuplicateUpload(DomainError):
    """File with this content hash already exists."""

    pass
