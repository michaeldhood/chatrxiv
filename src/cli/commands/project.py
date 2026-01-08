"""
Project management CLI commands.

Commands for creating, managing, and querying projects that group related workspaces.
"""
import click
from pathlib import Path
from typing import Optional

from src.cli.common import db_option


@click.group()
def project():
    """Manage projects (workspace groups)."""
    pass


@project.command('create')
@click.argument('name')
@click.option('--description', '-d', help='Project description')
@db_option
@click.pass_context
def create(ctx, name: str, description: Optional[str], db_path: Optional[Path]) -> None:
    """Create a new project.
    
    Example:
        chatrxiv project create myproject --description "My project description"
    """
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    try:
        project_id = db.create_project(name, description)
        click.secho(f"Created project '{name}' (ID: {project_id})", fg='green')
    except Exception as e:
        if 'UNIQUE constraint failed' in str(e):
            click.secho(f"Error: Project '{name}' already exists", fg='red', err=True)
        else:
            click.secho(f"Error creating project: {e}", fg='red', err=True)
        raise click.Abort()


@project.command('list')
@db_option
@click.pass_context
def list_projects(ctx, db_path: Optional[Path]) -> None:
    """List all projects."""
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    projects = db.list_projects()
    
    if not projects:
        click.echo("No projects found. Create one with: chatrxiv project create <name>")
        return
    
    click.echo(f"\nFound {len(projects)} project(s):\n")
    for proj in projects:
        click.echo(f"  {proj['id']:4d}  {proj['name']}")
        if proj['description']:
            click.echo(f"        {proj['description']}")
        click.echo(f"        Workspaces: {proj['workspace_count']}")
        click.echo()


@project.command('assign')
@click.argument('workspace_hash')
@click.argument('project_name')
@db_option
@click.pass_context
def assign(ctx, workspace_hash: str, project_name: str, db_path: Optional[Path]) -> None:
    """Assign a workspace to a project.
    
    Arguments:
        WORKSPACE_HASH: The workspace hash (or first N chars for partial match)
        PROJECT_NAME: Name of the project to assign to
        
    Example:
        chatrxiv project assign feb61fce2f6a4b75ea3bcd53bd82ae4d chatrxiv
    """
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    # Find the project
    proj = db.get_project_by_name(project_name)
    if not proj:
        click.secho(f"Error: Project '{project_name}' not found", fg='red', err=True)
        raise click.Abort()
    
    # Find workspace by hash (support partial matching)
    workspace = db.get_workspace_by_hash(workspace_hash)
    if not workspace:
        # Try partial match
        all_workspaces = db.list_workspaces()
        matches = [w for w in all_workspaces if w['workspace_hash'].startswith(workspace_hash)]
        if len(matches) == 1:
            workspace = matches[0]
        elif len(matches) > 1:
            click.secho(f"Error: Multiple workspaces match '{workspace_hash}':", fg='red', err=True)
            for w in matches:
                click.echo(f"  {w['workspace_hash']}  {w['resolved_path'] or 'Unknown'}")
            raise click.Abort()
        else:
            click.secho(f"Error: No workspace found matching '{workspace_hash}'", fg='red', err=True)
            raise click.Abort()
    
    # Assign workspace to project
    db.assign_workspace_to_project(workspace['id'], proj['id'])
    click.secho(
        f"Assigned workspace {workspace['workspace_hash'][:12]}... to project '{project_name}'", 
        fg='green'
    )
    if workspace['resolved_path']:
        click.echo(f"  Path: {workspace['resolved_path']}")


@project.command('workspaces')
@click.argument('project_name')
@db_option
@click.pass_context
def workspaces(ctx, project_name: str, db_path: Optional[Path]) -> None:
    """List workspaces in a project.
    
    Example:
        chatrxiv project workspaces chatrxiv
    """
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    # Find the project
    proj = db.get_project_by_name(project_name)
    if not proj:
        click.secho(f"Error: Project '{project_name}' not found", fg='red', err=True)
        raise click.Abort()
    
    # Get workspaces
    ws_list = db.get_workspaces_by_project(proj['id'])
    
    if not ws_list:
        click.echo(f"No workspaces in project '{project_name}'")
        click.echo("Use 'chatrxiv project assign <hash> <project>' to add workspaces")
        return
    
    click.echo(f"\nWorkspaces in project '{project_name}':\n")
    for ws in ws_list:
        click.echo(f"  {ws['workspace_hash'][:12]}...")
        if ws['resolved_path']:
            click.echo(f"    Path: {ws['resolved_path']}")
        click.echo()


@project.command('delete')
@click.argument('project_name')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation prompt')
@db_option
@click.pass_context
def delete(ctx, project_name: str, force: bool, db_path: Optional[Path]) -> None:
    """Delete a project (workspaces are kept but unlinked).
    
    Example:
        chatrxiv project delete myproject --force
    """
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    # Find the project
    proj = db.get_project_by_name(project_name)
    if not proj:
        click.secho(f"Error: Project '{project_name}' not found", fg='red', err=True)
        raise click.Abort()
    
    # Get workspace count
    ws_list = db.get_workspaces_by_project(proj['id'])
    ws_count = len(ws_list)
    
    if not force:
        msg = f"Delete project '{project_name}'"
        if ws_count > 0:
            msg += f" and unlink {ws_count} workspace(s)"
        msg += "?"
        if not click.confirm(msg):
            click.echo("Cancelled")
            return
    
    # Delete project
    if db.delete_project(proj['id']):
        click.secho(f"Deleted project '{project_name}'", fg='green')
        if ws_count > 0:
            click.echo(f"  {ws_count} workspace(s) unlinked")
    else:
        click.secho(f"Error: Failed to delete project", fg='red', err=True)
        raise click.Abort()


@project.command('show')
@click.argument('project_name')
@db_option
@click.pass_context
def show(ctx, project_name: str, db_path: Optional[Path]) -> None:
    """Show details of a project.
    
    Example:
        chatrxiv project show chatrxiv
    """
    if db_path:
        ctx.obj.db_path = db_path
    
    db = ctx.obj.get_db()
    
    # Find the project
    proj = db.get_project_by_name(project_name)
    if not proj:
        click.secho(f"Error: Project '{project_name}' not found", fg='red', err=True)
        raise click.Abort()
    
    # Get workspaces
    ws_list = db.get_workspaces_by_project(proj['id'])
    
    # Count chats in project
    chat_count = db.count_chats(project_id=proj['id'])
    
    click.echo(f"\nProject: {proj['name']}")
    click.echo(f"  ID: {proj['id']}")
    if proj['description']:
        click.echo(f"  Description: {proj['description']}")
    click.echo(f"  Created: {proj['created_at']}")
    click.echo(f"  Workspaces: {len(ws_list)}")
    click.echo(f"  Total Chats: {chat_count}")
    
    if ws_list:
        click.echo("\n  Workspace Paths:")
        for ws in ws_list:
            path = ws['resolved_path'] or f"({ws['workspace_hash'][:12]}...)"
            click.echo(f"    - {path}")
