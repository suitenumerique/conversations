"""MCP servers configuration: will be replaced by models."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

MCP_SERVERS = {
    "mcpServers": {
        # "github": {
        #     "url": "https://api.githubcopilot.com/mcp/",
        #     "headers": {"Authorization": "Bearer XXX"},
        # },
    }
}


def get_mcp_servers():
    """Retrieve MCP servers configuration."""
    return [
        MCPServerStreamableHTTP(**server_config)
        for _name, server_config in MCP_SERVERS["mcpServers"].items()
    ]
