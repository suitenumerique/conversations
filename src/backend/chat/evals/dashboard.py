"""Generate a self-contained HTML dashboard for saved eval runs."""

from __future__ import annotations

import json
from pathlib import Path

from chat.evals.storage import DASHBOARD_DIR, INDEX_PATH, resolve_run

DASHBOARD_TEMPLATE = DASHBOARD_DIR / "template.html"
DASHBOARD_OUTPUT = DASHBOARD_DIR / "dashboard.html"
EVAL_DATA_PLACEHOLDER = "__EVAL_DATA_JSON__"


def _load_runs_payload() -> dict:
    if not INDEX_PATH.exists():
        return {"runs": [], "baselines": {}, "run_records": []}

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    run_records = []
    for entry in index.get("runs", []):
        try:
            record, _ = resolve_run(entry["run_id"])
            run_records.append(record)
        except FileNotFoundError:
            continue
    return {
        "runs": index.get("runs", []),
        "baselines": index.get("baselines", {}),
        "run_records": run_records,
    }


def generate_dashboard(output_path: Path | None = None) -> Path:
    """Generate a self-contained HTML dashboard for saved eval runs."""
    output_path = output_path or DASHBOARD_OUTPUT
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    if EVAL_DATA_PLACEHOLDER not in template:
        raise ValueError(f"Dashboard template is missing placeholder {EVAL_DATA_PLACEHOLDER!r}.")

    payload = _load_runs_payload()
    data_json = json.dumps(payload, ensure_ascii=False)
    html = template.replace(EVAL_DATA_PLACEHOLDER, data_json, 1)
    output_path.write_text(html, encoding="utf-8")
    return output_path
