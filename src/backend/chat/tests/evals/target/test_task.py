"""Tests for the task function that runs one case against a target stack."""

import asyncio
import io
import json
import threading

import httpx
import pytest
from markitdown import MarkItDown

from chat.evals import EvalInputs
from chat.evals.target.client import TargetClient, TargetError
from chat.evals.target.runtime import Target, configure_target, current_target
from chat.evals.target.task import (
    load_document,
    make_target_task_fn,
    run_with_time_limit,
    user_turns,
)


@pytest.fixture(name="documents_dir")
def documents_dir_fixture(tmp_path):
    """A fixture folder with one markdown meeting report."""
    (tmp_path / "cr-mars.md").write_text(
        "Compte rendu du 3 mars\n\nResponsable : Mme Durand\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture(name="target")
def target_fixture():
    """Configure a target for the duration of a test."""
    configured = Target(
        url="http://target:18071", tag="v0.0.21", model="albert-mistral-medium-2508"
    )
    configure_target(configured)
    yield configured
    configure_target(None)


def test_current_target_requires_configuration():
    """Running a target dataset without a target is a clear error."""
    configure_target(None)

    with pytest.raises(RuntimeError, match="--target-url"):
        current_target()


def test_load_document_renders_markdown_as_docx(documents_dir):
    """Fixtures are markdown in git and uploaded as the docx a user would attach."""
    file_name, content = load_document(documents_dir, "cr-mars")

    text = MarkItDown().convert_stream(io.BytesIO(content), file_extension=".docx").text_content
    assert file_name == "cr-mars.docx"
    assert "Responsable : Mme Durand" in text


class _FakeTarget:
    """In-memory target: records requests and answers each turn with a v4 frame."""

    def __init__(self):
        self.requests = []
        self.bodies = []
        self.sent = []

    # path -> (status, JSON body, whether the request body is recorded)
    ROUTES = {
        "/api/v1.0/users/me/": (200, {"id": "u1"}, False),
        "/api/v1.0/users/u1/": (200, {"id": "u1"}, True),
        "/api/v1.0/projects/": (201, {"id": "p1"}, True),
        "/api/v1.0/projects/p1/attachments/backend-upload/": (201, {"id": "patt-1"}, False),
        "/api/v1.0/projects/p1/attachments/patt-1/": (
            200,
            {"upload_state": "ready", "index_state": "indexed"},
            False,
        ),
        "/api/v1.0/chats/": (201, {"id": "chat-1"}, True),
        "/api/v1.0/chats/chat-1/attachments/backend-upload/": (
            201,
            {"id": "att-1", "upload_state": "analyzing"},
            False,
        ),
        "/api/v1.0/chats/chat-1/attachments/att-1/": (
            200,
            {
                "id": "att-1",
                "key": "chat-1/attachments/f.docx",
                "file_name": "cr-mars.docx",
                "content_type": "application/x-test",
                "upload_state": "ready",
            },
            False,
        ),
    }

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Route a request to the canned response of the endpoint it targets."""
        self.requests.append((request.method, request.url.path))
        path = request.url.path
        if path == "/admin/login/":
            if request.method == "GET":
                return httpx.Response(200, headers={"set-cookie": "csrftoken=t; Path=/"})
            return httpx.Response(302, headers={"set-cookie": "conversations_sessionid=s; Path=/"})
        if path in self.ROUTES:
            status, body, record = self.ROUTES[path]
            if record:
                self.bodies.append(json.loads(request.content))
            return httpx.Response(status, json=body)
        return self._answer(request)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        """Stream one turn: a summarize call, a source, text."""
        last = json.loads(request.content)["messages"][-1]
        self.sent.append(last.get("content") or last["parts"][0]["text"])
        turn = len(self.sent)
        call = json.dumps(
            {"toolCallId": "c", "toolName": "summarize", "args": {"instructions": "x"}}
        )
        frames = [
            f"9:{call}",
            'h:{"sourceType":"url","id":"s1","url":"https://src.fr"}',
            f'0:"Réponse {turn}"',
        ]
        return httpx.Response(200, text="\n".join(frames) + "\n")


def _run(fake, documents_dir, inputs, **factory_kwargs):
    """Run one case through the task fn against the fake target."""

    def client_factory(configured):
        return TargetClient(
            httpx.Client(base_url=configured.url, transport=httpx.MockTransport(fake.handler))
        )

    run_agent = make_target_task_fn(documents_dir, client_factory, **factory_kwargs)("ignored")
    return asyncio.run(run_agent(inputs))


def test_task_runs_all_turns_and_returns_last_answer(documents_dir, target):
    """The task logs in once, uploads fixtures, sends every turn, returns the last text."""
    fake = _FakeTarget()

    def client_factory(configured):
        assert configured == target
        return TargetClient(
            httpx.Client(base_url=configured.url, transport=httpx.MockTransport(fake.handler))
        )

    run_agent = make_target_task_fn(documents_dir, client_factory)("ignored-harness-model")
    answer = asyncio.run(
        run_agent(
            EvalInputs(user_message="Résume", attachments=["cr-mars"], follow_ups=["En tableau"])
        )
    )

    assert answer == "Réponse 2"
    assert fake.requests.count(("POST", "/admin/login/")) == 1
    assert fake.requests.count(("POST", "/api/v1.0/chats/chat-1/conversation/")) == 2


def test_task_sets_smart_web_search_once(documents_dir, target):  # pylint: disable=unused-argument
    """The dataset's web-search opt-in is applied to the eval user before any case."""
    fake = _FakeTarget()

    _run(fake, documents_dir, EvalInputs(user_message="Q"), smart_web_search=True)

    assert {"allow_smart_web_search": True, "language": "fr-fr"} in fake.bodies


def test_task_runs_cases_as_a_french_user(documents_dir, target):  # pylint: disable=unused-argument
    """Prod users get "Answer in french" from their locale; the eval user must too.

    Without a language the backend falls back to LANGUAGE_CODE (en-us) and tells
    the model to answer in English, which confounds every language check.
    """
    fake = _FakeTarget()

    _run(fake, documents_dir, EvalInputs(user_message="Q"))

    assert fake.bodies[0] == {"allow_smart_web_search": False, "language": "fr-fr"}


def test_task_creates_project_with_instructions_and_files(documents_dir, target):  # pylint: disable=unused-argument
    """Project cases create the project, upload and index its files, then chat inside it."""
    fake = _FakeTarget()

    _run(
        fake,
        documents_dir,
        EvalInputs(
            user_message="Synthétise",
            project_instructions="Réponds en anglais",
            project_attachments=["cr-mars"],
        ),
    )

    assert fake.bodies[1]["llm_instructions"] == "Réponds en anglais"
    assert ("POST", "/api/v1.0/projects/p1/attachments/backend-upload/") in fake.requests
    assert {"title": "eval", "project": "p1"} in fake.bodies


def test_user_turns_prefixes_tool_output_to_the_first_message():
    """A case's tool_output is sent as context ahead of the first message only."""
    inputs = EvalInputs(user_message="Où ?", tool_output="https://a.fr", follow_ups=["Et ?"])

    assert user_turns(inputs) == [
        "[Tool output]\nhttps://a.fr\n\n[User question]\nOù ?",
        "Et ?",
    ]


def test_run_with_time_limit_returns_the_result():
    """A case that finishes in time returns its result."""
    assert asyncio.run(run_with_time_limit(lambda: "ok", 5)) == "ok"


def test_run_with_time_limit_propagates_errors():
    """A case that raises keeps its error (reported as a task failure)."""

    def failing():
        raise TargetError("boom")

    with pytest.raises(TargetError, match="boom"):
        asyncio.run(run_with_time_limit(failing, 5))


def test_run_with_time_limit_abandons_a_hung_case():
    """A case still running at the limit fails, and the hung thread blocks nothing."""
    release = threading.Event()

    with pytest.raises(TargetError, match="still running after 0s"):
        asyncio.run(run_with_time_limit(release.wait, 0.1))
    release.set()
