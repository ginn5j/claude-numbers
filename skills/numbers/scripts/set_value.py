#!/usr/bin/env python3
"""
set_value.py — Write literal values to cells in a .numbers file via AppleScript.

Requires macOS with Numbers.app installed. Numbers is launched automatically if
not already running. The file is opened, values written, and saved to a new
path. The original file is never overwritten.

Usage:
    python3 set_value.py <input.numbers> <output.numbers> \\
        --sheet "Sheet 1" --table "Table 1" \\
        --value B2 42.5 \\
        --value C2 "Updated" \\
        --value D2 true

Arguments:
    input       Path to the source .numbers file
    output      Path to save the result (must differ from input)

Options:
    --sheet     Sheet name containing the target table (default: first sheet)
    --table     Table name to write into (default: first table)
    --value     Cell address and value, auto-typed: integers and decimals are
                written as numbers, "true"/"false" as booleans, anything else
                as text. Repeat for multiple cells.
    --text      Cell address and value, always written as text (use when a
                value like "true" or "007" must stay literal).
    --no-close  Leave the document open in Numbers after saving

Notes:
    - Cell addresses use A1 notation (e.g. B2, C10, AA3).
    - Values beginning with "=" are rejected — Numbers would store them as
      formulas. Use set_formula.py for formulas.
    - If Numbers is already open with the same file, that document is reused
      and left open afterwards.
"""

import argparse
import sys
import textwrap
from pathlib import Path

from _common import applescript_value, build_writer_script, esc, run_applescript, sheet_table_refs


def auto_type(raw: str):
    low = raw.strip().lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def main():
    parser = argparse.ArgumentParser(
        description="Write literal values to a .numbers file via AppleScript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python3 set_value.py tracker.numbers tracker_v2.numbers \\
                  --sheet "Sheet 1" --table "Table 1" \\
                  --value B2 320 \\
                  --value C2 "On track" \\
                  --text D2 007
            """
        ),
    )
    parser.add_argument("input", help="Source .numbers file path")
    parser.add_argument("output", help="Output .numbers file path (must differ from input)")
    parser.add_argument("--sheet", metavar="NAME", help="Sheet name (default: first sheet)")
    parser.add_argument("--table", metavar="NAME", help="Table name (default: first table)")
    parser.add_argument(
        "--value",
        nargs=2,
        metavar=("CELL", "VALUE"),
        action="append",
        default=[],
        help="Cell address and auto-typed value, e.g. --value B2 42.5",
    )
    parser.add_argument(
        "--text",
        nargs=2,
        metavar=("CELL", "VALUE"),
        action="append",
        default=[],
        help="Cell address and value always written as text",
    )
    parser.add_argument(
        "--no-close",
        action="store_true",
        help="Leave the document open in Numbers after saving",
    )
    args = parser.parse_args()

    if not args.value and not args.text:
        parser.error("provide at least one --value or --text")

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    if input_path == output_path:
        print("ERROR: Output path must differ from input path.", file=sys.stderr)
        sys.exit(1)

    cells = [(addr, auto_type(raw)) for addr, raw in args.value]
    cells += [(addr, raw) for addr, raw in args.text]

    for addr, value in cells:
        if isinstance(value, str) and value.lstrip().startswith("="):
            print(
                f"ERROR: Value for cell {addr} starts with '=' — Numbers would store "
                "it as a formula. Use set_formula.py for formulas.",
                file=sys.stderr,
            )
            sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    value_lines = "\n".join(
        f'                set value of cell "{esc(addr)}" to {applescript_value(value)}'
        for addr, value in cells
    )
    sheet_ref, table_ref = sheet_table_refs(args.sheet, args.table)
    body = (
        f"            tell {sheet_ref}\n"
        f"                tell {table_ref}\n"
        f"{value_lines}\n"
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
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
