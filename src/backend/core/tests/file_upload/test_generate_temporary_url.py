"""Tests for generate_temporary_url utility function."""

from django.conf import settings
from django.core.cache import cache

import pytest

from chat.agents.local_media_url_processors import generate_temporary_url

pytestmark = pytest.mark.django_db


def test_generate_temporary_url_returns_string():
    """Test that generate_temporary_url returns a valid backend streaming URL."""
    cache.clear()
    url = generate_temporary_url("test/file.pdf")

    assert isinstance(url, str)
    assert url.startswith(settings.FILE_BACKEND_URL + "/api/v1.0/file-stream/")
    assert url.endswith("/")


def test_generate_temporary_url_creates_cache_entry():
    """Test that a cache entry is created with correct mapping."""
    cache.clear()
    s3_key = "conversation-id/attachments/file-uuid.pdf"
    url = generate_temporary_url(s3_key)

    # Extract temporary key from URL
    temporary_key = url.split("/file-stream/")[1].rstrip("/")

    # Verify cache entry
    cache_key = f"file_access:{temporary_key}"
    cached_value = cache.get(cache_key)
    assert cached_value == s3_key


def test_generate_temporary_url_unique_tokens():
    """Test that different S3 keys produce different temporary tokens."""
    cache.clear()
    url1 = generate_temporary_url("file1.pdf")
    url2 = generate_temporary_url("file2.pdf")

    assert url1 != url2

    key1 = url1.split("/file-stream/")[1].rstrip("/")
    key2 = url2.split("/file-stream/")[1].rstrip("/")

    assert cache.get(f"file_access:{key1}") == "file1.pdf"
    assert cache.get(f"file_access:{key2}") == "file2.pdf"


def test_generate_temporary_url_token_is_url_safe():
    """Test that generated tokens contain only URL-safe characters."""
    cache.clear()
    url = generate_temporary_url("test.pdf")

    temporary_key = url.split("/file-stream/")[1].rstrip("/")

    # Token should only contain alphanumeric, dash, and underscore
    assert all(c.isalnum() or c in "-_" for c in temporary_key)


def test_generate_temporary_url_token_sufficient_entropy():
    """Test that generated tokens have sufficient entropy."""
    cache.clear()
    url = generate_temporary_url("test.pdf")

    temporary_key = url.split("/file-stream/")[1].rstrip("/")

    # Token should be reasonably long
    assert len(temporary_key) >= 32


def test_generate_temporary_url_no_sensitive_data_in_url():
    """Test that temporary URLs don't contain S3 key information."""
    cache.clear()

    s3_key = "secret/conversation-123/attachments/file.pdf"
    url = generate_temporary_url(s3_key)

    # URL should not contain the actual S3 key
    assert "secret" not in url
    assert "conversation-123" not in url
    assert "file.pdf" not in url
    # Only the endpoint and random token
    assert "/api/v1.0/file-stream/" in url


def test_generate_temporary_url_various_key_formats():
    """Test generate_temporary_url with various S3 key formats."""
    cache.clear()

    test_keys = [
        "simple/key.pdf",
        "conversation-123/attachments/file-uuid.pdf",
        "nested/folder/structure/file.jpg",
        "file_with_special-chars_123.png",
    ]

    urls = []
    for key in test_keys:
        url = generate_temporary_url(key)
        urls.append(url)

        temporary_key = url.split("/file-stream/")[1].rstrip("/")
        assert cache.get(f"file_access:{temporary_key}") == key

    # All URLs should be different
    assert len(set(urls)) == len(urls)
