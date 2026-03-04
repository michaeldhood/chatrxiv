# chrome_cookies

A lightweight, single-file Chrome cookie extractor. Zero bloat — Chrome only, no browser detection scaffolding.

Drop-in replacement for `browser_cookie3.chrome()`.

## Install

```bash
pip install cryptography   # macOS / Linux
# pip install pycryptodome pywin32   # Windows
```

## Usage

### Python

```python
import chrome_cookies
import requests

# Load all cookies
jar = chrome_cookies.load()

# Filter by domain
jar = chrome_cookies.load(domain_name=".github.com")

# Use with requests
r = requests.get("https://github.com", cookies=jar)

# Custom cookie file path (e.g. a different Chrome profile)
jar = chrome_cookies.load(cookie_file="~/path/to/Cookies")
```

### CLI

```bash
# List all cookies for a domain
python chrome_cookies.py github.com

# JSON output
python chrome_cookies.py github.com --json

# Custom cookie file
python chrome_cookies.py --cookie-file /path/to/Cookies github.com
```

## How it works

Chrome stores cookies in a SQLite database encrypted with a platform-specific key:

| Platform | Encryption           | Key source                             |
| -------- | -------------------- | -------------------------------------- |
| macOS    | AES-128-CBC (PBKDF2) | macOS Keychain ("Chrome Safe Storage") |
| Linux    | AES-128-CBC (PBKDF2) | GNOME Keyring or fallback `peanuts`    |
| Windows  | AES-256-GCM          | `Local State` file + DPAPI             |

### Limitations

- **Windows Chrome 130+**: The `v20` App-Bound encryption requires SYSTEM-level DPAPI access and is not supported. If you're on a recent Chrome on Windows and cookies fail to decrypt, this is why.
- Chrome must not be running with a lock on the database (the script copies the DB to a temp file to work around this, but a WAL checkpoint may be needed in some cases).

## License

MIT — do whatever you want with it.

## Dependencies

# macOS / Linux

cryptography>=41.0.0
