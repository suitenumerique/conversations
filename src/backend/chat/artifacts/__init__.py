"""Visual artifacts (charts/tables/stats) rendered beside the chat.

The LLM never produces executable code: it fills a validated, declarative
``ArtifactSpec`` that the frontend maps to a whitelist of React components.
"""

from chat.artifacts.schema import ArtifactSpec

__all__ = ["ArtifactSpec"]
