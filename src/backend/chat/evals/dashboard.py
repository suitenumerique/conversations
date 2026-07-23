"""Generate a self-contained HTML dashboard for saved eval runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from chat.evals.storage import DASHBOARD_DIR, INDEX_PATH, resolve_run

DASHBOARD_TEMPLATE = DASHBOARD_DIR / "template.html"
DASHBOARD_OUTPUT = DASHBOARD_DIR / "dashboard.html"
DATASETS_DIR = DASHBOARD_DIR.parent / "datasets"
EVAL_DATA_PLACEHOLDER = "__EVAL_DATA_JSON__"
# Full run records embedded in the HTML; cap them so the file does not grow
# unbounded with saved runs (baseline runs are always kept).
DASHBOARD_MAX_RUNS = 20


def _leading_comment_description(raw: str) -> str | None:
    """Join consecutive ``#`` comment lines before the first YAML key."""
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            lines.append(stripped.lstrip("#").strip())
            continue
        if stripped:
            break
    text = " ".join(lines).strip()
    return text or None


def load_dataset_catalog(datasets_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load dataset and per-case descriptions from eval YAML files."""
    root = datasets_dir or DATASETS_DIR
    catalog: dict[str, dict[str, Any]] = {}
    for yaml_path in sorted(root.glob("*.yaml")):
        raw = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        case_descriptions: dict[str, str] = {}
        for case in data.get("cases", []):
            name = case.get("name")
            description = (case.get("metadata") or {}).get("description")
            if name and description:
                case_descriptions[name] = description
        catalog[yaml_path.stem] = {
            "description": _leading_comment_description(raw),
            "cases": case_descriptions,
        }
    return catalog


def _load_runs_payload() -> dict:
    if not INDEX_PATH.exists():
        return {
            "runs": [],
            "baselines": {},
            "run_records": [],
            "dataset_catalog": load_dataset_catalog(),
        }

    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    baselines = index.get("baselines", {})
    baseline_run_ids = {meta.get("run_id") for meta in baselines.values()}

    entries = index.get("runs", [])
    kept_entries = entries[:DASHBOARD_MAX_RUNS] + [
        entry for entry in entries[DASHBOARD_MAX_RUNS:] if entry["run_id"] in baseline_run_ids
    ]

    run_records = []
    resolved_entries = []
    for entry in kept_entries:
        try:
            record, _ = resolve_run(entry["run_id"])
        except FileNotFoundError:
            continue
        run_records.append(record)
        resolved_entries.append(entry)

    return {
        "runs": resolved_entries,
        "baselines": baselines,
        "run_records": run_records,
        "dataset_catalog": load_dataset_catalog(),
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
    # Model-generated text (judge reasons, comments, outputs) may contain "</script>";
    # escape "</" so the embedded JSON cannot close the script tag (valid JSON escape).
    data_json = data_json.replace("</", "<\\/")
    html = template.replace(EVAL_DATA_PLACEHOLDER, data_json, 1)
    output_path.write_text(html, encoding="utf-8")
    return output_path
