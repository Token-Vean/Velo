from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from velo_engine.file_guard import (
    FileValidationError,
    validate_uploaded_file,
    workspace_sync_warnings,
)


def test_rejects_unknown_extension(tmp_path: Path) -> None:
    path = tmp_path / "sample.exe"
    path.write_bytes(b"MZ fake executable")

    with pytest.raises(FileValidationError):
        validate_uploaded_file(path, "sample.exe", max_bytes=10_000)


def test_accepts_plain_txt(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("Texto de prueba", encoding="utf-8")

    result = validate_uploaded_file(path, "sample.txt", max_bytes=10_000)

    assert result.extension == ".txt"
    assert result.detected_type == "txt"


def test_rejects_fake_pdf(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"not really a pdf")

    with pytest.raises(FileValidationError):
        validate_uploaded_file(path, "fake.pdf", max_bytes=10_000)


def test_accepts_pdf_signature(tmp_path: Path) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"%PDF-1.7\n%fake minimal body\n%%EOF")

    result = validate_uploaded_file(path, "sample.pdf", max_bytes=10_000)

    assert result.extension == ".pdf"
    assert result.detected_type == "pdf"


def test_rejects_fake_docx(tmp_path: Path) -> None:
    path = tmp_path / "fake.docx"
    path.write_bytes(b"not a zip")

    with pytest.raises(FileValidationError):
        validate_uploaded_file(path, "fake.docx", max_bytes=10_000)


def test_accepts_minimal_docx_zip(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document></w:document>")

    result = validate_uploaded_file(path, "sample.docx", max_bytes=100_000)

    assert result.extension == ".docx"
    assert result.detected_type == "docx"


def test_detects_sync_folder_warning() -> None:
    warnings = workspace_sync_warnings("/Users/example/OneDrive/Velo/workspace")

    assert warnings
    assert "sincronizada" in warnings[0]
