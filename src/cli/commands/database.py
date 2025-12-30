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
from src.services.search import ChatSearchService
from src.services.exporter import ChatExporter
from src.services.topic_generator import TopicStatementGenerator
from src.cli.common import db_option, output_dir_option, format_option, create_progress_callback
from src.cli.orchestrators.ingestion import IngestionOrchestrator


@click.command()
@db_option
@click.option(
    '--source',
    type=click.Choice(['cursor', 'claude', 'all']),
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


@click.command()
@click.argument('query')
@click.option(
    '--limit',
    default=20,
    help='Maximum number of results'
)
@db_option
@click.pass_context
def search(ctx, query, limit, db_path):
    """Search chats in local database."""
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    try:
        search_service = ChatSearchService(db)
        results = search_service.search(query, limit)

        if not results:
            click.echo(f"No chats found matching '{query}'")
            raise click.Abort()

        click.secho(f"\nFound {len(results)} chats matching '{query}':\n", fg='green')

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


@click.command('generate-topics')
@db_option
@click.option(
    '--chat-id',
    type=int,
    help='Generate topic statement for specific chat by ID'
)
@click.option(
    '--all',
    'generate_all',
    is_flag=True,
    help='Generate topic statements for all chats without one'
)
@click.option(
    '--provider',
    type=click.Choice(['openai', 'anthropic', 'heuristic']),
    default='heuristic',
    help='AI provider to use for generation (default: heuristic, no API required)'
)
@click.option(
    '--api-key',
    help='API key for the provider (or set OPENAI_API_KEY/ANTHROPIC_API_KEY env var)'
)
@click.option(
    '--force',
    is_flag=True,
    help='Regenerate topic statements even if they already exist'
)
@click.pass_context
def generate_topics(ctx, db_path, chat_id, generate_all, provider, api_key, force):
    """Generate topic statements for chats.
    
    Topic statements are concise summaries of what each chat conversation is about.
    They can be generated using AI APIs (OpenAI, Anthropic) or simple heuristics.
    
    Examples:
    
    \b
        # Generate for a specific chat
        python -m src generate-topics --chat-id 123
        
    \b
        # Generate for all chats without topic statements
        python -m src generate-topics --all
        
    \b
        # Use OpenAI API (requires OPENAI_API_KEY env var)
        python -m src generate-topics --all --provider openai
        
    \b
        # Force regenerate all topic statements
        python -m src generate-topics --all --force
    """
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)

    db = ctx.obj.get_db()

    if not chat_id and not generate_all:
        click.secho("Error: Must specify either --chat-id or --all", fg='red', err=True)
        raise click.Abort()

    try:
        generator = TopicStatementGenerator(provider=provider, api_key=api_key)
        
        if chat_id:
            # Generate for single chat
            chat_data = db.get_chat(chat_id)
            if not chat_data:
                click.secho(f"Chat {chat_id} not found", fg='red', err=True)
                raise click.Abort()
            
            # Check if already has topic statement
            if chat_data.get("topic_statement") and not force:
                click.echo(f"Chat {chat_id} already has a topic statement: {chat_data['topic_statement']}")
                click.echo("Use --force to regenerate")
                return
            
            click.echo(f"Generating topic statement for chat {chat_id}...")
            topic = generator.update_chat_topic(db, chat_id)
            
            if topic:
                click.secho(f"Generated: {topic}", fg='green')
            else:
                click.secho("Failed to generate topic statement", fg='yellow')
        
        elif generate_all:
            # Generate for all chats without topic statements
            cursor = db.conn.cursor()
            
            if force:
                # Get all chats
                cursor.execute("SELECT id FROM chats ORDER BY id")
                click.echo("Generating topic statements for all chats...")
            else:
                # Get only chats without topic statements
                cursor.execute("SELECT id FROM chats WHERE topic_statement IS NULL OR topic_statement = '' ORDER BY id")
                click.echo("Generating topic statements for chats without one...")
            
            chat_ids = [row[0] for row in cursor.fetchall()]
            
            if not chat_ids:
                click.echo("No chats found to process")
                return
            
            click.echo(f"Processing {len(chat_ids)} chats...")
            
            success_count = 0
            error_count = 0
            
            for idx, cid in enumerate(chat_ids, 1):
                if idx % 10 == 0 or idx == len(chat_ids):
                    click.echo(f"Progress: {idx}/{len(chat_ids)}...")
                
                try:
                    topic = generator.update_chat_topic(db, cid)
                    if topic:
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error("Error generating topic for chat %d: %s", cid, e)
                    error_count += 1
            
            click.echo("\n" + "="*50)
            click.secho(f"Complete! Generated {success_count} topic statements", fg='green')
            if error_count > 0:
                click.secho(f"Errors: {error_count}", fg='yellow')

    except Exception as e:
        click.secho(f"Error during topic generation: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()
