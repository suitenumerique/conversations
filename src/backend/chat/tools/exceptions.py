"""Exceptions for tool function retries."""

from pydantic_ai import ModelRetry


class ModelRetryLast(ModelRetry):
    """
    Same as ModelRetry but also holds the last retry message to return when all attempts failed.
    """

    def __init__(self, message: str, last_retry_message: str):
        """Initialize ModelRetryLast with message and last retry message."""
        self.last_retry_message = last_retry_message
        super().__init__(message)


class ModelCannotRetry(ModelRetry):
    """
    Exception to raise when a tool function cannot be retried.

    We use this exception to signal that the model should not attempt to retry
    the tool call, typically because the error is not transient or recoverable.
    """
