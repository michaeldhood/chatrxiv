"""
Web UI server command.

Starts FastAPI server with uvicorn for async SSE support.
Integrates file watching for automatic ingestion of new chats.
"""
import os

import click


@click.command()
@click.option(
    '--host',
    default='127.0.0.1',
    help='Host to bind to (default: 127.0.0.1)'
)
@click.option(
    '--port',
    type=int,
    default=5000,
    help='Port to bind to (default: 5000)'
)
@click.option(
    '--db-path',
    type=click.Path(),
    help='Path to database file (default: OS-specific location)'
)
@click.option(
    '--reload',
    is_flag=True,
    help='Auto-reload on code changes'
)
@click.option(
    '--no-watch',
    is_flag=True,
    help='Disable automatic file watching (watching enabled by default)'
)
def web(host, port, db_path, reload, no_watch):
    """
    Start web server with automatic chat ingestion.
    
    This single command:
    - Serves the API for the web frontend
    - Watches Cursor database files for changes
    - Auto-ingests new chats when detected
    - Pushes live updates to the frontend via SSE
    
    Use --no-watch to disable automatic ingestion if you want
    to run the watcher separately or just browse existing chats.
    """
    if db_path:
        os.environ['CHATRXIV_DB_PATH'] = str(db_path)
    
    # Enable or disable file watching
    os.environ['CHATRXIV_WATCH'] = 'false' if no_watch else 'true'
    
    try:
        import uvicorn
    except ImportError:
        click.secho(
            "uvicorn is required. Install with: pip install uvicorn[standard]",
            fg='red',
            err=True
        )
        return
    
    click.echo(f"Starting chatrxiv server on http://{host}:{port}")
    if reload:
        click.echo("  Auto-reload: enabled (server restarts on code changes)")
    if not no_watch:
        click.echo("  File watching: enabled (new chats auto-ingested)")
        click.echo("  SSE updates: enabled (frontend auto-refreshes)")
    else:
        click.echo("  File watching: disabled")
    click.echo("\nPress Ctrl+C to stop\n")
    
    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload
    )
