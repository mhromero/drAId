from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image


class IngestionError(Exception):
    """Raised when a file cannot be ingested."""


@dataclass(slots=True)
class IngestedDocument:
    source_path: str
    raw_text: str


def ingest_file(file_path: str | Path) -> IngestedDocument:
    path = Path(file_path)
    if not path.exists():
        raise IngestionError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".txt":
        return IngestedDocument(source_path=str(path), raw_text=path.read_text(encoding="utf-8", errors="ignore"))

    if suffix == ".pdf":
        return IngestedDocument(source_path=str(path), raw_text=_extract_pdf_text(path))

    raise IngestionError(f"Unsupported extension '{suffix}' in file: {path}")


def _extract_pdf_text(path: Path) -> str:
    page_texts: list[str] = []

    try:
        with fitz.open(path) as pdf:
            for page in pdf:
                # Read digital text first to preserve native reading order.
                text = page.get_text("text").strip()
                if text:
                    page_texts.append(text)
                    continue

                # OCR fallback for scanned pages.
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                ocr_text = pytesseract.image_to_string(image).strip()
                if ocr_text:
                    page_texts.append(ocr_text)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError) as exc:
        raise IngestionError(f"Corrupt or unreadable PDF: {path}") from exc
    except Exception as exc:  # pragma: no cover - defensive wrapper for OCR/PDF backend issues
        raise IngestionError(f"Failed to extract PDF text from {path}: {exc}") from exc

    if not page_texts:
        raise IngestionError(f"No readable text found in PDF: {path}")

    return "\n\n".join(page_texts)
