"""Module containing custom exceptions for chat clients."""


class WebSearchEmptyException(Exception):
    """Exception raised when a web search returns no results."""

    def __init__(self, message="Web search returned no results."):
        self.message = message
        super().__init__(self.message)
