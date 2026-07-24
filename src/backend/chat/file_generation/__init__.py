"""Generation of office documents from model-produced specs."""

from .builder import PresentationBuildError, build_presentation
from .entities import Presentation, Slide, SlideType
from .templates import GENERIC_TEMPLATE

__all__ = [
    "GENERIC_TEMPLATE",
    "Presentation",
    "PresentationBuildError",
    "Slide",
    "SlideType",
    "build_presentation",
]
