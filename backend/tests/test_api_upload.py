"""Tests for file upload security: extension whitelist, MIME type, file size."""
import pytest
from app.services.document_service import _validate_file, ALLOWED_EXTENSIONS
from fastapi import HTTPException


def test_valid_extension():
    """Should not raise for allowed extensions."""
    for ext in [".pdf", ".docx", ".txt", ".csv", ".md", ".xlsx"]:
        _validate_file(f"test{ext}", "application/octet-stream", 1024)


def test_invalid_extension():
    """Should raise HTTPException 400 for disallowed extensions."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_file("malware.exe", "application/octet-stream", 1024)
    assert exc_info.value.status_code == 400
    assert "不支持的文件类型" in exc_info.value.detail


def test_invalid_extension_py():
    with pytest.raises(HTTPException) as exc_info:
        _validate_file("script.py", "text/x-python", 1024)
    assert exc_info.value.status_code == 400


def test_empty_filename():
    with pytest.raises(HTTPException):
        _validate_file("", "application/octet-stream", 1024)


def test_invalid_mime_type():
    """Should reject disallowed MIME types."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_file("test.pdf", "application/x-executable", 1024)
    assert exc_info.value.status_code == 400
    assert "MIME" in exc_info.value.detail


def test_file_size_limit():
    """Should reject files exceeding MAX_UPLOAD_SIZE_MB."""
    from app.config import settings
    over_limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1
    with pytest.raises(HTTPException) as exc_info:
        _validate_file("test.pdf", "application/pdf", over_limit)
    assert exc_info.value.status_code == 400
    assert "超过限制" in exc_info.value.detail


def test_file_size_within_limit():
    """Should pass for files within limit."""
    _validate_file("test.pdf", "application/pdf", 1024 * 1024)  # 1MB


def test_none_content_type_allowed():
    """None content type should be allowed (browser may not always send it)."""
    _validate_file("test.pdf", None, 1024)


def test_case_insensitive_extension():
    """Extensions should be case-insensitive."""
    _validate_file("TEST.PDF", "application/pdf", 1024)
    _validate_file("doc.DOCX", "application/octet-stream", 1024)
