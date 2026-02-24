"""Translation tool used for uploaded documents."""

import logging

from django.conf import settings

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from chat.agents.translate import TranslationAgent
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail, read_document_content

logger = logging.getLogger(__name__)


@last_model_retry_soft_fail
async def document_translate(
    ctx: RunContext,
    *,
    target_language: str | None = None,
    instructions: str | None = None,
) -> ToolReturn:
    """
    Translate the full content of the last uploaded document into the specified target language.
    Preserve the original markdown formatting unless the instructions say otherwise.
    Return this translation directly to the user WITHOUT any modification
    or additional summarization.
    The translation is already complete and MUST be presented as-is in the final response.

    If target_language isn't specified or unknown, the target language should be asked
    to the user.

    Instructions are optional but should reflect the user's request.

    Examples:
    "Translate this doc to English" -> target_language = "English", instructions = ""
    "Translate to Spanish, in formal tone" -> target_language = "Spanish",
        instructions = "Use formal tone"
    "Traduis ce document en français" -> target_language = "French", instructions = ""
    "Translate to German, keep technical terms in English" -> target_language = "German",
        instructions = "Keep technical terms in English"
    "Translate this" -> ask the user: "Which language would you like the document
        translated into?"

    Args:
        target_language (str | None): The language to translate the document into.
                                      If None, ask the user.
        instructions (str | None): Optional instructions for the translation style or preferences
    """
    try:
        if not target_language:
            raise ModelCannotRetry(
                "The target language is not specified. "
                "You must ask the user which language they want the document translated into."
            )
        instructions_hint = (
            f"Follow these instructions: {instructions.strip()}" if instructions else ""
        )
        translation_agent = TranslationAgent()

        # Get the last uploaded text document
        last_attachment = await (
            ctx.deps.conversation.attachments.filter(
                content_type__startswith="text/",
            )
            .order_by("-created_at")
            .afirst()
        )

        if not last_attachment:
            raise ModelCannotRetry(
                "No text documents found in the conversation. "
                "You must explain this to the user and ask them to provide documents."
            )

        doc_name, content = await read_document_content(last_attachment)

        max_chars = settings.TRANSLATION_MAX_CHARS
        if len(content) > max_chars:
            raise ModelCannotRetry(
                f"The document is too large to translate ({len(content):,} characters, "
                f"limit is {max_chars:,}). "
                "You must explain this to the user, without providing numerical details. "
                "Suggest them to reduce the document size by summarizing it or "
                "by splitting it into smaller parts. "
                "Also offer them to summarize the document in the target language instead, "
                "which can be a good alternative to translation for large documents."
            )

        logger.info(
            "[translate] translating '%s', %s chars, target_language='%s', instructions='%s'",
            doc_name,
            len(content),
            target_language,
            instructions_hint,
        )

        # Translate the document directly
        translate_prompt = (
            f"You are an agent specializing in text translation. "
            f"Translate the following document to {target_language}. "
            f"Preserve all markdown formatting exactly as-is. "
            f"{instructions_hint}\n\n"
            f"'''\n{content}\n'''\n\n"
            f"Respond directly with the translated text only, no commentary."
        )

        logger.debug("[translate] prompt for '%s'=> %s", doc_name, translate_prompt[:100] + "...")

        try:
            resp = await translation_agent.run(translate_prompt, usage=ctx.usage)
        except Exception as exc:
            logger.warning("Error during translation of '%s': %s", doc_name, exc, exc_info=True)
            raise ModelRetry(f"An error occurred while translating document '{doc_name}'.") from exc

        translated_text = (resp.output or "").strip()
        if not translated_text:
            raise ModelRetry(f"The translation of '{doc_name}' produced an empty result.")

        logger.debug("[translate] final translation length: %s chars", len(translated_text))

        return ToolReturn(
            return_value=translated_text,
            metadata={"sources": {doc_name}},
        )

    except (ModelCannotRetry, ModelRetry):
        raise
    except Exception as exc:
        logger.exception("Unexpected error in document_translate: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during document translation: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc
