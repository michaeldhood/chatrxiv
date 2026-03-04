"""
chrome_cookies.py - Lightweight Chrome cookie extractor

Extracts cookies from Google Chrome's local SQLite database and returns
them as a standard http.cookiejar.CookieJar for use with requests, urllib, etc.

Supports: macOS, Linux, Windows (v10 encryption)
License: MIT

Usage:
    import chrome_cookies
    import requests

    # All cookies
    jar = chrome_cookies.load()

    # Filtered by domain
    jar = chrome_cookies.load(domain_name=".github.com")

    # Use with requests
    r = requests.get("https://github.com", cookies=jar)
"""

import base64
import http.cookiejar
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

SYSTEM = platform.system()  # 'Darwin', 'Linux', 'Windows'


def _get_default_cookie_db_path() -> Path:
    """Return the default Chrome Cookies SQLite path for this OS."""
    if SYSTEM == "Darwin":
        return Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"
    elif SYSTEM == "Linux":
        return Path.home() / ".config/google-chrome/Default/Cookies"
    elif SYSTEM == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        return Path(local) / "Google/Chrome/User Data/Default/Network/Cookies"
    else:
        raise OSError(f"Unsupported platform: {SYSTEM}")


# ---------------------------------------------------------------------------
# Key retrieval (platform-specific)
# ---------------------------------------------------------------------------

def _get_key_darwin() -> bytes:
    """
    macOS: Chrome stores the encryption passphrase in the login keychain
    under the service name 'Chrome Safe Storage'. We derive a 16-byte
    AES-128 key using PBKDF2-HMAC-SHA1 with salt='saltysalt' and 1003 iterations.
    """
    import hashlib
    from subprocess import PIPE, Popen

    cmd = ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"]
    proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    password, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to retrieve Chrome Safe Storage key from Keychain: {err.decode()}"
        )
    password = password.strip()

    key = hashlib.pbkdf2_hmac(
        "sha1", password, b"saltysalt", iterations=1003, dklen=16
    )
    return key


def _get_key_linux() -> bytes:
    """
    Linux: Try to get the password from the GNOME keyring via the
    Secret Service API (via secretstorage). Falls back to the legacy
    hardcoded password 'peanuts'.
    
    Derives a 16-byte AES-128 key using PBKDF2-HMAC-SHA1 with
    salt='saltysalt' and 1 iteration.
    """
    import hashlib

    password = b"peanuts"  # legacy fallback

    try:
        import secretstorage

        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        if collection.is_locked():
            collection.unlock()
        for item in collection.get_all_items():
            if item.get_label() == "Chrome Safe Storage":
                password = item.get_secret()
                break
    except Exception:
        pass  # fall back to 'peanuts'

    key = hashlib.pbkdf2_hmac(
        "sha1", password, b"saltysalt", iterations=1, dklen=16
    )
    return key


def _get_key_windows() -> bytes:
    """
    Windows (v10): The AES-256-GCM key is stored in Chrome's 'Local State'
    JSON file, base64-encoded and encrypted with DPAPI. We decode it,
    strip the 'DPAPI' prefix, and decrypt via CryptUnprotectData.
    
    NOTE: This does NOT support v20 (App-Bound) encryption introduced
    in Chrome 130+. v20 requires SYSTEM-level DPAPI access.
    """
    import win32crypt  # type: ignore[import]

    local_state_path = (
        Path(os.environ["LOCALAPPDATA"])
        / "Google/Chrome/User Data/Local State"
    )
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)

    encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    # Strip the 'DPAPI' prefix (first 5 bytes)
    encrypted_key = encrypted_key[5:]
    # Decrypt with user's DPAPI credentials
    _, key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
    return key


def _get_encryption_key() -> bytes:
    """Dispatch to the correct platform key retrieval."""
    if SYSTEM == "Darwin":
        return _get_key_darwin()
    elif SYSTEM == "Linux":
        return _get_key_linux()
    elif SYSTEM == "Windows":
        return _get_key_windows()
    else:
        raise OSError(f"Unsupported platform: {SYSTEM}")


# ---------------------------------------------------------------------------
# Cookie decryption
# ---------------------------------------------------------------------------

def _decrypt_value(encrypted_value: bytes, key: bytes) -> str:
    """
    Decrypt a single cookie's encrypted_value blob.
    
    Chrome stores encrypted cookies with a version prefix:
      - 'v10' / 'v11': AES-CBC (macOS/Linux) or AES-GCM (Windows)
      - 'v20': App-Bound encryption (Windows Chrome 130+, not supported here)
      - No prefix: Legacy DPAPI (old Windows Chrome)
    """
    if not encrypted_value:
        return ""

    version = encrypted_value[:3]

    if SYSTEM in ("Darwin", "Linux"):
        # AES-128-CBC with PKCS7 padding
        # Format: 'v10' + encrypted_payload
        if version != b"v10" and version != b"v11":
            return ""  # unrecognized format

        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        iv = b" " * 16  # 16 space characters
        payload = encrypted_value[3:]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(payload) + decryptor.finalize()

        # Remove PKCS7 padding
        padding_len = decrypted[-1]
        if isinstance(padding_len, int) and 1 <= padding_len <= 16:
            decrypted = decrypted[:-padding_len]

        return decrypted.decode("utf-8", errors="replace")

    elif SYSTEM == "Windows":
        if version == b"v10" or version == b"v11":
            # AES-256-GCM
            # Format: 'v10' + 12-byte nonce + ciphertext + 16-byte GCM tag
            from Crypto.Cipher import AES  # type: ignore[import]

            nonce = encrypted_value[3:15]
            ciphertext_with_tag = encrypted_value[15:]
            ciphertext = ciphertext_with_tag[:-16]
            tag = ciphertext_with_tag[-16:]

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted.decode("utf-8", errors="replace")

        elif version == b"v20":
            raise ValueError(
                "v20 (App-Bound) encrypted cookies are not supported. "
                "This requires SYSTEM-level DPAPI access (Chrome 130+). "
                "See: https://github.com/nickmunroe/chrome_v20_decryption"
            )
        else:
            # Legacy DPAPI-encrypted cookie (no version prefix)
            try:
                import win32crypt  # type: ignore[import]

                _, decrypted = win32crypt.CryptUnprotectData(
                    encrypted_value, None, None, None, 0
                )
                return decrypted.decode("utf-8", errors="replace")
            except Exception:
                return ""

    return ""


# ---------------------------------------------------------------------------
# Cookie loading
# ---------------------------------------------------------------------------

def _make_cookie(
    host: str,
    path: str,
    secure: int,
    expires: int,
    name: str,
    value: str,
    http_only: int,
) -> http.cookiejar.Cookie:
    """Build a standard Cookie object."""
    # Chrome stores expiry as microseconds since 1601-01-01.
    # Convert to Unix epoch seconds. 0 = session cookie.
    if expires:
        # Chrome epoch offset: 11644473600 seconds from 1601 to 1970
        expires_unix = (expires / 1_000_000) - 11644473600
        if expires_unix < 0:
            expires_unix = 0
    else:
        expires_unix = None

    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=host,
        domain_specified=bool(host.startswith(".")),
        domain_initial_dot=host.startswith("."),
        path=path,
        path_specified=bool(path),
        secure=bool(secure),
        expires=expires_unix,
        discard=expires_unix is None,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": str(bool(http_only))},
    )


def load(
    cookie_file: str | Path | None = None,
    domain_name: str | None = None,
) -> http.cookiejar.CookieJar:
    """
    Load Chrome cookies into a CookieJar.
    
    Args:
        cookie_file: Path to the Chrome Cookies SQLite file.
                     If None, uses the default Chrome profile location.
        domain_name: Optional domain filter (e.g. '.github.com').
                     If None, loads all cookies.
    
    Returns:
        http.cookiejar.CookieJar ready to use with requests/urllib.
    """
    db_path = Path(cookie_file) if cookie_file else _get_default_cookie_db_path()

    if not db_path.exists():
        raise FileNotFoundError(f"Chrome cookie database not found at: {db_path}")

    # Chrome locks the cookie DB while running. Copy to a temp file.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(tmp_fd)

    try:
        shutil.copy2(str(db_path), tmp_path)

        key = _get_encryption_key()
        jar = http.cookiejar.CookieJar()

        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = (
            "SELECT host_key, path, is_secure, expires_utc, name, "
            "value, encrypted_value, is_httponly FROM cookies"
        )
        params: list = []

        if domain_name:
            query += " WHERE host_key LIKE ?"
            params.append(f"%{domain_name}%")

        cursor.execute(query, params)

        decryption_errors = 0
        for row in cursor.fetchall():
            host = row["host_key"]
            value = row["value"]
            encrypted_value = row["encrypted_value"]

            if value or not encrypted_value:
                # Already decrypted or empty
                decrypted_value = value or ""
            else:
                try:
                    decrypted_value = _decrypt_value(bytes(encrypted_value), key)
                except Exception:
                    decryption_errors += 1
                    decrypted_value = ""

            if decrypted_value:
                cookie = _make_cookie(
                    host=host,
                    path=row["path"],
                    secure=row["is_secure"],
                    expires=row["expires_utc"],
                    name=row["name"],
                    value=decrypted_value,
                    http_only=row["is_httponly"],
                )
                jar.set_cookie(cookie)

        conn.close()

        if decryption_errors:
            print(
                f"Warning: {decryption_errors} cookie(s) could not be decrypted. "
                f"This may indicate v20 App-Bound encryption (Chrome 130+ on Windows).",
                file=sys.stderr,
            )

        return jar

    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """Simple CLI to list cookies for a given domain."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract Chrome cookies")
    parser.add_argument(
        "domain",
        nargs="?",
        help="Domain to filter cookies (e.g. github.com)",
    )
    parser.add_argument(
        "--cookie-file",
        help="Path to Chrome Cookies SQLite file (uses default if omitted)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output as JSON",
    )
    args = parser.parse_args()

    jar = load(cookie_file=args.cookie_file, domain_name=args.domain)

    if args.as_json:
        cookies = []
        for cookie in jar:
            cookies.append({
                "domain": cookie.domain,
                "name": cookie.name,
                "value": cookie.value,
                "path": cookie.path,
                "secure": cookie.secure,
                "expires": cookie.expires,
                "http_only": cookie.get_nonstandard_attr("HttpOnly"),
            })
        print(json.dumps(cookies, indent=2))
    else:
        count = 0
        for cookie in jar:
            print(f"{cookie.domain}\t{cookie.name}\t{cookie.value[:40]}...")
            count += 1
        print(f"\n{count} cookie(s) found")


if __name__ == "__main__":
    main()
