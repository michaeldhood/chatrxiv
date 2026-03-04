"""
MCP server command.

Starts the Model Context Protocol server so LLMs can access the chat archive.
"""

import click


@click.command("mcp-server")
@click.option(
    "--db-path",
    type=click.Path(),
    help="Path to database file (default: OS-specific location)",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="MCP transport protocol (default: stdio)",
)
@click.pass_context
def mcp_server(ctx, db_path, transport):
    """Start the MCP server for LLM access to the chat archive.

    This exposes your chat archive through the Model Context Protocol,
    allowing AI assistants (Claude, Cursor, etc.) to search, browse,
    and read your archived conversations.

    \b
    Stdio transport (default):
      Used by Cursor, Claude Desktop, and other MCP hosts.
      Configure in your MCP client's settings file.

    \b
    SSE transport:
      Runs an HTTP server for web-based MCP clients.

    \b
    Example Cursor MCP config (mcp.json):
      {
        "mcpServers": {
          "chatrxiv": {
            "command": "python3",
            "args": ["-m", "src", "mcp-server"]
          }
        }
      }
    """
    try:
        from src.mcp_server import run_server
    except ImportError:
        click.secho(
            'MCP SDK not installed. Install with: pip install "mcp[cli]"',
            fg="red",
            err=True,
        )
        return

    resolved_path = db_path or (ctx.obj.db_path if ctx.obj else None)
    run_server(db_path=str(resolved_path) if resolved_path else None, transport=transport)
