"""PyMuPDF-based PDF extractor adapter."""

from pathlib import Path

from app.domain.ports.storage import ExtractedPdf, PdfExtractor
from app.ingestion.extract import extract_pdf


class PyMuPdfExtractor(PdfExtractor):
    """PyMuPDF implementation of PDF extraction."""

    def extract(self, file_path: str, fallback_title: str | None = None) -> ExtractedPdf:
        """Extract PDF using PyMuPDF."""
        return extract_pdf(Path(file_path), fallback_title)
