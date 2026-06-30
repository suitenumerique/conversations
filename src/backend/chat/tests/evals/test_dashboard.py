"""Tests for eval dashboard generation."""

import json
from pathlib import Path

from chat.evals.dashboard import (
    DASHBOARD_TEMPLATE,
    EVAL_DATA_PLACEHOLDER,
    generate_dashboard,
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
    assert payload == {"runs": [], "baselines": {}, "run_records": []}


def test_dashboard_template_exists():
    """Test that the dashboard template exists and contains the eval data placeholder."""
    template = Path(DASHBOARD_TEMPLATE).read_text(encoding="utf-8")
    assert Path(DASHBOARD_TEMPLATE).is_file()
    assert EVAL_DATA_PLACEHOLDER in template
    assert 'id="filter-dataset"' in template
    assert 'id="filter-case"' in template
