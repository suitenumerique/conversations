"""Task function running one eval case against the configured target stack."""

import asyncio
import re
from pathlib import Path

import httpx
from pydantic_evals.dataset import set_eval_attribute

from chat.evals import EvalInputs
from chat.evals.target.client import TargetClient, TargetError
from chat.evals.target.fixtures import build_docx
from chat.evals.target.runtime import ADMIN_EMAIL, ADMIN_PASSWORD, Target, current_target
from chat.evals.target.wire import StreamResult, tag_at_least, wire_for_tag

# Albert sometimes answers 503 (model_busy) under load: retry a turn twice.
TURN_RETRY_DELAYS = (30.0, 90.0)
# History summarization (and its visible `summarize` tool call) shipped in v0.0.22.
FIRST_SUMMARIZING_RELEASE = (0, 0, 22)
_PASTE_RE = re.compile(r"\{\{paste:([\w-]+)\}\}")
# Prod users are French; without a language the backend falls back to en-us and
# instructs the model to answer in English.
EVAL_USER_LANGUAGE = "fr-fr"


def load_document(documents_dir: Path, name: str) -> tuple[str, bytes]:
    """Render the markdown fixture `<name>.md` as the docx a user would attach."""
    source = (documents_dir / f"{name}.md").read_text(encoding="utf-8")
    lines = [line for line in source.splitlines() if line.strip()]
    return f"{name}.docx", build_docx(lines)


def expand_pastes(text: str, documents_dir: Path) -> str:
    """Replace each {{paste:<name>}} marker with the text of fixture `<name>.md`."""
    return _PASTE_RE.sub(
        lambda match: (documents_dir / f"{match.group(1)}.md").read_text(encoding="utf-8"), text
    )


def _is_history_summary(call: dict) -> bool:
    args = call.get("args") or {}
    return call.get("name") == "summarize" and args.get("summary_scope") == "conversation"


def check_history_summary(results: list[StreamResult], expected: bool | None, tag: str) -> None:
    """Raise when the target's conversation summary contradicts the case's expectation.

    Targets without history summarization must never summarize, whatever the case expects.
    """
    if expected is None:
        return
    required = expected and tag_at_least(tag, FIRST_SUMMARIZING_RELEASE)
    observed = any(_is_history_summary(call) for result in results for call in result.tool_calls)
    if observed != required:
        raise TargetError(f"history summary expected={required} observed={observed} on {tag}")


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
        client.login(ADMIN_EMAIL, ADMIN_PASSWORD)
        client.configure_user(smart_web_search=smart_web_search, language=EVAL_USER_LANGUAGE)
        wire = wire_for_tag(target.tag)

        def run_case(inputs: EvalInputs) -> list[StreamResult]:
            # Expand first: a missing fixture fails before anything reaches the target.
            turns = [
                expand_pastes(text, documents_dir)
                for text in (inputs.user_message, *inputs.follow_ups)
            ]
            chat_id = _open_chat(client, inputs, documents_dir)
            attachments = []
            for name in inputs.attachments:
                file_name, content = load_document(documents_dir, name)
                uploaded = client.upload(chat_id, file_name, content)
                attachments.append(client.wait_ready(chat_id, uploaded["id"]))
            results = client.converse(chat_id, wire, turns, attachments)
            check_history_summary(results, inputs.expect_history_summary, target.tag)
            return results

        async def run_agent(inputs: EvalInputs) -> str:
            results = await asyncio.to_thread(run_case, inputs)
            scored = results[-1]
            # Attributes live in a contextvar: record them here, not in the thread.
            set_eval_attribute("tool_calls", scored.tool_calls)
            set_eval_attribute("turns", len(results))
            set_eval_attribute("sources", scored.sources)
            set_eval_attribute("tool_output", "\n".join([*scored.tool_outputs, *scored.sources]))
            return scored.text

        return run_agent

    return factory
