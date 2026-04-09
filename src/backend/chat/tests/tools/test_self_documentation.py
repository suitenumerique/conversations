"""Unit tests for self-documentation payload builder."""

from types import SimpleNamespace

from chat.tools.self_documentation import build_self_documentation_payload


def test_build_self_documentation_payload_merges_static_and_runtime(settings):
    """The payload should include static doc plus runtime model/features."""
    configuration = SimpleNamespace(
        model_name="provider/model",
        human_readable_name="Provider Model",
        provider=SimpleNamespace(kind="openai", hrid="provider"),
        settings=SimpleNamespace(max_tokens=4096),
    )

    payload = build_self_documentation_payload(
        model_hrid="default-model",
        model_configuration=configuration,
        web_search_feature_enabled=True,
        smart_web_search_enabled=False,
        document_upload_enabled=True,
        web_search_runtime_enabled=False,
    )

    assert "self_documentation" in payload
    assert payload["runtime"]["model"]["hrid"] == "default-model"
    assert payload["runtime"]["model"]["max_tokens"] == 4096
    assert payload["runtime"]["features"]["web_search_feature_enabled"] is True
    assert payload["runtime"]["features"]["smart_web_search_enabled"] is False
    assert payload["runtime"]["features"]["internet_access_realtime"] is False
    assert payload["runtime"]["attachments"]["max_size_bytes"] == settings.ATTACHMENT_MAX_SIZE
    assert (
        payload["runtime"]["attachments"]["unsafe_mime_types_blacklist"]
        == settings.ATTACHMENT_UNSAFE_MIME_TYPES
    )


def test_build_self_documentation_payload_handles_missing_max_tokens():
    """The payload should gracefully expose null max_tokens when unset."""
    configuration = SimpleNamespace(
        model_name="provider/model",
        human_readable_name="Provider Model",
        provider=SimpleNamespace(kind="openai", hrid="provider"),
        settings=None,
    )

    payload = build_self_documentation_payload(
        model_hrid="default-model",
        model_configuration=configuration,
        web_search_feature_enabled=False,
        smart_web_search_enabled=False,
        document_upload_enabled=False,
        web_search_runtime_enabled=False,
    )

    assert payload["runtime"]["model"]["max_tokens"] is None
