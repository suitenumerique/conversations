"""Generation of office documents from model-produced specs."""

from .builder import PresentationBuildError, build_presentation
from .entities import (
    MAX_SLIDE_COUNT,
    Presentation,
    PresentationStyle,
    Slide,
    SlideType,
    TemplatedPresentation,
    TemplatedSlide,
)
from .from_template import (
    TemplateOutline,
    TemplateTooLargeError,
    build_from_template,
    outline_template,
)
from .templates import GENERIC_TEMPLATE

__all__ = [
    "GENERIC_TEMPLATE",
    "MAX_SLIDE_COUNT",
    "Presentation",
    "PresentationBuildError",
    "PresentationStyle",
    "Slide",
    "SlideType",
    "TemplateOutline",
    "TemplateTooLargeError",
    "TemplatedPresentation",
    "TemplatedSlide",
    "build_from_template",
    "build_presentation",
    "outline_template",
]
