#!/usr/bin/env python3
"""
Extract Claude.ai session token from browser cookies.

This script attempts to read the sessionKey cookie from your browser's
cookie storage. Works with Chrome, Firefox, and Safari.
"""

import sys
from pathlib import Path


def get_claude_session_key_browser_cookie3():
    """
    Extract Claude.ai sessionKey using browser_cookie3 library.
    
    Returns
    ----
    str or None
        Session key if found, None otherwise
    """
    try:
        import browser_cookie3
    except ImportError:
        print("Error: browser_cookie3 not installed. Install with: pip install browser-cookie3", file=sys.stderr)
        return None
    
    browsers = [
        ('Chrome', browser_cookie3.chrome),
        ('Firefox', browser_cookie3.firefox),
        ('Safari', browser_cookie3.safari),
        ('Edge', browser_cookie3.edge),
    ]
    
    for browser_name, browser_func in browsers:
        try:
            print(f"Trying {browser_name}...", file=sys.stderr)
            cj = browser_func(domain_name='claude.ai')
            for cookie in cj:
                if cookie.name == 'sessionKey':
                    print(f"✓ Found sessionKey in {browser_name}", file=sys.stderr)
                    return cookie.value
        except Exception as e:
            print(f"  {browser_name}: {e}", file=sys.stderr)
            continue
    
    return None


def get_claude_session_key_manual_chrome():
    """
    Manually extract sessionKey from Chrome's SQLite cookies database.
    
    This is a fallback if browser_cookie3 doesn't work.
    
    Returns
    ----
    str or None
        Session key if found, None otherwise
    """
    import sqlite3
    import shutil
    import tempfile
    from pathlib import Path
    
    # Chrome cookie database locations
    if sys.platform == 'darwin':  # macOS
        cookie_path = Path.home() / 'Library/Application Support/Google/Chrome/Default/Cookies'
    elif sys.platform == 'win32':  # Windows
        cookie_path = Path.home() / 'AppData/Local/Google/Chrome/User Data/Default/Network/Cookies'
    else:  # Linux
        cookie_path = Path.home() / '.config/google-chrome/Default/Cookies'
    
    if not cookie_path.exists():
        print(f"Chrome cookies not found at: {cookie_path}", file=sys.stderr)
        return None
    
    # Copy to temp file (Chrome locks the database)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp:
        tmp_path = tmp.name
        shutil.copy2(cookie_path, tmp_path)
    
    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # Query for Claude.ai sessionKey cookie
        cursor.execute(
            "SELECT value FROM cookies WHERE host_key LIKE '%claude.ai' AND name = 'sessionKey'"
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # Note: Chrome encrypts cookie values on some systems
            # If you get encrypted data, you'll need to decrypt it (OS-specific)
            return result[0]
        
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main():
    """Main entry point."""
    print("Searching for Claude.ai session token...\n", file=sys.stderr)
    
    # Try browser_cookie3 first (easiest)
    session_key = get_claude_session_key_browser_cookie3()
    
    # Fallback to manual Chrome extraction
    if not session_key:
        print("\nTrying manual Chrome extraction...", file=sys.stderr)
        session_key = get_claude_session_key_manual_chrome()
    
    if session_key:
        print("\n" + "="*60, file=sys.stderr)
        print("SUCCESS! Found session key:", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        
        # Output just the key to stdout (so it can be captured)
        print(session_key)
        
        print(f"\nTo set as environment variable:", file=sys.stderr)
        print(f"export CLAUDE_SESSION_KEY='{session_key}'", file=sys.stderr)
        
        return 0
    else:
        print("\n" + "="*60, file=sys.stderr)
        print("ERROR: Session key not found", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print("\nPlease ensure:", file=sys.stderr)
        print("1. You are logged into claude.ai in your browser", file=sys.stderr)
        print("2. Your browser is supported (Chrome, Firefox, Safari, Edge)", file=sys.stderr)
        print("3. browser_cookie3 is installed: pip install browser-cookie3", file=sys.stderr)
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
