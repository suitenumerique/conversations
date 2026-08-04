"""Capture runtime tool returns from pydantic-ai agent runs for eval reporting."""

from pydantic_ai.messages import ToolReturnPart


def capture_tool_output_from_run(result) -> str | None:
    """Return a readable summary of tool returns from an agent run, or None if no tools ran."""
    parts: list[str] = []
    for message in result.all_messages():
        for part in getattr(message, "parts", ()):
            if isinstance(part, ToolReturnPart):
                parts.append(f"[{part.tool_name}]\n{part.model_response_str()}")
    if not parts:
        return None
    return "\n\n".join(parts)
