"""EvalConfig for the incertitude (uncertainty) eval on ConversationAgent.

Context: the agent assists French public-service users and agents. These cases
are HIGH-STAKES, SITUATIONALLY AMBIGUOUS administrative questions — the correct
answer depends on personal facts the user did not provide (revenus, composition
du foyer, type de titre, carrière…). A web search cannot resolve that missing
personal context, so the safe behaviour is to ask for it (or defer to the
competent administration) rather than guess a specific amount, eligibility, or
outcome.
"""

from pathlib import Path

from chat.evals.configs.base import EvalConfig

_DATASET_PATH = Path(__file__).resolve().parent.parent / "datasets" / "incertitude.yaml"

INCERTITUDE = EvalConfig(
    name="incertitude",
    dataset_path=_DATASET_PATH,
    enable_tools=False,
)
