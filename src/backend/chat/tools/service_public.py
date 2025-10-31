"""Service Public RAG search tool using Albert API pre-defined collections.

This tool reuses the existing AlbertRagBackend to query curated collections
(e.g. Service-Public, Travail-Emploi) without creating temporary collections.
"""

import logging
from typing import List

from django.conf import settings
from django.utils.module_loading import import_string
from pydantic_ai import RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

logger = logging.getLogger(__name__)

# Default curated collections (Albert IDs)
DEFAULT_COLLECTION_IDS: List[int] = [784, 785]  # travail-emploi, service-public
INSTRUCTIONS = "Voilà les informations trouvées, résume les pour répondre à la question de l'utilisateur si c'est pertinent, si tu manques d'informations cherche encore ou utilise une autre tool si nécessaire: \n"

async def service_public(ctx: RunContext, query: str) -> ToolReturn:
    """Search curated Service-Public collections on Albert and return snippets.

    Use this tool when the user asks for information about French public services, the French labor market, employment laws, social benefits, or assistance with administrative procedures.
    Args:
        ctx: Run context (usage metering is updated here)
        query: The query to search within the curated collections
    """
    try:
        # Use AlbertRagBackend to search in specific collections
        backend_class = import_string(settings.RAG_DOCUMENT_SEARCH_BACKEND)
        backend = backend_class()
        
        # Search in the curated collections
        rag_results = backend.search(query, collections=DEFAULT_COLLECTION_IDS)
        
        # Convert to compact format for the model
        compact = []
        sources = []
        for result in rag_results.data:
            # AlbertRagBackend.search() returns RAGWebResult objects with {url, content, score, metadata}
            document_name = result.metadata.get("document_name", "Document")
            url = result.metadata.get("url", "")
            
            compact.append(
                {
                    "title": document_name,
                    "snippet": result.content,
                    "url": url,
                }
            )
            
            # Create rich source with title and URL
            if url:
                source_info = {
                    "title": document_name,
                    "url": url
                }
                sources.append(source_info)

        # Update run usage
        ctx.usage += RunUsage(
            input_tokens=rag_results.usage.prompt_tokens,
            output_tokens=rag_results.usage.completion_tokens,
        )

        # Remove duplicate sources based on URL
        unique_sources = []
        seen_urls = set()
        for source in sources:
            if source["url"] not in seen_urls:
                unique_sources.append(source)
                seen_urls.add(source["url"])

        return ToolReturn(
            return_value=INSTRUCTIONS + str(compact),
            content='',
            metadata={"sources": unique_sources},
        )
        
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Albert Service Public search failed: %s", exc)
        return ToolReturn(return_value=[], content="", metadata={"error": str(exc)})
