"""Exceptions for tool function retries."""

from pydantic_ai import ModelRetry


class ModelCannotRetry(ModelRetry):
    """
    Exception to raise when a tool function cannot be retried.

    We use this exception to signal that the model should not attempt to retry
    the tool call, typically because the error is not transient or recoverable.
    """
