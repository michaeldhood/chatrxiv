#!/usr/bin/env python3
"""
Analyze bubble schema and extract categorical variable values.

This script reads a bubbles JSON file and:
1. Extracts the complete schema structure
2. Identifies all categorical variables
3. Collects all unique values for each categorical variable
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Set


def collect_schema(
    obj: Any, path: str = "", schema: Dict[str, Set[type]] = None
) -> Dict[str, Set[type]]:
    """
    Recursively collect schema information from a JSON object.

    Parameters
    ----
    obj : Any
        The JSON object to analyze
    path : str
        Current path in the object hierarchy
    schema : Dict[str, Set[type]]
        Accumulated schema information

    Returns
    ----
    Dict[str, Set[type]]
        Schema mapping paths to their types
    """
    if schema is None:
        schema = defaultdict(set)

    if obj is None:
        schema[path].add(type(None))
    elif isinstance(obj, dict):
        schema[path].add(dict)
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            collect_schema(value, new_path, schema)
    elif isinstance(obj, list):
        schema[path].add(list)
        if obj:
            # Analyze first item to understand list structure
            collect_schema(obj[0], f"{path}[]", schema)
    else:
        schema[path].add(type(obj))

    return schema


def collect_categorical_values(
    obj: Any, path: str = "", values: Dict[str, Set[Any]] = None
) -> Dict[str, Set[Any]]:
    """
    Recursively collect all values for potential categorical variables.

    Parameters
    ----
    obj : Any
        The JSON object to analyze
    path : str
        Current path in the object hierarchy
    values : Dict[str, Set[Any]]
        Accumulated values for each path

    Returns
    ----
    Dict[str, Set[Any]]
        Values mapping paths to sets of unique values
    """
    if values is None:
        values = defaultdict(set)

    if obj is None:
        values[path].add(None)
    elif isinstance(obj, dict):
        for key, value in obj.items():
            new_path = f"{path}.{key}" if path else key
            collect_categorical_values(value, new_path, values)
    elif isinstance(obj, list):
        for item in obj:
            collect_categorical_values(item, f"{path}[]", values)
    else:
        # Store primitive values
        values[path].add(obj)

    return values


def identify_categorical_variables(
    values: Dict[str, Set[Any]], max_unique: int = 50
) -> Dict[str, Set[Any]]:
    """
    Identify which variables are likely categorical based on number of unique values.

    Parameters
    ----
    values : Dict[str, Set[Any]]
        All collected values
    max_unique : int
        Maximum number of unique values to consider a variable categorical

    Returns
    ----
    Dict[str, Set[Any]]
        Filtered dictionary containing only categorical variables
    """
    categorical = {}
    for path, value_set in values.items():
        # Remove None from count if it's not the only value
        non_none_values = {v for v in value_set if v is not None}
        unique_count = len(non_none_values)

        # Consider categorical if:
        # 1. Has limited unique values (categorical)
        # 2. Or is a known categorical field (type, status, tool, etc.)
        is_known_categorical = any(
            keyword in path.lower()
            for keyword in ["type", "status", "tool", "id", "name", "kind", "category"]
        )

        if unique_count <= max_unique or is_known_categorical:
            categorical[path] = value_set

    return categorical


def format_schema_report(
    schema: Dict[str, Set[type]], categorical: Dict[str, Set[Any]]
) -> str:
    """
    Format the schema and categorical values into a readable report.

    Parameters
    ----
    schema : Dict[str, Set[type]]
        Schema information
    categorical : Dict[str, Set[Any]]
        Categorical variable values

    Returns
    ----
    str
        Formatted markdown report
    """
    lines = []
    lines.append("# Bubble Schema Analysis")
    lines.append("")
    lines.append("## Complete Schema Structure")
    lines.append("")

    # Sort paths for readability
    sorted_paths = sorted(schema.keys())

    for path in sorted_paths:
        types = schema[path]
        type_str = " | ".join(
            t.__name__ for t in sorted(types, key=lambda x: x.__name__)
        )
        lines.append(f"- **`{path}`**: `{type_str}`")

    lines.append("")
    lines.append("## Categorical Variables and Values")
    lines.append("")
    lines.append(
        "The following variables have limited unique values and are likely categorical:"
    )
    lines.append("")

    # Sort categorical paths
    sorted_categorical = sorted(categorical.keys())

    for path in sorted_categorical:
        values = categorical[path]
        lines.append(f"### `{path}`")
        lines.append("")

        # Sort values for display (None first, then by value)
        sorted_values = sorted(values, key=lambda x: (x is None, str(x)))

        for value in sorted_values:
            if value is None:
                lines.append("- `null`")
            elif isinstance(value, str):
                # Escape special characters in strings
                escaped = value.replace("`", "\\`").replace("\n", "\\n")
                if len(escaped) > 100:
                    escaped = escaped[:97] + "..."
                lines.append(f"- `{escaped}`")
            else:
                lines.append(f"- `{json.dumps(value)}`")

        lines.append("")
        lines.append(f"**Total unique values:** {len(values)}")
        lines.append("")

    return "\n".join(lines)


def main():
    """Main execution function."""
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python analyze_bubble_schema.py <bubbles_json_file> [output_file]"
        )
        sys.exit(1)

    input_file = Path(sys.argv[1])
    output_file = (
        Path(sys.argv[2])
        if len(sys.argv) > 2
        else input_file.parent / f"{input_file.stem}_schema.md"
    )

    print(f"Reading {input_file}...")
    with open(input_file, "r", encoding="utf-8") as f:
        bubbles = json.load(f)

    print(f"Analyzing {len(bubbles)} bubbles...")

    # Collect schema
    schema = defaultdict(set)
    values = defaultdict(set)

    for bubble in bubbles:
        bubble_schema = collect_schema(bubble)
        bubble_values = collect_categorical_values(bubble)

        # Merge into global collections
        for path, types in bubble_schema.items():
            schema[path].update(types)

        for path, value_set in bubble_values.items():
            values[path].update(value_set)

    # Identify categorical variables
    categorical = identify_categorical_variables(values)

    # Generate report
    report = format_schema_report(schema, categorical)

    # Write output
    print(f"Writing report to {output_file}...")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    print("✓ Analysis complete!")
    print(f"  - Total schema paths: {len(schema)}")
    print(f"  - Categorical variables: {len(categorical)}")
    print(f"  - Report written to: {output_file}")


if __name__ == "__main__":
    main()
