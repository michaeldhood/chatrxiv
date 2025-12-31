"""
HAR File Parser for API Discovery
=================================

Parses HTTP Archive (HAR) files exported from browser DevTools to automatically
discover and document internal web application APIs.

Usage
-----
    python scripts/api_discovery/har_parser.py path/to/export.har --output docs/api-reference.md

Process
-------
1. Open target web app in browser while logged in
2. Open DevTools → Network tab
3. Use the app (navigate, click, submit forms)
4. Right-click in Network tab → "Save all as HAR with content"
5. Run this parser on the HAR file

Notes
-----
HAR files contain ALL network traffic including:
- API calls (what we want)
- Static assets (ignored)
- Analytics (optionally captured)
- Third-party requests (filtered out)
"""

import json
import re
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Any


def load_har(har_path: str) -> dict:
    """Load and parse a HAR file."""
    with open(har_path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_api_request(entry: dict, api_patterns: list[str] | None = None) -> bool:
    """
    Determine if a HAR entry is an API request worth documenting.
    
    Parameters
    ----------
    entry : dict
        HAR entry object
    api_patterns : list[str], optional
        List of URL patterns to match (e.g., ['/api/', '/v1/'])
    """
    request = entry.get("request", {})
    url = request.get("url", "")
    mime_type = entry.get("response", {}).get("content", {}).get("mimeType", "")
    
    # Default patterns for API detection
    if api_patterns is None:
        api_patterns = ["/api/", "/v1/", "/v2/", "/graphql"]
    
    # Check URL patterns
    url_match = any(pattern in url for pattern in api_patterns)
    
    # Check content type (API responses are usually JSON)
    is_json = "application/json" in mime_type or "text/event-stream" in mime_type
    
    # Exclude static assets
    static_extensions = [".js", ".css", ".png", ".jpg", ".svg", ".woff", ".ico"]
    is_static = any(url.endswith(ext) for ext in static_extensions)
    
    return (url_match or is_json) and not is_static


def extract_endpoint_pattern(url: str, org_id_patterns: list[str] | None = None) -> str:
    """
    Extract a normalized endpoint pattern from a URL.
    
    Replaces UUIDs and known IDs with placeholders.
    
    Parameters
    ----------
    url : str
        Full URL
    org_id_patterns : list[str], optional
        Specific org/user ID patterns to replace
    """
    parsed = urlparse(url)
    path = parsed.path
    
    # UUID pattern (standard format)
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    path = re.sub(uuid_pattern, "{ID}", path)
    
    # Numeric IDs
    path = re.sub(r"/\d{10,}/", "/{TIMESTAMP}/", path)
    path = re.sub(r"/\d+/", "/{NUM_ID}/", path)
    
    # Hash-like strings (32+ hex chars)
    path = re.sub(r"/[0-9a-f]{32,}/", "/{HASH}/", path)
    
    return path


def parse_request_body(entry: dict) -> dict | None:
    """Extract and parse the request body."""
    request = entry.get("request", {})
    post_data = request.get("postData", {})
    
    if not post_data:
        return None
    
    mime_type = post_data.get("mimeType", "")
    text = post_data.get("text", "")
    
    if "application/json" in mime_type and text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"_raw": text}
    
    return {"_raw": text} if text else None


def parse_response_body(entry: dict) -> dict | str | None:
    """Extract and parse the response body."""
    response = entry.get("response", {})
    content = response.get("content", {})
    
    mime_type = content.get("mimeType", "")
    text = content.get("text", "")
    
    if not text:
        return None
    
    # Handle JSON responses
    if "application/json" in mime_type:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    
    # Handle SSE (Server-Sent Events) - common for streaming APIs
    if "text/event-stream" in mime_type:
        return {"_type": "sse", "_raw_truncated": text[:1000] + "..." if len(text) > 1000 else text}
    
    return text if len(text) < 500 else text[:500] + "..."


def infer_schema(obj: Any, max_depth: int = 3, current_depth: int = 0) -> dict:
    """
    Infer a JSON schema from an object.
    
    Parameters
    ----------
    obj : Any
        The object to analyze
    max_depth : int
        Maximum recursion depth
    current_depth : int
        Current depth (for recursion)
    """
    if current_depth >= max_depth:
        return {"type": "..."}
    
    if obj is None:
        return {"type": "null"}
    elif isinstance(obj, bool):
        return {"type": "boolean"}
    elif isinstance(obj, int):
        return {"type": "integer"}
    elif isinstance(obj, float):
        return {"type": "number"}
    elif isinstance(obj, str):
        # Try to detect common string types
        if re.match(r"^\d{4}-\d{2}-\d{2}T", obj):
            return {"type": "string", "format": "datetime"}
        elif re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", obj):
            return {"type": "string", "format": "uuid"}
        elif obj.startswith("http"):
            return {"type": "string", "format": "url"}
        return {"type": "string"}
    elif isinstance(obj, list):
        if not obj:
            return {"type": "array", "items": {}}
        # Sample first item
        return {"type": "array", "items": infer_schema(obj[0], max_depth, current_depth + 1)}
    elif isinstance(obj, dict):
        return {
            "type": "object",
            "properties": {
                k: infer_schema(v, max_depth, current_depth + 1) 
                for k, v in obj.items()
            }
        }
    return {"type": str(type(obj).__name__)}


def group_endpoints(entries: list[dict]) -> dict[str, list[dict]]:
    """Group HAR entries by their normalized endpoint pattern."""
    grouped = defaultdict(list)
    
    for entry in entries:
        if not is_api_request(entry):
            continue
        
        request = entry["request"]
        url = request["url"]
        method = request["method"]
        
        pattern = extract_endpoint_pattern(url)
        key = f"{method} {pattern}"
        
        grouped[key].append(entry)
    
    return dict(grouped)


def generate_markdown(
    grouped_endpoints: dict[str, list[dict]], 
    app_name: str = "Unknown App",
    base_url: str | None = None
) -> str:
    """
    Generate markdown documentation from grouped endpoints.
    
    Parameters
    ----------
    grouped_endpoints : dict
        Endpoints grouped by pattern
    app_name : str
        Name of the application being documented
    base_url : str, optional
        Base URL to use in examples
    """
    lines = [
        f"# {app_name} Internal API Reference",
        "",
        "> **Auto-generated** from HAR file analysis",
        f"> **Generated**: {datetime.now().isoformat()}",
        "",
        "---",
        "",
        "## Endpoints",
        ""
    ]
    
    # Sort endpoints for consistent output
    for endpoint_pattern in sorted(grouped_endpoints.keys()):
        entries = grouped_endpoints[endpoint_pattern]
        method, path = endpoint_pattern.split(" ", 1)
        
        # Get a representative entry
        entry = entries[0]
        request = entry["request"]
        response = entry["response"]
        
        lines.append(f"### `{method} {path}`")
        lines.append("")
        
        # URL with query params
        parsed = urlparse(request["url"])
        if parsed.query:
            lines.append("**Query Parameters**:")
            lines.append("")
            lines.append("| Parameter | Example Value |")
            lines.append("|-----------|---------------|")
            for key, values in parse_qs(parsed.query).items():
                lines.append(f"| `{key}` | `{values[0]}` |")
            lines.append("")
        
        # Request body (if POST/PUT/PATCH)
        if method in ["POST", "PUT", "PATCH"]:
            body = parse_request_body(entry)
            if body and not body.get("_raw"):
                lines.append("**Request Body**:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(body, indent=2)[:2000])
                lines.append("```")
                lines.append("")
        
        # Response
        status = response.get("status", 0)
        status_text = response.get("statusText", "")
        lines.append(f"**Response**: `{status} {status_text}`")
        lines.append("")
        
        response_body = parse_response_body(entry)
        if response_body:
            if isinstance(response_body, dict) and response_body.get("_type") == "sse":
                lines.append("**Response Type**: Server-Sent Events (SSE)")
                lines.append("")
                lines.append("```")
                lines.append(response_body.get("_raw_truncated", ""))
                lines.append("```")
            elif isinstance(response_body, dict):
                # Truncate large responses
                json_str = json.dumps(response_body, indent=2)
                if len(json_str) > 3000:
                    json_str = json_str[:3000] + "\n... (truncated)"
                lines.append("```json")
                lines.append(json_str)
                lines.append("```")
            else:
                lines.append("```")
                lines.append(str(response_body)[:1000])
                lines.append("```")
            lines.append("")
        
        # Observations (count of requests)
        lines.append(f"*Observed {len(entries)} request(s)*")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    return "\n".join(lines)


def analyze_har(
    har_path: str,
    output_path: str | None = None,
    app_name: str = "Unknown App",
    api_patterns: list[str] | None = None,
    verbose: bool = False
) -> str:
    """
    Main function to analyze a HAR file and generate API documentation.
    
    Parameters
    ----------
    har_path : str
        Path to the HAR file
    output_path : str, optional
        Path to write the markdown output
    app_name : str
        Name of the application
    api_patterns : list[str], optional
        URL patterns to match for API detection
    verbose : bool
        Print verbose output
    
    Returns
    -------
    str
        Generated markdown documentation
    """
    if verbose:
        print(f"Loading HAR file: {har_path}")
    
    har_data = load_har(har_path)
    entries = har_data.get("log", {}).get("entries", [])
    
    if verbose:
        print(f"Found {len(entries)} total entries")
    
    # Filter to API requests
    api_entries = [e for e in entries if is_api_request(e, api_patterns)]
    
    if verbose:
        print(f"Found {len(api_entries)} API requests")
    
    # Group by endpoint
    grouped = group_endpoints(api_entries)
    
    if verbose:
        print(f"Found {len(grouped)} unique endpoint patterns")
        for pattern in sorted(grouped.keys()):
            print(f"  - {pattern} ({len(grouped[pattern])} requests)")
    
    # Generate markdown
    markdown = generate_markdown(grouped, app_name)
    
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        if verbose:
            print(f"Wrote documentation to: {output_path}")
    
    return markdown


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Parse HAR files to discover and document internal APIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python har_parser.py export.har --output docs/api-reference.md
  
  # Specify app name
  python har_parser.py claude.har --app-name "Claude.ai" --output docs/claude-api.md
  
  # Custom API patterns
  python har_parser.py export.har --api-pattern "/api/" --api-pattern "/graphql"
  
  # Verbose output
  python har_parser.py export.har -v
        """
    )
    
    parser.add_argument("har_file", help="Path to the HAR file")
    parser.add_argument("--output", "-o", help="Output markdown file path")
    parser.add_argument("--app-name", default="Unknown App", help="Name of the application")
    parser.add_argument("--api-pattern", action="append", dest="api_patterns",
                        help="URL patterns to match (can be specified multiple times)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    result = analyze_har(
        args.har_file,
        args.output,
        args.app_name,
        args.api_patterns,
        args.verbose
    )
    
    if not args.output:
        print(result)


if __name__ == "__main__":
    main()
