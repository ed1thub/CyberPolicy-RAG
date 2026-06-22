"""Tests for document loader and chunker (T05)."""

from pathlib import Path

import pytest

from backend.app.documents.chunker import (
    MAX_WORDS,
    chunk_document,
    _build_heading_map,
    _split_paragraphs,
)
from backend.app.documents.loader import (
    LoadedDocument,
    _parse_front_matter,
    load_document,
    load_markdown,
    load_txt,
    load_all_from_directory,
)

SAMPLE_POLICIES_DIR = Path("data/sample_policies")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_md_file(tmp_path: Path) -> Path:
    content = """\
---
title: Test Password Policy
sensitivity_level: internal
allowed_roles: user,security_analyst,admin
---

# Test Password Policy

## Password Requirements

Passwords must be at least 14 characters long and include uppercase, lowercase,
numbers, and special characters. Users must not reuse any of their last 12
passwords. Passphrases of four or more random words are encouraged.

## Multi-Factor Authentication

MFA is mandatory for all remote access connections and all privileged accounts.
Approved methods include authenticator apps and hardware security keys. SMS
one-time passwords are not approved for new enrolments.
"""
    path = tmp_path / "test_password_policy.md"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def sample_txt_file(tmp_path: Path) -> Path:
    content = "This is a plain text policy document.\n\nIt has multiple paragraphs.\n"
    path = tmp_path / "plain_policy.txt"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def long_body_document() -> LoadedDocument:
    """A LoadedDocument whose body exceeds MAX_WORDS to force multiple chunks."""
    # ~1800 words across clearly separated paragraphs
    para = " ".join(["word"] * 200)
    body = "\n\n".join([f"## Section {i}\n\n{para}" for i in range(1, 10)])
    return LoadedDocument(
        title="Long Document",
        filename="long_doc.md",
        sensitivity_level="internal",
        allowed_roles="user,security_analyst,admin",
        body=body,
    )


@pytest.fixture
def short_body_document() -> LoadedDocument:
    """A LoadedDocument whose body is well below TARGET_WORDS."""
    return LoadedDocument(
        title="Short Document",
        filename="short_doc.md",
        sensitivity_level="public",
        allowed_roles="user,security_analyst,admin",
        body="## Overview\n\nThis policy is very short and fits in one chunk.",
    )


# ---------------------------------------------------------------------------
# Loader: front matter parsing
# ---------------------------------------------------------------------------


def test_parse_front_matter_extracts_metadata() -> None:
    text = (
        "---\ntitle: My Policy\nsensitivity_level: confidential\n"
        "allowed_roles: security_analyst,admin\n---\n\nBody text here."
    )
    meta, body = _parse_front_matter(text)

    assert meta["title"] == "My Policy"
    assert meta["sensitivity_level"] == "confidential"
    assert meta["allowed_roles"] == "security_analyst,admin"
    assert "Body text here." in body


def test_parse_front_matter_returns_empty_when_missing() -> None:
    text = "No front matter here.\n\nJust body text."
    meta, body = _parse_front_matter(text)

    assert meta == {}
    assert "Just body text." in body


def test_load_markdown_reads_title(sample_md_file: Path) -> None:
    doc = load_markdown(sample_md_file)
    assert doc.title == "Test Password Policy"


def test_load_markdown_reads_sensitivity_level(sample_md_file: Path) -> None:
    doc = load_markdown(sample_md_file)
    assert doc.sensitivity_level == "internal"


def test_load_markdown_reads_allowed_roles(sample_md_file: Path) -> None:
    doc = load_markdown(sample_md_file)
    assert doc.allowed_roles == "user,security_analyst,admin"


def test_load_markdown_body_excludes_front_matter(sample_md_file: Path) -> None:
    doc = load_markdown(sample_md_file)
    assert "---" not in doc.body
    assert "Password Requirements" in doc.body


def test_load_markdown_filename_is_set(sample_md_file: Path) -> None:
    doc = load_markdown(sample_md_file)
    assert doc.filename == sample_md_file.name


def test_load_markdown_rejects_invalid_sensitivity(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.md"
    bad_file.write_text(
        "---\ntitle: Bad\nsensitivity_level: top_secret\nallowed_roles: admin\n---\nBody.",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown sensitivity_level"):
        load_markdown(bad_file)


# ---------------------------------------------------------------------------
# Loader: TXT files
# ---------------------------------------------------------------------------


def test_load_txt_returns_body_text(sample_txt_file: Path) -> None:
    doc = load_txt(sample_txt_file)
    assert "plain text policy document" in doc.body


def test_load_txt_derives_title_from_filename(sample_txt_file: Path) -> None:
    doc = load_txt(sample_txt_file)
    assert doc.title == "Plain Policy"


def test_load_txt_defaults_to_internal_sensitivity(sample_txt_file: Path) -> None:
    doc = load_txt(sample_txt_file)
    assert doc.sensitivity_level == "internal"


# ---------------------------------------------------------------------------
# Loader: dispatch
# ---------------------------------------------------------------------------


def test_load_document_dispatches_md(sample_md_file: Path) -> None:
    doc = load_document(sample_md_file)
    assert doc.title == "Test Password Policy"


def test_load_document_dispatches_txt(sample_txt_file: Path) -> None:
    doc = load_document(sample_txt_file)
    assert "plain text" in doc.body


def test_load_document_rejects_unsupported_extension(tmp_path: Path) -> None:
    bad = tmp_path / "policy.docx"
    bad.write_text("content")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_document(bad)


# ---------------------------------------------------------------------------
# Loader: PDF (optional — requires PyMuPDF)
# ---------------------------------------------------------------------------


def test_load_pdf_function_is_importable() -> None:
    from backend.app.documents.loader import load_pdf
    from inspect import signature

    sig = signature(load_pdf)
    assert "file_path" in sig.parameters


def test_load_pdf_page_by_page(tmp_path: Path) -> None:
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "test_policy.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), "This is a test PDF policy document.")
    doc.save(str(pdf_path))
    doc.close()

    from backend.app.documents.loader import load_pdf

    loaded = load_pdf(pdf_path)

    assert len(loaded.pages) == 1
    assert loaded.pages[0].page_number == 1
    assert "test PDF policy document" in loaded.pages[0].text


# ---------------------------------------------------------------------------
# Loader: directory loading
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not SAMPLE_POLICIES_DIR.exists(),
    reason="data/sample_policies directory not found",
)
def test_load_all_sample_policies_without_error() -> None:
    documents = load_all_from_directory(SAMPLE_POLICIES_DIR)
    assert len(documents) == 7


@pytest.mark.skipif(
    not SAMPLE_POLICIES_DIR.exists(),
    reason="data/sample_policies directory not found",
)
def test_sample_policy_sensitivity_levels_are_valid() -> None:
    valid = {"public", "internal", "confidential", "restricted"}
    documents = load_all_from_directory(SAMPLE_POLICIES_DIR)

    for doc in documents:
        assert doc.sensitivity_level in valid, (
            f"{doc.filename} has invalid sensitivity_level '{doc.sensitivity_level}'"
        )


@pytest.mark.skipif(
    not SAMPLE_POLICIES_DIR.exists(),
    reason="data/sample_policies directory not found",
)
def test_sample_policies_have_non_empty_titles() -> None:
    documents = load_all_from_directory(SAMPLE_POLICIES_DIR)
    for doc in documents:
        assert doc.title.strip(), f"{doc.filename} has empty title"


# ---------------------------------------------------------------------------
# Chunker: helpers
# ---------------------------------------------------------------------------


def test_split_paragraphs_on_blank_lines() -> None:
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    parts = _split_paragraphs(text)
    assert parts == ["First paragraph.", "Second paragraph.", "Third paragraph."]


def test_split_paragraphs_filters_empty_blocks() -> None:
    text = "Para one.\n\n\n\nPara two."
    parts = _split_paragraphs(text)
    assert len(parts) == 2


def test_build_heading_map_tracks_current_heading() -> None:
    paragraphs = [
        "## Introduction",
        "Some intro text.",
        "## Requirements",
        "Requirement details.",
        "More requirement details.",
    ]
    heading_map = _build_heading_map(paragraphs, initial=None)

    assert heading_map[0] == "Introduction"
    assert heading_map[1] == "Introduction"
    assert heading_map[2] == "Requirements"
    assert heading_map[3] == "Requirements"
    assert heading_map[4] == "Requirements"


def test_build_heading_map_uses_initial_when_no_heading() -> None:
    paragraphs = ["Just a paragraph.", "Another paragraph."]
    heading_map = _build_heading_map(paragraphs, initial="Prior Section")

    assert heading_map[0] == "Prior Section"
    assert heading_map[1] == "Prior Section"


# ---------------------------------------------------------------------------
# Chunker: document chunking
# ---------------------------------------------------------------------------


def test_short_document_produces_single_chunk(short_body_document: LoadedDocument) -> None:
    chunks = chunk_document(short_body_document)
    assert len(chunks) == 1


def test_long_document_produces_multiple_chunks(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    assert len(chunks) > 1


def test_chunk_word_counts_within_bounds(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks[:-1]:  # last chunk may be shorter
        wc = len(chunk.text.split())
        assert wc <= MAX_WORDS + 50, (
            f"Chunk {chunk.chunk_id} has {wc} words, exceeds MAX_WORDS={MAX_WORDS}"
        )


def test_chunk_ids_are_unique(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"


def test_chunk_ids_follow_naming_convention(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks:
        assert chunk.chunk_id.startswith("long_doc_"), (
            f"Unexpected chunk_id format: {chunk.chunk_id}"
        )


def test_chunk_metadata_preserves_title(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks:
        assert chunk.document_title == "Long Document"


def test_chunk_metadata_preserves_filename(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks:
        assert chunk.filename == "long_doc.md"


def test_chunk_metadata_preserves_sensitivity(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks:
        assert chunk.sensitivity_level == "internal"


def test_chunk_metadata_preserves_allowed_roles(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    for chunk in chunks:
        assert chunk.allowed_roles == "user,security_analyst,admin"


def test_chunk_section_heading_is_tracked(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    headings = [c.section_heading for c in chunks if c.section_heading]
    assert len(headings) > 0, "No section headings were tracked"


def test_to_metadata_returns_all_required_keys(short_body_document: LoadedDocument) -> None:
    chunks = chunk_document(short_body_document)
    meta = chunks[0].to_metadata()
    required_keys = {
        "document_title",
        "filename",
        "sensitivity_level",
        "allowed_roles",
        "section_heading",
        "page",
        "chunk_id",
    }
    assert required_keys.issubset(meta.keys())


def test_to_metadata_all_values_are_scalars(short_body_document: LoadedDocument) -> None:
    chunks = chunk_document(short_body_document)
    meta = chunks[0].to_metadata()
    for key, value in meta.items():
        assert isinstance(value, (str, int, float, bool)), (
            f"Metadata key '{key}' has non-scalar value: {type(value)}"
        )


def test_adjacent_chunks_share_words(long_body_document: LoadedDocument) -> None:
    chunks = chunk_document(long_body_document)
    if len(chunks) < 2:
        pytest.skip("Need at least 2 chunks to test overlap")

    for i in range(len(chunks) - 1):
        words_a = set(chunks[i].text.split())
        words_b = set(chunks[i + 1].text.split())
        shared = words_a & words_b
        assert len(shared) > 0, (
            f"Chunks {chunks[i].chunk_id} and {chunks[i + 1].chunk_id} share no words"
        )


# ---------------------------------------------------------------------------
# Chunker: integration with sample policies
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not SAMPLE_POLICIES_DIR.exists(),
    reason="data/sample_policies directory not found",
)
def test_sample_policies_chunk_without_error() -> None:
    documents = load_all_from_directory(SAMPLE_POLICIES_DIR)
    for doc in documents:
        chunks = chunk_document(doc)
        assert len(chunks) >= 1, f"{doc.filename} produced no chunks"


@pytest.mark.skipif(
    not SAMPLE_POLICIES_DIR.exists(),
    reason="data/sample_policies directory not found",
)
def test_sample_policy_chunks_have_required_metadata() -> None:
    required_keys = {
        "document_title",
        "filename",
        "sensitivity_level",
        "allowed_roles",
        "section_heading",
        "page",
        "chunk_id",
    }
    documents = load_all_from_directory(SAMPLE_POLICIES_DIR)
    for doc in documents:
        for chunk in chunk_document(doc):
            meta = chunk.to_metadata()
            assert required_keys.issubset(meta.keys()), (
                f"{chunk.chunk_id} missing keys: {required_keys - meta.keys()}"
            )
