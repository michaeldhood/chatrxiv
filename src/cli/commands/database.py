"""
Database-related CLI commands.

Commands for ingesting, searching, importing, and exporting chat data
from the local database.
"""
import click
from pathlib import Path

from src.core.db import ChatDatabase
from src.core.config import get_default_db_path
from src.services.legacy_importer import LegacyChatImporter
from src.services.chatgpt_export_importer import ChatGPTExportImporter
from src.services.search import ChatSearchService
from src.services.exporter import ChatExporter
from src.cli.common import db_option, output_dir_option, format_option, create_progress_callback
from src.cli.orchestrators.ingestion import IngestionOrchestrator


@click.command()
@db_option
@click.option(
    '--source',
    type=click.Choice(['cursor', 'claude', 'chatgpt', 'all']),
    default='cursor',
    help='Source to ingest from'
)
@click.option(
    '--incremental',
    is_flag=True,
    help='Only ingest chats updated since last run (faster)'
)
@click.pass_context
def ingest(ctx, db_path, source, incremental):
    """Ingest chats from Cursor databases into local DB."""
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        orchestrator = IngestionOrchestrator(db)

        # Create progress callback
        def progress_callback(item_id, total, current):
            if current % 100 == 0 or current == total:
                click.echo(f"Progress: {current}/{total} items processed...")

        mode_str = "incremental" if incremental else "full"
        click.echo(f"Ingesting chats from {source} ({mode_str} mode)...")

        stats = orchestrator.ingest(source, incremental, progress_callback)

        # Display results
        click.echo(f"\nIngestion complete!")
        click.secho(f"  Ingested: {stats['ingested']} chats", fg='green')
        click.echo(f"  Skipped: {stats['skipped']} chats")
        if stats['errors'] > 0:
            click.secho(f"  Errors: {stats['errors']} chats", fg='yellow')
            raise click.Abort()

    except Exception as e:
        click.secho(f"Error during ingestion: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()


@click.command('import-legacy')
@click.argument('path', default='.', type=click.Path(exists=True))
@click.option(
    '--pattern',
    default='chat_data_*.json',
    help='File pattern for directory import'
)
@db_option
@click.pass_context
def import_legacy(ctx, path, pattern, db_path):
    """Import legacy chat_data_*.json files."""
    click.echo("Importing legacy chat files...")

    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        importer = LegacyChatImporter(db)
        path_obj = Path(path)

        if path_obj.is_file():
            # Import single file
            count = importer.import_file(path_obj)
            click.secho(f"Imported {count} chats from {path}", fg='green')
        else:
            # Import directory
            stats = importer.import_directory(path_obj, pattern)
            click.echo("\nImport complete!")
            click.echo(f"  Files processed: {stats['files']}")
            click.secho(f"  Chats imported: {stats['chats']}", fg='green')
            if stats['errors'] > 0:
                click.secho(f"  Errors: {stats['errors']}", fg='yellow')

        if not (count if path_obj.is_file() else stats['chats']):
            raise click.Abort()

    except Exception as e:
        click.secho(f"Error during import: {e}", fg='red', err=True)
        raise click.Abort()


@click.command('import-chatgpt')
@click.argument('path', type=click.Path(exists=True))
@db_option
@click.pass_context
def import_chatgpt(ctx, path, db_path):
    """Import ChatGPT manual export (ZIP or conversations.json file)."""
    click.echo("Importing ChatGPT export...")

    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        importer = ChatGPTExportImporter(db)
        path_obj = Path(path)

        if path_obj.suffix.lower() == '.zip':
            # Import from ZIP file
            count = importer.import_zip(path_obj)
            click.secho(f"Imported {count} chats from {path}", fg='green')
        elif path_obj.is_file() and path_obj.name == 'conversations.json':
            # Import conversations.json directly
            count = importer.import_file(path_obj)
            click.secho(f"Imported {count} chats from {path}", fg='green')
        elif path_obj.is_dir():
            # Look for conversations.json in directory
            conversations_json = path_obj / 'conversations.json'
            if conversations_json.exists():
                count = importer.import_file(conversations_json)
                click.secho(f"Imported {count} chats from {conversations_json}", fg='green')
            else:
                click.secho(f"No conversations.json found in {path}", fg='red')
                raise click.Abort()
        else:
            click.secho(f"Expected ZIP file or conversations.json, got {path}", fg='red')
            raise click.Abort()

        if count == 0:
            click.secho("No chats imported. Check the file format.", fg='yellow')
            raise click.Abort()

    except Exception as e:
        click.secho(f"Error during import: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()


@click.command()
@click.argument('query')
@click.option(
    '--limit',
    default=20,
    help='Maximum number of results'
)
@click.option(
    '--project', '-p',
    help='Filter to chats within a project (by name)'
)
@db_option
@click.pass_context
def search(ctx, query, limit, project, db_path):
    """Search chats in local database.
    
    Examples:
        chatrxiv search "authentication"
        chatrxiv search "API design" --project chatrxiv
    """
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        # Resolve project name to ID if provided
        project_id = None
        if project:
            proj = db.get_project_by_name(project)
            if not proj:
                click.secho(f"Error: Project '{project}' not found", fg='red', err=True)
                raise click.Abort()
            project_id = proj['id']
        
        search_service = ChatSearchService(db)
        results = search_service.search(query, limit, project_id=project_id)

        if not results:
            msg = f"No chats found matching '{query}'"
            if project:
                msg += f" in project '{project}'"
            click.echo(msg)
            raise click.Abort()

        result_msg = f"\nFound {len(results)} chats matching '{query}'"
        if project:
            result_msg += f" in project '{project}'"
        click.secho(result_msg + ":\n", fg='green')

        for chat in results:
            click.echo(f"Chat ID: {chat['id']}")
            click.echo(f"  Title: {chat['title']}")
            click.echo(f"  Mode: {chat['mode']}")
            click.echo(f"  Created: {chat['created_at']}")
            if chat.get('workspace_path'):
                click.echo(f"  Workspace: {chat['workspace_path']}")
            click.echo()

    except Exception as e:
        click.secho(f"Error during search: {e}", fg='red', err=True)
        raise click.Abort()


@click.command('rebuild-index')
@db_option
@click.pass_context
def rebuild_index(ctx, db_path):
    """Rebuild the full-text search index.
    
    Run this after bulk imports or if search results seem incomplete.
    The index covers chat titles, message content, tags, and file paths.
    """
    click.echo("Rebuilding search index...")
    
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        db.rebuild_search_index()
        click.secho("Search index rebuilt successfully!", fg='green')
    except Exception as e:
        click.secho(f"Error rebuilding index: {e}", fg='red', err=True)
        raise click.Abort()


@click.command()
@format_option(['markdown', 'json'], default='markdown')
@output_dir_option(default='exports')
@click.option(
    '--chat-id',
    type=int,
    help='Export specific chat by ID (otherwise exports all)'
)
@db_option
@click.pass_context
def export(ctx, format, output_dir, chat_id, db_path):
    """Export chats from database."""
    click.echo("Exporting chats...")

    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        exporter = ChatExporter(db)
        output_path = Path(output_dir)

        if chat_id:
            # Export single chat
            chat_file = output_path / f"chat_{chat_id}.md"
            if exporter.export_chat_markdown(chat_id, chat_file):
                click.secho(f"Exported chat {chat_id} to {chat_file}", fg='green')
            else:
                raise click.Abort()
        else:
            # Export all chats
            if format == 'markdown':
                count = exporter.export_all_markdown(output_path)
                click.secho(f"Exported {count} chats to {output_path}", fg='green')
                if count == 0:
                    raise click.Abort()
            else:
                click.secho("JSON export not yet implemented", fg='yellow')
                raise click.Abort()

    except Exception as e:
        click.secho(f"Error during export: {e}", fg='red', err=True)
        raise click.Abort()


@click.command()
@db_option
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be deleted without actually deleting'
)
@click.pass_context
def cleanup(ctx, db_path, dry_run):
    """Remove empty chats (messages_count = 0) from database."""
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        # Count empty chats first
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chats WHERE messages_count = 0")
        count = cursor.fetchone()[0]

        if count == 0:
            click.echo("No empty chats found in database.")
            return

        if dry_run:
            click.echo(f"Would delete {count} empty chat(s)")
            click.echo("Run without --dry-run to actually delete them.")
            return

        # Actually delete
        deleted = db.delete_empty_chats()
        click.secho(f"Deleted {deleted} empty chat(s)", fg='green')

    except Exception as e:
        click.secho(f"Error during cleanup: {e}", fg='red', err=True)
        raise click.Abort()
