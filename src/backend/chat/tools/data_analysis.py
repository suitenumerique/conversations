import base64
import json
import logging
import uuid
from io import BytesIO

from django.core.files.storage import default_storage
from django.db.models import Q

import boto3
import botocore
from asgiref.sync import sync_to_async
from pydantic_ai import RunContext, RunUsage
from pydantic_ai.messages import ToolReturn

from core.file_upload.utils import generate_retrieve_policy

from chat import models
from chat.mcp_servers import get_data_analysis_mcp_server
from conversations import settings

logger = logging.getLogger(__name__)


async def data_analysis(ctx: RunContext, query: str) -> ToolReturn:
    """
    Call this tool to perform a data analysis.

    Args:
        query: The query to perform the data analysis/To plot stuff or compute stuff from files and data.
        The query should be very clear and precise, explaining what results you expect, tables, numbers or plots.

    Returns:
        The result of the data analysis and/or the plot requested.
    """
    # Prepare files - Get all attachments in the conversation (exclude markdown conversions)
    # Filter for CSV/Excel files that can be analyzed
    attachments = [
        attachment
        async for attachment in models.ChatConversationAttachment.objects.filter(
            Q(conversion_from__isnull=True) | Q(conversion_from=""),
            conversation=ctx.deps.conversation,
            upload_state=models.AttachmentStatus.READY,
        ).exclude(content_type="text/markdown")
    ]

    # Filter for tabular files (CSV, Excel)
    tabular_attachments = [
        att for att in attachments if att.file_name.endswith((".csv", ".xls", ".xlsx"))
    ]

    # Prepare tool arguments
    tool_args = {"query": query}

    # S3 client dedicated to MCP URLs (endpoint = AWS_S3_MCP_URL, e.g. ngrok)
    mcp_s3_client = boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY,
        endpoint_url=settings.AWS_S3_MCP_URL,
        config=botocore.client.Config(
            region_name=settings.AWS_S3_REGION_NAME,
            signature_version=settings.AWS_S3_SIGNATURE_VERSION,
        ),
    )

    # If we have tabular files, use the first one (or let the tool handle multiple files)
    # TODO: Handle multiple files
    if tabular_attachments:
        logger.debug(f"Tabular file found: {tabular_attachments[-1].file_name}")
        # Use the last tabular file found
        attachment = tabular_attachments[-1]
        presigned_url = mcp_s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": default_storage.bucket_name, "Key": attachment.key},
            ExpiresIn=settings.AWS_S3_RETRIEVE_POLICY_EXPIRATION,
        )
        tool_args["document"] = presigned_url
    else:
        return ToolReturn(
            return_value={"error": "No tabular file found, ask the user to upload a tabular file."},
            content="",
            metadata={},
        )
    tool_args["document_name"] = attachment.file_name
    logger.debug(f"Tool arguments: {tool_args}")

    # Connect to MCP server and call the tool
    async with get_data_analysis_mcp_server() as session:
        tool_result = await session.call_tool(
            "data_analysis_tool",
            tool_args,
        )
        logger.info(f"Tool result: {tool_result}")
        logger.info(f"Tool result type: {type(tool_result)}")

        # tool_result is a CallToolResult MCP
        parsed_result = {}
        if getattr(tool_result, "content", None):
            first_content = tool_result.content[0]
            text = getattr(first_content, "text", str(first_content))
            try:
                parsed_result = json.loads(text)
            except json.JSONDecodeError:
                parsed_result = {"raw": text}
        else:
            parsed_result = {"raw": str(tool_result)}

        # Prepare results
        result = {
            "result": str(parsed_result.get("result")),
        }
        metadata = {
            "query": parsed_result.get("query"),
            "query_code": parsed_result.get("query_code"),
            "metadata": parsed_result.get("metadata"),
        }

        # Check if result has plot
        plot_image_base64 = parsed_result.get("plot_image")
        plot_url = None

        if plot_image_base64:
            # Decode base64 image
            plot_image = base64.b64decode(plot_image_base64)

            plot_filename = f"plot_{uuid.uuid4().hex[:8]}.png"
            plot_key = f"{ctx.deps.conversation.pk}/plots/{plot_filename}"

            # Save to storage
            await sync_to_async(default_storage.save)(plot_key, BytesIO(plot_image))

            browser_plot_url = await sync_to_async(generate_retrieve_policy)(plot_key)
            plot_url = browser_plot_url

            # Do NOT include plot_url in result so the model can't see it.
            # plot_url will be added to the stream by pydantic_ai.py.
            # Add a clear message in the content for the model.
            result["result"] += (
                "Le graphique a été inséré automatiquement dans la conversation pour l'utilisateur. "
                "Ne donnes JAMAIS d'url de plot."
                "Dis à l'utilisateur 'Tu trouveras le graphique ci-dessus.' ou quelque chose comme ça et commente le graphique si besoin."
            )
            metadata["plot_url"] = plot_url

    return ToolReturn(
        return_value=result,
        content="",
        metadata=metadata,
    )
