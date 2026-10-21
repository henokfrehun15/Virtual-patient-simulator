from app.services.extraction import ExtractedPage, chunk_pages, split_text


def test_short_text_single_piece() -> None:
    assert split_text("hello world", 100, 10) == ["hello world"]


def test_empty_text_returns_no_pieces() -> None:
    assert split_text("   ", 100, 10) == []


def test_long_text_splits_within_target() -> None:
    text = ("The patient presents with a cough and fever. " * 200).strip()

    pieces = split_text(text, 500, 50)

    assert len(pieces) > 1
    assert all(len(piece) <= 500 for piece in pieces)
    assert all(piece for piece in pieces)


def test_paragraph_boundary_preferred() -> None:
    first = "A" * 300
    second = "B" * 300
    text = f"{first}\n\n{second}"

    pieces = split_text(text, 400, 40)

    assert len(pieces) == 2
    assert pieces[0] == first


def test_chunk_pages_assigns_sequential_indices_and_skips_empty_pages() -> None:
    pages = [
        ExtractedPage(page_number=1, text="alpha", ocr_used=False, meta={}),
        ExtractedPage(page_number=2, text=None, ocr_used=False, meta={}),
        ExtractedPage(page_number=3, text="beta", ocr_used=False, meta={}),
    ]

    chunks = chunk_pages(pages, target_chars=100, overlap_chars=10)

    assert [(chunk.chunk_index, chunk.page_number, chunk.text) for chunk in chunks] == [
        (0, 1, "alpha"),
        (1, 3, "beta"),
    ]
