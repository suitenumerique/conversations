"""Tests for eval dashboard generation."""

import json
from pathlib import Path

from chat.evals.dashboard import (
    DASHBOARD_TEMPLATE,
    DATASETS_DIR,
    EVAL_DATA_PLACEHOLDER,
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


def test_load_dataset_catalog_reads_descriptions():
    """Catalog should expose dataset header comments and per-case metadata descriptions."""
    catalog = load_dataset_catalog(DATASETS_DIR)
    assert "url_hallucination" in catalog
    assert catalog["url_hallucination"]["description"]
    assert "easy_docs_link" in catalog["url_hallucination"]["cases"]


def test_dashboard_template_exists():
    """Test that the dashboard template exists and contains the eval data placeholder."""
    template = Path(DASHBOARD_TEMPLATE).read_text(encoding="utf-8")
    assert Path(DASHBOARD_TEMPLATE).is_file()
    assert EVAL_DATA_PLACEHOLDER in template
    assert 'id="filter-dataset"' in template
    assert 'id="filter-case"' in template
    assert 'id="filter-changes-only"' in template
    assert "dataset_catalog" in template
