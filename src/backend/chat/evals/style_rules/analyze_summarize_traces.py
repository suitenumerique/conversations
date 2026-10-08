"""Aggregate-only analysis of Langfuse exports of the summarize path, before vs after a switch.

Never prints or writes trace content: only counts, rates, densities and CIs.
Errors are reported by exception class name only. The one exception is --sample, which
prints raw content for local debugging: never share its output.

Q1  Markdown density of `summarize` / `summarize_project` tool returns (summarizer output).
Q2  Final answer after the tool: empty relay, similarity to the tool return, Markdown density.
Q3  Same answer shares, on traces whose instructions forbid some formatting (regex, approximate).

Usage:
  python3 -I analyze_summarize_traces.py --schema DIR
  python3 -I analyze_summarize_traces.py --sample DIR
  python3 -I analyze_summarize_traces.py --window before=DIR --window after=DIR [--out FILE]
"""

import argparse
import csv
import difflib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

SUMMARIZE_TOOL = re.compile(r"\bsummarize(?:_project)?\b")
BOLD = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")
BULLET = re.compile(r"(?m)^\s*(?:[-*+•]|\d+[.)])\s+")
HEADING = re.compile(r"(?m)^\s*#{1,6}\s")
PROHIBITION = re.compile(
    r"(?:n['’]utilise|\bpas de\b|\bsans\b|\bévite|\bne mets\b|\bjamais de\b|"
    r"\bno\b|\bdon['’]t use\b|\bavoid\b|\bnever use\b|\bwithout\b)"
    r"[^.\n]{0,60}?(?:gras|puces|titres|markdown|bold|bullet|heading)",
    re.IGNORECASE,
)
TEXT_KEYS = {"content", "text", "returnvalue", "parts", "messages", "output"}
SKIPPED_PART_TYPES = ("tool", "function")
EMPTY_ANSWER_CHARS = 50
SIMILARITY_CHARS = 4000
VERBATIM_RATIO = 0.8
REWRITE_RATIO = 0.4
Z_95 = 1.96
SKELETON_DEPTH = 4
DATA_SUFFIXES = (".jsonl", ".json", ".csv")
SUMMARY_KEYS = ("records_by_type", "parse_errors", "start_time_range", "final_answer_models")


def _out(*parts) -> None:
    sys.stdout.write(" ".join(str(part) for part in parts) + "\n")


def normalize_key(key):
    """Make 'trace_id', 'traceId' and 'Trace ID' compare equal."""
    return re.sub(r"[^a-z]", "", str(key).lower())


def field(record, *names):
    """Return the first non-empty value whose normalized key is in names."""
    wanted = {normalize_key(name) for name in names}
    for key, value in record.items():
        if normalize_key(key) in wanted and value is not None and value != "":
            return value
    return None


def maybe_json(value):
    """CSV exports (and some JSON exports) carry nested values as JSON strings."""
    if isinstance(value, str) and value[:1] in '[{"':
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def load_records(directory, errors):
    """Yield records from every .jsonl / .json / .csv file in directory."""
    csv.field_size_limit(2**31 - 1)
    for path in sorted(Path(directory).iterdir()):
        suffix = path.suffix.lower()
        try:
            if suffix == ".jsonl":
                with path.open(encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            yield json.loads(line)
            elif suffix == ".json":
                with path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    data = data.get("data") or data.get("observations") or [data]
                yield from data
            elif suffix == ".csv":
                with path.open(encoding="utf-8", newline="") as handle:
                    yield from csv.DictReader(handle)
        except (OSError, ValueError, csv.Error) as exc:
            # Class name only: exception messages can quote the record.
            errors[type(exc).__name__] += 1


def skeleton(value, depth=0):
    """Structure of a value (keys and types) without any of its content."""
    value = maybe_json(value)
    if depth >= SKELETON_DEPTH:
        return type(value).__name__
    if isinstance(value, dict):
        return {key: skeleton(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [skeleton(value[0], depth + 1)] if value else []
    if isinstance(value, str):
        return f"str(len={len(value)})"
    return type(value).__name__


def collect_texts(value, out):
    """Collect text strings from a message structure, skipping tool-call parts."""
    value = maybe_json(value)
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, list):
        for item in value:
            collect_texts(item, out)
    elif isinstance(value, dict):
        part_type = str(value.get("type") or value.get("part_kind") or "").lower()
        if part_type.startswith(SKIPPED_PART_TYPES):
            return
        for key, item in value.items():
            if normalize_key(key) in TEXT_KEYS:
                collect_texts(item, out)


def instruction_texts(value, out):
    """Collect system / instruction strings from a generation input."""
    value = maybe_json(value)
    if isinstance(value, list):
        for item in value:
            instruction_texts(item, out)
    elif isinstance(value, dict):
        if str(value.get("role", "")).lower() == "system":
            collect_texts(value, out)
            return
        for key, item in value.items():
            if "instruction" in normalize_key(key):
                collect_texts(item, out)
            elif isinstance(maybe_json(item), (dict, list)):
                instruction_texts(item, out)


def text_of(value):
    """All text of a message structure, joined."""
    parts = []
    collect_texts(value, parts)
    return "\n".join(part for part in parts if part)


def _metadata_tool_names(value):
    """Values of keys ending in 'tool name' (e.g. gen_ai.tool.name), anywhere in metadata."""
    value = maybe_json(value)
    if isinstance(value, dict):
        for key, item in value.items():
            if normalize_key(key).endswith("toolname") and isinstance(item, str):
                yield item
            else:
                yield from _metadata_tool_names(item)
    elif isinstance(value, list):
        for item in value:
            yield from _metadata_tool_names(item)


def tool_name_of(record):
    """'summarize' / 'summarize_project' from the observation name or its tool-name metadata.

    Only tool-name keys are read from metadata: an agent-run span also lists the tool
    definitions, and must not be mistaken for a tool call.
    """
    candidates = [field(record, "name"), *_metadata_tool_names(field(record, "metadata"))]
    for candidate in candidates:
        match = SUMMARIZE_TOOL.search(str(candidate or ""))
        if match:
            return match.group(0)
    return None


def markdown_stats(text):
    """Bold / bullet / heading density per 1k chars, and whether each is present."""
    per_1k = 1000 / max(len(text), 1)
    bold, bullets, headings = (len(pattern.findall(text)) for pattern in (BOLD, BULLET, HEADING))
    return {
        "bold_per_1k": bold * per_1k,
        "bullets_per_1k": bullets * per_1k,
        "headings_per_1k": headings * per_1k,
        "has_bold": float(bold > 0),
        "has_bullets": float(bullets > 0),
        "has_headings": float(headings > 0),
    }


def mean_with_ci(values):
    """Mean with a 95% CI: Wilson for 0/1 rates, normal approximation otherwise."""
    if not values:
        return None
    n = len(values)
    mean = statistics.fmean(values)
    if set(values) <= {0.0, 1.0}:
        denominator = 1 + Z_95**2 / n
        centre = (mean + Z_95**2 / (2 * n)) / denominator
        half = Z_95 * math.sqrt(mean * (1 - mean) / n + Z_95**2 / (4 * n**2)) / denominator
    else:
        half = Z_95 * statistics.stdev(values) / math.sqrt(n) if n > 1 else 0.0
        centre = mean
    return {"n": n, "mean": mean, "ci95": [centre - half, centre + half]}


def _index_records(directory):
    """Group summarize tool calls and generations by trace id."""
    errors, types = Counter(), Counter()
    tools_by_trace, generations_by_trace = defaultdict(list), defaultdict(list)
    times = []
    for record in load_records(directory, errors):
        if not isinstance(record, dict):
            errors["non_dict_record"] += 1
            continue
        trace_id = field(record, "trace_id", "traceId")
        start = str(field(record, "start_time", "startTime", "timestamp") or "")
        kind = str(field(record, "type") or "").upper()
        types[kind or "UNKNOWN"] += 1
        if start:
            times.append(start)
        if not trace_id:
            errors["missing_trace_id"] += 1
            continue
        tool = tool_name_of(record) if kind != "GENERATION" else None
        if tool:
            tools_by_trace[trace_id].append((start, tool, field(record, "output")))
        elif kind == "GENERATION" or field(record, "model", "providedModelName"):
            model = field(record, "model", "providedModelName")
            generations_by_trace[trace_id].append((start, model, record))
    summary = {
        "records_by_type": dict(types),
        "parse_errors": dict(errors),
        "start_time_range": [min(times), max(times)] if times else None,
    }
    return summary, tools_by_trace, generations_by_trace


def _score_answer(final, tool_text, metrics, counts):
    """Q2 and Q3 metrics of the final answer that follows the last summarize call."""
    answer = text_of(field(final, "output"))
    metrics["Q2_answer_empty"].append(float(len(answer.strip()) < EMPTY_ANSWER_CHARS))
    if not answer.strip():
        return
    if tool_text.strip():
        ratio = difflib.SequenceMatcher(
            None, answer[:SIMILARITY_CHARS], tool_text[:SIMILARITY_CHARS]
        ).ratio()
        metrics["Q2_similarity_to_tool"].append(ratio)
        metrics["Q2_verbatim_relay"].append(float(ratio >= VERBATIM_RATIO))
        metrics["Q2_rewrite"].append(float(ratio < REWRITE_RATIO))
    stats = markdown_stats(answer)
    for name, value in stats.items():
        metrics[f"Q2_answer_{name}"].append(value)
    instructions = []
    instruction_texts(field(final, "input"), instructions)
    counts["traces_with_instructions_found"] += bool(instructions)
    if PROHIBITION.search("\n".join(instructions)):
        counts["traces_with_formatting_prohibition"] += 1
        for name in ("has_bold", "has_bullets", "has_headings"):
            metrics[f"Q3_prohibited_answer_{name}"].append(stats[name])


def analyse_window(directory):
    """Aggregates (no content) for one export directory."""
    summary, tools_by_trace, generations_by_trace = _index_records(directory)
    metrics, counts, models = defaultdict(list), Counter(), Counter()
    for trace_id, tool_calls in tools_by_trace.items():
        tool_calls.sort(key=lambda item: item[0])
        for _, tool, output in tool_calls:
            counts[f"tool_calls_{tool}"] += 1
            if output is None:
                counts["tool_return_missing"] += 1
                continue
            tool_text = text_of(output)
            if not tool_text.strip():
                counts["tool_return_unparsed"] += 1
                continue
            for name, value in markdown_stats(tool_text).items():
                metrics[f"Q1_tool_{name}"].append(value)

        last_tool_start, _, last_output = tool_calls[-1]
        after = sorted(
            (gen for gen in generations_by_trace.get(trace_id, []) if gen[0] >= last_tool_start),
            key=lambda item: item[0],
        )
        if not after:
            counts["traces_without_generation_after_tool"] += 1
            continue
        _, model, final = after[-1]
        models[str(model)] += 1
        counts["traces_analysed"] += 1
        _score_answer(final, text_of(last_output), metrics, counts)

    return {
        **summary,
        "final_answer_models": dict(models),
        "counts": dict(counts),
        "metrics": {name: mean_with_ci(values) for name, values in sorted(metrics.items())},
    }


def print_schema(directory):
    """One skeleton per (type, summarize tool) pair: keys and types, never values."""
    errors, seen = Counter(), set()
    for record in load_records(directory, errors):
        if not isinstance(record, dict):
            continue
        kind = str(field(record, "type") or "UNKNOWN").upper()
        tool = tool_name_of(record) or "-"
        if (kind, tool) in seen:
            continue
        seen.add((kind, tool))
        _out(f"### type={kind} summarize_tool={tool}")
        _out(json.dumps(skeleton(record), indent=2))
    _out("parse_errors:", dict(errors))


def print_sample(directory):
    """Print the raw first line of each export file. Shows real content: keep it local."""
    sys.stderr.write("WARNING: raw trace content below, do not share it.\n")
    for path in sorted(Path(directory).iterdir()):
        if path.suffix.lower() not in DATA_SUFFIXES:
            continue
        with path.open(encoding="utf-8") as handle:
            _out(f"### {path.name}")
            _out(handle.readline().rstrip("\n"))


def _format_stat(stat):
    """'mean [low, high] (n)' or '-'."""
    if stat is None:
        return "-"
    low, high = stat["ci95"]
    return f"{stat['mean']:.3f} [{low:.3f}, {high:.3f}] ({stat['n']})"


def print_report(results):
    """Sanity block per window, then one row per metric with a column per window."""
    for label, result in results.items():
        _out(f"\n== {label}")
        for key in (*SUMMARY_KEYS, "counts"):
            _out(f"{key}:", result[key])
    names = sorted({name for result in results.values() for name in result["metrics"]})
    _out("\nmetric | " + " | ".join(f"{label} mean [95% CI] (n)" for label in results))
    for name in names:
        cells = (_format_stat(result["metrics"].get(name)) for result in results.values())
        _out(f"{name} | " + " | ".join(cells))


def main():
    """Parse arguments and run the schema check or the analysis."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--schema", metavar="DIR", help="print record skeletons, no values")
    parser.add_argument(
        "--sample", metavar="DIR", help="print the raw first line of each file (real content)"
    )
    parser.add_argument("--window", action="append", default=[], metavar="LABEL=DIR")
    parser.add_argument("--out", metavar="FILE", help="write the aggregates as JSON")
    args = parser.parse_args()
    if args.schema:
        print_schema(args.schema)
        return
    if args.sample:
        print_sample(args.sample)
        return
    if not args.window:
        parser.error("give --schema DIR, --sample DIR or at least one --window LABEL=DIR")
    results = {}
    for spec in args.window:
        label, _, directory = spec.partition("=")
        results[label] = analyse_window(directory)
    print_report(results)
    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
