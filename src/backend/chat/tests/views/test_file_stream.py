"""Tests for the file stream endpoint."""

from io import BytesIO
from unittest import mock

from django.core.cache import cache


def test_file_stream_invalid_key(api_client):
    """Test that invalid temporary keys return 404."""
    cache.clear()
    url = "/api/v1.0/file-stream/invalid-key/"
    response = api_client.get(url)

    assert response.status_code == 404
    error = response.json()["detail"].lower()
    assert "expired" in error or "invalid" in error


def test_file_stream_expired_key(api_client):
    """Test that expired keys return 404."""
    cache.clear()
    # Create a key that's already expired
    cache.set("file_access:expired-key", "path/to/file.pdf", timeout=0)

    url = "/api/v1.0/file-stream/expired-key/"
    response = api_client.get(url)

    assert response.status_code == 404


@mock.patch("chat.views.magic.Magic")
@mock.patch("chat.views.default_storage.open")
def test_file_stream_valid_key_streams_file(mock_storage_open, mock_magic, api_client):
    """Test that valid temporary keys stream file content."""
    cache.clear()

    # Create a valid temporary key
    temporary_key = "test-valid-key"
    s3_key = "test/path/file.pdf"
    cache.set(f"file_access:{temporary_key}", s3_key, timeout=300)

    # Mock storage.open to return file content
    file_mock = BytesIO(b"PDF content here")
    mock_storage_open.return_value = file_mock

    # Mock magic detector
    mock_magic_instance = mock.MagicMock()
    mock_magic_instance.from_buffer.return_value = "application/pdf"
    mock_magic.return_value = mock_magic_instance

    url = f"/api/v1.0/file-stream/{temporary_key}/"
    response = api_client.get(url)

    assert response.status_code == 200
