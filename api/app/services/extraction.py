import io
from dataclasses import dataclass

import fitz
import pytesseract
from PIL import Image

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.extraction")


class ExtractionError(Exception):
    pass


@dataclass
class ExtractedPage:
    page_number: int
    text: str | None
    ocr_used: bool
    meta: dict


@dataclass
class PageChunk:
    chunk_index: int
    page_number: int
    text: str


def extract_pages(pdf_bytes: bytes) -> list[ExtractedPage]:
    settings = get_settings()
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("Unable to open PDF document") from exc

    pages: list[ExtractedPage] = []
    with document:
        for page in document:
            text = page.get_text("text") or ""
            image_count = len(page.get_images(full=True))
            ocr_used = False
            if len(text.strip()) < settings.ocr_min_text_chars and image_count > 0:
                ocr_text = _ocr_page(page, dpi=settings.ocr_dpi)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    ocr_used = True
            pages.append(
                ExtractedPage(
                    page_number=page.number + 1,
                    text=text.strip() or None,
                    ocr_used=ocr_used,
                    meta={"char_count": len(text), "image_count": image_count},
                )
            )
    return pages


def _ocr_page(page: fitz.Page, dpi: int) -> str:
    try:
        pixmap = page.get_pixmap(dpi=dpi)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image) or ""
    except Exception:
        logger.warning("ocr_failed", page_number=page.number + 1)
        return ""


def chunk_pages(
    pages: list[ExtractedPage], target_chars: int, overlap_chars: int
) -> list[PageChunk]:
    chunks: list[PageChunk] = []
    for page in pages:
        if not page.text:
            continue
        for piece in split_text(page.text, target_chars, overlap_chars):
            chunks.append(
                PageChunk(
                    chunk_index=len(chunks),
                    page_number=page.page_number,
                    text=piece,
                )
            )
    return chunks


def split_text(text: str, target: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    min_length = target // 2
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target, len(text))
        if end < len(text):
            end = _find_boundary(text, start, end, min_length)
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [piece for piece in pieces if piece]


def _find_boundary(text: str, start: int, end: int, min_length: int) -> int:
    window = text[start:end]
    for separator in ("\n\n", ". ", "? ", "! ", "\n", " "):
        index = window.rfind(separator)
        if index != -1 and index + len(separator) >= min_length:
            return start + index + len(separator)
    return end
