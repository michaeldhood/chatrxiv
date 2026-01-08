"""
Web UI server command.

Starts FastAPI server with uvicorn for async SSE support.
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
def web(host, port, db_path, reload):
    """
    Start FastAPI web server with SSE support.
    
    The server uses uvicorn for async support, enabling Server-Sent Events
    for live frontend updates when new chats are ingested.
    """
    if db_path:
        os.environ['CHATRXIV_DB_PATH'] = str(db_path)
    
    try:
        import uvicorn
    except ImportError:
        click.secho(
            "uvicorn is required. Install with: pip install uvicorn[standard]",
            fg='red',
            err=True
        )
        return
    
    click.echo(f"Starting FastAPI server on http://{host}:{port}")
    if reload:
        click.echo("Auto-reload enabled - server will restart on code changes")
    click.echo("SSE enabled - frontend will auto-update when new chats are ingested")
    click.echo("Press Ctrl+C to stop")
    
    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload
    )

