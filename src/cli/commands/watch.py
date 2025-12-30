"""
Watch and update-modes CLI commands.

Commands for daemon mode file watching and lightweight mode updates.
"""
import os
import signal
import sys
import time
from pathlib import Path

import click

from src.cli.common import db_option
from src.core.db import ChatDatabase
from src.services.aggregator import ChatAggregator
from src.readers.workspace_reader import WorkspaceStateReader
from src.readers.global_reader import GlobalComposerReader
from src.core.models import ChatMode


@click.command()
@click.option(
    '--source',
    type=click.Choice(['cursor', 'claude', 'all']),
    default='all',
    help='Source to ingest from (default: all)'
)
@click.option(
    '--poll-interval',
    type=float,
    default=30.0,
    help='Polling interval in seconds (default: 30.0, only used if watchdog unavailable)'
)
@click.option(
    '--debounce',
    type=float,
    default=5.0,
    help='Debounce time in seconds before triggering ingestion (default: 5.0)'
)
@click.option(
    '--use-polling',
    is_flag=True,
    help='Force use of polling instead of file system events'
)
@db_option
@click.pass_context
def watch(ctx, source, poll_interval, debounce, use_polling, db_path):
    """
    Watch for changes and automatically ingest (daemon mode).
    
    Runs in the background, monitoring Cursor database files for changes
    and automatically ingesting new chats. Press Ctrl+C to stop gracefully.
    """
    # Get database from context
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    # Get the actual db path (string) for creating new connections in threads
    from src.core.config import get_default_db_path
    db_path_str = str(ctx.obj.db_path) if ctx.obj.db_path else str(get_default_db_path())
    
    try:
        # Perform initial ingestion with main thread connection
        aggregator = ChatAggregator(db)
        
        def do_ingestion():
            """Perform incremental ingestion in background thread."""
            # Create new database connection in this thread (SQLite is thread-local)
            thread_db = ChatDatabase(db_path_str)
            thread_aggregator = ChatAggregator(thread_db)
            
            try:
                sources_to_ingest = []
                if source == "cursor" or source == "all":
                    sources_to_ingest.append("cursor")
                if source == "claude" or source == "all":
                    sources_to_ingest.append("claude")
                
                for source_name in sources_to_ingest:
                    if source_name == "cursor":
                        stats = thread_aggregator.ingest_all(incremental=True)
                        click.echo(f"Auto-ingestion: {stats['ingested']} ingested, "
                                 f"{stats['skipped']} skipped, {stats['errors']} errors")
                    elif source_name == "claude":
                        stats = thread_aggregator.ingest_claude(incremental=True)
                        click.echo(f"Auto-ingestion: {stats['ingested']} ingested, "
                                 f"{stats['skipped']} skipped, {stats['errors']} errors")
            except Exception as e:
                click.secho(f"Error during automatic ingestion: {e}", fg='red', err=True)
            finally:
                thread_db.close()
        
        # Perform initial ingestion
        click.echo("Performing initial ingestion...")
        # Use main thread connection for initial ingestion
        sources_to_ingest = []
        if source == "cursor" or source == "all":
            sources_to_ingest.append("cursor")
        if source == "claude" or source == "all":
            sources_to_ingest.append("claude")
        
        for source_name in sources_to_ingest:
            if source_name == "cursor":
                stats = aggregator.ingest_all(incremental=True)
                click.echo(f"Initial ingestion: {stats['ingested']} ingested, "
                         f"{stats['skipped']} skipped, {stats['errors']} errors")
            elif source_name == "claude":
                stats = aggregator.ingest_claude(incremental=True)
                click.echo(f"Initial ingestion: {stats['ingested']} ingested, "
                         f"{stats['skipped']} skipped, {stats['errors']} errors")
        
        # Start watcher
        from src.services.watcher import IngestionWatcher
        
        watcher = IngestionWatcher(
            ingestion_callback=do_ingestion,
            use_watchdog=None if not use_polling else False,
            debounce_seconds=debounce,
            poll_interval=poll_interval
        )
        
        # Handle shutdown gracefully
        def signal_handler(sig, frame):
            click.echo("\nShutting down watcher...")
            watcher.stop()
            db.close()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        watcher.start()
        click.echo("Watcher started. Press Ctrl+C to stop.")
        
        # Keep running
        try:
            while watcher.is_running():
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(None, None)
        
    except Exception as e:
        click.secho(f"Error in watch mode: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()
    finally:
        db.close()


@click.command('update-modes')
@db_option
@click.pass_context
def update_modes(ctx, db_path):
    """
    Update chat modes from Cursor databases (lightweight, no re-ingest).
    
    This command reads all chats from the database, looks up their correct modes
    from Cursor's databases, and updates only the mode field if it's different.
    Much faster than a full re-ingest since it doesn't re-process messages.
    """
    # Get database from context
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    try:
        click.echo("Updating chat modes from Cursor databases...")
        
        # Get all chats from database
        all_chats = db.list_chats(limit=100000, offset=0)  # Get all chats
        click.echo(f"Found {len(all_chats)} chats in database")
        
        # Initialize readers
        workspace_reader = WorkspaceStateReader()
        global_reader = GlobalComposerReader()
        
        # Load workspace data to get composer heads
        workspaces_metadata = workspace_reader.read_all_workspaces()
        composer_heads = {}
        for workspace_hash, metadata in workspaces_metadata.items():
            composer_data = metadata.get("composer_data")
            if composer_data and isinstance(composer_data, dict):
                all_composers = composer_data.get("allComposers", [])
                for composer in all_composers:
                    composer_id = composer.get("composerId")
                    if composer_id:
                        composer_heads[composer_id] = {
                            "unifiedMode": composer.get("unifiedMode"),
                            "forceMode": composer.get("forceMode"),
                        }
        
        click.echo(f"Loaded {len(composer_heads)} composer heads from workspaces")
        
        # Mode mapping
        mode_map = {
            "chat": ChatMode.CHAT,
            "edit": ChatMode.EDIT,
            "agent": ChatMode.AGENT,
            "composer": ChatMode.COMPOSER,
            "plan": ChatMode.PLAN,
            "debug": ChatMode.DEBUG,
            "ask": ChatMode.ASK,
        }
        
        updated_count = 0
        unchanged_count = 0
        not_found_count = 0
        
        # Update each chat's mode
        for chat in all_chats:
            composer_id = chat.get("composer_id")
            current_mode = chat.get("mode", "chat")
            
            # Try to get mode from composer head first
            composer_head = composer_heads.get(composer_id)
            force_mode = None
            unified_mode = None
            
            if composer_head:
                force_mode = composer_head.get("forceMode")
                unified_mode = composer_head.get("unifiedMode")
            
            # If not in workspace head, try global database
            if not force_mode and not unified_mode:
                composer_data = global_reader.read_composer(composer_id)
                if composer_data and composer_data.get("data"):
                    data = composer_data["data"]
                    force_mode = data.get("forceMode")
                    unified_mode = data.get("unifiedMode")
            
            # Determine correct mode
            correct_mode_str = force_mode or unified_mode or "chat"
            correct_mode = mode_map.get(correct_mode_str, ChatMode.CHAT)
            
            # Update if different
            if current_mode != correct_mode.value:
                cursor = db.conn.cursor()
                cursor.execute("UPDATE chats SET mode = ? WHERE id = ?",
                             (correct_mode.value, chat["id"]))
                db.conn.commit()
                updated_count += 1
                if updated_count % 10 == 0:
                    click.echo(f"Updated {updated_count} chats...")
            else:
                unchanged_count += 1
        
        click.echo("\nMode update complete!")
        click.secho(f"  Updated: {updated_count} chats", fg='green')
        click.echo(f"  Unchanged: {unchanged_count} chats")
        click.echo(f"  Not found in Cursor: {not_found_count} chats")
        
    except Exception as e:
        click.secho(f"Error updating modes: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()
    finally:
        db.close()

