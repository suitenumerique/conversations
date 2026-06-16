"""Tool that renders a declarative visual artifact beside the chat.

The model supplies a typed ``ArtifactSpec`` (validated by PydanticAI before the
tool body runs). We hand the validated spec back to the frontend through the
``ToolReturn`` metadata under the ``artifact`` key; the frontend maps it to a
whitelist of React components. No executable code is produced or evaluated.
"""

import logging

from pydantic import ValidationError
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn

from chat.artifacts.schema import ArtifactSpec
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)


@last_model_retry_soft_fail
async def render_artifact(
    ctx: RunContext,  # pylint: disable=unused-argument
    *,
    spec: ArtifactSpec,
) -> ToolReturn:
    """
    Render a visual artifact (charts, tables, metrics, callouts) beside the chat.

    The ``spec`` is already validated by PydanticAI against ``ArtifactSpec``;
    this re-validation is a defensive belt-and-braces step so that a spec built
    programmatically (e.g. in tests) still goes through the same bounds checks.

    Args:
        spec (ArtifactSpec): Declarative description of the artifact to render.

    Returns:
        ToolReturn: a short acknowledgement for the model, plus the serialized
        artifact in ``metadata['artifact']`` for the frontend renderer.
    """
    try:
        # `spec` is typically already an ArtifactSpec instance, but revalidate to
        # enforce bounds uniformly regardless of how it was constructed.
        validated = ArtifactSpec.model_validate(spec)
    except ValidationError as exc:
        logger.warning("Invalid artifact spec from model: %s", exc)
        raise ModelRetry(
            "The artifact spec is invalid. Fix the following and call the tool "
            f"again:\n{exc}"
        ) from exc

    logger.debug(
        "[render_artifact] title=%r blocks=%s",
        validated.title,
        [block.type for block in validated.blocks],
    )

    return ToolReturn(
        return_value=(
            f"Artifact '{validated.title}' rendered with "
            f"{len(validated.blocks)} block(s). Introduce it briefly to the user; "
            "do not repeat its full content in your reply."
        ),
        metadata={"artifact": validated.model_dump(mode="json")},
    )
