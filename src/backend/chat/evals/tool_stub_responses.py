"""Production-shaped simulated tool payloads for behavioral evals."""

from __future__ import annotations

import contextvars
import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai.messages import ToolReturn

# Default document corpus aligned with EVAL_FAKE_DOCUMENT_LISTING (rapport-eval.pdf).
DEFAULT_RAG_CHUNKS = (
    "[1] Section introduction : ce rapport présente l'évaluation du projet Alpha "
    "pour l'année 2025 et fixe les objectifs pour 2026.\n"
    "[2] Section méthodologie : les tests ont été menés sur un échantillon de "
    "120 utilisateurs entre janvier et mars 2025.\n"
    "[3] Risques légaux : le document mentionne une conformité RGPD partielle "
    "et des clauses contractuelles encore en cours de révision.\n"
    "[4] Calendrier : la dernière mise à jour interne du rapport date de mars 2025."
)

DEFAULT_SUMMARIZE_TEXT = (
    "Résumé du document rapport-eval.pdf :\n"
    "- Le projet Alpha vise une mise en production en Q4 2025.\n"
    "- Les tests utilisateurs montrent une satisfaction de 78 %.\n"
    "- Des risques juridiques (RGPD, clauses contractuelles) restent à traiter.\n"
    "- La dernière révision interne du rapport date de mars 2025."
)

DEFAULT_RAG_RISK_CHUNKS = (
    "[1] Risques légaux : conformité RGPD partielle — certaines bases légales "
    "de traitement ne sont pas documentées.\n"
    "[2] Risques contractuels : clauses de responsabilité en cours de révision "
    "avec le prestataire cloud.\n"
    "[3] Risques opérationnels : dépendance à un fournisseur unique pour l'hébergement."
)

DEFAULT_SUMMARIZE_RISKS_TEXT = (
    "Résumé des risques (3 points) :\n"
    "1. Conformité RGPD incomplète sur les bases légales de traitement.\n"
    "2. Clauses contractuelles de responsabilité encore en négociation.\n"
    "3. Risque opérationnel lié à la dépendance à un hébergeur unique."
)

DEFAULT_WEB_SEARCH_RESULTS: dict[str, Any] = {
    "0": {
        "url": "https://actualites.ia.com/ia-generative-2026",
        "title": "IA générative : les avancées de mi-2026",
        "snippets": [
            "En juin 2026, les modèles multimodaux ont gagné en précision sur les "
            "documents longs et les tableaux complexes.",
            "L'Union européenne a publié de nouvelles lignes directrices sur les "
            "systèmes d'IA à usage général.",
        ],
    },
    "1": {
        "url": "https://actualites.ia.com/recherche-ia-actualites",
        "title": "Actualités récentes en intelligence artificielle",
        "snippets": [
            "Les agents autonomes sont déployés dans la santé et l'administration publique.",
            "Les coûts d'inférence ont baissé de 30 % sur les modèles open-weight.",
        ],
    },
}

DEFAULT_SELF_DOCUMENTATION_DB = (
    "Je suis un assistant conversationnel destiné aux agents publics. "
    "Je peux analyser des documents joints, effectuer des recherches web lorsque "
    "l'information doit être à jour, et répondre à des questions sur mes capacités. "
    "Mes réponses s'appuient sur un modèle de langage configuré par l'administrateur."
)

_CURRENT_STUBS: contextvars.ContextVar[ToolStubResponses | None] = contextvars.ContextVar(
    "eval_tool_stub_responses", default=None
)


class ToolStubResponses(BaseModel):
    """Per-case simulated tool payloads (JSON in dataset ``tool_output``)."""

    web_search: dict[str, Any] | None = None
    document_search_rag: str | None = None
    summarize: str | None = None
    self_documentation: str | None = None
    web_search_sources: set[str] = Field(default_factory=set)

    def web_search_return(self) -> ToolReturn:
        """Return the web search payload."""
        payload = self.web_search if self.web_search is not None else DEFAULT_WEB_SEARCH_RESULTS
        sources = self.web_search_sources or {
            entry["url"]
            for entry in payload.values()
            if isinstance(entry, dict) and entry.get("url")
        }
        return ToolReturn(return_value=payload, metadata={"sources": sources})

    def document_search_rag_return(self) -> ToolReturn:
        """Return the document search RAG payload."""
        chunks = (
            self.document_search_rag if self.document_search_rag is not None else DEFAULT_RAG_CHUNKS
        )
        return ToolReturn(return_value=json.dumps({"chunks": chunks}, ensure_ascii=False))

    def summarize_return(self) -> ToolReturn:
        """Return the summarize payload."""
        text = self.summarize if self.summarize is not None else DEFAULT_SUMMARIZE_TEXT
        return ToolReturn(return_value=text)

    def self_documentation_db_text(self) -> str:
        """Return the self documentation database text."""
        return (
            self.self_documentation
            if self.self_documentation is not None
            else DEFAULT_SELF_DOCUMENTATION_DB
        )


def parse_tool_stub_responses(tool_output: str | None) -> ToolStubResponses:
    """Parse optional per-case stub config from ``tool_output``."""
    if not tool_output:
        return ToolStubResponses()
    stripped = tool_output.strip()
    if stripped.startswith("{"):
        return ToolStubResponses.model_validate(json.loads(stripped))
    # Plain text: treat as RAG chunks only (faithfulness_rag-style shorthand).
    return ToolStubResponses(document_search_rag=stripped)


def set_current_tool_stubs(stubs: ToolStubResponses) -> contextvars.Token:
    """Stage stub payloads for the case currently being evaluated."""
    return _CURRENT_STUBS.set(stubs)


def reset_current_tool_stubs(token: contextvars.Token) -> None:
    """Reset the current tool stub responses."""
    _CURRENT_STUBS.reset(token)


def get_current_tool_stubs() -> ToolStubResponses:
    """Get the current tool stub responses."""
    return _CURRENT_STUBS.get() or ToolStubResponses()
