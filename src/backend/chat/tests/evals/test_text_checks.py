"""Tests for deterministic answer-text evaluators."""

from types import SimpleNamespace

import pytest

from chat.evals.evaluators.text_checks import (
    EndsWith,
    ExactBullets,
    FactRecall,
    HasMarkdownTable,
    Language,
    MaxItems,
    MaxWords,
    MustNotMatch,
    Regex,
    StartsWith,
    TurnsWithoutMatch,
    ValidJson,
    count_bullets,
    count_words,
    detect_language,
)


def _ctx(output):
    """Minimal EvaluatorContext stand-in: these evaluators only read ctx.output."""
    return SimpleNamespace(output=output, attributes={})


def test_fact_recall_passes_when_all_facts_present():
    """Every reference fact quoted in the answer passes."""
    result = FactRecall(facts=["Mme Durand", "15 avril"]).evaluate(
        _ctx("Mme Durand pilotera le déploiement prévu le 15 avril.")
    )

    assert result.value is True


def test_fact_recall_ignores_markdown_case_and_apostrophes():
    """Bold markers, case, typographic apostrophes and line breaks do not hide a fact."""
    result = FactRecall(facts=["Mme Durand", "l'équipe RH"]).evaluate(
        _ctx("**MME DURAND** confirme que\nl’équipe   RH validera.")
    )

    assert result.value is True


def test_fact_recall_reports_missing_facts():
    """A missing fact fails and is named in the reason."""
    result = FactRecall(facts=["Mme Durand", "15 avril"]).evaluate(_ctx("Mme Durand pilote."))

    assert result.value is False
    assert "15 avril" in result.reason


def test_fact_recall_min_ratio():
    """min_ratio allows a share of facts to be missing."""
    evaluator = FactRecall(facts=["a1", "b2", "c3", "d4"], min_ratio=0.75)

    assert evaluator.evaluate(_ctx("a1 b2 c3")).value is True
    assert evaluator.evaluate(_ctx("a1 b2")).value is False


def test_count_words_handles_french_elision_and_markdown():
    """Elided words count once; markdown symbols are not words."""
    assert count_words("**L'équipe** a validé - le budget.") == 5


def test_max_words():
    """Answers at the limit pass; one word over fails with the count."""
    assert MaxWords(limit=3).evaluate(_ctx("un deux trois")).value is True
    result = MaxWords(limit=3).evaluate(_ctx("un deux trois quatre"))
    assert result.value is False
    assert "4" in result.reason


def test_count_bullets_counts_top_level_items_only():
    """Dash, star, bullet and numbered items count; nested items do not."""
    text = "Intro\n- un\n* deux\n• trois\n1. quatre\n2) cinq\n  - imbriqué\nFin"

    assert count_bullets(text) == 5


def test_exact_bullets():
    """Exactly N top-level items pass; any other count fails."""
    assert ExactBullets(count=2).evaluate(_ctx("- a\n- b")).value is True
    assert ExactBullets(count=2).evaluate(_ctx("- a\n- b\n- c")).value is False


def test_has_markdown_table():
    """A header separator row identifies a markdown table."""
    table = "| Décision | Responsable |\n|---|:---:|\n| Report | Mme Durand |"

    assert HasMarkdownTable().evaluate(_ctx(table)).value is True
    assert HasMarkdownTable().evaluate(_ctx("Décision : report")).value is False


def test_detect_language():
    """Stopword counts tell French from English; no signal gives None."""
    assert detect_language("The committee and the team agreed on the budget.") == "en"
    assert detect_language("Le comité et les équipes ont validé le budget.") == "fr"
    assert detect_language("Budget 2026") is None


def test_language_evaluator():
    """Language passes only when the detected language matches."""
    assert Language(code="en").evaluate(_ctx("The decision is to postpone.")).value is True
    assert Language(code="en").evaluate(_ctx("La décision est de reporter.")).value is False


def test_non_string_output_fails_cleanly():
    """A non-str output is treated as empty text, never raises."""
    assert FactRecall(facts=["x"]).evaluate(_ctx(None)).value is False
    assert MaxWords(limit=10).evaluate(_ctx(None)).value is True


def test_fact_recall_accepts_numeric_dates():
    """'1er septembre' and '15 juin' match 01/09/2026 and 15/06 written by the model."""
    evaluator = FactRecall(facts=["1er septembre", "15 juin"])

    assert evaluator.evaluate(_ctx("Report : 15/06 → 01/09/2026.")).value is True
    assert evaluator.evaluate(_ctx("Report au 1/9/2026 au lieu du 15-06-2026.")).value is True


def test_fact_recall_accepts_amount_formats():
    """'380 000' matches 380000, 380.000, 380,000 and 380 k€."""
    evaluator = FactRecall(facts=["380 000"])

    for text in ["380000 €", "380.000 €", "€380,000", "380 k€", "380 K€"]:
        assert evaluator.evaluate(_ctx(text)).value is True, text


def test_fact_recall_date_variants_do_not_overmatch():
    """A different day or month still fails."""
    evaluator = FactRecall(facts=["1er septembre"])

    assert evaluator.evaluate(_ctx("Mise en service le 11/09/2026.")).value is False
    assert evaluator.evaluate(_ctx("Mise en service le 01/10/2026.")).value is False


def test_regex_passes_on_a_match_anywhere():
    """Regex searches every line, ignoring case."""
    assert Regex(pattern=r"^objet\s*:").evaluate(_ctx("Bonjour\nOBJET : report")).value is True


def test_regex_fails_without_match_and_names_pattern():
    """No match fails with the pattern in the reason."""
    result = Regex(pattern=r"^Objet").evaluate(_ctx("Madame,"))

    assert result.value is False
    assert "^Objet" in result.reason


def test_regex_report_column_defaults_to_its_type_or_takes_a_name():
    """A dataset can name the Regex column after the rule it checks."""
    assert Regex(pattern="x").get_default_evaluation_name() == "Regex"
    assert (
        Regex(pattern="x", evaluation_name="kiwi_present").get_default_evaluation_name()
        == "kiwi_present"
    )


def test_must_not_match_fails_on_any_forbidden_pattern():
    """One forbidden pattern found is enough to fail, and it is reported."""
    result = MustNotMatch(patterns=[r"\*\*", r"innov"]).evaluate(_ctx("Un projet Innovant."))

    assert result.value is False
    assert "innov" in result.reason


def test_must_not_match_passes_when_clean():
    """No forbidden pattern passes."""
    assert MustNotMatch(patterns=[r"^\s*#"]).evaluate(_ctx("Texte simple.")).value is True


def test_starts_with_ignores_case_markdown_and_leading_space():
    """Bold markers, case and leading blank lines do not hide the required opening."""
    evaluator = StartsWith(prefix="Madame la Directrice,")

    assert evaluator.evaluate(_ctx("\n**madame la directrice,**\nJe vous...")).value is True
    assert evaluator.evaluate(_ctx("Bonjour Madame la Directrice,")).value is False


def test_ends_with_ignores_trailing_punctuation_and_markdown():
    """Trailing period, spaces and bold markers do not hide the required ending."""
    evaluator = EndsWith(suffix="Cordialement")

    assert evaluator.evaluate(_ctx("Merci.\n\n**Cordialement.**  \n")).value is True


def test_ends_with_fails_when_text_follows():
    """A signature after the required ending fails."""
    result = EndsWith(suffix="Cordialement").evaluate(_ctx("Cordialement,\n[Votre nom]"))

    assert result.value is False


def test_valid_json_accepts_one_code_fence():
    """A JSON object inside one ```json fence is accepted when it has every key."""
    answer = '```json\n{"nom": "Martine", "date": "3 octobre", "montant": "1 250 €"}\n```'

    assert ValidJson(keys=["nom", "date", "montant"]).evaluate(_ctx(answer)).value is True


def test_valid_json_accepts_a_fence_on_one_line():
    """A fence without line breaks around the object is still one code fence."""
    answer = '```json {"nom": "Martine"}```'

    assert ValidJson(keys=["nom"]).evaluate(_ctx(answer)).value is True


def test_valid_json_rejects_surrounding_prose():
    """Text around the JSON means the answer is not JSON only."""
    answer = 'Voici le JSON : {"nom": "Martine", "date": "x", "montant": "y"}'

    assert ValidJson(keys=["nom"]).evaluate(_ctx(answer)).value is False


def test_valid_json_reports_missing_keys():
    """A parsable object missing a key fails and names it."""
    result = ValidJson(keys=["nom", "montant"]).evaluate(_ctx('{"nom": "Martine"}'))

    assert result.value is False
    assert "montant" in result.reason


def test_max_items_counts_bullets_and_numbers():
    """MaxItems counts top-level list items, bulleted or numbered."""
    answer = "1. a\n2. b\n3. c\n- d\n- e\n- f"

    assert MaxItems(limit=6).evaluate(_ctx(answer)).value is True
    assert MaxItems(limit=5).evaluate(_ctx(answer)).value is False


def test_ends_with_matches_whole_words_only():
    """A suffix glued to a longer word ("enfin", "la fin") does not count as the ending."""
    evaluator = EndsWith(suffix="FIN")

    assert evaluator.evaluate(_ctx("Le projet avance enfin.")).value is False
    assert evaluator.evaluate(_ctx("Réponse.\n\n**FIN**")).value is True


def test_regex_scoped_case_sensitive_last_line():
    """A scoped (?-i:...) pattern checks that the last line is exactly the uppercase marker."""
    evaluator = Regex(pattern=r"(?-i:^\W*FIN\W*\Z)")

    assert evaluator.evaluate(_ctx("Réponse.\n\n**FIN**\n")).value is True
    assert evaluator.evaluate(_ctx("Livraison prévue d'ici la fin.")).value is False


@pytest.mark.parametrize("evaluator_class", [StartsWith, EndsWith])
def test_edge_checks_reject_an_empty_edge(evaluator_class):
    """An empty prefix or suffix would pass every answer: it is a dataset typo."""
    with pytest.raises(ValueError, match="empty"):
        evaluator_class()


def test_turns_without_match_scores_the_share_of_clean_turns():
    """Bullets in turns 1 and 3 of 4 score 0.5 and name both turns, even when the last is clean."""
    ctx = SimpleNamespace(
        output="Prose.",
        attributes={"turn_texts": ["- un\n- deux", "Prose.", "Voici :\n- trois", "Prose."]},
    )

    result = TurnsWithoutMatch(patterns=[r"^\s*[-*]\s+"]).evaluate(ctx)

    assert result.value == 0.5
    assert result.reason == "turns 1, 3 of 4 match"


def test_turns_without_match_falls_back_to_the_scored_answer():
    """Without turn_texts (single-turn tasks), only the answer is checked: 1.0 or 0.0."""
    evaluator = TurnsWithoutMatch(patterns=[r"\*\*"])

    assert evaluator.evaluate(_ctx("Sans gras.")).value == 1.0
    assert evaluator.evaluate(_ctx("Avec **gras**.")).value == 0.0
