"""Smoke run: one document, one question, one answer from a target stack.

Usage (from the current stack's app-dev container):
    python -m chat.evals.target.smoke --base-url http://host.docker.internal:18071 \
        --tag v0.0.21 --format docx
"""

import argparse
import json
import sys
from dataclasses import asdict

import httpx

from chat.evals.target.client import TargetClient, TargetError
from chat.evals.target.fixtures import build_docx, build_pdf
from chat.evals.target.runtime import ADMIN_EMAIL, ADMIN_PASSWORD
from chat.evals.target.wire import StreamResult, wire_for_tag

EXPECTED_FACT = "Mme Arlette Quenouille"
DOCUMENT_LINES = [
    "Compte rendu de la réunion du comité de pilotage du 3 mars",
    "Décision : le déploiement est reporté au 15 avril.",
    f"Responsable du suivi : {EXPECTED_FACT}.",
]
QUESTION = "D'après le document joint, qui est responsable du suivi ? Réponds en une phrase."


def check_result(result: StreamResult, expected_fact: str) -> list[str]:
    """Return what is wrong with an answer; an empty list means the smoke run passed."""
    if result.errors:
        return [f"stream errors: {'; '.join(result.errors)}"]
    if not result.text.strip():
        return ["empty answer"]
    if expected_fact.lower() not in result.text.lower():
        return [f"answer does not mention {expected_fact!r}"]
    return []


def _document(file_format: str) -> tuple[str, bytes]:
    if file_format == "pdf":
        return "compte-rendu.pdf", build_pdf(DOCUMENT_LINES)
    return "compte-rendu.docx", build_docx(DOCUMENT_LINES)


def _write(summary: dict) -> None:
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Run the smoke flow and print a JSON summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--tag", required=True, help="git ref the target runs (picks the wire)")
    parser.add_argument("--format", choices=["docx", "pdf"], default="docx")
    args = parser.parse_args(argv)

    wire = wire_for_tag(args.tag)
    file_name, content = _document(args.format)
    summary = {"tag": args.tag, "wire": wire.value, "format": args.format}
    with httpx.Client(base_url=args.base_url, timeout=60.0) as http:
        client = TargetClient(http)
        try:
            client.login(ADMIN_EMAIL, ADMIN_PASSWORD)
            chat_id = client.create_chat(f"smoke {args.tag} {args.format}")
            uploaded = client.upload(chat_id, file_name, content)
            summary["content_type"] = uploaded.get("content_type")
            attachment = client.wait_ready(chat_id, uploaded["id"])
            result = client.send(chat_id, wire, QUESTION, [attachment])
        except TargetError as error:
            summary["problems"] = [str(error)]
            _write(summary)
            return 1

    summary.update(asdict(result))
    summary["problems"] = check_result(result, EXPECTED_FACT)
    _write(summary)
    return 1 if summary["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
