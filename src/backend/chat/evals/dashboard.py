"""Generate a self-contained HTML dashboard for saved eval runs."""

from __future__ import annotations

import json
from pathlib import Path

from chat.evals.storage import DASHBOARD_DIR, INDEX_PATH, resolve_run

DASHBOARD_OUTPUT = DASHBOARD_DIR / "dashboard.html"


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
    output_path = output_path or DASHBOARD_OUTPUT
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    payload = _load_runs_payload()
    data_json = json.dumps(payload, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conversations — Eval Runs</title>
  <style>
    :root {{
      --bg: #f4f6f9;
      --card: #fff;
      --text: #111827;
      --muted: #6b7280;
      --border: #e5e7eb;
      --pass: #047857;
      --pass-bg: #d1fae5;
      --fail: #b91c1c;
      --fail-bg: #fee2e2;
      --warn: #b45309;
      --warn-bg: #fef3c7;
      --accent: #1d4ed8;
      --accent-bg: #dbeafe;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: var(--bg); color: var(--text); font-size: 14px; }}
    header {{ padding: 1.25rem 2rem; background: #111827; color: #fff; }}
    header h1 {{ margin: 0 0 .25rem; font-size: 1.35rem; }}
    header p {{ margin: 0; color: #9ca3af; font-size: .9rem; }}
    main {{ padding: 1.25rem 2rem 3rem; max-width: 1440px; margin: 0 auto; }}
    h2 {{ margin: 0 0 .75rem; font-size: 1.05rem; }}
    h3 {{ margin: 0 0 .5rem; font-size: .95rem; }}
    .grid {{ display: grid; gap: 1rem; }}
    .grid-2 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
    .grid-4 {{ grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.15rem; }}
    .muted {{ color: var(--muted); }}
    .badge {{ display: inline-block; padding: .1rem .45rem; border-radius: 999px; font-size: .75rem; font-weight: 600; }}
    .badge-pass {{ background: var(--pass-bg); color: var(--pass); }}
    .badge-fail {{ background: var(--fail-bg); color: var(--fail); }}
    .badge-warn {{ background: var(--warn-bg); color: var(--warn); }}
    .badge-baseline {{ background: var(--accent-bg); color: var(--accent); }}
    .badge-neutral {{ background: #f3f4f6; color: var(--muted); }}
    .badge-partial-up {{ background: #ecfdf5; color: #059669; }}
    .badge-partial-down {{ background: #fef2f2; color: #dc2626; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .88rem; }}
    th, td {{ padding: .5rem .45rem; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }}
    tr.row-fail td {{ background: #fffbfb; }}
    tr.row-pass td {{ background: #fafffe; }}
    tr.row-changed td {{ background: #fffbeb; }}
    button, select {{ border: 1px solid var(--border); border-radius: 7px; padding: .4rem .65rem; background: #fff; cursor: pointer; font-size: .88rem; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: .75rem; align-items: center; margin-bottom: .75rem; }}
    .stat {{ text-align: center; }}
    .stat .value {{ font-size: 1.6rem; font-weight: 700; line-height: 1.2; }}
    .stat .label {{ font-size: .78rem; color: var(--muted); margin-top: .15rem; }}
    .delta-pos {{ color: var(--pass); font-weight: 600; }}
    .delta-neg {{ color: var(--fail); font-weight: 600; }}
    .param-grid {{ display: grid; grid-template-columns: auto 1fr; gap: .2rem .75rem; font-size: .85rem; }}
    .param-grid dt {{ color: var(--muted); }}
    .param-grid dd {{ margin: 0; }}
    details {{ margin-top: .35rem; }}
    details summary {{ cursor: pointer; color: var(--accent); font-size: .82rem; }}
    .reason {{ margin-top: .35rem; padding: .5rem .65rem; background: #f9fafb; border-left: 3px solid var(--border); font-size: .82rem; color: #374151; border-radius: 0 6px 6px 0; }}
    .reason.fail {{ border-left-color: var(--fail); }}
    code {{ font-size: .82rem; background: #f3f4f6; padding: .1rem .3rem; border-radius: 4px; }}
    .section {{ margin-top: 1rem; }}
    .run-meta {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    @media (max-width: 768px) {{ .run-meta {{ grid-template-columns: 1fr; }} }}
    .change-context-card {{
      background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
      border: 1px solid #bfdbfe;
      border-left: 4px solid var(--accent);
      border-radius: 10px;
      padding: 1rem 1.15rem;
      margin-bottom: .75rem;
    }}
    .change-context-title {{
      font-size: .72rem;
      font-weight: 700;
      letter-spacing: .06em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: .65rem;
    }}
    .change-context-body {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: .65rem 1rem;
    }}
    .change-ref {{
      flex: 1 1 220px;
      min-width: 0;
      padding: .55rem .75rem;
      background: rgba(255,255,255,.75);
      border: 1px solid var(--border);
      border-radius: 8px;
    }}
    .change-ref-highlight {{
      background: #fff;
      border-color: #93c5fd;
      box-shadow: 0 1px 2px rgba(29,78,216,.08);
    }}
    .change-ref-empty {{ color: var(--muted); }}
    .change-ref-label {{
      display: block;
      font-size: .68rem;
      font-weight: 700;
      letter-spacing: .04em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: .25rem;
    }}
    .change-ref-highlight .change-ref-label {{ color: var(--accent); }}
    .change-ref-text {{ font-size: .95rem; font-weight: 600; line-height: 1.35; word-break: break-word; }}
    .change-arrow {{ color: var(--muted); font-size: 1.1rem; font-weight: 700; flex: 0 0 auto; }}
    .run-change-note {{
      margin: 0 0 .75rem;
      padding: .55rem .75rem;
      background: var(--accent-bg);
      border-left: 3px solid var(--accent);
      border-radius: 0 8px 8px 0;
      font-size: .92rem;
      font-weight: 600;
      line-height: 1.35;
      word-break: break-word;
    }}
    .change-chip {{
      display: inline-block;
      max-width: 100%;
      padding: .25rem .55rem;
      background: var(--accent-bg);
      color: #1e3a8a;
      border-radius: 6px;
      font-size: .82rem;
      font-weight: 600;
      line-height: 1.35;
      word-break: break-word;
    }}
    .change-empty {{ color: var(--muted); font-style: italic; }}
    .run-id-sub {{ font-size: .75rem; color: var(--muted); margin-top: .25rem; display: inline-block; }}
    h2.run-detail-title {{ line-height: 1.35; word-break: break-word; }}
  </style>
</head>
<body>
  <header>
    <h1>Eval Runs Dashboard</h1>
    <p>Comparaison des runs behavioral evals — baselines, scores moyens et détail par case.</p>
  </header>
  <main>
    <section class="grid grid-4 section" id="stats-row"></section>

    <section class="card section">
      <h2>Comparaison</h2>
      <div class="controls">
        <label>Référence (A) <select id="run-a"></select></label>
        <label>À comparer (B) <select id="run-b"></select></label>
        <button id="swap-runs" type="button">Inverser</button>
        <button id="use-baseline" type="button">Baseline → dernier run</button>
      </div>
      <div id="change-context"></div>
      <div id="comparison-summary" class="muted"></div>
      <div class="run-meta section" id="run-meta"></div>
      <div class="grid grid-4 section" id="comparison-stats"></div>
    </section>

    <section class="card section">
      <h2>Détail par case</h2>
      <div id="comparison-table"></div>
    </section>

    <section class="grid grid-2 section">
      <div class="card">
        <h2>Historique des runs</h2>
        <div id="runs-list"></div>
      </div>
      <div class="card">
        <h2>Baselines</h2>
        <div id="baselines-list"></div>
      </div>
    </section>

    <section class="card section">
      <h2 id="run-b-detail-title" class="run-detail-title">Détail du run B</h2>
      <div id="run-b-detail" class="muted">Sélectionnez un run B.</div>
    </section>
  </main>

  <script id="eval-data" type="application/json">{data_json}</script>
  <script>
    const payload = JSON.parse(document.getElementById("eval-data").textContent);
    const recordsById = Object.fromEntries(payload.run_records.map((r) => [r.run_id, r]));
    const baselineRunId = Object.values(payload.baselines || {{}})[0]?.run_id;

    function pct(v) {{ return `${{Math.round((v || 0) * 100)}}%`; }}
    function pct1(v) {{ return `${{((v || 0) * 100).toFixed(1)}}%`; }}
    function fmtDate(iso) {{
      if (!iso) return "—";
      try {{ return new Date(iso).toLocaleString("fr-FR"); }} catch {{ return iso; }}
    }}
    function fmtMs(ms) {{
      if (!ms) return "—";
      return ms >= 1000 ? `${{(ms / 1000).toFixed(1)}}s` : `${{Math.round(ms)}}ms`;
    }}
    function runNote(run) {{
      return run?.comment || run?.label || "";
    }}
    function escapeHtml(text) {{
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }}
    function shortRunId(id) {{
      if (!id) return "—";
      const parts = id.split("_");
      return parts.length > 1 ? parts.slice(0, -1).join("_") : id;
    }}
    function optionLabel(entry) {{
      const note = entry.comment || entry.label;
      const rate = pct(entry.overall_pass_rate);
      const bl = entry.is_baseline ? " · baseline" : "";
      const sid = shortRunId(entry.run_id);
      if (note) return `${{note}} (${{rate}})${{bl}} — ${{sid}}`;
      return `${{sid}} (${{rate}})${{bl}}`;
    }}
    function changeChip(note) {{
      if (!note) return '<span class="change-empty">—</span>';
      return `<span class="change-chip">${{escapeHtml(note)}}</span>`;
    }}
    function renderChangeContext(beforeRun, afterRun) {{
      const el = document.getElementById("change-context");
      if (!beforeRun || !afterRun) {{
        el.innerHTML = "";
        return;
      }}
      const noteA = runNote(beforeRun);
      const noteB = runNote(afterRun);
      if (!noteA && !noteB) {{
        el.innerHTML = "";
        return;
      }}
      const refA = noteA
        ? `<div class="change-ref"><span class="change-ref-label">Référence (A)</span><div class="change-ref-text">${{escapeHtml(noteA)}}</div></div>`
        : `<div class="change-ref change-ref-empty"><span class="change-ref-label">Référence (A)</span><div class="change-ref-text"><em>Aucune note</em></div></div>`;
      const refB = noteB
        ? `<div class="change-ref change-ref-highlight"><span class="change-ref-label">Changement testé (B)</span><div class="change-ref-text">${{escapeHtml(noteB)}}</div></div>`
        : `<div class="change-ref change-ref-empty"><span class="change-ref-label">Run testé (B)</span><div class="change-ref-text"><em>Aucune note</em></div></div>`;
      el.innerHTML = `
        <div class="change-context-card">
          <div class="change-context-title">Contexte du run</div>
          <div class="change-context-body">
            ${{refA}}
            <span class="change-arrow" aria-hidden="true">→</span>
            ${{refB}}
          </div>
        </div>`;
    }}
    function statusBadge(passed) {{
      return passed
        ? '<span class="badge badge-pass">PASS</span>'
        : '<span class="badge badge-fail">FAIL</span>';
    }}
    function caseDelta(b, a) {{
      const isChanged = b.passed !== a.passed || b.pass_rate !== a.pass_rate
        || JSON.stringify(b.avg_scores || {{}}) !== JSON.stringify(a.avg_scores || {{}});
      if (!isChanged) return {{ kind: "stable", badge: '<span class="badge badge-neutral">=</span>' }};
      if (b.passed && !a.passed) return {{ kind: "regression", badge: '<span class="badge badge-fail">↓ régression</span>' }};
      if (!b.passed && a.passed) return {{ kind: "improvement", badge: '<span class="badge badge-pass">↑ amélioration</span>' }};
      if (!b.passed && !a.passed && a.pass_rate > b.pass_rate) {{
        return {{ kind: "partial_up", badge: '<span class="badge badge-partial-up">↑ partiel</span>' }};
      }}
      if (!b.passed && !a.passed && a.pass_rate < b.pass_rate) {{
        return {{ kind: "partial_down", badge: '<span class="badge badge-partial-down">↓ partiel</span>' }};
      }}
      return {{ kind: "changed", badge: '<span class="badge badge-warn">~ changé</span>' }};
    }}
    function runParamsHtml(run, title, {{ highlightChange = false }} = {{}}) {{
      if (!run) return "";
      const p = run.params || {{}};
      const g = run.git || {{}};
      const note = runNote(run);
      const noteBlock = highlightChange && note
        ? `<p class="run-change-note">${{escapeHtml(note)}}</p>`
        : "";
      const commentRow = !highlightChange && note
        ? `<dt>Note</dt><dd>${{escapeHtml(note)}}</dd>`
        : "";
      return `
        <div class="card" style="padding:.75rem 1rem;">
          <h3>${{title}}</h3>
          ${{noteBlock}}
          <dl class="param-grid">
            <dt>Run ID</dt><dd><code>${{run.run_id}}</code></dd>
            <dt>Date</dt><dd>${{fmtDate(run.created_at)}}</dd>
            ${{commentRow}}
            <dt>Modèle</dt><dd><code>${{p.model_hrid || "?"}}</code></dd>
            <dt>LLM judge</dt><dd>${{p.llm_judge ? "oui" : "non"}}</dd>
            <dt>Runs / case</dt><dd>${{p.runs_per_case || 1}}</dd>
            <dt>Datasets</dt><dd>${{(p.datasets || []).join(", ") || "—"}}</dd>
            <dt>Case filter</dt><dd>${{p.case_filter || "—"}}</dd>
            <dt>Git commit</dt><dd><code>${{g.commit_short || g.commit || "?"}}</code>${{g.dirty ? ' <span class="badge badge-warn">dirty</span>' : ""}}</dd>
            <dt>Branche</dt><dd>${{g.branch || "?"}}</dd>
            <dt>Pass rate global</dt><dd><strong>${{pct(run.summary?.overall_pass_rate)}}</strong></dd>
          </dl>
        </div>`;
    }}

    function renderStats() {{
      const runs = payload.runs || [];
      const baselines = Object.keys(payload.baselines || {{}});
      document.getElementById("stats-row").innerHTML = [
        ["Runs sauvegardés", runs.length],
        ["Baselines", baselines.length],
        ["Dernier run", runs[0] ? pct(runs[0].overall_pass_rate) : "—"],
        ["Baseline", baselineRunId ? pct(recordsById[baselineRunId]?.summary?.overall_pass_rate) : "—"],
      ].map(([label, value]) => `
        <div class="card stat"><div class="value">${{value}}</div><div class="label">${{label}}</div></div>`
      ).join("");
    }}

    function renderRuns() {{
      const runs = payload.runs || [];
      document.getElementById("runs-list").innerHTML = runs.length
        ? `<table>
            <thead><tr>
              <th>Changement</th><th>Date</th><th>Pass</th><th>Modèle</th><th>N</th><th>Datasets</th>
            </tr></thead>
            <tbody>${{runs.map((run) => {{
              const note = run.comment || run.label;
              return `
              <tr>
                <td>
                  ${{changeChip(note)}}
                  ${{run.is_baseline ? '<br><span class="badge badge-baseline">baseline</span>' : ""}}
                  <br><code class="run-id-sub">${{run.run_id}}</code>
                </td>
                <td class="muted">${{fmtDate(run.created_at)}}</td>
                <td><strong>${{pct(run.overall_pass_rate)}}</strong></td>
                <td><code>${{run.model_hrid || "?"}}</code></td>
                <td>${{run.runs_per_case || 1}}</td>
                <td>${{(run.datasets || []).join("<br>")}}</td>
              </tr>`;
            }}).join("")}}
            </tbody></table>`
        : '<p class="muted">Aucun run. <code>make eval EVAL_ARGS=--save</code></p>';
    }}

    function renderBaselines() {{
      const baselines = Object.values(payload.baselines || {{}});
      document.getElementById("baselines-list").innerHTML = baselines.length
        ? baselines.map((b) => {{
            const rec = recordsById[b.run_id];
            return `<div style="margin-bottom:1rem;padding-bottom:1rem;border-bottom:1px solid var(--border);">
              <strong>${{b.name}}</strong>${{b.label ? ` — ${{escapeHtml(b.label)}}` : ""}}
              ${{rec && runNote(rec) ? `<p class="run-change-note" style="margin-top:.5rem;margin-bottom:0;">${{escapeHtml(runNote(rec))}}</p>` : ""}}
              <dl class="param-grid" style="margin-top:.5rem;">
                <dt>Run</dt><dd><code>${{b.run_id}}</code></dd>
                <dt>Commit</dt><dd><code>${{b.git_commit || "?"}}</code></dd>
                <dt>Modèle</dt><dd><code>${{b.model_hrid || "?"}}</code></dd>
                <dt>Pass rate</dt><dd>${{rec ? pct(rec.summary?.overall_pass_rate) : "?"}}</dd>
                <dt>Créée le</dt><dd>${{fmtDate(b.created_at)}}</dd>
              </dl>
            </div>`;
          }}).join("")
        : "<p class='muted'>Aucune baseline. <code>make eval-baseline</code></p>";
    }}

    function compareRuns(beforeId, afterId) {{
      const before = recordsById[beforeId];
      const after = recordsById[afterId];
      if (!before || !after) return null;

      const datasets = [...new Set([
        ...Object.keys(before.datasets || {{}}),
        ...Object.keys(after.datasets || {{}}),
      ])].sort();

      let regressions = 0, improvements = 0, partialUp = 0, partialDown = 0, stable = 0, changed = 0;
      const rows = [];

      for (const dataset of datasets) {{
        const bd = before.datasets[dataset];
        const ad = after.datasets[dataset];
        if (!bd || !ad) continue;

        const hashMatch = before.dataset_hashes?.[dataset] === after.dataset_hashes?.[dataset];
        const bCases = Object.fromEntries(bd.cases.map((c) => [c.name, c]));
        const aCases = Object.fromEntries(ad.cases.map((c) => [c.name, c]));

        for (const name of [...new Set([...Object.keys(bCases), ...Object.keys(aCases)])].sort()) {{
          const b = bCases[name], a = aCases[name];
          if (!b || !a) continue;

          const {{ kind }} = caseDelta(b, a);
          const isChanged = kind !== "stable";
          if (isChanged) changed++;
          if (kind === "regression") regressions++;
          else if (kind === "improvement") improvements++;
          else if (kind === "partial_up") partialUp++;
          else if (kind === "partial_down") partialDown++;
          else if (kind === "stable") stable++;

          rows.push({{ dataset, name, b, a, kind, hashMatch, bd, ad }});
        }}
      }}

      return {{ before, after, datasets, regressions, improvements, partialUp, partialDown, stable, changed, rows }};
    }}

    function renderRunDetail(run) {{
      if (!run) return '<p class="muted">—</p>';
      const parts = [];
      for (const [dsName, ds] of Object.entries(run.datasets || {{}})) {{
        parts.push(`<h3>${{dsName}} — ${{ds.cases_passed}}/${{ds.cases_total}} pass (${{pct(ds.pass_rate)}})</h3>`);
        parts.push(`<p class="muted">Avg repeat pass: ${{pct1(ds.pass_rate_avg_repeats)}} · ` +
          Object.entries(ds.evaluators || {{}}).map(([n, e]) => `${{n}}: ${{pct1(e.pass_rate)}}`).join(" · ") +
          `</p>`);
        parts.push(`<table><thead><tr>
          <th>Case</th><th>Difficulté</th><th>Catégorie</th><th>Status</th>
          <th>Repeat pass</th><th>Scores</th><th>Durée</th>
        </tr></thead><tbody>`);
        for (const c of ds.cases) {{
          const reasons = Object.entries(c.reasons || {{}}).filter(([, r]) => r);
          parts.push(`<tr class="${{c.passed ? "row-pass" : "row-fail"}}">
            <td><code>${{c.name}}</code></td>
            <td>${{c.metadata?.difficulty || "—"}}</td>
            <td>${{c.metadata?.category || "—"}}</td>
            <td>${{statusBadge(c.passed)}}</td>
            <td>${{c.repeats > 1 ? pct1(c.pass_rate) + ` (${{c.repeats}}×)` : "—"}}</td>
            <td>${{Object.entries(c.avg_scores || {{}}).map(([n, s]) => `${{n}}=${{s}}`).join("<br>") || "—"}}</td>
            <td>${{fmtMs(c.task_duration_ms)}}</td>
          </tr>`);
          if (reasons.length) {{
            parts.push(`<tr><td colspan="7">`);
            for (const [ev, reason] of reasons) {{
              parts.push(`<details><summary>Raison (${{ev}})</summary>
                <div class="reason ${{c.passed ? "" : "fail"}}">${{reason}}</div></details>`);
            }}
            parts.push(`</td></tr>`);
          }}
        }}
        parts.push(`</tbody></table>`);
      }}
      return parts.join("");
    }}

    function renderComparison() {{
      const runA = document.getElementById("run-a").value;
      const runB = document.getElementById("run-b").value;
      const summary = document.getElementById("comparison-summary");
      const meta = document.getElementById("run-meta");
      const stats = document.getElementById("comparison-stats");
      const table = document.getElementById("comparison-table");
      const detail = document.getElementById("run-b-detail");

      const detailTitle = document.getElementById("run-b-detail-title");
      const changeContext = document.getElementById("change-context");

      if (!runA || !runB) {{
        summary.textContent = "Sélectionnez deux runs.";
        changeContext.innerHTML = "";
        meta.innerHTML = stats.innerHTML = table.innerHTML = detail.innerHTML = "";
        detailTitle.textContent = "Détail du run B";
        return;
      }}

      const recordA = recordsById[runA];
      const recordB = recordsById[runB];
      renderChangeContext(recordA, recordB);
      meta.innerHTML = runParamsHtml(recordA, "Référence (A)") +
        runParamsHtml(recordB, "À comparer (B)", {{ highlightChange: true }});
      detail.innerHTML = renderRunDetail(recordB);
      const noteB = runNote(recordB);
      detailTitle.textContent = noteB ? `Détail — ${{noteB}}` : "Détail du run B";

      if (runA === runB) {{
        summary.innerHTML = "Sélectionnez deux runs <strong>différents</strong> pour comparer.";
        stats.innerHTML = table.innerHTML = "";
        return;
      }}

      const result = compareRuns(runA, runB);
      if (!result) {{
        summary.textContent = "Impossible de charger un des runs.";
        stats.innerHTML = table.innerHTML = "";
        return;
      }}

      const beforeRate = result.before.summary?.overall_pass_rate || 0;
      const afterRate = result.after.summary?.overall_pass_rate || 0;
      const delta = afterRate - beforeRate;
      const deltaClass = delta < 0 ? "delta-neg" : delta > 0 ? "delta-pos" : "";
      const deltaLabel = delta < 0 ? "régression" : delta > 0 ? "amélioration" : "stable";

      summary.innerHTML = `
        Pass rate global <strong>${{pct(beforeRate)}} → ${{pct(afterRate)}}</strong>
        <span class="${{deltaClass}}">(${{delta >= 0 ? "+" : ""}}${{Math.round(delta * 100)}}pp, ${{deltaLabel}})</span>
        · <code>${{shortRunId(runB)}}</code> vs <code>${{shortRunId(runA)}}</code>`;

      stats.innerHTML = [
        ["Régressions", result.regressions, "delta-neg"],
        ["Améliorations", result.improvements, "delta-pos"],
        ["↑ partiel", result.partialUp, "delta-pos"],
        ["↓ partiel", result.partialDown, "delta-neg"],
        ["Stables", result.stable, ""],
      ].map(([label, value, cls]) => `
        <div class="card stat">
          <div class="value ${{cls}}">${{value}}</div>
          <div class="label">${{label}}</div>
        </div>`).join("");

      if (!result.rows.length) {{
        table.innerHTML = "<p class='muted'>Aucun dataset en commun.</p>";
        return;
      }}

      const byDataset = {{}};
      for (const row of result.rows) {{
        (byDataset[row.dataset] = byDataset[row.dataset] || []).push(row);
      }}

      table.innerHTML = Object.entries(byDataset).map(([dataset, rows]) => {{
        const bd = rows[0].bd, ad = rows[0].ad;
        const hashWarn = !rows[0].hashMatch
          ? '<p class="badge badge-warn">Dataset modifié entre les deux runs</p>' : "";
        const dsDelta = ad.pass_rate - bd.pass_rate;
        const dsClass = dsDelta < 0 ? "delta-neg" : dsDelta > 0 ? "delta-pos" : "";

        return `<div style="margin-bottom:1.5rem;">
          <h3>${{dataset}}</h3>
          ${{hashWarn}}
          <p class="muted">
            Pass rate: ${{pct(bd.pass_rate)}} (${{bd.cases_passed}}/${{bd.cases_total}})
            → ${{pct(ad.pass_rate)}} (${{ad.cases_passed}}/${{ad.cases_total}})
            <span class="${{dsClass}}">(${{Math.round(dsDelta * 100)}}pp)</span>
            · Avg repeat: ${{pct1(bd.pass_rate_avg_repeats)}} → ${{pct1(ad.pass_rate_avg_repeats)}}
          </p>
          <table>
            <thead><tr>
              <th>Case</th><th>Diff.</th><th>Catégorie</th>
              <th>A</th><th>B</th><th>Repeat A→B</th><th>Scores B</th><th>Δ</th>
            </tr></thead>
            <tbody>${{rows.map(({{ name, b, a, kind }}) => {{
              const rowClass = kind === "stable" ? (a.passed ? "row-pass" : "row-fail")
                : kind === "regression" || kind === "partial_down" ? "row-changed"
                : kind === "improvement" || kind === "partial_up" ? "row-changed" : "row-changed";
              const deltaIcon = caseDelta(b, a).badge;
              const reasons = Object.entries(a.reasons || {{}}).filter(([, r]) => r && !a.passed);
              const reasonHtml = reasons.length
                ? `<tr class="${{rowClass}}"><td colspan="8">${{reasons.map(([ev, r]) =>
                    `<details><summary>Raison B (${{ev}})</summary>
                     <div class="reason fail">${{r}}</div></details>`).join("")}}</td></tr>` : "";
              return `
                <tr class="${{rowClass}}">
                  <td><code>${{name}}</code></td>
                  <td>${{a.metadata?.difficulty || "—"}}</td>
                  <td>${{a.metadata?.category || "—"}}</td>
                  <td>${{statusBadge(b.passed)}}</td>
                  <td>${{statusBadge(a.passed)}}</td>
                  <td>${{b.repeats > 1 || a.repeats > 1
                    ? `${{pct1(b.pass_rate)}} → ${{pct1(a.pass_rate)}}`
                    : (b.passed === a.passed ? "=" : "changement")}}</td>
                  <td>${{Object.entries(a.avg_scores || {{}}).map(([n,s]) => `${{n}}=${{s}}`).join("<br>") || "—"}}</td>
                  <td>${{deltaIcon}}</td>
                </tr>${{reasonHtml}}`;
            }}).join("")}}
            </tbody>
          </table>
        </div>`;
      }}).join("");
    }}

    function initSelectors() {{
      const runs = payload.runs || [];
      const opts = runs.map((r) => `<option value="${{r.run_id}}">${{optionLabel(r)}}</option>`).join("");
      document.getElementById("run-a").innerHTML = opts;
      document.getElementById("run-b").innerHTML = opts;

      if (baselineRunId && runs.some((r) => r.run_id === baselineRunId)) {{
        document.getElementById("run-a").value = baselineRunId;
        document.getElementById("run-b").value = runs[0].run_id;
      }} else if (runs.length > 1) {{
        document.getElementById("run-a").value = runs[1].run_id;
        document.getElementById("run-b").value = runs[0].run_id;
      }}

      document.getElementById("run-a").addEventListener("change", renderComparison);
      document.getElementById("run-b").addEventListener("change", renderComparison);
      document.getElementById("swap-runs").addEventListener("click", () => {{
        const a = document.getElementById("run-a"), b = document.getElementById("run-b");
        [a.value, b.value] = [b.value, a.value];
        renderComparison();
      }});
      document.getElementById("use-baseline").addEventListener("click", () => {{
        if (baselineRunId) document.getElementById("run-a").value = baselineRunId;
        if (runs[0]) document.getElementById("run-b").value = runs[0].run_id;
        renderComparison();
      }});
    }}

    renderStats();
    renderRuns();
    renderBaselines();
    initSelectors();
    renderComparison();
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
    return output_path
