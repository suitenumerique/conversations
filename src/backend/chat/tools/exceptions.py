"""Exceptions for tool function retries."""

from pydantic_ai import ModelRetry


class ModelCannotRetry(ModelRetry):
    """
    Exception to raise when a tool function cannot be retried.

    We use this exception to signal that the model should not attempt to retry
    the tool call, typically because the error is not transient or recoverable.
    """


class UserContentModelRetry(ModelRetry):
    """
    A ModelRetry whose message carries user content (e.g. column names of an attachment).

    The model gets the message to fix its call, but `last_model_retry_soft_fail`
    leaves it out of the logs.
    """
