"""What is safe to put in a log line."""

import logging
import re
from typing import Any

import httpx
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

# Errors from an LLM or RAG provider: their message carries the response body,
# which can echo the prompt or document content.
PROVIDER_ERRORS = (ModelAPIError, httpx.HTTPStatusError)


def provider_errors_in_chain(exc: BaseException | None) -> list[BaseException]:
    """The provider errors in `exc` and in what it was raised from, outermost first.

    A traceback renders the whole chain, explicit (`raise ... from`) and implicit
    (raised while handling another), so a provider error anywhere in it leaks.
    """
    found = []
    seen = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, PROVIDER_ERRORS):
            found.append(exc)
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return found


def find_provider_error(exc: BaseException | None) -> BaseException | None:
    """The outermost provider error in `exc`'s chain, if any."""
    errors = provider_errors_in_chain(exc)
    return errors[0] if errors else None


def safe_error_fields(exc: BaseException | None) -> dict[str, Any]:
    """The parts of a failure that are safe to log: its type and HTTP status.

    Never the message or traceback: a provider error carries the response body,
    which can echo the prompt or document content.
    """
    if isinstance(exc, ModelHTTPError):
        status_code = exc.status_code
    elif isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
    else:
        status_code = None
    return {"error_type": type(exc).__name__ if exc else None, "status_code": status_code}


# The temporary key in a file-stream path grants access to the file: keep it
# out of the logs (see chat/views/files.py).
_FILE_STREAM_KEY_RE = re.compile(r"^(/api/[^/]+/file-stream/)[^/]+")


def redact_file_stream_key(path: str) -> str:
    """`path`, with the temporary key of a file-stream path replaced."""
    return _FILE_STREAM_KEY_RE.sub(r"\1[redacted]", path)


class RedactFileStreamKeys(logging.Filter):
    """Redact file-stream keys from the arguments a stdlib record is formatted with.

    django.request logs every 4xx and 5xx response with its path as an argument
    ("Method Not Allowed: <path>"), including a refused request to a key that is
    still live.
    """

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact_file_stream_key(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        return True
