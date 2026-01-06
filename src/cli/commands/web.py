"""
Web UI server command.

Starts Flask server with gevent for SSE (Server-Sent Events) support.
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
def web(host, port, db_path):
    """
    Start web UI server with SSE support.
    
    The server uses gevent for async support, enabling Server-Sent Events
    for live frontend updates when new chats are ingested.
    """
    if db_path:
        os.environ['CHATRXIV_DB_PATH'] = str(db_path)
    
    # Import gevent WSGIServer for async support (required for SSE)
    # Note: monkey.patch_all() is already called in __main__.py before imports
    try:
        from gevent.pywsgi import WSGIServer
    except ImportError:
        click.secho(
            "gevent is required for SSE support. Install with: pip install gevent",
            fg='yellow',
            err=True
        )
        click.echo("Falling back to standard Flask server (SSE may not work properly)", err=True)
        from src.ui.web.app import app
        app.run(host=host, port=port, debug=True)
        return
    
    from src.ui.web.app import app
    
    click.echo(f"Starting web UI server on http://{host}:{port}")
    click.echo("SSE enabled - frontend will auto-update when new chats are ingested")
    click.echo("Press Ctrl+C to stop")
    
    server = WSGIServer((host, port), app)
    server.serve_forever()

