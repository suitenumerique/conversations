"""Tests for eval case inputs and metadata models."""

import pytest
from pydantic import ValidationError

from chat.evals import EvalInputs, EvalMetadata


def test_inputs_default_to_single_turn_without_attachments():
    """Existing datasets keep working: no attachments, no follow-ups."""
    inputs = EvalInputs(user_message="Bonjour")

    assert not inputs.attachments
    assert not inputs.follow_ups


def test_inputs_accept_attachments_and_follow_ups():
    """Multi-document, multi-turn cases declare fixture names and later turns."""
    inputs = EvalInputs(
        user_message="Résume ces comptes rendus",
        attachments=["cr-janvier", "cr-fevrier"],
        follow_ups=["Ajoute les échéances"],
    )

    assert inputs.attachments == ["cr-janvier", "cr-fevrier"]
    assert inputs.follow_ups == ["Ajoute les échéances"]


def test_metadata_doc_set_is_short_or_long():
    """doc_set tags which fixture set a case uses, for aggregation."""
    assert EvalMetadata(difficulty="easy", doc_set="long").doc_set == "long"
    assert EvalMetadata(difficulty="easy").doc_set is None
    with pytest.raises(ValidationError):
        EvalMetadata(difficulty="easy", doc_set="medium")


def test_inputs_accept_project_and_summary_expectation():
    """Project cases declare instructions and files; long chats declare the summary expectation."""
    inputs = EvalInputs(
        user_message="Bonjour",
        project_instructions="Réponds en anglais",
        project_attachments=["court-cr-01"],
        expect_history_summary=True,
    )

    assert inputs.project_instructions == "Réponds en anglais"
    assert inputs.project_attachments == ["court-cr-01"]
    assert inputs.expect_history_summary is True
    assert EvalInputs(user_message="x").expect_history_summary is None
