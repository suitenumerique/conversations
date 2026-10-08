"""Tests for the frontend-like HTTP client, against an in-memory transport."""

import json

import httpx
import pytest

from chat.evals.target.client import TargetClient, TargetError
from chat.evals.target.wire import AttachmentRef, Wire

BASE_URL = "http://target:18071"


def _client(handler) -> TargetClient:
    return TargetClient(httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(handler)))


def test_login_posts_admin_form_with_csrf():
    """Login fetches the CSRF cookie, then posts the admin form with it."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, headers={"set-cookie": "csrftoken=tok1; Path=/"})
        seen["body"] = request.content.decode()
        return httpx.Response(
            302,
            headers=[
                ("location", "/admin/"),
                ("set-cookie", "sessionid=s1; Path=/"),
                ("set-cookie", "csrftoken=tok2; Path=/"),
            ],
        )

    client = _client(handler)
    client.login("admin@example.com", "admin")

    assert "username=admin%40example.com" in seen["body"]
    assert "csrfmiddlewaretoken=tok1" in seen["body"]


@pytest.mark.parametrize("cookie", ["conversations_sessionid", "conversations_sessionid_s4"])
def test_login_accepts_renamed_session_cookie(cookie):
    """Deployments rename the session cookie (prefix, per-worktree suffix); login succeeds."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, headers={"set-cookie": "csrftoken=tok1; Path=/"})
        return httpx.Response(
            302,
            headers=[
                ("location", "/admin/"),
                ("set-cookie", f"{cookie}=s1; Path=/"),
            ],
        )

    _client(handler).login("admin@example.com", "admin")


def test_login_fails_without_session():
    """A re-rendered login page (bad credentials) raises."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, headers={"set-cookie": "csrftoken=tok1; Path=/"})
        return httpx.Response(200, text="Please enter the correct email")

    with pytest.raises(TargetError, match="login failed"):
        _client(handler).login("admin@example.com", "wrong")


def test_create_chat_sends_csrf_header():
    """Unsafe API calls carry the CSRF token for DRF SessionAuthentication."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["csrf"] = request.headers.get("x-csrftoken")
        seen["path"] = request.url.path
        return httpx.Response(201, json={"id": "chat-1"})

    client = _client(handler)
    client._http.cookies.set("csrftoken", "tok2")  # pylint: disable=protected-access

    assert client.create_chat("smoke") == "chat-1"
    assert seen == {"csrf": "tok2", "path": "/api/v1.0/chats/"}


def test_upload_posts_multipart():
    """Upload goes to backend-upload with file and file_name."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = request.content
        return httpx.Response(201, json={"id": "att-1", "upload_state": "analyzing"})

    attachment = _client(handler).upload("chat-1", "cr.docx", b"PK-bytes")

    assert attachment["id"] == "att-1"
    assert seen["path"] == "/api/v1.0/chats/chat-1/attachments/backend-upload/"
    assert b'name="file_name"' in seen["body"]
    assert b"PK-bytes" in seen["body"]


def test_api_error_raises_with_status():
    """HTTP errors surface method, path and status."""
    client = _client(lambda request: httpx.Response(403, json={"detail": "nope"}))

    with pytest.raises(TargetError, match=r"POST /api/v1.0/chats/ -> HTTP 403"):
        client.create_chat("smoke")


def _attachment_json(state: str) -> dict:
    return {
        "id": "att-1",
        "key": "chat-1/attachments/f.docx",
        "file_name": "cr.docx",
        "content_type": "application/x-test",
        "upload_state": state,
    }


def test_wait_ready_polls_until_ready():
    """Polling stops on ready and returns the reference used in messages."""
    states = iter(["analyzing", "analyzing", "ready"])
    client = _client(lambda request: httpx.Response(200, json=_attachment_json(next(states))))

    ref = client.wait_ready("chat-1", "att-1", sleep=lambda _seconds: None)

    assert ref == AttachmentRef(
        key="chat-1/attachments/f.docx", file_name="cr.docx", content_type="application/x-test"
    )


def test_wait_ready_rejects_suspicious():
    """A terminal state other than ready is an error, not a usable document."""
    client = _client(lambda request: httpx.Response(200, json=_attachment_json("suspicious")))

    with pytest.raises(TargetError, match="suspicious"):
        client.wait_ready("chat-1", "att-1", sleep=lambda _seconds: None)


def test_wait_ready_times_out():
    """An attachment stuck in analyzing stops the run after the timeout."""
    ticks = iter([0.0, 1.0, 2.0, 3.0])
    client = _client(lambda request: httpx.Response(200, json=_attachment_json("analyzing")))

    with pytest.raises(TargetError, match="not ready after 2"):
        client.wait_ready(
            "chat-1", "att-1", timeout=2.0, sleep=lambda _seconds: None, clock=lambda: next(ticks)
        )


def test_send_v4_streams_and_parses():
    """send posts the v4 body with ?protocol=data and parses the data stream."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["query"] = dict(request.url.params)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text='0:"Bonjour"\n0:" !"\nd:{"finishReason":"stop"}\n')

    ref = AttachmentRef(key="k", file_name="cr.docx", content_type="application/x-test")
    result = _client(handler).send("chat-1", Wire.V4, "Résume", [ref])

    assert result.text == "Bonjour !"
    assert seen["query"] == {"protocol": "data"}
    assert seen["body"]["messages"][0]["experimental_attachments"][0]["url"] == "/media-key/k"


def test_send_non_200_raises():
    """A rejected chat request surfaces the status and body."""
    client = _client(lambda request: httpx.Response(400, text="Frontend input error"))

    with pytest.raises(TargetError, match="HTTP 400"):
        client.send("chat-1", Wire.V5, "Résume", [])


def _turn_handler(answers, bodies):
    """Answer each conversation POST with the next v5 text, recording request bodies."""
    replies = iter(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        text = next(replies)
        frame = json.dumps({"type": "text-delta", "id": "t", "delta": text}) if text else ""
        return httpx.Response(200, text=f"data: {frame}\n\ndata: [DONE]\n\n" if text else "")

    return handler


def test_converse_replays_history_and_attaches_only_first_turn():
    """Turn 2 resends turn 1 (user + assistant) and no attachments of its own."""
    bodies = []
    ref = AttachmentRef(key="k", file_name="cr.docx", content_type="application/x-test")
    client = _client(_turn_handler(["Synthèse", "Tableau"], bodies))

    results = client.converse("chat-1", Wire.V5, ["Résume", "En tableau"], [ref])

    assert [result.text for result in results] == ["Synthèse", "Tableau"]
    first, second = (body["messages"] for body in bodies)
    assert [part["type"] for part in first[0]["parts"]] == ["text", "file"]
    assert [message["role"] for message in second] == ["user", "assistant", "user"]
    assert second[0] == first[0]
    assert second[1]["parts"] == [{"type": "text", "text": "Synthèse"}]
    assert [part["type"] for part in second[2]["parts"]] == ["text"]


def test_converse_raises_on_empty_turn():
    """An empty answer is an infrastructure failure naming the turn."""
    client = _client(_turn_handler(["Synthèse", ""], []))

    with pytest.raises(TargetError, match="turn 2: empty answer"):
        client.converse("chat-1", Wire.V5, ["Résume", "En tableau"], [])


def test_converse_raises_on_stream_error():
    """A stream error event is an infrastructure failure naming the turn."""

    def handler(request: httpx.Request) -> httpx.Response:
        frame = json.dumps({"type": "error", "errorText": "model unavailable"})
        return httpx.Response(200, text=f"data: {frame}\n\n")

    with pytest.raises(TargetError, match="turn 1: stream errors: model unavailable"):
        _client(handler).converse("chat-1", Wire.V5, ["Résume"], [])


def test_converse_retries_a_failed_turn_after_a_delay():
    """A transient provider error (e.g. model_busy) is retried before giving up."""
    waits = []
    frames = iter(
        [
            f"data: {json.dumps({'type': 'error', 'errorText': 'model_busy'})}\n\n",
            f"data: {json.dumps({'type': 'text-delta', 'id': 't', 'delta': 'Synthèse'})}\n\n",
        ]
    )
    client = TargetClient(
        httpx.Client(
            base_url=BASE_URL,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text=next(frames))),
        ),
        sleep=waits.append,
        retry_delays=(30.0, 90.0),
    )

    results = client.converse("chat-1", Wire.V5, ["Résume"], [])

    assert [result.text for result in results] == ["Synthèse"]
    assert waits == [30.0]


def test_converse_gives_up_after_all_retries():
    """When every retry fails, the turn is an infrastructure failure."""
    waits = []
    frame = f"data: {json.dumps({'type': 'error', 'errorText': 'model_busy'})}\n\n"
    client = TargetClient(
        httpx.Client(
            base_url=BASE_URL,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text=frame)),
        ),
        sleep=waits.append,
        retry_delays=(30.0, 90.0),
    )

    with pytest.raises(TargetError, match="turn 1: stream errors: model_busy"):
        client.converse("chat-1", Wire.V5, ["Résume"], [])
    assert waits == [30.0, 90.0]


def test_configure_user_patches_language_and_smart_search():
    """Eval user settings are user fields: read my id, then PATCH them."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content.decode()))
        if request.url.path == "/api/v1.0/users/me/":
            return httpx.Response(200, json={"id": "u1"})
        return httpx.Response(200, json={"id": "u1"})

    _client(handler).configure_user(smart_web_search=True, language="fr-fr")

    assert seen[0][:2] == ("GET", "/api/v1.0/users/me/")
    assert seen[1][:2] == ("PATCH", "/api/v1.0/users/u1/")
    assert json.loads(seen[1][2]) == {"allow_smart_web_search": True, "language": "fr-fr"}


def test_create_project_sends_instructions_and_required_fields():
    """Projects need an icon and a color; instructions ride along."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "p1"})

    assert _client(handler).create_project("eval", "Réponds en anglais") == "p1"
    assert seen["path"] == "/api/v1.0/projects/"
    assert seen["body"] == {
        "title": "eval",
        "icon": "folder",
        "color": "color_1",
        "llm_instructions": "Réponds en anglais",
    }


def test_create_chat_in_project():
    """A chat is attached to its project at creation (immutable afterwards)."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "chat-1"})

    _client(handler).create_chat("eval", project="p1")

    assert seen["body"] == {"title": "eval", "project": "p1"}


def test_upload_to_project_posts_to_project_backend_upload():
    """Project files go to the project's backend-upload action."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(201, json={"id": "att-1"})

    assert _client(handler).upload_to_project("p1", "cr.docx", b"x") == {"id": "att-1"}
    assert seen["path"] == "/api/v1.0/projects/p1/attachments/backend-upload/"


def test_wait_project_indexed_polls_until_indexed():
    """A project file is usable once uploaded (ready) and indexed."""
    states = iter([("analyzing", "not_indexed"), ("ready", "indexing"), ("ready", "indexed")])

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1.0/projects/p1/attachments/att-1/"
        upload_state, index_state = next(states)
        return httpx.Response(200, json={"upload_state": upload_state, "index_state": index_state})

    _client(handler).wait_project_indexed("p1", "att-1", sleep=lambda _: None)


@pytest.mark.parametrize(
    ("upload_state", "index_state"), [("ready", "failed"), ("suspicious", "not_indexed")]
)
def test_wait_project_indexed_raises_on_terminal_failure(upload_state, index_state):
    """Failed indexing or a rejected upload raises at once instead of polling to timeout."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"upload_state": upload_state, "index_state": index_state})

    with pytest.raises(TargetError, match="att-1"):
        _client(handler).wait_project_indexed("p1", "att-1", sleep=lambda _: None)
