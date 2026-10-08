"""Tests for eval case inputs and metadata models."""

import pytest
from pydantic import ValidationError

from chat.evals import EvalInputs, EvalMetadata


def test_inputs_default_to_a_fresh_single_turn_conversation():
    """Existing datasets keep working: no documents, no follow-ups, no prior history."""
    inputs = EvalInputs(user_message="Bonjour")

    assert not inputs.attachments
    assert not inputs.follow_ups
    assert inputs.project_instructions is None
    assert not inputs.project_attachments
    assert inputs.history_summary is None
    assert not inputs.message_history


def test_inputs_accept_documents_projects_and_follow_ups():
    """Cases declare fixture names, a project and later turns."""
    inputs = EvalInputs(
        user_message="Résume ces comptes rendus",
        attachments=["cr-janvier", "cr-fevrier"],
        follow_ups=["Ajoute les échéances"],
        project_instructions="Réponds en anglais",
        project_attachments=["court-cr-01"],
    )

    assert inputs.attachments == ["cr-janvier", "cr-fevrier"]
    assert inputs.follow_ups == ["Ajoute les échéances"]
    assert inputs.project_instructions == "Réponds en anglais"
    assert inputs.project_attachments == ["court-cr-01"]


def test_message_history_roles_are_user_or_assistant():
    """A long-chat state lists prior messages by role."""
    inputs = EvalInputs(
        user_message="Et ensuite ?",
        history_summary="Résumé",
        message_history=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
    )

    assert [message.role for message in inputs.message_history] == ["user", "assistant"]
    with pytest.raises(ValidationError):
        EvalInputs(user_message="x", message_history=[{"role": "system", "content": "a"}])


def test_metadata_doc_set_is_short_or_long():
    """doc_set tags which fixture set a case uses, for aggregation."""
    assert EvalMetadata(difficulty="easy", doc_set="long").doc_set == "long"
    assert EvalMetadata(difficulty="easy").doc_set is None
    with pytest.raises(ValidationError):
        EvalMetadata(difficulty="easy", doc_set="medium")
