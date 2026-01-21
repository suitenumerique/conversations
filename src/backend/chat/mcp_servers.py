"""MCP servers configuration: will be replaced by models."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

MCP_SERVERS = {
    "mcpServers": {
        # "github": {
        #     "url": "https://api.githubcopilot.com/mcp/",
        #     "headers": {"Authorization": "Bearer XXX"},
        # },
        # "data-analysis": {
        #    "url": "http://host.docker.internal:8000/mcp",
        # },
    }
}


DATA_ANALYSIS_MCP_SERVER = {
    "data-analysis": {
        "url": "http://host.docker.internal:8000/mcp",
    },
}


def get_mcp_servers():
    """Retrieve MCP servers configuration."""
    return [
        MCPServerStreamableHTTP(**server_config)
        for _name, server_config in MCP_SERVERS["mcpServers"].items()
    ]


from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@asynccontextmanager
async def get_data_analysis_mcp_server():
    """
    Connect to the data analysis MCP server and return the initialized session.
    """
    server_url = DATA_ANALYSIS_MCP_SERVER["data-analysis"]["url"]

    # Create a streamable HTTP connection to the MCP server.
    async with streamablehttp_client(server_url) as (read_stream, write_stream, _):
        # Create a client session using the streams.
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the session (handshake).
            await session.initialize()
            # Yield the session so it stays open while being used
            yield session
