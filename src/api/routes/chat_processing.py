"""
Helpers for transforming raw chat messages into processed chat view blocks.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _attach_span(item: Dict[str, Any], start: int, end: int) -> Dict[str, Any]:
    item["source_span"] = {"start": start, "end": end}
    return item


def _item_intersects_window(item: Dict[str, Any], start: int, end: int) -> bool:
    span = item.get("source_span")
    if not span:
        return False
    return span["start"] < end and span["end"] > start


def select_processed_window(
    processed_messages: List[Dict[str, Any]],
    message_offset: int,
    message_limit: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Select processed messages whose source spans intersect a raw-message window.

    Returns the selected items and the expanded raw-message coverage window.
    """
    window_start = message_offset
    window_end = message_offset + message_limit

    selected = [
        deepcopy(item)
        for item in processed_messages
        if _item_intersects_window(item, window_start, window_end)
    ]

    if not selected:
        return [], {"covered_start": window_start, "covered_end": window_start}

    covered_start = min(item["source_span"]["start"] for item in selected)
    covered_end = max(item["source_span"]["end"] for item in selected)
    return selected, {"covered_start": covered_start, "covered_end": covered_end}
