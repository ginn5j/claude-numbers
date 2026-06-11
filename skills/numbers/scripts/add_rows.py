#!/usr/bin/env python3
"""
add_rows.py — Append rows of data to a table in a .numbers file.

Requires macOS with Numbers.app installed. Rows are appended by growing the
table's row count, then filling the new cells. The result is saved to a new
path; the original file is never overwritten.

Usage:
    python3 add_rows.py <input.numbers> <output.numbers> \\
        --sheet "Sheet 1" --table "Table 1" \\
        --row '["Alice", "East", 100]' \\
        --row '["Bob", "West", true]'

Arguments:
    input       Path to the source .numbers file
    output      Path to save the result (must differ from input)

Options:
    --sheet     Sheet name containing the target table (default: first sheet)
    --table     Table name to append to (default: first table)
    --row       One row as a JSON array; strings, numbers, booleans, and null
                (leaves the cell empty) are allowed. Repeat for multiple rows.
    --no-close  Leave the document open in Numbers after saving

Notes:
    - The table's column count is grown if a row is wider than the table.
    - Tables with footer rows: appended rows land after the footer.
    - If Numbers is already open with the same file, that document is reused
      and left open afterwards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import applescript_value, build_writer_script, run_applescript, sheet_table_refs


def parse_rows(raw_rows: list[str]) -> list[list]:
    rows = []
    for raw in raw_rows:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"ERROR: --row is not valid JSON: {raw!r} ({e})", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed, list):
            print(f"ERROR: --row must be a JSON array, got: {raw!r}", file=sys.stderr)
            sys.exit(1)
        for v in parsed:
            if v is not None and not isinstance(v, (str, int, float, bool)):
                print(
                    f"ERROR: row values must be strings, numbers, booleans, or null; "
                    f"got {v!r} in {raw!r}",
                    file=sys.stderr,
                )
                sys.exit(1)
        rows.append(parsed)
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Append rows of data to a table in a .numbers file."
    )
    parser.add_argument("input", help="Source .numbers file path")
    parser.add_argument("output", help="Output .numbers file path (must differ from input)")
    parser.add_argument("--sheet", metavar="NAME", help="Sheet name (default: first sheet)")
    parser.add_argument("--table", metavar="NAME", help="Table name (default: first table)")
    parser.add_argument(
        "--row",
        metavar="JSON_ARRAY",
        action="append",
        required=True,
        help='One row as a JSON array, e.g. --row \'["Alice", 100, true]\'',
    )
    parser.add_argument(
        "--no-close",
        action="store_true",
        help="Leave the document open in Numbers after saving",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    if input_path == output_path:
        print("ERROR: Output path must differ from input path.", file=sys.stderr)
        sys.exit(1)

    rows = parse_rows(args.row)
    max_cols = max(len(r) for r in rows)
    if max_cols == 0:
        print("ERROR: rows are empty — nothing to append.", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cell_lines = []
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            if value is None:
                continue
            cell_lines.append(
                f"                set value of cell {j + 1} of row (baseRows + {i + 1}) "
                f"to {applescript_value(value)}"
            )

    sheet_ref, table_ref = sheet_table_refs(args.sheet, args.table)
    body = (
        f"            tell {sheet_ref}\n"
        f"                tell {table_ref}\n"
        f"                    set baseRows to row count\n"
        f"                    if column count < {max_cols} then set column count to {max_cols}\n"
        f"                    set row count to baseRows + {len(rows)}\n"
        + "\n".join(cell_lines) + "\n"
        f"                end tell\n"
        f"            end tell"
    )

    script = build_writer_script(
        input_path=str(input_path),
        output_path=str(output_path),
        body=body,
        close_after=not args.no_close,
    )

    run_applescript(script)
    print(f"Appended {len(rows)} row(s). Saved to: {output_path}")


if __name__ == "__main__":
    main()
