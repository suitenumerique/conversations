"""Constants and schemas for the Albert RAG agent from Albert API codebase."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, constr, model_validator


# - app/schemas/chunks.py
class Chunk(BaseModel):
    """Model representing a chunk of text with metadata."""

    object: Literal["chunk"] = "chunk"
    id: int
    metadata: Dict[str, Any]
    content: str


class Chunks(BaseModel):
    """Model representing a list of chunks."""

    object: Literal["list"] = "list"
    data: List[Chunk]


# - app/schemas/usage.py
class CarbonFootprintUsageKWh(BaseModel):
    """Model representing the carbon footprint usage in kWh (kilowatt-hours)."""

    min: Optional[float] = Field(default=None, description="Minimum carbon footprint in kWh.")
    max: Optional[float] = Field(default=None, description="Maximum carbon footprint in kWh.")


class CarbonFootprintUsageKgCO2eq(BaseModel):
    """Model representing the carbon footprint usage in kgCO2eq (kilograms of CO2 equivalent)."""

    min: Optional[float] = Field(
        default=None, description="Minimum carbon footprint in kgCO2eq (global warming potential)."
    )
    max: Optional[float] = Field(
        default=None, description="Maximum carbon footprint in kgCO2eq (global warming potential)."
    )


class CarbonFootprintUsage(BaseModel):
    """Model representing the carbon footprint usage in kWh and kgCO2eq."""

    kWh: CarbonFootprintUsageKWh = Field(default_factory=CarbonFootprintUsageKWh)
    kgCO2eq: CarbonFootprintUsageKgCO2eq = Field(default_factory=CarbonFootprintUsageKgCO2eq)


class BaseUsage(BaseModel):
    """Base model for usage statistics in the Albert API."""

    prompt_tokens: int = Field(
        default=0, description="Number of prompt tokens (e.g. input tokens)."
    )
    completion_tokens: int = Field(
        default=0, description="Number of completion tokens (e.g. output tokens)."
    )
    total_tokens: int = Field(
        default=0, description="Total number of tokens (e.g. input and output tokens)."
    )
    cost: float = Field(default=0.0, description="Total cost of the request.")
    carbon: CarbonFootprintUsage = Field(default_factory=CarbonFootprintUsage)


# - app/schemas/usage.py
class Detail(BaseModel):
    """Model representing a detail in the usage statistics."""

    id: str
    model: str
    usage: BaseUsage = Field(default_factory=BaseUsage)


class Usage(BaseUsage):
    """Model representing the usage statistics for the Albert API."""

    details: List[Detail] = []


class SearchMethod(str, Enum):
    """
    Enum representing the search methods available (will be displayed in this order in playground).
    """

    MULTIAGENT = "multiagent"
    HYBRID = "hybrid"
    SEMANTIC = "semantic"
    LEXICAL = "lexical"


class SearchArgs(BaseModel):
    """Model representing the arguments for a search request in the Albert API."""

    collections: List[Any] = Field(default=[], description="List of collections ID")
    rff_k: int = Field(default=20, description="k constant in RFF algorithm")
    k: int = Field(gt=0, default=4, description="Number of results to return")
    method: SearchMethod = Field(default=SearchMethod.SEMANTIC)
    score_threshold: Optional[float] = (
        Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description=(
                "Score of cosine similarity threshold for filtering results, "
                "only available for semantic search method."
            ),
        ),
    )
    web_search: bool = Field(
        default=False, description="Whether add internet search to the results."
    )
    web_search_k: int = Field(default=5, description="Number of results to return for web search.")

    @model_validator(mode="after")
    def score_threshold_filter(self, values):
        """Validate the score threshold based on the search method."""
        if values.score_threshold and values.method not in (
            SearchMethod.SEMANTIC,
            SearchMethod.MULTIAGENT,
        ):
            raise ValueError(
                "Score threshold is only available for semantic and multiagent search methods."
            )
        return values


class SearchRequest(SearchArgs):
    """Model representing a search request in the Albert API."""

    prompt: constr(strip_whitespace=True, min_length=1) = Field(
        description="Prompt related to the search"
    )


class Search(BaseModel):
    """Model representing a search result in the Albert API."""

    method: SearchMethod
    score: float
    chunk: Chunk


class Searches(BaseModel):
    """Model representing a list of search results in the Albert API."""

    object: Literal["list"] = "list"
    data: List[Search]
    usage: Usage = Field(default_factory=Usage, description="Usage information for the request.")
