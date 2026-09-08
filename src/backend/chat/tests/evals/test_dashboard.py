"""Tests for eval dashboard generation."""

import json
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from chat.evals.dashboard import (
    DASHBOARD_TEMPLATE,
    DATASETS_DIR,
    EVAL_DATA_PLACEHOLDER,
    _build_comparisons,
    generate_dashboard,
    load_dataset_catalog,
)


def test_generate_dashboard_injects_payload(tmp_path, monkeypatch):
    """Test that the dashboard template is injected with the eval data."""
    template_path = tmp_path / "template.html"
    output_path = tmp_path / "dashboard.html"
    template_path.write_text(
        (
            '<html><script id="eval-data" type="application/json">'
            f"{EVAL_DATA_PLACEHOLDER}"
            "</script></html>"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("chat.evals.dashboard.DASHBOARD_TEMPLATE", template_path)
    monkeypatch.setattr("chat.evals.dashboard.INDEX_PATH", tmp_path / "index.json")

    result = generate_dashboard(output_path=output_path)

    html = result.read_text(encoding="utf-8")
    assert EVAL_DATA_PLACEHOLDER not in html
    payload = json.loads(html.split('type="application/json">', 1)[1].split("</script>", 1)[0])
    assert "dataset_catalog" in payload
    assert payload["runs"] == []
    assert payload["baselines"] == {}
    assert payload["run_records"] == []
    assert payload["comparisons"] == {}


def test_generate_dashboard_escapes_script_close_sequence(tmp_path, monkeypatch):
    """Model-generated text containing </script> must not break out of the JSON block."""
    template_path = tmp_path / "template.html"
    output_path = tmp_path / "dashboard.html"
    template_path.write_text(
        (
            '<html><script id="eval-data" type="application/json">'
            f"{EVAL_DATA_PLACEHOLDER}"
            "</script></html>"
        ),
        encoding="utf-8",
    )
    hostile_comment = "reason with </script><script>alert(1)</script>"
    monkeypatch.setattr("chat.evals.dashboard.DASHBOARD_TEMPLATE", template_path)
    monkeypatch.setattr(
        "chat.evals.dashboard._load_runs_payload",
        lambda: {
            "runs": [],
            "baselines": {},
            "run_records": [{"comment": hostile_comment}],
            "dataset_catalog": {},
        },
    )

    html = generate_dashboard(output_path=output_path).read_text(encoding="utf-8")

    assert "</script><script>alert" not in html
    # "<\/" is a valid JSON escape: the payload must round-trip unchanged.
    payload = json.loads(html.split('type="application/json">', 1)[1].split("</script>", 1)[0])
    assert payload["run_records"][0]["comment"] == hostile_comment


def test_generate_dashboard_escapes_every_left_angle_bracket(tmp_path, monkeypatch):
    """Every '<' in model text is escaped, covering mixed-case and comment vectors."""
    template_path = tmp_path / "template.html"
    output_path = tmp_path / "dashboard.html"
    template_path.write_text(
        (
            '<html><script id="eval-data" type="application/json">'
            f"{EVAL_DATA_PLACEHOLDER}"
            "</script></html>"
        ),
        encoding="utf-8",
    )
    # Mixed-case close tag and an HTML-comment/script vector: none may survive raw.
    hostile_comment = "</SCRIPT ><script>alert(1)</script> <!--<script>"
    monkeypatch.setattr("chat.evals.dashboard.DASHBOARD_TEMPLATE", template_path)
    monkeypatch.setattr(
        "chat.evals.dashboard._load_runs_payload",
        lambda: {
            "runs": [],
            "baselines": {},
            "run_records": [{"comment": hostile_comment}],
            "dataset_catalog": {},
        },
    )

    html = generate_dashboard(output_path=output_path).read_text(encoding="utf-8")

    injected = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    # The embedded JSON must contain no literal '<': every one is escaped to <.
    assert "<" not in injected
    payload = json.loads(injected)
    assert payload["run_records"][0]["comment"] == hostile_comment


def test_build_comparisons_covers_all_ordered_pairs():
    """Every ordered pair of embedded runs must get a precomputed comparison."""

    def record(run_id, passed):
        return {
            "run_id": run_id,
            "datasets": {
                "ds": {
                    "pass_rate": 1.0 if passed else 0.0,
                    "pass_rate_avg_repeats": 1.0 if passed else 0.0,
                    "cases": [
                        {
                            "name": "case",
                            "passed": passed,
                            "pass_rate": 1.0 if passed else 0.0,
                            "avg_scores": {},
                            "reasons": {},
                        }
                    ],
                }
            },
            "dataset_hashes": {"ds": "h"},
        }

    comparisons = _build_comparisons([record("a", True), record("b", False)])

    assert set(comparisons) == {"a::b", "b::a"}
    assert comparisons["a::b"]["before_run_id"] == "a"
    kinds = {c["name"]: c["kind"] for c in comparisons["a::b"]["datasets"]["ds"]["case_changes"]}
    assert kinds == {"case": "regression"}


def test_load_dataset_catalog_reads_descriptions():
    """Catalog should expose dataset header comments and per-case metadata descriptions."""
    catalog = load_dataset_catalog(DATASETS_DIR)
    assert "url_hallucination" in catalog
    assert catalog["url_hallucination"]["description"]
    assert "easy_docs_link" in catalog["url_hallucination"]["cases"]


def test_generate_eval_dashboard_command_handles_path_outside_base_dir(tmp_path, monkeypatch):
    """When the output is outside BASE_DIR, the command reports the absolute path
    instead of crashing on Path.relative_to after the file was already written."""
    outside = tmp_path / "dashboard.html"
    outside.write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(
        "chat.management.commands.generate_eval_dashboard.generate_dashboard",
        lambda: outside,
    )

    out = StringIO()
    call_command("generate_eval_dashboard", stdout=out)

    assert str(outside) in out.getvalue()


def test_dashboard_template_exists():
    """Test that the dashboard template exists and contains the eval data placeholder."""
    template = Path(DASHBOARD_TEMPLATE).read_text(encoding="utf-8")
    assert Path(DASHBOARD_TEMPLATE).is_file()
    assert EVAL_DATA_PLACEHOLDER in template
    assert 'id="filter-dataset"' in template
    assert 'id="filter-case"' in template
    assert 'id="filter-changes-only"' in template
    assert "dataset_catalog" in template
    assert "payload.comparisons" in template
