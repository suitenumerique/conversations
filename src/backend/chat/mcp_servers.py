"""MCP servers configuration: will be replaced by models."""

from pydantic_ai.mcp import MCPServerStreamableHTTP

MCP_SERVERS = {
    "mcpServers": {
        #"local": {
        #    "url": "http://host.docker.internal:8007/mcp",
        #},
        # "github": {
        #     "url": "https://api.githubcopilot.com/mcp/",
        #     "headers": {"Authorization": "Bearer XXX"},
        # },
    }
}


def get_mcp_servers(custom_url: str | None = None):
    """Retrieve MCP servers configuration."""
    servers = [
        MCPServerStreamableHTTP(**server_config)
        for _name, server_config in MCP_SERVERS["mcpServers"].items()
    ]
    
    if custom_url:
        servers.append(MCPServerStreamableHTTP(url=custom_url))
        
    return servers
