"""
GitHub activity CLI commands.

Commands for discovering repositories, ingesting commits/PRs,
and cross-referencing chats with GitHub activity.
"""
import click
from pathlib import Path
from datetime import datetime

from src.cli.common import db_option


@click.group()
def github():
    """GitHub activity integration commands.
    
    Discover repositories, ingest commits/PRs, and link them to chats.
    
    Examples:
    
        # Discover repos from workspaces
        python -m src github discover
        
        # Add a specific repository
        python -m src github add owner/repo
        
        # Ingest commits from all repos
        python -m src github ingest --commits
        
        # Ingest PRs
        python -m src github ingest --prs --state merged
        
        # Link chats to GitHub activity
        python -m src github link
        
        # Show activity for a chat
        python -m src github show --chat-id 123
        
        # Show summary
        python -m src github summary
    """
    pass


@github.command()
@db_option
@click.pass_context
def discover(ctx, db_path):
    """Discover GitHub repositories from workspace paths.
    
    Scans all workspaces for .git directories and maps them to GitHub repos.
    """
    from src.services.github_aggregator import GitHubAggregator
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        aggregator = GitHubAggregator(db)
        
        def progress(path, total, current):
            if current % 10 == 0 or current == total:
                click.echo(f"  [{current}/{total}] Checking: {path}")
        
        click.echo("Discovering GitHub repositories from workspaces...\n")
        stats = aggregator.discover_repositories(progress_callback=progress)
        
        click.echo()
        click.secho(f"Discovery complete!", fg='green')
        click.echo(f"  Discovered: {stats['discovered']} new repos")
        click.echo(f"  Updated: {stats['updated']} existing repos")
        click.echo(f"  Skipped: {stats['skipped']} (no git repo)")
        if stats['errors']:
            click.secho(f"  Errors: {stats['errors']}", fg='yellow')
            
    except RuntimeError as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        click.echo("\nMake sure gh CLI is installed and authenticated:", err=True)
        click.echo("  https://cli.github.com/", err=True)
        raise click.Abort()
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()


@github.command()
@click.argument('repo')
@click.option(
    '--workspace-id',
    type=int,
    help='Link to specific workspace ID'
)
@db_option
@click.pass_context
def add(ctx, repo, workspace_id, db_path):
    """Add a GitHub repository manually.
    
    REPO should be in owner/repo format (e.g., anthropics/claude-code).
    """
    from src.services.github_aggregator import GitHubAggregator
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        aggregator = GitHubAggregator(db)
        
        click.echo(f"Adding repository: {repo}")
        repo_id = aggregator.add_repository(repo, workspace_id)
        
        if repo_id:
            click.secho(f"Added repository (id={repo_id})", fg='green')
        else:
            click.secho("Failed to add repository", fg='red')
            raise click.Abort()
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()


@github.command()
@click.option('--commits', is_flag=True, help='Ingest commits')
@click.option('--prs', is_flag=True, help='Ingest pull requests')
@click.option('--all', 'ingest_all', is_flag=True, help='Ingest both commits and PRs')
@click.option(
    '--repo-id',
    type=int,
    help='Limit to specific repository ID'
)
@click.option(
    '--since',
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help='Only commits after this date (YYYY-MM-DD)'
)
@click.option(
    '--state',
    type=click.Choice(['open', 'closed', 'merged', 'all']),
    default='all',
    help='PR state filter'
)
@click.option(
    '--limit',
    type=int,
    default=100,
    help='Maximum items per repository'
)
@click.option(
    '--no-details',
    is_flag=True,
    help='Skip fetching file-level commit details (faster)'
)
@db_option
@click.pass_context
def ingest(ctx, commits, prs, ingest_all, repo_id, since, state, limit, no_details, db_path):
    """Ingest commits and/or PRs from GitHub.
    
    Examples:
    
        # Ingest everything
        python -m src github ingest --all
        
        # Just commits since January
        python -m src github ingest --commits --since 2024-01-01
        
        # Just merged PRs
        python -m src github ingest --prs --state merged
    """
    from src.services.github_aggregator import GitHubAggregator
    
    if not (commits or prs or ingest_all):
        click.echo("Specify --commits, --prs, or --all")
        raise click.Abort()
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        aggregator = GitHubAggregator(db)
        
        def progress(item, total, current):
            if current % 20 == 0 or current == total:
                click.echo(f"  [{current}/{total}] {item}")
        
        if commits or ingest_all:
            click.echo("\nIngesting commits...")
            stats = aggregator.ingest_commits(
                repo_id=repo_id,
                since=since,
                limit=limit,
                fetch_details=not no_details,
                progress_callback=progress
            )
            click.secho(f"  Commits: {stats['ingested']} ingested, {stats['skipped']} skipped", fg='green')
        
        if prs or ingest_all:
            click.echo("\nIngesting pull requests...")
            stats = aggregator.ingest_pull_requests(
                repo_id=repo_id,
                state=state,
                limit=limit,
                progress_callback=progress
            )
            click.secho(f"  PRs: {stats['ingested']} ingested, {stats['updated']} updated", fg='green')
        
        click.secho("\nIngestion complete!", fg='green')
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        if ctx.obj.verbose:
            import traceback
            click.echo(traceback.format_exc(), err=True)
        raise click.Abort()


@github.command()
@click.option(
    '--chat-id',
    type=int,
    help='Link specific chat (otherwise links all)'
)
@click.option(
    '--workspace-id',
    type=int,
    help='Limit to specific workspace'
)
@click.option(
    '--window',
    type=int,
    default=24,
    help='Time window in hours for temporal linking (default: 24)'
)
@db_option
@click.pass_context
def link(ctx, chat_id, workspace_id, window, db_path):
    """Link chats to GitHub activity.
    
    Creates cross-references between chats and commits/PRs based on:
    - Temporal proximity (activity within time window of chat)
    - File overlap (same files mentioned in chat and changed in commits)
    """
    from src.services.github_aggregator import GitHubAggregator
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        aggregator = GitHubAggregator(db)
        
        if chat_id:
            click.echo(f"Linking chat {chat_id} to GitHub activity...")
            stats = aggregator.link_chat_to_activity(
                chat_id,
                time_window_hours=window
            )
            click.secho(f"Created {stats['commit_links']} commit links, {stats['pr_links']} PR links", fg='green')
        else:
            def progress(title, total, current):
                if current % 50 == 0 or current == total:
                    click.echo(f"  [{current}/{total}] {title[:50]}...")
            
            click.echo("Linking all chats to GitHub activity...")
            stats = aggregator.link_all_chats(
                workspace_id=workspace_id,
                time_window_hours=window,
                progress_callback=progress
            )
            click.echo()
            click.secho(f"Linking complete!", fg='green')
            click.echo(f"  Chats processed: {stats['chats_processed']}")
            click.echo(f"  Commit links: {stats['commit_links']}")
            click.echo(f"  PR links: {stats['pr_links']}")
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()


@github.command()
@click.option(
    '--chat-id',
    type=int,
    required=True,
    help='Chat ID to show activity for'
)
@db_option
@click.pass_context
def show(ctx, chat_id, db_path):
    """Show GitHub activity linked to a chat."""
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        # Get chat info
        chat = db.get_chat(chat_id)
        if not chat:
            click.secho(f"Chat {chat_id} not found", fg='red')
            raise click.Abort()
        
        click.echo(f"\nChat: {chat['title']}")
        click.echo(f"  Created: {chat['created_at']}")
        click.echo(f"  Messages: {chat['messages_count']}")
        
        # Get linked activity
        activity = db.get_activity_for_chat(chat_id)
        
        if not activity:
            click.echo("\nNo linked GitHub activity found.")
            click.echo("Run 'python -m src github link' to create links.")
            return
        
        click.echo(f"\nLinked GitHub Activity ({len(activity)} items):\n")
        
        for item in activity:
            if item['activity_type'] == 'commit':
                click.echo(f"  📝 Commit: {item['short_sha']} - {item['message'][:60]}...")
                click.echo(f"     Author: {item['author_login']}, Date: {item['authored_at']}")
                click.echo(f"     +{item['additions']}/-{item['deletions']}")
            else:
                click.echo(f"  🔀 PR #{item['number']}: {item['title'][:60]}...")
                click.echo(f"     Author: {item['author_login']}, State: {item['state']}")
                click.echo(f"     Branch: {item['head_branch']}")
            
            click.echo(f"     Link: {item['link_type']} (confidence: {item['confidence']:.2f})")
            click.echo()
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()


@github.command()
@db_option
@click.pass_context
def repos(ctx, db_path):
    """List discovered GitHub repositories."""
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    repos = db.list_repositories()
    
    if not repos:
        click.echo("No repositories found.")
        click.echo("Run 'python -m src github discover' to find repos from workspaces.")
        return
    
    click.echo(f"\nFound {len(repos)} repositories:\n")
    
    for repo in repos:
        click.echo(f"  [{repo['id']}] {repo['full_name']}")
        click.echo(f"      Branch: {repo['default_branch']}")
        if repo['workspace_path']:
            click.echo(f"      Path: {repo['workspace_path']}")
        if repo['last_synced_at']:
            click.echo(f"      Last sync: {repo['last_synced_at']}")
        
        # Get counts
        commits = db.count_commits(repo['id'])
        prs = db.count_pull_requests(repo['id'])
        click.echo(f"      Activity: {commits} commits, {prs} PRs")
        click.echo()


@github.command()
@click.option(
    '--workspace-id',
    type=int,
    help='Limit to specific workspace'
)
@click.option(
    '--limit',
    type=int,
    default=30,
    help='Maximum items to show'
)
@db_option
@click.pass_context
def timeline(ctx, workspace_id, limit, db_path):
    """Show interleaved timeline of chats and GitHub activity."""
    from src.services.github_aggregator import GitHubAggregator
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    if not workspace_id:
        # Get first workspace with a repo
        repos = db.list_repositories()
        if repos:
            workspace_id = repos[0].get('workspace_id')
    
    if not workspace_id:
        click.echo("No workspace found. Specify --workspace-id or run 'github discover' first.")
        return
    
    try:
        aggregator = GitHubAggregator(db)
        timeline_items = aggregator.get_activity_timeline(workspace_id, limit=limit)
        
        if not timeline_items:
            click.echo("No activity found for this workspace.")
            return
        
        click.echo(f"\nTimeline ({len(timeline_items)} items):\n")
        
        for item in timeline_items:
            ts = item.get('timestamp', '')[:19] if item.get('timestamp') else 'Unknown'
            
            if item['type'] == 'chat':
                click.secho(f"  💬 {ts} - Chat: {item['title'][:50]}...", fg='cyan')
                click.echo(f"     Mode: {item['mode']}, Messages: {item['messages_count']}")
            elif item['type'] == 'commit':
                click.secho(f"  📝 {ts} - Commit: {item['sha']} - {item['title'][:40]}...", fg='green')
                click.echo(f"     By: {item['author']}, +{item['additions']}/-{item['deletions']}")
            elif item['type'] == 'pr':
                state_color = 'green' if item['state'] == 'merged' else 'yellow'
                click.secho(f"  🔀 {ts} - PR #{item['number']}: {item['title'][:40]}...", fg=state_color)
                click.echo(f"     By: {item['author']}, State: {item['state']}")
            
            click.echo()
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()


@github.command()
@db_option
@click.pass_context
def summary(ctx, db_path):
    """Show GitHub integration summary statistics."""
    from src.services.github_aggregator import GitHubAggregator
    
    if db_path:
        ctx.obj.db_path = Path(db_path)
    
    db = ctx.obj.get_db()
    
    try:
        aggregator = GitHubAggregator(db)
        stats = aggregator.get_summary()
        
        click.echo("\nGitHub Integration Summary:")
        click.echo(f"  Repositories: {stats['repositories']}")
        click.echo(f"  Commits: {stats['commits']}")
        click.echo(f"  Pull Requests: {stats['pull_requests']}")
        click.echo(f"\nCross-Reference Links:")
        click.echo(f"  Chat → Commit: {stats['commit_links']}")
        click.echo(f"  Chat → PR: {stats['pr_links']}")
        
        total_chats = db.count_chats()
        if stats['commit_links'] or stats['pr_links']:
            click.echo(f"\n  {total_chats} total chats in database")
            
    except Exception as e:
        click.secho(f"Error: {e}", fg='red', err=True)
        raise click.Abort()
