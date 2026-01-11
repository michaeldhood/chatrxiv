"""
Modern Click-based CLI for chatrxiv.

This module provides the main Click group and entry point for the refactored CLI.
Commands are organized in the commands/ subpackage.
"""
import click
import logging
import sys

from .context import CLIContext

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """
    chatrxiv - Tools for working with Cursor AI chat logs.

    This CLI provides commands for extracting, converting, searching, and managing
    chat data from the Cursor AI editor.
    """
    # Create context and store in Click's context object
    ctx.obj = CLIContext(verbose=verbose)

    # Configure logging level based on verbosity
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.result_callback()
@click.pass_context
def cleanup(ctx, result, **kwargs):
    """
    Clean up resources after command execution.

    This callback is called after every command completes (or fails).
    Ensures database connections are properly closed, which is critical
    for WAL mode to checkpoint the write-ahead log.
    """
    if ctx.obj:
        ctx.obj.close()


# Import and register command groups here as they're migrated
# Phase 2: Simple commands (info, list, view)
from .commands.misc import info, list, view, export_composer, batch, load_activity, visualize, estimate_costs

cli.add_command(info)
cli.add_command(list)
cli.add_command(view)
cli.add_command(export_composer)
cli.add_command(batch)
cli.add_command(load_activity)
cli.add_command(visualize)
cli.add_command(estimate_costs)

# Phase 3: Extract/convert commands
from .commands.extract import extract, convert

cli.add_command(extract)
cli.add_command(convert)

# Phase 4: Database commands
from .commands.database import ingest, import_legacy, import_chatgpt, search, export, rebuild_index, cleanup

cli.add_command(ingest)
cli.add_command(import_legacy)
cli.add_command(import_chatgpt)
cli.add_command(search)
cli.add_command(export)
cli.add_command(rebuild_index)
cli.add_command(cleanup)

# Tag commands
from .commands.tag import tag
cli.add_command(tag)

# Project commands
from .commands.project import project
cli.add_command(project)

# Phase 7a: Journal commands
from .commands.journal import journal
cli.add_command(journal)

# Phase 7c: Web command
from .commands.web import web
cli.add_command(web)

# Phase 6: Watch commands
from .commands.watch import watch, update_modes
cli.add_command(watch)
cli.add_command(update_modes)


def main():
    """
    Main entry point for the CLI.

    Used by __main__.py when USE_NEW_CLI environment variable is set.
    """
    try:
        cli()
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
