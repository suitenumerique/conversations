"""Tool calling utilities for the chat agent."""

import functools
import logging
import uuid
from typing import Any, Callable, Iterable, Set
from urllib.parse import urlparse

from pydantic_ai import ModelRetry, RunContext

from chat import models
from chat.tools.exceptions import ModelCannotRetry

logger = logging.getLogger(__name__)


def normalize_domain(value: str) -> str:
    """Normalize a domain for comparison: lowercase, no leading www. or trailing dot."""
    domain = (value or "").strip().lower()
    domain = domain.lstrip(".")
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.rstrip(".")


def extract_domain(url: str) -> str:
    """Extract the normalized hostname from a URL, or '' when unparseable."""
    try:
        return normalize_domain(urlparse(url or "").hostname or "")
    except ValueError, AttributeError, TypeError:
        return ""


def is_blocked_url(url: str, blocked_domains: Set[str]) -> bool:
    """Check whether a URL belongs to a blocked domain (subdomains included).

    Both the URL hostname and the entries of `blocked_domains` are normalized,
    so "WWW.Facebook.com" matches a "facebook.com" entry, while lookalikes such
    as "notfacebook.com" do not.
    """
    if not blocked_domains:
        return False
    domain = extract_domain(url)
    if not domain:
        return False
    normalized_blocked = {normalize_domain(entry) for entry in blocked_domains}
    normalized_blocked.discard("")
    return any(
        domain == blocked or domain.endswith("." + blocked) for blocked in normalized_blocked
    )


def parse_domain_list(raw) -> Set[str]:
    """Parse a comma-separated domain string (or an iterable) into a set.

    Accepts the shape of a `*_BLOCKED_DOMAINS` setting value: a string such as
    "facebook.com, x.com", any iterable of entries, or a falsy value meaning
    "no blocklist". Entries are normalized, blanks are dropped.
    """
    if not raw:
        return set()
    if isinstance(raw, str):
        entries = raw.split(",")
    else:
        try:
            entries = list(raw)
        except TypeError:
            return set()
    return {normalized for entry in entries if (normalized := normalize_domain(entry))}


def filter_blocked_results(results, blocked_domains: Set[str], max_results=None):
    """Drop blocklisted results, preserving order.

    Runs right after a search API call and before any fetch/extract/RAG work so
    blocked domains never cost HTTP fetches or summarization tokens.

    Args:
        results: Raw result dicts carrying a `url` key (any provider shape).
        blocked_domains: Domains to drop, subdomains included.
        max_results: Optional cap applied after filtering. Providers that cannot
            overfetch (fixed result count) pass None and keep what survives.

    Returns:
        The kept results as a new list.
    """
    if not blocked_domains:
        return list(results)[:max_results]

    kept = []
    dropped_domains = []
    for result in results:
        url = result.get("url", "") if isinstance(result, dict) else ""
        if url and is_blocked_url(url, blocked_domains):
            dropped_domains.append(extract_domain(url))
            continue
        kept.append(result)

    if dropped_domains:
        # Log domains only: never the user query nor full URLs.
        logger.info(
            "Filtered %d blocked web search result(s) (domains: %s)",
            len(dropped_domains),
            ", ".join(sorted(set(dropped_domains))),
        )
    return kept[:max_results]


def resolve_attachment_by_id(
    attachments: Iterable[models.ChatConversationAttachment],
    document_id: str,
) -> models.ChatConversationAttachment:
    """
    Resolve a model-supplied ``document_id`` string to one of the listed attachments.

    Raises ``ModelRetry`` on invalid UUID or missing attachment so the model can
    correct itself within the tool-retry budget.
    """
    try:
        parsed_document_id = uuid.UUID(document_id)
    except ValueError as exc:
        raise ModelRetry("Invalid document_id. Expected a valid UUID.") from exc

    for attachment in attachments:
        if attachment.id == parsed_document_id:
            return attachment

    raise ModelRetry("document_id was not found among attached text documents.")


def last_model_retry_soft_fail(
    tool_func: Callable[..., Any],
) -> Callable[..., Any]:
    """
    Wrap a tool function to handle ModelRetry exceptions.

    If the tool function raises ModelRetry and the maximum number of retries
    has been reached, a ModelCannotRetry exception is raised instead.

    Args:
        tool_func: The original tool function to wrap.

    Returns:
        A wrapped tool function with retry handling.
    """

    @functools.wraps(tool_func)
    async def wrapper(ctx: RunContext, *args, **kwargs) -> Any:
        try:
            return await tool_func(ctx, *args, **kwargs)
        except ModelCannotRetry as exc:
            return str(exc.message)
        except ModelRetry as exc:
            logger.error("Tool '%s' raised ModelRetry: %s", ctx.tool_name, exc.message)
            if (ctx.retries.get(ctx.tool_name, 0) + 1) >= ctx.max_retries:
                logger.error("Max retries reached for tool '%s'.", ctx.tool_name)
                # A bit of a hack to signal that we cannot retry here, while preventing
                # the LLM to generate an outdated answer.
                # We may define a more specific exception later base on ModelRetry which
                # adds a specific message for this case.
                return (
                    f"{exc.message} You must explain this to the user and "
                    "not try to answer based on your knowledge."
                )
            raise  # Re-raise to allow retrying

    return wrapper
