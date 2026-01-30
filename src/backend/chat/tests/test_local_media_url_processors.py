"""Tests for local_media_url_processors."""

from io import BytesIO
from unittest.mock import patch

import pytest
from pydantic_ai import (
    DocumentUrl,
    ImageUrl,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from core.file_upload.enums import FileToLLMMode

from chat.agents.local_media_url_processors import (
    _get_file_url_for_llm,
    update_history_local_urls,
    update_local_urls,
)
from chat.factories import ChatConversationFactory

pytestmark = pytest.mark.django_db


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls(mock_generate_retrieve_policy):
    """Test that update_local_urls replaces local URLs with presigned URLs."""
    conversation = ChatConversationFactory()
    mock_generate_retrieve_policy.side_effect = lambda _key: f"presigned_url-{_key}"

    key = f"{conversation.pk}/test.jpg"
    contents = [
        ImageUrl(url=f"/media-key/{key}"),
        DocumentUrl(url=f"/media-key/{conversation.pk}/test.pdf"),
        ImageUrl(url="https://example.com/image.jpg"),
    ]
    updated_urls = {}

    result = list(update_local_urls(conversation, contents, updated_urls))

    assert len(result) == 3
    assert result[0].url == f"presigned_url-{key}"
    assert result[1].url == f"presigned_url-{conversation.pk}/test.pdf"
    assert result[2].url == "https://example.com/image.jpg"

    assert mock_generate_retrieve_policy.call_count == 2
    mock_generate_retrieve_policy.assert_any_call(key)
    mock_generate_retrieve_policy.assert_any_call(f"{conversation.pk}/test.pdf")

    assert len(updated_urls) == 2
    assert updated_urls[f"presigned_url-{key}"] == f"/media-key/{key}"
    assert (
        updated_urls[f"presigned_url-{conversation.pk}/test.pdf"]
        == f"/media-key/{conversation.pk}/test.pdf"
    )


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_security_check(mock_generate_retrieve_policy):
    """Test that update_local_urls performs a security check."""
    conversation = ChatConversationFactory()
    contents = [ImageUrl(url="/media-key/other_conversation/test.jpg")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "/media-key/other_conversation/test.jpg"
    mock_generate_retrieve_policy.assert_not_called()


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_no_media(mock_generate_retrieve_policy):
    """Test that update_local_urls handles no media URLs."""
    conversation = ChatConversationFactory()
    contents = []
    result = list(update_local_urls(conversation, contents))
    assert len(result) == 0
    mock_generate_retrieve_policy.assert_not_called()


@patch("chat.agents.local_media_url_processors.update_local_urls")
def test_update_history_local_urls(mock_update_local_urls):
    """Test that update_history_local_urls processes messages."""
    conversation = ChatConversationFactory()
    mock_update_local_urls.return_value = iter([])
    key = f"{conversation.pk}/test.jpg"
    user_prompt_content = [
        ImageUrl(url=f"/media-key/{key}"),
        DocumentUrl(url=f"/media-key/{conversation.pk}/test.pdf"),
    ]
    messages = [
        ModelRequest(parts=[UserPromptPart(content=user_prompt_content)]),
        ModelResponse(parts=[TextPart(content="I see your images.")]),
    ]

    result = update_history_local_urls(conversation, messages)

    assert len(result) == 2
    mock_update_local_urls.assert_called_once_with(conversation, user_prompt_content)


def test_update_history_local_urls_no_requests():
    """Test that update_history_local_urls handles no ModelRequest messages."""
    conversation = ChatConversationFactory()
    messages = [
        ModelRequest(parts=["Hello"]),
        ModelResponse(parts=[TextPart(content="Hi there!")]),
    ]

    with patch("chat.agents.local_media_url_processors.update_local_urls") as mock:
        result = update_history_local_urls(conversation, messages)
        assert result == messages
        mock.assert_not_called()


def test_update_history_local_urls_no_user_prompt_parts():
    """Test that update_history_local_urls handles no UserPromptPart."""
    conversation = ChatConversationFactory()
    messages = [ModelRequest(parts=[])]

    with patch("chat.agents.local_media_url_processors.update_local_urls") as mock:
        result = update_history_local_urls(conversation, messages)
        assert result == messages
        mock.assert_not_called()


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_local_urls_uses_get_file_url_for_llm(mock_get_file_url):
    """Test that update_local_urls uses _get_file_url_for_llm for mode-aware URLs."""
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "mode-aware-url"

    key = f"{conversation.pk}/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "mode-aware-url"
    mock_get_file_url.assert_called_once()


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_get_file_url_presigned_mode(mock_policy):
    """Test URL generation in presigned_url mode."""

    mock_policy.return_value = "presigned_s3_url"

    url = _get_file_url_for_llm("test/key.pdf", FileToLLMMode.PRESIGNED_URL)

    assert url == "presigned_s3_url"
    mock_policy.assert_called_once_with("test/key.pdf")


@patch("chat.agents.local_media_url_processors.generate_temporary_url")
def test_get_file_url_backend_temporary_url_mode(mock_temp_url):
    """Test URL generation in backend_temporary_url mode."""

    mock_temp_url.return_value = "/api/v1.0/file-stream/token123/"

    url = _get_file_url_for_llm("test/key.pdf", FileToLLMMode.BACKEND_TEMPORARY_URL)

    assert url == "/api/v1.0/file-stream/token123/"
    mock_temp_url.assert_called_once_with("test/key.pdf")


@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_get_file_url_backend_base64_mode(mock_storage):
    """Test URL generation in backend_base64 mode."""

    # Mock file content
    file_content = b"PDF binary content"
    mock_file = BytesIO(file_content)
    mock_storage.return_value.__enter__.return_value = mock_file

    url = _get_file_url_for_llm("test/key.pdf", FileToLLMMode.BACKEND_BASE64)

    # URL should be a data URL
    assert url.startswith("data:")
    assert "base64" in url
    mock_storage.assert_called_once()


@patch(
    "chat.agents.local_media_url_processors.default_storage.open", side_effect=Exception("S3 error")
)
@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_get_file_url_backend_base64_fallback(mock_policy, _mock_storage):
    """Test fallback to presigned URL when base64 encoding fails."""

    mock_policy.return_value = "fallback_presigned_url"

    url = _get_file_url_for_llm("test/key.pdf", FileToLLMMode.BACKEND_BASE64)

    # Should fall back to presigned URL
    assert url == "fallback_presigned_url"
    mock_policy.assert_called_once()


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_local_urls_multiple_images_with_modes(mock_get_file_url):
    """Test handling multiple images with mode-aware URL generation."""
    conversation = ChatConversationFactory()

    # Mock different URLs for different calls
    urls = ["url1", "url2", "url3"]
    mock_get_file_url.side_effect = urls

    key1 = f"{conversation.pk}/image1.jpg"
    key2 = f"{conversation.pk}/image2.png"
    key3 = f"{conversation.pk}/document.pdf"

    contents = [
        ImageUrl(url=f"/media-key/{key1}"),
        ImageUrl(url=f"/media-key/{key2}"),
        DocumentUrl(url=f"/media-key/{key3}"),
    ]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 3
    assert result[0].url == "url1"
    assert result[1].url == "url2"
    assert result[2].url == "url3"
    assert mock_get_file_url.call_count == 3


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_local_urls_mixed_external_and_local_urls(mock_get_file_url):
    """Test handling of mixed external and local URLs."""
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "mode-aware-url"

    key = f"{conversation.pk}/test.jpg"
    contents = [
        ImageUrl(url=f"/media-key/{key}"),  # Local URL - will be processed
        ImageUrl(url="https://external.com/image.jpg"),  # External URL - kept as is
        ImageUrl(url="http://another.com/image.png"),  # External URL - kept as is
    ]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 3
    assert result[0].url == "mode-aware-url"
    assert result[1].url == "https://external.com/image.jpg"
    assert result[2].url == "http://another.com/image.png"
    # Only one local URL was processed
    assert mock_get_file_url.call_count == 1


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_history_local_urls_with_mode_detection(mock_get_file_url):
    """Test that update_history_local_urls uses mode detection for URLs."""
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "mode-aware-url"

    key = f"{conversation.pk}/test.jpg"
    user_prompt_content = [ImageUrl(url=f"/media-key/{key}")]

    messages = [
        ModelRequest(parts=[UserPromptPart(content=user_prompt_content)]),
        ModelResponse(parts=[TextPart(content="I see your image.")]),
    ]

    with patch("chat.agents.local_media_url_processors.update_local_urls") as mock_update:
        mock_update.return_value = iter([ImageUrl(url="mode-aware-url")])
        result = update_history_local_urls(conversation, messages)

        assert len(result) == 2
        mock_update.assert_called_once()


def test_update_local_urls_preserves_other_url_types():
    """Test that update_local_urls preserves other URL types unchanged."""
    conversation = ChatConversationFactory()

    contents = [
        ImageUrl(url="data:image/png;base64,iVBORw0KG..."),  # Already data URL
        ImageUrl(url="https://example.com/image.jpg"),  # HTTPS
        ImageUrl(url="http://example.com/image.jpg"),  # HTTP
    ]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 3
    assert result[0].url == "data:image/png;base64,iVBORw0KG..."
    assert result[1].url == "https://example.com/image.jpg"
    assert result[2].url == "http://example.com/image.jpg"


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_local_urls_stores_updated_urls_mapping(mock_get_file_url):
    """Test that update_local_urls stores the mapping of new to old URLs."""
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "new-mode-aware-url"

    key = f"{conversation.pk}/test.jpg"
    old_url = f"/media-key/{key}"
    contents = [ImageUrl(url=old_url)]
    updated_urls = {}

    list(update_local_urls(conversation, contents, updated_urls))

    assert "new-mode-aware-url" in updated_urls
    assert updated_urls["new-mode-aware-url"] == old_url


def test_update_local_urls_security_prevents_other_conversation_access():
    """Test that security check prevents accessing other conversation's files."""
    conversation = ChatConversationFactory()
    other_conversation_key = "other-uuid/attachments/file.jpg"

    # Try to access file from different conversation
    contents = [ImageUrl(url=f"/media-key/{other_conversation_key}")]

    with patch("chat.agents.local_media_url_processors._get_file_url_for_llm") as mock_get:
        result = list(update_local_urls(conversation, contents))

        # URL should not be processed (security check failed)
        assert result[0].url == f"/media-key/{other_conversation_key}"
        # _get_file_url_for_llm should NOT be called
        mock_get.assert_not_called()


@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_get_file_url_is_called_with_correct_arguments(mock_get_file_url):
    """Test that _get_file_url_for_llm is called with correct arguments."""
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "processed-url"

    key = f"{conversation.pk}/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{key}")]

    list(update_local_urls(conversation, contents))

    # Verify the function was called with the S3 key (without /media-key/ prefix)
    mock_get_file_url.assert_called_once()
    call_args = mock_get_file_url.call_args
    assert call_args[0][0] == key  # First argument should be the S3 key


# ==================== Tests for FILE_TO_LLM_MODE settings ====================


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_with_presigned_url_mode(mock_policy, settings):
    """Test update_local_urls with PRESIGNED_URL mode."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.PRESIGNED_URL
    conversation = ChatConversationFactory()
    mock_policy.return_value = "https://s3.example.com/presigned-url"

    key = f"{conversation.pk}/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "https://s3.example.com/presigned-url"
    mock_policy.assert_called_once_with(key)


@patch("chat.agents.local_media_url_processors.generate_temporary_url")
def test_update_local_urls_with_backend_temporary_url_mode(mock_temp_url, settings):
    """Test update_local_urls with BACKEND_TEMPORARY_URL mode."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_TEMPORARY_URL
    conversation = ChatConversationFactory()
    mock_temp_url.return_value = "/api/v1.0/file-stream/temp-token-123/"

    key = f"{conversation.pk}/test.pdf"
    contents = [DocumentUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "/api/v1.0/file-stream/temp-token-123/"
    mock_temp_url.assert_called_once_with(key)


@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_update_local_urls_with_backend_base64_mode(mock_storage, settings):
    """Test update_local_urls with BACKEND_BASE64 mode."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_BASE64
    conversation = ChatConversationFactory()

    file_content = b"Mock image binary content"
    mock_file = BytesIO(file_content)
    mock_storage.return_value.__enter__.return_value = mock_file

    key = f"{conversation.pk}/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    # Should be a data URL
    assert result[0].url.startswith("data:")
    assert "base64" in result[0].url
    mock_storage.assert_called_once()


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_update_local_urls_backend_base64_fallback_on_error(mock_storage, mock_policy, settings):
    """Test that update_local_urls falls back to presigned URL when base64 fails."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_BASE64
    conversation = ChatConversationFactory()
    mock_storage.side_effect = Exception("S3 connection error")
    mock_policy.return_value = "https://s3.example.com/fallback-url"

    key = f"{conversation.pk}/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    # Should fall back to presigned URL
    assert result[0].url == "https://s3.example.com/fallback-url"
    mock_policy.assert_called_once_with(key)


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_multiple_files_presigned_mode(mock_policy, settings):
    """Test update_local_urls with multiple files in PRESIGNED_URL mode."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.PRESIGNED_URL
    conversation = ChatConversationFactory()
    mock_policy.side_effect = [
        "https://s3.example.com/image1-presigned",
        "https://s3.example.com/image2-presigned",
        "https://s3.example.com/document-presigned",
    ]

    key1 = f"{conversation.pk}/image1.jpg"
    key2 = f"{conversation.pk}/image2.png"
    key3 = f"{conversation.pk}/document.pdf"

    contents = [
        ImageUrl(url=f"/media-key/{key1}"),
        ImageUrl(url=f"/media-key/{key2}"),
        DocumentUrl(url=f"/media-key/{key3}"),
    ]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 3
    assert result[0].url == "https://s3.example.com/image1-presigned"
    assert result[1].url == "https://s3.example.com/image2-presigned"
    assert result[2].url == "https://s3.example.com/document-presigned"
    assert mock_policy.call_count == 3


@patch("chat.agents.local_media_url_processors.generate_temporary_url")
def test_update_local_urls_multiple_files_temporary_url_mode(mock_temp_url, settings):
    """Test update_local_urls with multiple files in BACKEND_TEMPORARY_URL mode."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_TEMPORARY_URL
    conversation = ChatConversationFactory()
    mock_temp_url.side_effect = [
        "/api/v1.0/file-stream/token1/",
        "/api/v1.0/file-stream/token2/",
        "/api/v1.0/file-stream/token3/",
    ]

    key1 = f"{conversation.pk}/image1.jpg"
    key2 = f"{conversation.pk}/image2.png"
    key3 = f"{conversation.pk}/document.pdf"

    contents = [
        ImageUrl(url=f"/media-key/{key1}"),
        ImageUrl(url=f"/media-key/{key2}"),
        DocumentUrl(url=f"/media-key/{key3}"),
    ]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 3
    assert result[0].url == "/api/v1.0/file-stream/token1/"
    assert result[1].url == "/api/v1.0/file-stream/token2/"
    assert result[2].url == "/api/v1.0/file-stream/token3/"
    assert mock_temp_url.call_count == 3


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_presigned_mode_preserves_mapping(mock_policy, settings):
    """Test that PRESIGNED_URL mode correctly stores updated URLs mapping."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.PRESIGNED_URL
    conversation = ChatConversationFactory()
    presigned_url = "https://s3.example.com/presigned-123"
    mock_policy.return_value = presigned_url

    key = f"{conversation.pk}/test.jpg"
    original_url = f"/media-key/{key}"
    contents = [ImageUrl(url=original_url)]
    updated_urls = {}

    list(update_local_urls(conversation, contents, updated_urls))

    assert presigned_url in updated_urls
    assert updated_urls[presigned_url] == original_url


@patch("chat.agents.local_media_url_processors.generate_temporary_url")
def test_update_local_urls_temporary_url_mode_preserves_mapping(mock_temp_url, settings):
    """Test that BACKEND_TEMPORARY_URL mode correctly stores updated URLs mapping."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_TEMPORARY_URL
    conversation = ChatConversationFactory()
    temp_url = "/api/v1.0/file-stream/temp-abc-def/"
    mock_temp_url.return_value = temp_url

    key = f"{conversation.pk}/test.pdf"
    original_url = f"/media-key/{key}"
    contents = [DocumentUrl(url=original_url)]
    updated_urls = {}

    list(update_local_urls(conversation, contents, updated_urls))

    assert temp_url in updated_urls
    assert updated_urls[temp_url] == original_url


@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_update_local_urls_base64_mode_preserves_mapping(mock_storage, settings):
    """Test that BACKEND_BASE64 mode correctly stores updated URLs mapping."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_BASE64
    conversation = ChatConversationFactory()

    file_content = b"test image content"
    mock_file = BytesIO(file_content)
    mock_storage.return_value.__enter__.return_value = mock_file

    key = f"{conversation.pk}/test.jpg"
    original_url = f"/media-key/{key}"
    contents = [ImageUrl(url=original_url)]
    updated_urls = {}

    result = list(update_local_urls(conversation, contents, updated_urls))

    # Verify mapping was stored
    assert len(updated_urls) == 1
    # The data URL should be the key in the mapping
    data_url = result[0].url
    assert data_url in updated_urls
    assert updated_urls[data_url] == original_url


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_presigned_mode_security_check(mock_policy, settings):
    """Test that PRESIGNED_URL mode respects security checks."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.PRESIGNED_URL
    conversation = ChatConversationFactory()
    other_key = "other-conversation-id/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{other_key}")]

    result = list(update_local_urls(conversation, contents))

    # URL should remain unchanged
    assert result[0].url == f"/media-key/{other_key}"
    # generate_retrieve_policy should not be called
    mock_policy.assert_not_called()


@patch("chat.agents.local_media_url_processors.generate_temporary_url")
def test_update_local_urls_temporary_mode_security_check(mock_temp_url, settings):
    """Test that BACKEND_TEMPORARY_URL mode respects security checks."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_TEMPORARY_URL
    conversation = ChatConversationFactory()
    other_key = "other-conversation-id/test.pdf"
    contents = [DocumentUrl(url=f"/media-key/{other_key}")]

    result = list(update_local_urls(conversation, contents))

    # URL should remain unchanged
    assert result[0].url == f"/media-key/{other_key}"
    # generate_temporary_url should not be called
    mock_temp_url.assert_not_called()


@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_update_local_urls_base64_mode_security_check(mock_storage, settings):
    """Test that BACKEND_BASE64 mode respects security checks."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_BASE64
    conversation = ChatConversationFactory()
    other_key = "other-conversation-id/test.jpg"
    contents = [ImageUrl(url=f"/media-key/{other_key}")]

    result = list(update_local_urls(conversation, contents))

    # URL should remain unchanged
    assert result[0].url == f"/media-key/{other_key}"
    # Storage should not be opened
    mock_storage.assert_not_called()


@pytest.mark.parametrize(
    "file_to_llm_mode",
    [
        FileToLLMMode.PRESIGNED_URL,
        FileToLLMMode.BACKEND_TEMPORARY_URL,
        FileToLLMMode.BACKEND_BASE64,
    ],
)
@patch("chat.agents.local_media_url_processors._get_file_url_for_llm")
def test_update_local_urls_all_modes_with_external_urls(
    mock_get_file_url, file_to_llm_mode, settings
):
    """Test that all modes preserve external URLs unchanged."""
    settings.FILE_TO_LLM_MODE = file_to_llm_mode
    conversation = ChatConversationFactory()
    mock_get_file_url.return_value = "processed-url"

    key = f"{conversation.pk}/test.jpg"
    external_urls = [
        "https://example.com/image.jpg",
        "http://another.com/image.png",
        "data:image/png;base64,iVBORw0KG...",
    ]

    contents = [ImageUrl(url=f"/media-key/{key}")] + [ImageUrl(url=url) for url in external_urls]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 4
    assert result[0].url == "processed-url"
    for i, external_url in enumerate(external_urls, start=1):
        assert result[i].url == external_url


@patch("chat.agents.local_media_url_processors.default_storage.open")
def test_update_local_urls_base64_mode_with_different_file_types(mock_storage, settings):
    """Test BACKEND_BASE64 mode with different file MIME types."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.BACKEND_BASE64
    conversation = ChatConversationFactory()

    # Test with different file types
    test_cases = [
        ("test.jpg", b"JPEG binary"),
        ("test.png", b"PNG binary"),
        ("test.pdf", b"PDF binary"),
        ("test.txt", b"Text content"),
    ]

    for filename, content in test_cases:
        mock_file = BytesIO(content)
        mock_storage.return_value.__enter__.return_value = mock_file

        key = f"{conversation.pk}/{filename}"
        contents = [ImageUrl(url=f"/media-key/{key}")]

        result = list(update_local_urls(conversation, contents))

        assert len(result) == 1
        # Should be a data URL
        assert result[0].url.startswith("data:")
        assert "base64" in result[0].url


@patch("chat.agents.local_media_url_processors.generate_retrieve_policy")
def test_update_local_urls_presigned_mode_with_special_characters_in_key(mock_policy, settings):
    """Test PRESIGNED_URL mode handles keys with special characters."""
    settings.FILE_TO_LLM_MODE = FileToLLMMode.PRESIGNED_URL
    conversation = ChatConversationFactory()
    mock_policy.return_value = "https://s3.example.com/presigned"

    # Key with special characters (should be handled properly by S3)
    key = f"{conversation.pk}/attachments/file (1).pdf"
    contents = [DocumentUrl(url=f"/media-key/{key}")]

    result = list(update_local_urls(conversation, contents))

    assert len(result) == 1
    assert result[0].url == "https://s3.example.com/presigned"
    mock_policy.assert_called_once_with(key)
