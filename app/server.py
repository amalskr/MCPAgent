
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("SME MySQL Agent")


@mcp.tool()
def say_hello(name: str) -> str:
    """Return a welcome message for the SME agent user."""
    return f"Hello, {name}! Your MCP server is working."


if __name__ == "__main__":
    mcp.run()
