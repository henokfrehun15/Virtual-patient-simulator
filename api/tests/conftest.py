import io

import fitz
import pytest


def make_pdf_bytes(page_texts: list[str]) -> bytes:
    document = fitz.open()
    for text in page_texts:
        page = document.new_page()
        page.insert_textbox(fitz.Rect(50, 50, 545, 790), text)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf_bytes(
        [
            "Chapter 1: Respiratory infections. Pneumonia is an infection of the lung parenchyma.",
            "Chapter 2: Cardiology. Myocardial infarction presents with central chest pain.",
        ]
    )
