"""HTTP client that drives a target Conversations stack the way the frontend does."""

import time

import httpx

from chat.evals.target.wire import (
    AttachmentRef,
    StreamResult,
    Wire,
    build_assistant_message,
    build_user_message,
    conversation_query,
    parse_stream,
)

API_PREFIX = "/api/v1.0"
TERMINAL_UPLOAD_STATES = {"ready", "suspicious", "file_too_large_to_analyze"}
STREAM_TIMEOUT = httpx.Timeout(10.0, read=600.0)


class TargetError(RuntimeError):
    """The target rejected a step of the flow."""


class TargetClient:
    """Session-authenticated client for one target stack."""

    def __init__(self, http: httpx.Client, *, sleep=time.sleep, retry_delays=()):
        self._http = http
        self._sleep = sleep
        # Waits (seconds) before retrying a turn that failed transiently (e.g.
        # model_busy, the provider's 503); empty means no retry.
        self._retry_delays = tuple(retry_delays)

    def _csrf_token(self) -> str:
        return self._http.cookies.get("csrftoken", "")

    def _api_headers(self) -> dict[str, str]:
        return {"X-CSRFToken": self._csrf_token()}

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.is_error:
            raise TargetError(
                f"{response.request.method} {response.request.url.path} -> "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

    def login(self, email: str, password: str) -> None:
        """Open a Django admin session (staff superuser)."""
        self._check(self._http.get("/admin/login/"))
        response = self._http.post(
            "/admin/login/",
            data={
                "username": email,
                "password": password,
                "csrfmiddlewaretoken": self._csrf_token(),
                "next": "/admin/",
            },
        )
        # The session cookie name is a deployment setting (conversations_sessionid, or with a
        # per-worktree suffix such as conversations_sessionid_s4).
        has_session = any("sessionid" in name for name in self._http.cookies)
        if response.status_code != 302 or not has_session:
            raise TargetError(f"Admin login failed (HTTP {response.status_code})")

    def create_chat(self, title: str, project: str | None = None) -> str:
        """Create an empty conversation (inside `project` if given) and return its id."""
        body = {"title": title} if project is None else {"title": title, "project": project}
        response = self._http.post(f"{API_PREFIX}/chats/", json=body, headers=self._api_headers())
        self._check(response)
        return response.json()["id"]

    def configure_user(self, *, smart_web_search: bool, language: str) -> None:
        """Set the logged-in user's smart web search opt-in and interface language.

        The language drives the agent's "Answer in <language>" instruction.
        """
        response = self._http.get(f"{API_PREFIX}/users/me/")
        self._check(response)
        response = self._http.patch(
            f"{API_PREFIX}/users/{response.json()['id']}/",
            json={"allow_smart_web_search": smart_web_search, "language": language},
            headers=self._api_headers(),
        )
        self._check(response)

    def create_project(self, title: str, llm_instructions: str) -> str:
        """Create a project with custom instructions and return its id."""
        response = self._http.post(
            f"{API_PREFIX}/projects/",
            json={
                "title": title,
                "icon": "folder",
                "color": "color_1",
                "llm_instructions": llm_instructions,
            },
            headers=self._api_headers(),
        )
        self._check(response)
        return response.json()["id"]

    def upload(self, chat_id: str, file_name: str, content: bytes) -> dict:
        """Upload a file through the backend (backend_to_s3 flow)."""
        response = self._http.post(
            f"{API_PREFIX}/chats/{chat_id}/attachments/backend-upload/",
            data={"file_name": file_name},
            files={"file": (file_name, content)},
            headers=self._api_headers(),
        )
        self._check(response)
        return response.json()

    def upload_to_project(self, project_id: str, file_name: str, content: bytes) -> dict:
        """Upload a file to a project through the backend (backend_to_s3 flow)."""
        response = self._http.post(
            f"{API_PREFIX}/projects/{project_id}/attachments/backend-upload/",
            data={"file_name": file_name},
            files={"file": (file_name, content)},
            headers=self._api_headers(),
        )
        self._check(response)
        return response.json()

    def wait_project_indexed(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        project_id: str,
        attachment_id: str,
        *,
        timeout: float = 300.0,
        poll_interval: float = 2.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        """Poll a project attachment until uploaded and indexed; raise on any failure."""
        deadline = clock() + timeout
        while True:
            response = self._http.get(
                f"{API_PREFIX}/projects/{project_id}/attachments/{attachment_id}/"
            )
            self._check(response)
            attachment = response.json()
            upload_state, index_state = attachment["upload_state"], attachment["index_state"]
            if upload_state == "ready" and index_state == "indexed":
                return
            rejected = upload_state in TERMINAL_UPLOAD_STATES and upload_state != "ready"
            if rejected or index_state == "failed":
                raise TargetError(
                    f"Project attachment {attachment_id} ended {upload_state}/{index_state}"
                )
            if clock() >= deadline:
                raise TargetError(
                    f"Project attachment {attachment_id} not indexed after {timeout:g}s "
                    f"({upload_state}/{index_state})"
                )
            sleep(poll_interval)

    def wait_ready(  # noqa: PLR0913  # pylint: disable=too-many-arguments
        self,
        chat_id: str,
        attachment_id: str,
        *,
        timeout: float = 180.0,
        poll_interval: float = 1.0,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> AttachmentRef:
        """Poll an attachment until it is ready; raise on any other outcome."""
        deadline = clock() + timeout
        while True:
            response = self._http.get(f"{API_PREFIX}/chats/{chat_id}/attachments/{attachment_id}/")
            self._check(response)
            attachment = response.json()
            state = attachment["upload_state"]
            if state in TERMINAL_UPLOAD_STATES:
                if state != "ready":
                    raise TargetError(f"Attachment {attachment_id} ended in state {state}")
                return AttachmentRef(
                    key=attachment["key"],
                    file_name=attachment["file_name"],
                    content_type=attachment["content_type"],
                )
            if clock() >= deadline:
                raise TargetError(
                    f"Attachment {attachment_id} not ready after {timeout:g}s (state {state})"
                )
            sleep(poll_interval)

    def _post_messages(self, chat_id: str, wire: Wire, messages: list[dict]) -> StreamResult:
        with self._http.stream(
            "POST",
            f"{API_PREFIX}/chats/{chat_id}/conversation/",
            params=conversation_query(wire),
            json={"messages": messages},
            headers=self._api_headers(),
            timeout=STREAM_TIMEOUT,
        ) as response:
            if response.status_code != 200:
                response.read()
                raise TargetError(
                    f"POST conversation -> HTTP {response.status_code}: {response.text[:500]}"
                )
            return parse_stream(response.iter_lines(), wire)

    def send(
        self, chat_id: str, wire: Wire, text: str, attachments: list[AttachmentRef]
    ) -> StreamResult:
        """Send one user message and read the whole answer stream."""
        return self._post_messages(chat_id, wire, [build_user_message(wire, text, attachments)])

    def _send_turn(
        self, chat_id: str, wire: Wire, messages: list[dict], number: int
    ) -> StreamResult:
        """Post one turn, retrying after each configured delay if it fails."""
        for delay in (*self._retry_delays, None):
            result = self._post_messages(chat_id, wire, messages)
            problem = (
                f"turn {number}: stream errors: {'; '.join(result.errors)}"
                if result.errors
                else f"turn {number}: empty answer"
                if not result.text.strip()
                else None
            )
            if problem is None:
                return result
            if delay is None:
                raise TargetError(problem)
            self._sleep(delay)
        raise AssertionError("unreachable")

    def converse(
        self, chat_id: str, wire: Wire, turns: list[str], attachments: list[AttachmentRef]
    ) -> list[StreamResult]:
        """Send user turns in order, replaying history like the frontend.

        Attachments ride on the first turn only. Each turn must produce text
        without stream errors, otherwise the run is an infrastructure failure.
        """
        history: list[dict] = []
        results = []
        for number, text in enumerate(turns, start=1):
            user_message = build_user_message(wire, text, attachments if number == 1 else [])
            result = self._send_turn(chat_id, wire, [*history, user_message], number)
            history += [user_message, build_assistant_message(wire, result.text)]
            results.append(result)
        return results
