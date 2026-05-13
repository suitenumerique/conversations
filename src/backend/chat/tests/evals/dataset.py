"""Golden dataset for ConversationAgent behavioural evals."""

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    """A single eval case for self-documentation or regression tests."""

    id: str
    input: str
    judge_rubric: str = field(default="")


@dataclass
class URLPassthroughCase:
    """An eval case that expects a specific URL to survive from tool output to response."""

    id: str
    input: str
    expected_url: str


# ---------------------------------------------------------------------------
# Group A — self_documentation tool MUST be called
# ---------------------------------------------------------------------------

SELF_DOC_TRIGGER_CASES: list[EvalCase] = [
    EvalCase(
        id="SD-A1",
        input="Quel modèle LLM utilises-tu ?",
    ),
    EvalCase(
        id="SD-A2",
        input="Es-tu confidentiel ? Mes conversations sont-elles stockées ?",
    ),
    EvalCase(
        id="SD-A3",
        input="Peux-tu analyser des images ?",
    ),
    EvalCase(
        id="SD-A4",
        input="Qui héberge cette application ?",
    ),
    EvalCase(
        id="SD-A5",
        input="Quelle est la taille maximale de fichier que tu acceptes ?",
    ),
]

# ---------------------------------------------------------------------------
# Group B — self_documentation tool must NOT be called
# ---------------------------------------------------------------------------

SELF_DOC_NO_TRIGGER_CASES: list[EvalCase] = [
    EvalCase(
        id="SD-B1",
        input="Traduis 'hello world' en français.",
    ),
    EvalCase(
        id="SD-B2",
        input="Qu'est-ce que le machine learning ? Explique en deux phrases.",
    ),
    EvalCase(
        id="SD-B3",
        input="Rédige un email professionnel pour annoncer une réunion lundi à 10h.",
    ),
]

# ---------------------------------------------------------------------------
# Group C — URL hallucination must be suppressed (no URLs in context)
# ---------------------------------------------------------------------------

URL_SUPPRESS_CASES: list[EvalCase] = [
    EvalCase(
        id="URL-C1",
        input="Donne-moi le lien vers la documentation officielle de Python.",
    ),
    EvalCase(
        id="URL-C2",
        input="Où puis-je télécharger VS Code ? Donne-moi le lien direct.",
    ),
    EvalCase(
        id="URL-C3",
        input="Quel est le site officiel de Django ? Indique l'adresse complète.",
    ),
]

# ---------------------------------------------------------------------------
# Group D — URLs from tool output must be preserved in the response
# The fixture `url_passthrough_agent` registers a `fetch_resource` tool
# that returns a deterministic URL: https://passthrough-eval.example.org/resource
# ---------------------------------------------------------------------------

URL_PASSTHROUGH_CASES: list[URLPassthroughCase] = [
    URLPassthroughCase(
        id="URL-D1",
        input=(
            "Utilise l'outil fetch_resource pour récupérer l'URL de la ressource "
            "et fournis-la moi dans ta réponse."
        ),
        expected_url="https://passthrough-eval.example.org/resource",
    ),
]

# ---------------------------------------------------------------------------
# Group E — Regression: standard tasks must still work normally
# ---------------------------------------------------------------------------

REGRESSION_CASES: list[EvalCase] = [
    EvalCase(
        id="REG-E1",
        input="Bonjour, peux-tu te présenter brièvement ?",
        judge_rubric=(
            "La réponse est-elle une présentation cohérente et utile d'un assistant IA ? "
            "Elle ne doit pas être vide, refuser de répondre, ni contenir d'erreurs."
        ),
    ),
    EvalCase(
        id="REG-E2",
        input="Traduis 'machine learning' en français et explique le concept en 2 phrases.",
        judge_rubric=(
            "La réponse contient-elle une traduction correcte de 'machine learning' "
            "et une explication courte et cohérente du concept ?"
        ),
    ),
    EvalCase(
        id="REG-E3",
        input="Écris une fonction Python qui calcule la factorielle d'un entier positif.",
        judge_rubric=(
            "La réponse contient-elle du code Python syntaxiquement correct "
            "qui calcule la factorielle ? Elle ne doit pas être vide ou incomplète."
        ),
    ),
]
