"""Task function running one eval case against the configured target stack."""

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path

import httpx
from pydantic_evals.dataset import set_eval_attribute

from chat.evals import EvalInputs
from chat.evals.target.client import TargetClient, TargetError
from chat.evals.target.fixtures import build_docx
from chat.evals.target.runtime import Target, current_target
from chat.evals.target.wire import StreamResult, wire_for_tag

# Albert sometimes answers 503 (model_busy) under load: retry a turn twice.
TURN_RETRY_DELAYS = (30.0, 90.0)
# A provider can hold a streamed answer open without finishing (each read stays under the
# HTTP timeout): past this, the case fails and the run moves on.
CASE_TIME_LIMIT = 15 * 60.0
# Prod users are French; without a language the backend falls back to en-us and
# instructs the model to answer in English.
EVAL_USER_LANGUAGE = "fr-fr"


def load_document(documents_dir: Path, name: str) -> tuple[str, bytes]:
    """Render the markdown fixture `<name>.md` as the docx a user would attach."""
    source = (documents_dir / f"{name}.md").read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if line.strip()]
    return f"{name}.docx", build_docx(lines)


def user_turns(inputs: EvalInputs) -> list[str]:
    """The user messages to send; a case's tool_output prefixes the first.

    tool_output is context the user supplies (e.g. search results with their URLs), sent
    as part of the message the way the in-process runner injects it.
    """
    first = inputs.user_message
    if inputs.tool_output:
        first = f"[Tool output]\n{inputs.tool_output}\n\n[User question]\n{first}"
    return [first, *inputs.follow_ups]


async def run_with_time_limit[T](function: Callable[[], T], time_limit: float) -> T:
    """Run blocking `function` in a daemon thread; raise TargetError after `time_limit` seconds.

    A daemon thread, not asyncio.to_thread: a hung request then keeps neither the event
    loop's shutdown nor the process's exit waiting.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def settle(result=None, error: BaseException | None = None) -> None:
        if future.done():  # timed out meanwhile
            return
        if error is None:
            future.set_result(result)
        else:
            future.set_exception(error)

    def target() -> None:
        try:
            outcome = (function(), None)
        except BaseException as error:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            outcome = (None, error)
        try:
            loop.call_soon_threadsafe(settle, *outcome)
        except RuntimeError:  # the loop closed after the time limit: nobody is waiting
            pass

    threading.Thread(target=target, daemon=True).start()
    try:
        return await asyncio.wait_for(future, time_limit)
    except TimeoutError as error:
        raise TargetError(f"case still running after {time_limit:.0f}s: abandoned") from error


def _default_client(target: Target) -> TargetClient:
    return TargetClient(
        httpx.Client(base_url=target.url, timeout=60.0), retry_delays=TURN_RETRY_DELAYS
    )


def _open_chat(client: TargetClient, inputs: EvalInputs, documents_dir: Path) -> str:
    """Create the case's conversation, inside a fresh project when the case has one."""
    if inputs.project_instructions is None and not inputs.project_attachments:
        return client.create_chat("eval")
    project_id = client.create_project("eval", inputs.project_instructions or "")
    for name in inputs.project_attachments:
        file_name, content = load_document(documents_dir, name)
        uploaded = client.upload_to_project(project_id, file_name, content)
        client.wait_project_indexed(project_id, uploaded["id"])
    return client.create_chat("eval", project=project_id)


def make_target_task_fn(documents_dir: Path, client_factory=None, *, smart_web_search=False):
    """Return a TaskFactory whose task runs cases on the configured target.

    `smart_web_search` is the eval user's opt-in for model-decided web search,
    applied once per dataset run with the user's language (off is the prod default).
    """

    def factory(_model_hrid: str):
        # The model under test is the target's (--target-model), not the harness's.
        target = current_target()
        client = (client_factory or _default_client)(target)
        client.login(target.admin_email, target.admin_password)
        client.configure_user(smart_web_search=smart_web_search, language=EVAL_USER_LANGUAGE)
        wire = wire_for_tag(target.tag)

        def run_case(inputs: EvalInputs) -> list[StreamResult]:
            chat_id = _open_chat(client, inputs, documents_dir)
            attachments = []
            for name in inputs.attachments:
                file_name, content = load_document(documents_dir, name)
                uploaded = client.upload(chat_id, file_name, content)
                attachments.append(client.wait_ready(chat_id, uploaded["id"]))
            return client.converse(chat_id, wire, user_turns(inputs), attachments)

        async def run_agent(inputs: EvalInputs) -> str:
            results = await run_with_time_limit(lambda: run_case(inputs), CASE_TIME_LIMIT)
            scored = results[-1]
            # Attributes live in a contextvar: record them here, not in the thread.
            set_eval_attribute("tool_calls", scored.tool_calls)
            set_eval_attribute("turns", len(results))
            set_eval_attribute("turn_texts", [result.text for result in results])
            set_eval_attribute("sources", scored.sources)
            set_eval_attribute("tool_output", "\n".join([*scored.tool_outputs, *scored.sources]))
            return scored.text

        return run_agent

    return factory
