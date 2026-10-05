"""Tests for the smoke run verdict."""

from chat.evals.target.smoke import EXPECTED_FACT, check_result
from chat.evals.target.wire import StreamResult


def test_check_result_passes_when_fact_is_in_answer():
    """An answer quoting the planted fact passes."""
    result = StreamResult(text=f"Le responsable est {EXPECTED_FACT}.")

    assert not check_result(result, EXPECTED_FACT)


def test_check_result_fact_match_ignores_case():
    """Case differences do not fail the smoke run."""
    result = StreamResult(text=EXPECTED_FACT.upper())

    assert not check_result(result, EXPECTED_FACT)


def test_check_result_fails_on_empty_text():
    """A 200 stream without text is a failure."""
    assert check_result(StreamResult(text="  "), EXPECTED_FACT) == ["empty answer"]


def test_check_result_fails_on_errors():
    """Stream errors fail the run even if some text came back."""
    result = StreamResult(text=EXPECTED_FACT, errors=["rag backend error"])

    assert check_result(result, EXPECTED_FACT) == ["stream errors: rag backend error"]


def test_check_result_fails_when_fact_missing():
    """An answer that does not use the document fails."""
    result = StreamResult(text="Je n'ai pas accès au document.")

    assert check_result(result, EXPECTED_FACT) == [f"answer does not mention {EXPECTED_FACT!r}"]
