"""Data analysis tool for tabular files (CSV, Excel)."""

import base64
import functools
import json
import logging
import uuid
from io import BytesIO
from typing import Any, Dict

import matplotlib
import numpy as np

matplotlib.use("Agg")  # Use non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd

from django.conf import settings
from django.core.files.storage import default_storage
from django.db.models import Q
from asgiref.sync import sync_to_async
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolReturn

from core.file_upload.enums import AttachmentStatus
from core.file_upload.utils import generate_retrieve_policy

from chat.agents.base import BaseAgent, prepare_custom_model
from chat.models import ChatConversationAttachment
from chat.tools.exceptions import ModelCannotRetry
from chat.tools.utils import last_model_retry_soft_fail

logger = logging.getLogger(__name__)

# MIME types for tabular files
TABULAR_MIME_TYPES = [
    "text/csv",
    "application/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/excel",
]


@sync_to_async
def read_tabular_file(attachment) -> bytes:
    """Read tabular file content asynchronously."""
    with default_storage.open(attachment.key, "rb") as f:
        return f.read()


def detect_csv_separator(file_data: bytes) -> str:
    """
    Detect the CSV separator by analyzing the first few lines.
    
    Returns the most likely separator: ',', ';', or '\t'
    """
    # Read first 10KB to analyze
    sample = file_data[:10240].decode("utf-8", errors="ignore")
    lines = sample.split("\n")[:10]  # First 10 lines
    
    if not lines:
        return ","  # Default to comma
    
    # Count occurrences of each separator in the first few lines
    comma_count = sum(line.count(",") for line in lines)
    semicolon_count = sum(line.count(";") for line in lines)
    tab_count = sum(line.count("\t") for line in lines)
    
    # Return the separator with the highest count
    if tab_count > comma_count and tab_count > semicolon_count:
        return "\t"
    elif semicolon_count > comma_count:
        return ";"
    else:
        return ","  # Default to comma


def _convert_to_serializable(obj: Any) -> Any:
    """
    Convert pandas/numpy types to Python native types for JSON serialization.
    
    Handles:
    - pandas DataFrame/Series
    - numpy scalars (int64, float64, etc.)
    - numpy arrays
    - pandas Timestamp
    - Other non-serializable types
    
    Args:
        obj: The object to convert.
        
    Returns:
        A JSON-serializable version of the object.
    """
    
    # Handle pandas DataFrame
    if isinstance(obj, pd.DataFrame):
        # Limit number of rows to avoid huge responses
        if len(obj) > 1000:
            obj = obj.head(1000)
            logger.warning("Result truncated to 1000 rows")
        return obj.to_dict(orient="records")
    
    # Handle pandas Series
    if isinstance(obj, pd.Series):
        # Convert Series to dict, handling index
        result_dict = obj.to_dict()
        # Convert any numpy/pandas types in the values
        return {str(k): _convert_to_serializable(v) for k, v in result_dict.items()}
    
    # Handle numpy scalars
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()  # Convert to Python native int/float
    
    # Handle numpy arrays
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    
    # Handle pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    
    # Handle lists and tuples - recursively convert elements
    if isinstance(obj, (list, tuple)):
        return [_convert_to_serializable(item) for item in obj]
    
    # Handle dicts - recursively convert values
    if isinstance(obj, dict):
        return {str(k): _convert_to_serializable(v) for k, v in obj.items()}
    
    # Handle None, bool, int, float, str - these are already serializable
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    
    # Fallback: try to convert to string
    try:
        return str(obj)
    except Exception:
        logger.warning("Could not serialize object of type %s, returning None", type(obj))
        return None


def _is_valid_excel_file(file_data: bytes, file_name: str) -> bool:
    """
    Check if the file data appears to be a valid Excel file.
    
    XLSX files are ZIP archives, so they should start with ZIP signature (PK\x03\x04).
    XLS files have a different signature.
    """
    if not file_data:
        return False
    
    file_lower = file_name.lower()
    
    # Check for XLSX (ZIP-based) signature
    if file_lower.endswith((".xlsx", ".xlsm", ".xlsb")):
        # XLSX files are ZIP archives, should start with PK\x03\x04
        return file_data[:4] == b"PK\x03\x04"
    
    # Check for XLS (OLE2) signature
    if file_lower.endswith(".xls"):
        # XLS files are OLE2 compound documents, should start with specific signature
        # Common signatures: 0xD0CF11E0 (OLE2) or 0x504B0304 (sometimes saved as ZIP)
        return (
            file_data[:4] == b"\xd0\xcf\x11\xe0"  # OLE2 signature
            or file_data[:4] == b"PK\x03\x04"  # Sometimes XLS are actually ZIP
        )
    
    return False


@sync_to_async
def load_dataframe(file_data: bytes, content_type: str, file_name: str) -> Dict[str, pd.DataFrame]:
    """
    Load tabular file into pandas DataFrames.
    
    Returns a dictionary mapping sheet/table names to DataFrames.
    For CSV files, uses 'default' as the key.
    For Excel files, uses sheet names as keys.
    """
    try:
        # Handle CSV files - also accept text/plain if file extension is .csv
        if content_type in ["text/csv", "application/csv"] or (
            content_type == "text/plain" and file_name.lower().endswith(".csv")
        ):
            # Detect the separator
            separator = detect_csv_separator(file_data)
            logger.debug("Detected CSV separator: %r", separator)
            
            # Read CSV with detected separator
            df = pd.read_csv(
                BytesIO(file_data),
                sep=separator,
                on_bad_lines="skip",  # Skip problematic lines
                engine="python",  # More flexible parser
                encoding="utf-8",
            )
            
            if df.empty:
                raise ValueError("CSV file appears to be empty or could not be parsed")
            
            return {"default": df}
        elif content_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
            "application/excel",
        ] or file_name.lower().endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
            # Validate Excel file format before attempting to read
            if not _is_valid_excel_file(file_data, file_name):
                logger.warning(
                    "File '%s' does not appear to be a valid Excel file. "
                    "File size: %d bytes, First bytes: %r",
                    file_name,
                    len(file_data),
                    file_data[:20] if len(file_data) >= 20 else file_data,
                )
                raise ValueError(
                    f"File '{file_name}' does not appear to be a valid Excel file. "
                    "It may be corrupted or in an unsupported format."
                )
            
            file_lower = file_name.lower()
            dataframes = {}
            
            # Try different engines based on file extension
            if file_lower.endswith(".xls"):
                # Old Excel format - try xlrd engine
                try:
                    logger.debug("Attempting to read .xls file with xlrd engine")
                    excel_file = pd.ExcelFile(BytesIO(file_data), engine="xlrd")
                    dataframes = {
                        sheet_name: excel_file.parse(sheet_name)
                        for sheet_name in excel_file.sheet_names
                    }
                except Exception as xlrd_error:
                    logger.warning("Failed to read .xls with xlrd: %s", xlrd_error)
                    # Fallback: try openpyxl (sometimes .xls files are actually .xlsx)
                    try:
                        logger.debug("Trying openpyxl as fallback for .xls file")
                        excel_file = pd.ExcelFile(BytesIO(file_data), engine="openpyxl")
                        dataframes = {
                            sheet_name: excel_file.parse(sheet_name)
                            for sheet_name in excel_file.sheet_names
                        }
                    except Exception as openpyxl_error:
                        logger.error("Failed to read .xls with both engines: %s", openpyxl_error)
                        raise ValueError(
                            f"Failed to read Excel file '{file_name}': "
                            f"xlrd error: {xlrd_error}, openpyxl error: {openpyxl_error}"
                        ) from openpyxl_error
            else:
                # XLSX format - try openpyxl first
                try:
                    logger.debug("Attempting to read Excel file with openpyxl engine")
                    excel_file = pd.ExcelFile(BytesIO(file_data), engine="openpyxl")
                    dataframes = {
                        sheet_name: excel_file.parse(sheet_name)
                        for sheet_name in excel_file.sheet_names
                    }
                except Exception as openpyxl_error:
                    logger.warning("Failed to read with openpyxl: %s", openpyxl_error)
                    # Try calamine engine if available (faster and more robust)
                    try:
                        logger.debug("Trying calamine engine as fallback")
                        excel_file = pd.ExcelFile(BytesIO(file_data), engine="calamine")
                        dataframes = {
                            sheet_name: excel_file.parse(sheet_name)
                            for sheet_name in excel_file.sheet_names
                        }
                    except ImportError:
                        logger.debug("calamine engine not available")
                        raise ValueError(
                            f"Failed to read Excel file '{file_name}' with openpyxl: {openpyxl_error}. "
                            "The file may be corrupted or in an unsupported format."
                        ) from openpyxl_error
                    except Exception as calamine_error:
                        logger.error("Failed to read with calamine: %s", calamine_error)
                        raise ValueError(
                            f"Failed to read Excel file '{file_name}': "
                            f"openpyxl error: {openpyxl_error}, calamine error: {calamine_error}"
                        ) from calamine_error
            
            if not dataframes:
                raise ValueError(f"Excel file '{file_name}' contains no readable sheets")
            
            logger.info(
                "Successfully loaded Excel file '%s' with %d sheet(s): %s",
                file_name,
                len(dataframes),
                list(dataframes.keys()),
            )
            return dataframes
        else:
            raise ValueError(f"Unsupported content type: {content_type}")
    except Exception as e:
        logger.error("Error loading tabular file: %s", e, exc_info=True)
        raise ModelCannotRetry(f"Failed to load file: {str(e)}") from e


def generate_metadata(dataframes: Dict[str, pd.DataFrame], file_name: str) -> Dict[str, Any]:
    """
    Generate metadata about the tabular file.
    
    Returns:
        Dictionary containing:
        - sheets: List of sheet/table names
        - schemas: Dictionary mapping sheet names to their schemas
        - row_counts: Dictionary mapping sheet names to row counts
        - column_info: Dictionary mapping sheet names to column information
    """
    metadata = {
        "file_name": file_name,
        "sheets": list(dataframes.keys()),
        "schemas": {},
        "row_counts": {},
        "column_info": {},
    }

    for sheet_name, df in dataframes.items():
        # Schema: column names and types
        metadata["schemas"][sheet_name] = {
            col: str(dtype) for col, dtype in df.dtypes.items()
        }
        
        # Row count
        metadata["row_counts"][sheet_name] = len(df)
        
        # Column info: name, type, sample values, null counts
        metadata["column_info"][sheet_name] = {}
        for col in df.columns:
            col_info = {
                "type": str(df[col].dtype),
                "null_count": int(df[col].isna().sum()),
                "unique_count": int(df[col].nunique()),
            }
            # Add sample values (non-null)
            sample_values = df[col].dropna().head(5).tolist()
            if sample_values:
                col_info["sample_values"] = [str(v) for v in sample_values]
            metadata["column_info"][sheet_name][col] = col_info

    return metadata


async def generate_query(
    user_query: str, metadata: Dict[str, Any], query_agent: BaseAgent, ctx: RunContext
) -> str:
    """
    Use an LLM agent to generate a pandas query from user query and file metadata.
    """
    metadata_str = json.dumps(metadata, indent=2)
    
    prompt = f"""You are a data analysis assistant. Given a user query and file metadata, generate a Python pandas query to answer the question.

File metadata:
{metadata_str}

User query: {user_query}

Generate a Python code snippet that:
1. Uses pandas operations (filter, groupby, aggregate, etc.)
2. Works with the dataframes loaded in memory (available as 'dataframes' dict)
3. Assigns the final result to a variable named 'result'
4. Handles the specific sheet/table if multiple sheets exist
5. ALWAYS handles NaN/NA values in boolean conditions using .notna() or .fillna() before filtering
6. If the user asks for a plot/graph/chart, create it using matplotlib and save to 'plot_image' variable as base64

IMPORTANT RULES:
- The code MUST assign the final result to a variable named 'result'
- When filtering with conditions, ALWAYS check for NaN first: df[df['col'].notna() & (df['col'] > value)]
- Use .dropna() if you need to remove rows with missing values
- Use .fillna() if you need to replace missing values
- If plotting: use plt (already imported), create the plot, convert to base64:
  ```python
  plt.figure(figsize=(10, 6))
  # ... your plot code ...
  buf = BytesIO()
  plt.savefig(buf, format='png')
  buf.seek(0)
  plot_image = base64.b64encode(buf.getvalue()).decode('utf-8')
  plt.close()
  ```
  NOTE: Do NOT use import statements - plt, base64, BytesIO are already available.

Return ONLY the Python code, without markdown formatting or explanations. The code should be executable and use variables:
- 'dataframes': dict mapping sheet names to DataFrames
- Sheet names available: {', '.join(metadata['sheets'])}

Example format (without plot):
df = dataframes['default']
df = df[df['column'].notna()]  # Remove NaN values first
result = df[df['column'] > 100].groupby('category').sum()

Example format (with plot):
df = dataframes['default']
plt.figure(figsize=(10, 6))
plt.plot(df.index, df['close'])
plt.xlabel('Index')
plt.ylabel('Close')
plt.title('Close vs Index')
buf = BytesIO()
plt.savefig(buf, format='png')
buf.seek(0)
plot_image = base64.b64encode(buf.getvalue()).decode('utf-8')
plt.close()
result = "Plot generated successfully. The plot image has been saved and is available in the tool response."

IMPORTANT: 
- Do NOT use import statements in the code. All necessary modules (pd, plt, np, base64, BytesIO) are already available. Do NOT use anything else than these modules.
- When returning the result text, mention that a plot was generated and will be available in the response, but do NOT include the URL in the text - the system will handle displaying it.

Generate the query code:"""

    try:
        response = await query_agent.run(prompt, usage=ctx.usage)
        query_code = response.output.strip()
        
        # Extract code from markdown code blocks if present
        if "```python" in query_code:
            query_code = query_code.split("```python")[1].split("```")[0].strip()
        elif "```" in query_code:
            query_code = query_code.split("```")[1].split("```")[0].strip()
        
        return query_code
    except Exception as e:
        logger.error("Error generating query: %s", e, exc_info=True)
        raise ModelRetry("Failed to generate query. Please try rephrasing your question.") from e


@sync_to_async
def execute_query(query_code: str, dataframes: Dict[str, pd.DataFrame]) -> Any:
    """
    Execute the generated pandas query safely.
    
    Note: Uses exec() in a restricted environment. The query code is generated
    by an LLM based on file metadata, so it should be relatively safe, but
    we restrict the available builtins and globals.
    """
    try:
        # Pre-process dataframes to handle common issues
        processed_dataframes = {}
        for name, df in dataframes.items():
            # Make a copy to avoid modifying original
            df_processed = df.copy()
            # Replace common NaN representations
            df_processed = df_processed.replace(["", " ", "nan", "NaN", "None", "null"], pd.NA)
            processed_dataframes[name] = df_processed
        
        # Create a safe execution environment
        safe_globals = {
            "pd": pd,
            "plt": plt,
            "np": np,
            "base64": base64,
            "BytesIO": BytesIO,
            "dataframes": processed_dataframes,
            "__builtins__": {
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "range": range,
                "sum": sum,
                "max": max,
                "min": min,
                "abs": abs,
                "round": round,
            },
        }
        
        # Clean up query code - remove any import statements that might cause issues
        # Split by lines and filter out import statements
        lines = query_code.split("\n")
        cleaned_lines = [
            line
            for line in lines
            if not line.strip().startswith("import ") and not line.strip().startswith("from ")
        ]
        query_code = "\n".join(cleaned_lines)
        
        # Execute the query in a restricted namespace
        local_vars = {}
        exec(query_code, safe_globals, local_vars)  # noqa: S102
        
        # Get the result - check if 'result' variable exists, otherwise try 'df'
        if "result" in local_vars:
            result = local_vars["result"]
        elif "df" in local_vars:
            result = local_vars["df"]
        else:
            # If no explicit result variable, get the last expression
            # This is a fallback - ideally the LLM should assign to 'result'
            raise ValueError("Query must assign result to 'result' variable")
        
        # Check if a plot was generated
        plot_image = None
        if "plot_image" in local_vars:
            plot_image = local_vars["plot_image"]
            logger.info("Plot image generated")
        
        # Convert result to a serializable format
        result = _convert_to_serializable(result)
        
        return {"result": result, "plot_image": plot_image}
    except Exception as e:
        logger.error("Error executing query: %s", e, exc_info=True)
        # Provide more helpful error message
        error_msg = str(e)
        if "NaN" in error_msg or "NA" in error_msg:
            error_msg = (
                f"{error_msg}. "
                "The query may need to handle missing values (NaN/NA) using .notna() or .dropna() before filtering."
            )
        raise ModelCannotRetry(f"Failed to execute query: {error_msg}") from e


@last_model_retry_soft_fail
async def data_analysis(ctx: RunContext, query: str) -> ToolReturn:
    """
    Analyze tabular data files (CSV, Excel) based on user query.
    Can also generate plots/graphs/charts.
    
    This tool:
    1. Loads the tabular file(s) from attachments
    2. Generates metadata about the file structure
    3. Uses an LLM to generate a pandas query based on user query
    4. Executes the query and returns results
    
    Args:
        ctx (RunContext): The run context containing the conversation.
        query (str): The user's data analysis question.
    
    Returns:
        ToolReturn: Contains the analysis results and metadata.
    """
    try:
        # Find tabular files in attachments
        # First, get all attachments for debugging
        all_attachments = await sync_to_async(list)(
            ctx.deps.conversation.attachments.all()
        )
        logger.info(
            "All attachments in conversation: %s",
            [
                {
                    "file_name": a.file_name,
                    "content_type": a.content_type,
                    "upload_state": a.upload_state,
                    "conversion_from": a.conversion_from,
                }
                for a in all_attachments
            ],
        )

        # Find tabular files - exclude converted files (they have conversion_from set)
        # First try by content_type
        tabular_attachments_by_type = await sync_to_async(list)(
            ctx.deps.conversation.attachments.filter(
                content_type__in=TABULAR_MIME_TYPES,
                upload_state=AttachmentStatus.READY,
            )
            .filter(
                Q(conversion_from__isnull=True) | Q(conversion_from="")
            )
        )
        
        # If no files found by content_type, try by file extension as fallback
        # (some systems detect CSV as text/plain instead of text/csv)
        if not tabular_attachments_by_type:
            csv_extensions = [".csv", ".xlsx", ".xls"]
            all_ready_attachments = await sync_to_async(list)(
                ctx.deps.conversation.attachments.filter(
                    upload_state=AttachmentStatus.READY,
                )
                .filter(
                    Q(conversion_from__isnull=True) | Q(conversion_from="")
                )
            )
            tabular_attachments = [
                att
                for att in all_ready_attachments
                if any(att.file_name.lower().endswith(ext) for ext in csv_extensions)
                # Exclude Markdown files (converted files have .md extension or content_type text/markdown)
                and not att.file_name.lower().endswith(".md")
                and att.content_type != "text/markdown"
            ]
            if tabular_attachments:
                logger.info(
                    "Found %d tabular file(s) by extension fallback (content_type was not recognized): %s",
                    len(tabular_attachments),
                    [f"{a.file_name} ({a.content_type})" for a in tabular_attachments],
                )
        else:
            tabular_attachments = tabular_attachments_by_type

        # If still no files found, check if there are converted files that might have originals
        # This handles the case where an Excel file was converted to Markdown for RAG
        if not tabular_attachments:
            # Look for converted files with tabular extensions
            csv_extensions = [".csv", ".xlsx", ".xls"]
            converted_attachments = await sync_to_async(list)(
                ctx.deps.conversation.attachments.filter(
                    upload_state=AttachmentStatus.READY,
                )
                .exclude(
                    Q(conversion_from__isnull=True) | Q(conversion_from="")
                )
            )
            
            # For each converted file, try to find the original
            for converted_att in converted_attachments:
                if any(converted_att.file_name.lower().endswith(ext) for ext in csv_extensions):
                    # Try to find the original file using conversion_from key
                    original_key = converted_att.conversion_from
                    if original_key:
                        original_attachment = await sync_to_async(
                            ctx.deps.conversation.attachments.filter(
                                key=original_key,
                                upload_state=AttachmentStatus.READY,
                            ).first
                        )()
                        if original_attachment:
                            logger.info(
                                "Found original file '%s' for converted file '%s'",
                                original_attachment.file_name,
                                converted_att.file_name,
                            )
                            tabular_attachments.append(original_attachment)
                            break

        logger.info(
            "Found %d tabular attachment(s): %s",
            len(tabular_attachments),
            [f"{a.file_name} ({a.content_type})" for a in tabular_attachments],
        )

        if not tabular_attachments:
            raise ModelCannotRetry(
                "No tabular files (CSV or Excel) found in the conversation. "
                "Please upload a CSV or Excel file first. "
                "Note: If you uploaded an Excel file that was converted to Markdown for RAG, "
                "the original file must still be available."
            )

        # Use the first tabular file
        attachment = tabular_attachments[0]
        logger.info("Analyzing file: %s (type: %s)", attachment.file_name, attachment.content_type)

        # Load file data
        file_data = await read_tabular_file(attachment)
        
        # Validate that this is actually a valid Excel/CSV file (not a converted Markdown file)
        # Check if it's an Excel file that should have ZIP signature
        if attachment.file_name.lower().endswith((".xlsx", ".xls", ".xlsm", ".xlsb")):
            if not _is_valid_excel_file(file_data, attachment.file_name):
                logger.warning(
                    "File '%s' does not appear to be a valid Excel file. "
                    "It may be a converted Markdown file. Searching for original...",
                    attachment.file_name,
                )
                # Try to find the original file
                # Look for an attachment with the same name but without conversion_from
                original_attachment = await sync_to_async(
                    ctx.deps.conversation.attachments.filter(
                        file_name=attachment.file_name,
                        upload_state=AttachmentStatus.READY,
                    )
                    .filter(
                        Q(conversion_from__isnull=True) | Q(conversion_from="")
                    )
                    .exclude(pk=attachment.pk)
                    .first
                )()
                
                if original_attachment:
                    logger.info(
                        "Found original file '%s' (key: %s), using it instead",
                        original_attachment.file_name,
                        original_attachment.key,
                    )
                    attachment = original_attachment
                    file_data = await read_tabular_file(attachment)
                elif hasattr(attachment, 'conversion_from') and attachment.conversion_from:
                    # Try to find by key if this file has a conversion_from
                    original_attachment = await sync_to_async(
                        ctx.deps.conversation.attachments.filter(
                            key=attachment.conversion_from,
                            upload_state=AttachmentStatus.READY,
                        ).first
                    )()
                    if original_attachment:
                        logger.info(
                            "Found original file via conversion_from: '%s'",
                            original_attachment.file_name,
                        )
                        attachment = original_attachment
                        file_data = await read_tabular_file(attachment)
                    else:
                        raise ModelCannotRetry(
                            f"File '{attachment.file_name}' appears to be a converted Markdown file, "
                            "not the original Excel file. The original file is not available. "
                            "Please re-upload the original Excel file."
                        )
                else:
                    raise ModelCannotRetry(
                        f"File '{attachment.file_name}' does not appear to be a valid Excel file. "
                        "It may be corrupted or in an unsupported format."
                    )

        # Load into pandas DataFrames
        dataframes = await load_dataframe(file_data, attachment.content_type, attachment.file_name)

        # Generate metadata
        metadata = generate_metadata(dataframes, attachment.file_name)
        logger.debug("File metadata: %s", json.dumps(metadata, indent=2))

        # Generate query using LLM
        # NOTE:
        # We intentionally create a "bare" Agent instance here instead of using BaseAgent
        # with tools enabled. Using BaseAgent would attach all configured tools (including
        # this data_analysis tool itself), which can cause the model to try to call tools
        # while we're already inside a tool execution, leading to nested tool calls and
        # failures like "Failed to generate query. Please try rephrasing your question.".
        #
        # Here we reuse the same model configuration as BaseAgent but WITHOUT any tools,
        # so this internal call is purely text-to-text.
        llm_config = settings.LLM_CONFIGURATIONS[settings.LLM_DEFAULT_MODEL_HRID]
        if llm_config.is_custom:
            model_instance = prepare_custom_model(llm_config)
        else:
            # Rely on pydantic-ai's built-in model registry / name inference
            model_instance = llm_config.model_name

        # Use the same keyword as when using BaseAgent, which forwards to Agent.
        # On the current pydantic_ai version, the correct kwarg is `output_type`,
        # not `result_type` (passing `result_type` raises a UserError).
        query_agent = Agent(model=model_instance, output_type=str)
        query_code = await generate_query(query, metadata, query_agent, ctx)
        logger.debug("Generated query: %s", query_code)

        # Execute query
        try:
            execution_result = await execute_query(query_code, dataframes)
            result = execution_result.get("result")
            plot_image_base64 = execution_result.get("plot_image")
        except Exception as e:
            logger.error("Query execution failed: %s", e, exc_info=True)
            raise ModelRetry(
                f"Failed to execute the generated query: {str(e)}. "
                "Please try rephrasing your question."
            ) from e

        # Format result for return
        return_value = {
            "query": query,
            "query_code": query_code,
            "result": result,
            "metadata": metadata,
        }
        
        # Save plot image to storage if generated
        plot_url = None
        plot_attachment = None
        if plot_image_base64:
            try:
                # Decode base64 image
                plot_image_data = base64.b64decode(plot_image_base64)
                
                # Generate a unique filename for the plot
                plot_filename = f"plot_{uuid.uuid4().hex[:8]}.png"
                plot_key = f"{ctx.deps.conversation.pk}/plots/{plot_filename}"
                
                # Save to storage
                await sync_to_async(default_storage.save)(
                    plot_key, BytesIO(plot_image_data)
                )
                
                # Create a permanent attachment record in the database
                plot_attachment = await sync_to_async(ChatConversationAttachment.objects.create)(
                    conversation=ctx.deps.conversation,
                    uploaded_by=ctx.deps.user,
                    key=plot_key,
                    file_name=plot_filename,
                    content_type="image/png",
                    upload_state=AttachmentStatus.READY,
                    size=len(plot_image_data),
                )
                
                # Generate presigned URL for immediate access (valid for 1 hour)
                plot_url = await sync_to_async(generate_retrieve_policy)(plot_key)
                logger.info(
                    "Plot image saved to storage and database: %s (presigned URL: %s)", 
                    plot_key, 
                    plot_url[:50] + "..."
                )
            except Exception as e:
                logger.error("Failed to save plot image: %s", e, exc_info=True)
                # Continue without plot URL if save fails
        
        if plot_url:
            # Include both local and presigned URLs
            return_value["plot_url"] = plot_url  # Presigned URL for direct access
            return_value["plot_local_url"] = f"/media-key/{plot_key}"  # Local URL for reference
            # Include attachment ID for reference
            if plot_attachment:
                return_value["plot_attachment_id"] = str(plot_attachment.pk)
        
        return ToolReturn(
            return_value=return_value,
            metadata={"file_name": attachment.file_name, "content_type": attachment.content_type},
        )

    except (ModelCannotRetry, ModelRetry):
        # Re-raise these as-is
        raise
    except Exception as exc:
        # Unexpected error - stop and inform user
        logger.exception("Unexpected error in data_analysis: %s", exc)
        raise ModelCannotRetry(
            f"An unexpected error occurred during data analysis: {type(exc).__name__}. "
            "You must explain this to the user and not try to answer based on your knowledge."
        ) from exc


def add_data_analysis_tool(agent: Agent) -> None:
    """Add the data analysis tool to an existing agent."""

    @agent.tool(retries=2)
    @functools.wraps(data_analysis)
    async def data_analysis_tool(ctx: RunContext, query: str) -> ToolReturn:
        """
        Analyze tabular data files (CSV, Excel) based on user query.
        
        This tool loads tabular files, generates metadata about their structure,
        uses an LLM to generate a pandas query based on the user's question,
        executes the query, and returns the results.
        
        Use this tool when the user asks questions about data in CSV or Excel files,
        such as:
        - "What is the average sales by region?"
        - "Show me the top 10 products by revenue"
        - "How many records are in this file?"
        - "Filter data where column X is greater than Y"
        
        Args:
            ctx (RunContext): The run context containing the conversation.
            query (str): The user's data analysis question.
        """
        # Import here to avoid circular import
        from chat.tools.data_analysis import data_analysis as _data_analysis
        
        return await _data_analysis(ctx, query)

    @agent.instructions
    def data_analysis_instructions() -> str:
        """Dynamic system prompt function to add data analysis instructions."""
        return (
            "When the user asks questions about data in CSV or Excel files, "
            "use the data_analysis tool to analyze the data and answer their question. "
            "The tool will handle loading the file, generating queries, and executing them. "
            "When a plot is generated, the tool returns a 'plot_url' in the result. "
            "Use this presigned URL directly in markdown image syntax: ![Description](plot_url). "
            "Do NOT use local URLs like /media-key/... - always use the presigned URL from plot_url. "
            "Present the results clearly to the user."
        )

