"""
Miscellaneous CLI commands (info, list, view, export-composer, batch).

Simple utility commands for inspecting the Cursor installation and
browsing exported chat files.
"""
import json
from datetime import datetime
from pathlib import Path

import click
import sys

from src.core.config import get_cursor_workspace_storage_path
from src.viewer import list_chat_files, find_chat_file, display_chat_file
from src.cli.common import output_dir_option, format_option, db_option
from src.cli.orchestrators.batch import BatchOrchestrator


@click.command()
@click.option('--db-path', type=click.Path(), help='Path to database file', envvar='CHATRXIV_DB')
@click.pass_context
def info(ctx, db_path):
    """Show information about Cursor installation and database stats."""
    from src.core.db import ChatDatabase
    from src.core.config import get_default_db_path
    
    cursor_path = str(get_cursor_workspace_storage_path())
    click.echo(f"Cursor chat path: {cursor_path}")
    click.echo(f"Python: {sys.version}")
    click.echo(f"Platform: {sys.platform}")
    
    # Show database stats if database exists
    db_file = Path(db_path) if db_path else get_default_db_path()
    if db_file.exists():
        click.echo(f"\nDatabase: {db_file}")
        click.echo(f"  Size: {db_file.stat().st_size / 1024:.1f} KB")
        
        try:
            db = ChatDatabase(str(db_file))
            
            # Chat counts
            total_chats = db.count_chats()
            non_empty = db.count_chats(empty_filter='non_empty')
            empty = db.count_chats(empty_filter='empty')
            
            click.echo(f"\nChat Statistics:")
            click.echo(f"  Total chats: {total_chats}")
            click.echo(f"  With messages: {non_empty}")
            click.echo(f"  Empty: {empty}")
            
            # Workspace count
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM workspaces")
            workspace_count = cursor.fetchone()[0]
            click.echo(f"  Workspaces: {workspace_count}")
            
            # Tag stats
            tags = db.get_all_tags()
            if tags:
                click.echo(f"  Tags: {len(tags)} unique tags")
            
            # Last updated
            last_updated = db.get_last_updated_at()
            if last_updated:
                click.echo(f"\n  Last updated: {last_updated}")
            
            db.close()
            
        except Exception as e:
            click.secho(f"  Error reading database: {e}", fg='yellow')
    else:
        click.echo(f"\nDatabase: {db_file} (not found)")
        click.echo("  Run 'python -m src ingest' to create and populate the database.")


@click.command()
@click.option(
    '--directories',
    multiple=True,
    help='Directories to search (default: ., chat_exports, markdown_chats)'
)
def list(directories):
    """List available chat files."""
    # Convert tuple to list (or None if empty)
    dirs = list(directories) if directories else None
    chat_groups = list_chat_files(dirs)

    if not chat_groups:
        raise click.Abort()


@click.command()
@click.argument('file')
def view(file):
    """View a chat file."""
    filepath = find_chat_file(file)
    if filepath:
        if not display_chat_file(filepath):
            raise click.Abort()
    else:
        click.secho(f"File not found: {file}", fg='red', err=True)
        click.echo("\nAvailable files:")
        list_chat_files()
        raise click.Abort()


@click.command('export-composer')
@click.argument('composer_id')
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file path (default: composer_{id}.json)'
)
@click.option(
    '--include-workspace',
    is_flag=True,
    help='Include workspace metadata if available'
)
def export_composer(composer_id, output, include_workspace):
    """Export raw composer data from Cursor database to JSON."""
    click.echo(f"Exporting composer {composer_id}...")
    
    try:
        from src.readers.global_reader import GlobalComposerReader
        from src.readers.workspace_reader import WorkspaceStateReader
        
        # Read composer data from global database
        global_reader = GlobalComposerReader()
        composer_info = global_reader.read_composer(composer_id)
        
        if not composer_info:
            click.secho(f"Composer {composer_id} not found in global database", fg='red', err=True)
            raise click.Abort()
        
        composer_data = composer_info["data"]
        
        # Resolve conversation bubbles if using headers-only format
        conversation = composer_data.get("conversation", [])
        if not conversation:
            headers = composer_data.get("fullConversationHeadersOnly", [])
            if headers:
                click.echo("Resolving conversation bubbles from headers...")
                from src.services.aggregator import ChatAggregator
                from src.core.db import ChatDatabase
                # Create a temporary aggregator just to use the resolution method
                temp_db = ChatDatabase(":memory:")  # In-memory DB just for method access
                temp_aggregator = ChatAggregator(temp_db)
                conversation = temp_aggregator._resolve_conversation_from_headers(composer_id, headers)
                temp_db.close()
                # Add resolved conversation to export data
                composer_data = composer_data.copy()
                composer_data["conversation_resolved"] = conversation
                click.echo(f"Resolved {len(conversation)} conversation bubbles")
        
        export_data = {
            "composer_id": composer_id,
            "source": "cursor_global_database",
            "exported_at": datetime.now().isoformat(),
            "composer_data": composer_data,
        }
        
        # Optionally include workspace metadata
        if include_workspace:
            click.echo("Looking up workspace metadata...")
            workspace_reader = WorkspaceStateReader()
            workspaces = workspace_reader.read_all_workspaces()
            
            workspace_info = None
            for workspace_hash, metadata in workspaces.items():
                composer_data = metadata.get("composer_data")
                if composer_data and isinstance(composer_data, dict):
                    all_composers = composer_data.get("allComposers", [])
                    for composer in all_composers:
                        if composer.get("composerId") == composer_id:
                            workspace_info = {
                                "workspace_hash": workspace_hash,
                                "workspace_metadata": {
                                    "project_path": metadata.get("project_path"),
                                    "composer_head": {
                                        "name": composer.get("name"),
                                        "subtitle": composer.get("subtitle"),
                                        "createdAt": composer.get("createdAt"),
                                        "lastUpdatedAt": composer.get("lastUpdatedAt"),
                                        "unifiedMode": composer.get("unifiedMode"),
                                        "forceMode": composer.get("forceMode"),
                                    }
                                }
                            }
                            break
                    if workspace_info:
                        break
            
            if workspace_info:
                export_data["workspace_info"] = workspace_info
                click.echo(f"Found workspace metadata for workspace {workspace_info['workspace_hash']}")
            else:
                click.echo("No workspace metadata found for this composer")
        
        # Determine output file
        if output:
            output_path = Path(output)
        else:
            output_path = Path(f"composer_{composer_id}.json")
        
        # Write JSON file with pretty formatting
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        click.secho(f"Exported composer to {output_path}", fg='green')
        click.echo(f"  File size: {output_path.stat().st_size} bytes")
        
        # Print summary
        final_composer_data = export_data["composer_data"]
        click.echo("\nComposer Summary:")
        click.echo(f"  ID: {composer_id}")
        click.echo(f"  Name: {final_composer_data.get('name') or final_composer_data.get('subtitle') or 'Untitled'}")
        click.echo(f"  Created: {final_composer_data.get('createdAt')}")
        click.echo(f"  Updated: {final_composer_data.get('lastUpdatedAt')}")
        
    except Exception as e:
        click.secho(f"Error exporting composer: {e}", fg='red', err=True)
        if click.get_current_context().obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()


@click.command()
@click.option(
    '--extract',
    is_flag=True,
    help='Extract chat data'
)
@click.option(
    '--convert',
    is_flag=True,
    help='Convert to specified format'
)
@click.option(
    '--tag',
    is_flag=True,
    help='Auto-tag extracted chats (requires database)'
)
@format_option(['csv', 'markdown'], default='markdown')
@output_dir_option(default='chat_exports')
@db_option
@click.pass_context
def batch(ctx, extract, convert, tag, format, output_dir, db_path):
    """
    Batch operations: extract, convert, and tag.
    
    Combines multiple operations for processing chat data. If no flags are
    specified, all operations (extract, convert, tag) are performed.
    
    Note: Tagging requires a database. JSON files will be imported to the
    database before tagging.
    """
    # Get database from context if tagging is requested
    db = None
    if tag:
        if db_path:
            ctx.obj.db_path = db_path
        db = ctx.obj.get_db()

    try:
        orchestrator = BatchOrchestrator(db=db)
        
        click.echo("=== Starting batch operations ===")
        
        stats = orchestrator.run_batch(
            extract=extract,
            convert=convert,
            tag=tag,
            format=format,
            output_dir=str(output_dir),
        )
        
        # Display results
        if stats['extracted_files']:
            click.echo(f"\nExtracted {len(stats['extracted_files'])} files")
        
        if stats['converted_count'] > 0:
            click.secho(f"Converted {stats['converted_count']} files", fg='green')
        
        if stats['tagged_count'] > 0:
            click.secho(f"Tagged {stats['tagged_count']} chats", fg='green')
        
        if stats['errors']:
            for error in stats['errors']:
                click.secho(f"Error: {error}", fg='yellow', err=True)
            if len(stats['errors']) == len(stats.get('extracted_files', [])):
                raise click.Abort()
        
        click.secho("\n=== Batch operation completed ===", fg='green')
        
    except Exception as e:
        click.secho(f"Error during batch operation: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()
