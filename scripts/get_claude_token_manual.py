#!/usr/bin/env python3
"""
Manually extract Claude.ai session token without external dependencies.

This version only works with Firefox (unencrypted cookies) to avoid
needing external libraries for decryption.
"""

import sqlite3
import sys
from pathlib import Path
import shutil
import tempfile


def find_firefox_profile():
    """
    Find Firefox profile directory.
    
    Returns
    ----
    Path or None
        Path to Firefox profile directory
    """
    if sys.platform == 'darwin':  # macOS
        firefox_dir = Path.home() / 'Library/Application Support/Firefox/Profiles'
    elif sys.platform == 'win32':  # Windows
        firefox_dir = Path.home() / 'AppData/Roaming/Mozilla/Firefox/Profiles'
    else:  # Linux
        firefox_dir = Path.home() / '.mozilla/firefox'
    
    if not firefox_dir.exists():
        return None
    
    # Find default profile (usually ends with .default or .default-release)
    for profile in firefox_dir.iterdir():
        if profile.is_dir() and ('default' in profile.name.lower()):
            return profile
    
    return None


def extract_claude_token_firefox():
    """
    Extract Claude.ai sessionKey from Firefox cookies.
    
    Firefox doesn't encrypt cookies, making this simpler than Chrome.
    
    Returns
    ----
    str or None
        Session key if found, None otherwise
    """
    profile = find_firefox_profile()
    if not profile:
        print("Firefox profile not found", file=sys.stderr)
        return None
    
    cookies_db = profile / 'cookies.sqlite'
    if not cookies_db.exists():
        print(f"Firefox cookies database not found at: {cookies_db}", file=sys.stderr)
        return None
    
    # Copy to temp (Firefox may lock the file)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite') as tmp:
        tmp_path = tmp.name
        shutil.copy2(cookies_db, tmp_path)
    
    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # Firefox schema: moz_cookies table
        cursor.execute("""
            SELECT name, value, host 
            FROM moz_cookies 
            WHERE host LIKE '%claude.ai%' 
            AND name = 'sessionKey'
        """)
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            name, value, host = result
            print(f"✓ Found {name} cookie for {host}", file=sys.stderr)
            return value
        
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main():
    """Main entry point."""
    print("Extracting Claude.ai token from Firefox (no external deps)...\n", file=sys.stderr)
    
    token = extract_claude_token_firefox()
    
    if token:
        print("\n" + "="*60, file=sys.stderr)
        print("SUCCESS! Found session key:", file=sys.stderr)
        print("="*60 + "\n", file=sys.stderr)
        
        # Output to stdout
        print(token)
        
        print(f"\nTo set as environment variable:", file=sys.stderr)
        print(f"export CLAUDE_SESSION_KEY='{token}'", file=sys.stderr)
        
        return 0
    else:
        print("\n" + "="*60, file=sys.stderr)
        print("ERROR: Session key not found", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print("\nThis script only works with Firefox.", file=sys.stderr)
        print("For Chrome support, use browser-cookie3 library.", file=sys.stderr)
        print("\nEnsure you are logged into claude.ai in Firefox.", file=sys.stderr)
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
