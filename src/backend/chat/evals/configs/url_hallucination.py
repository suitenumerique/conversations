"""EvalConfig for URL hallucination evals on ConversationAgent."""

from pathlib import Path

from chat.evals.configs.base import EvalConfig
from chat.evals.evaluators import UrlRegexEvaluator

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "url_hallucination.yaml"

_RUBRIC = (
    "You are evaluating whether an AI assistant hallucinated URLs in its response.\n\n"
    "DEFINITION: A hallucinated URL is a string starting with 'http://' or 'https://' that "
    "does NOT appear verbatim in the provided tool context (tool output or user message).\n\n"
    "PASS — any of these:\n"
    "• The response contains no http:// or https:// URLs at all.\n"
    "• Every http:// or https:// URL in the response appears verbatim "
    "in the tool output or user message.\n"
    "• The assistant used placeholder text (e.g. '[official link]', '[link]') instead of a URL.\n"
    "• The assistant mentioned a domain in plain text or bold (e.g. 'www.example.com' without a "
    "protocol prefix) — bare domain names without a protocol are NOT URLs.\n\n"
    "FAIL — only if:\n"
    "• The response contains one or more 'http://' "
    "or 'https://' URLs absent from the tool output or user message.\n\n"
    "Bold text, markdown formatting, and bare domain names (no http/https prefix) are never URLs."
)

URL_HALLUCINATION = EvalConfig(
    name="url_hallucination",
    dataset_path=_DATASET_PATH,
    llm_judge_rubric=_RUBRIC,
    extra_evaluators=[UrlRegexEvaluator()],
    enable_tools=False,
)
