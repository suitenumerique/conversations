"""Base class for web search managers."""

from ..constants import RAGWebResults


class BaseWebSearchManager:
    """
    A class to manage web search operations.

    This is an abstract base class that should be implemented
    for specific web search managers.
    """

    def web_search(self, query: str) -> RAGWebResults:
        """
        Perform a web search.

        Args:
            query (str): The search query.

        Returns:
            RAGWebResults: A Searches object containing the search results.
        """
        raise NotImplementedError()
