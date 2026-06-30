"""EvalConfig for URL hallucination evals on ConversationAgent.

Rubric and evaluators live in the dataset YAML ``config`` block.
"""

from pathlib import Path

from chat.evals.configs.base import EvalConfig

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "url_hallucination.yaml"

URL_HALLUCINATION = EvalConfig(
    name="url_hallucination",
    dataset_path=_DATASET_PATH,
    enable_tools=False,
)
