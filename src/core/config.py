"""
Configuration and path resolution for chatrxiv.

Centralizes OS-specific path logic for Cursor data directories and default database location.
"""
import os
import platform
from pathlib import Path


def get_cursor_workspace_storage_path() -> Path:
    """
    Get the path to Cursor workspace storage directory.
    
    Returns
    ----
    Path
        Path to workspaceStorage directory
        
    Raises
    ---
    OSError
        If running on unsupported OS
    """
    system = platform.system()
    home = Path.home()
    
    if system == 'Darwin':  # macOS
        return home / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage"
    elif system == 'Windows':
        return Path(home) / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
    elif system == 'Linux':
        # Check for WSL
        if os.path.exists('/proc/version'):
            with open('/proc/version', 'r') as f:
                if 'microsoft' in f.read().lower():
                    # WSL - get Windows path
                    windows_home = os.popen('cd /mnt/c && cmd.exe /c echo %USERPROFILE%').read().strip()
                    windows_path = Path(windows_home) / "AppData" / "Roaming" / "Cursor" / "User" / "workspaceStorage"
                    wsl_path = os.popen(f'wslpath "{windows_path}"').read().strip()
                    return Path(wsl_path)
        # Native Linux
        return home / ".config" / "Cursor" / "User" / "workspaceStorage"
    else:
        raise OSError(f"Unsupported operating system: {system}")


def get_cursor_global_storage_path() -> Path:
    """
    Get the path to Cursor global storage directory.

    Returns
    ----
    Path
        Path to globalStorage directory
        
    Raises
    ---
    OSError
        If running on unsupported OS
    """
    home = Path.home()
    system = platform.system()

    if system == "Darwin":  # macOS
        return (
            home
            / "Library"
            / "Application Support"
            / "Cursor"
            / "User"
            / "globalStorage"
        )
    elif system == "Windows":
        return Path(home) / "AppData" / "Roaming" / "Cursor" / "User" / "globalStorage"
    elif system == "Linux":
        return home / ".config" / "Cursor" / "User" / "globalStorage"
    else:
        raise OSError(f"Unsupported operating system: {system}")


def get_claude_code_projects_path() -> Path:
    """
    Get the path to Claude Code projects directory.

    Returns
    ----
    Path
        Path to ~/.claude/projects/
    """
    return Path.home() / ".claude" / "projects"


def get_default_db_path() -> Path:
    """
    Get the default database path based on OS.
    
    Returns
    ----
    Path
        Default path to chats.db
    """
    system = platform.system()
    home = Path.home()
    
    if system == 'Darwin':  # macOS
        base_dir = home / "Library" / "Application Support" / "chatrxiv"
    elif system == 'Windows':
        base_dir = home / "AppData" / "Roaming" / "chatrxiv"
    elif system == 'Linux':
        base_dir = home / ".local" / "share" / "chatrxiv"
    else:
        base_dir = home / ".chatrxiv"
    
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "chats.db"

