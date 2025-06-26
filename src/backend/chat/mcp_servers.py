"""MCP servers configuration: will be replaced by models."""

from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams

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
        MCPServerStreamableHttp(
            name=name,
            params=MCPServerStreamableHttpParams(**server),
        )
        for name, server in MCP_SERVERS["mcpServers"].items()
    ]
