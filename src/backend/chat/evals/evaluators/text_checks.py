"""Deterministic checks on answer text: facts, length, structure, language."""

import json
import re
import unicodedata
from dataclasses import dataclass, field

from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from pydantic_evals.evaluators.evaluator import EvaluationReason

_WORD_RE = re.compile(r"\w+(?:['’]\w+)*")
_BULLET_RE = re.compile(r"^(?:[-*+•]|\d+[.)])\s+\S", re.MULTILINE)
_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", re.MULTILINE
)
_MARKDOWN_EMPHASIS = str.maketrans("", "", "*_`")
_MONTHS = (
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre"
).split()
_FRENCH_DATE_RE = re.compile(rf"(1er|\d{{1,2}}) ({'|'.join(_MONTHS)})")
_THOUSANDS_RE = re.compile(r"(\d{1,3}) 000")
_STOPWORDS = {
    "en": {"the", "and", "of", "to", "is", "in", "for", "with", "on", "that", "are", "be", "by"},
    "fr": {"le", "la", "les", "et", "des", "du", "de", "pour", "est", "une", "un", "dans", "sur"},
}
_REGEX_FLAGS = re.IGNORECASE | re.MULTILINE
_EDGE_NOISE = " \t\n.,;:!*_`"
_CODE_FENCE_RE = re.compile(r"\A\s*```[\w-]*\s*(.*?)\s*```\s*\Z", re.DOTALL)


def _text(ctx: EvaluatorContext) -> str:
    return ctx.output if isinstance(ctx.output, str) else ""


def normalize(text: str) -> str:
    """Fold case, apostrophes, markdown emphasis and whitespace for fact matching."""
    text = unicodedata.normalize("NFC", text).replace("’", "'").translate(_MARKDOWN_EMPHASIS)
    return " ".join(text.casefold().split())


def fact_patterns(fact: str) -> list[re.Pattern]:
    """Regexes matching a fact in normalized text, including common format variants.

    Dates ("1er septembre") also match numeric forms (01/09, 1-9-2026); amounts
    ("380 000") also match 380000, 380.000, 380,000 and 380 k€.
    """
    normalized = normalize(fact)
    patterns = [re.compile(re.escape(normalized))]
    if date := _FRENCH_DATE_RE.fullmatch(normalized):
        day = 1 if date.group(1) == "1er" else int(date.group(1))
        month = _MONTHS.index(date.group(2)) + 1
        patterns.append(re.compile(rf"(?<!\d)0?{day}\s*[/.-]\s*0?{month}(?!\d)"))
        patterns.append(re.compile(rf"(?<!\d){day} {date.group(2)}"))
    if amount := _THOUSANDS_RE.fullmatch(normalized):
        thousands = amount.group(1)
        patterns.append(re.compile(rf"(?<![\d.,]){thousands}[ .,]?000(?!\d)"))
        patterns.append(re.compile(rf"(?<![\d.,]){thousands} ?k"))
    return patterns


def _edges(text: str) -> str:
    """Normalized text without surrounding whitespace, punctuation or markdown."""
    return normalize(text).strip(_EDGE_NOISE)


def count_words(text: str) -> int:
    """Number of words, an elided form (l'équipe) counting as one."""
    return len(_WORD_RE.findall(text))


def count_bullets(text: str) -> int:
    """Number of top-level list items (unindented bullets or numbers)."""
    return len(_BULLET_RE.findall(text))


def detect_language(text: str) -> str | None:
    """Return 'fr' or 'en' from stopword counts, or None without a clear winner."""
    words = [word.casefold() for word in _WORD_RE.findall(text)]
    counts = {lang: sum(word in stop for word in words) for lang, stop in _STOPWORDS.items()}
    best = max(counts, key=counts.get)
    tied = list(counts.values()).count(counts[best]) > 1
    return None if counts[best] == 0 or tied else best


@dataclass(repr=False)
class FactRecall(Evaluator):
    """Pass when the answer contains at least `min_ratio` of the reference facts."""

    facts: list[str] = field(default_factory=list)
    min_ratio: float = 1.0

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        answer = normalize(_text(ctx))
        missing = [
            fact
            for fact in self.facts
            if not any(pattern.search(answer) for pattern in fact_patterns(fact))
        ]
        ratio = 1 - len(missing) / len(self.facts) if self.facts else 1.0
        reason = (
            f"missing {len(missing)}/{len(self.facts)}: {'; '.join(missing)}" if missing else None
        )
        return EvaluationReason(value=ratio >= self.min_ratio, reason=reason)


@dataclass(repr=False)
class MaxWords(Evaluator):
    """Pass when the answer has at most `limit` words."""

    limit: int = 0

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        words = count_words(_text(ctx))
        passed = words <= self.limit
        return EvaluationReason(
            value=passed, reason=None if passed else f"{words} words > {self.limit}"
        )


@dataclass(repr=False)
class ExactBullets(Evaluator):
    """Pass when the answer has exactly `count` top-level list items."""

    count: int = 0

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        bullets = count_bullets(_text(ctx))
        passed = bullets == self.count
        return EvaluationReason(
            value=passed, reason=None if passed else f"{bullets} items != {self.count}"
        )


@dataclass(repr=False)
class HasMarkdownTable(Evaluator):
    """Pass when the answer contains a markdown table."""

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        passed = bool(_TABLE_SEPARATOR_RE.search(_text(ctx)))
        return EvaluationReason(value=passed, reason=None if passed else "no markdown table")


@dataclass(repr=False)
class Language(Evaluator):
    """Pass when the answer is written in `code` ('fr' or 'en')."""

    code: str = "fr"

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        detected = detect_language(_text(ctx))
        passed = detected == self.code
        return EvaluationReason(value=passed, reason=None if passed else f"detected {detected}")


@dataclass(repr=False)
class Regex(Evaluator):
    """Pass when `pattern` matches somewhere in the answer (case-insensitive, multiline)."""

    pattern: str = ""
    # Report column, so a dataset can name what the pattern checks.
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        passed = bool(re.search(self.pattern, _text(ctx), _REGEX_FLAGS))
        return EvaluationReason(
            value=passed, reason=None if passed else f"no match: {self.pattern}"
        )


@dataclass(repr=False)
class MustNotMatch(Evaluator):
    """Pass when none of `patterns` matches the answer (case-insensitive, multiline)."""

    patterns: list[str] = field(default_factory=list)

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        text = _text(ctx)
        found = [pattern for pattern in self.patterns if re.search(pattern, text, _REGEX_FLAGS)]
        return EvaluationReason(
            value=not found, reason=f"forbidden: {'; '.join(found)}" if found else None
        )


@dataclass(repr=False)
class TurnsWithoutMatch(Evaluator):
    """Score the share of turns matching none of `patterns`; the reason lists the others.

    A graded score (1.0 = every turn clean) shows how far a rule holds over a conversation, where
    a pass/fail check stops at the first slip. Reads the `turn_texts` attribute set by multi-turn
    tasks, falling back to the scored answer.
    """

    patterns: list[str] = field(default_factory=list)
    # Report column, so a dataset can check several rules with this evaluator.
    evaluation_name: str | None = field(default=None)

    def get_default_evaluation_name(self) -> str:
        if self.evaluation_name is not None:
            return self.evaluation_name
        return self.get_serialization_name()

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        turns = ctx.attributes.get("turn_texts") or [_text(ctx)]
        failing = [
            number
            for number, text in enumerate(turns, start=1)
            if any(re.search(pattern, text, _REGEX_FLAGS) for pattern in self.patterns)
        ]
        reason = f"turns {', '.join(map(str, failing))} of {len(turns)} match" if failing else None
        return EvaluationReason(value=1 - len(failing) / len(turns), reason=reason)


@dataclass(repr=False)
class StartsWith(Evaluator):
    """Pass when the answer opens with `prefix` (case, markdown and spacing folded)."""

    prefix: str = ""

    def __post_init__(self):
        if not _edges(self.prefix):
            raise ValueError("StartsWith needs a non-empty prefix")

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        opening = _edges(_text(ctx))
        passed = opening.startswith(_edges(self.prefix))
        return EvaluationReason(value=passed, reason=None if passed else f"starts: {opening[:60]}")


@dataclass(repr=False)
class EndsWith(Evaluator):
    """Pass when the answer closes with `suffix` (case, markdown, spacing, punctuation folded)."""

    suffix: str = ""

    def __post_init__(self):
        if not _edges(self.suffix):
            raise ValueError("EndsWith needs a non-empty suffix")

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        closing = _edges(_text(ctx))
        suffix = _edges(self.suffix)
        # Whole words only: "enfin" does not end with "fin".
        passed = closing.endswith(suffix) and not closing[: -len(suffix)][-1:].isalnum()
        return EvaluationReason(value=passed, reason=None if passed else f"ends: {closing[-60:]}")


@dataclass(repr=False)
class ValidJson(Evaluator):
    """Pass when the whole answer (or one code fence around it) is a JSON object with `keys`."""

    keys: list[str] = field(default_factory=list)

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        text = _text(ctx).strip()
        if fenced := _CODE_FENCE_RE.match(text):
            text = fenced.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            return EvaluationReason(value=False, reason=f"not JSON: {error.msg}")
        if not isinstance(data, dict):
            return EvaluationReason(value=False, reason="not a JSON object")
        missing = [key for key in self.keys if key not in data]
        return EvaluationReason(
            value=not missing, reason=f"missing keys: {', '.join(missing)}" if missing else None
        )


@dataclass(repr=False)
class MaxItems(Evaluator):
    """Pass when the answer has at most `limit` top-level list items."""

    limit: int = 0

    def evaluate(self, ctx: EvaluatorContext) -> EvaluationReason:
        items = count_bullets(_text(ctx))
        passed = items <= self.limit
        return EvaluationReason(
            value=passed, reason=None if passed else f"{items} items > {self.limit}"
        )
