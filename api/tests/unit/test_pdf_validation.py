import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.services.ingestion import validate_pdf_upload


def test_valid_pdf_returns_page_count(pdf_bytes: bytes) -> None:
    assert (
        validate_pdf_upload(
            filename="notes.pdf", content_type="application/pdf", data=pdf_bytes
        )
        == 2
    )


def test_rejects_non_pdf_bytes() -> None:
    with pytest.raises(AppError) as exc_info:
        validate_pdf_upload(
            filename="notes.pdf", content_type="application/pdf", data=b"not a pdf at all"
        )
    assert exc_info.value.code == "MATERIAL_INVALID"


def test_rejects_wrong_extension(pdf_bytes: bytes) -> None:
    with pytest.raises(AppError) as exc_info:
        validate_pdf_upload(filename="notes.txt", content_type="text/plain", data=pdf_bytes)
    assert exc_info.value.code == "MATERIAL_INVALID"


def test_rejects_wrong_content_type(pdf_bytes: bytes) -> None:
    with pytest.raises(AppError) as exc_info:
        validate_pdf_upload(
            filename="notes.pdf", content_type="image/png", data=pdf_bytes
        )
    assert exc_info.value.code == "MATERIAL_INVALID"


def test_rejects_too_many_pages(pdf_bytes: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "max_pdf_pages", 1)
    with pytest.raises(AppError) as exc_info:
        validate_pdf_upload(
            filename="notes.pdf", content_type="application/pdf", data=pdf_bytes
        )
    assert exc_info.value.code == "MATERIAL_INVALID"
