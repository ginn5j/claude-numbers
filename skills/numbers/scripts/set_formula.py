#!/usr/bin/env python3
"""
set_formula.py — Write formulas to cells in a .numbers file via AppleScript.

Requires macOS with Numbers.app installed. Numbers is launched automatically if
not already running. The file is opened, formulas applied, and saved to a new
path. The original file is never overwritten.

Usage:
    python3 set_formula.py <input.numbers> <output.numbers> \\
        --sheet "Sheet 1" --table "Table 1" \\
        --formula B2 "=SUM(A1:A10)" \\
        --formula C2 "=AVERAGE(A1:A10)"

Arguments:
    input       Path to the source .numbers file
    output      Path to save the result (must differ from input)

Options:
    --sheet     Sheet name containing the target table (default: first sheet)
    --table     Table name to write formulas into (default: first table)
    --formula   Cell address and formula string, e.g. --formula B2 "=SUM(A1:A10)"
                Repeat to set multiple formulas in one pass.
    --no-close  Leave the document open in Numbers after saving

Notes:
    - Cell addresses use A1 notation (e.g. B2, C10, AA3).
    - Formula strings must begin with "=" (added automatically if missing).
    - Numbers.app will be visible while this runs.
    - If Numbers is already open with the same file, that document is reused
      and left open afterwards.
"""

import argparse
import sys
import textwrap
from pathlib import Path

from _common import build_writer_script, esc, run_applescript, sheet_table_refs


def main():
    parser = argparse.ArgumentParser(
        description="Write formulas to a .numbers file via AppleScript.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              # Set a single formula
              python3 set_formula.py budget.numbers budget_v2.numbers \\
                  --sheet "Sheet 1" --table "Table 1" \\
                  --formula B10 "=SUM(B2:B9)"

              # Set multiple formulas at once
              python3 set_formula.py data.numbers data_out.numbers \\
                  --sheet "Summary" --table "Totals" \\
                  --formula C2 "=AVERAGE(Sheet1::Table1::B:B)" \\
                  --formula C3 "=MAX(Sheet1::Table1::B:B)" \\
                  --formula C4 "=MIN(Sheet1::Table1::B:B)"
            """
        ),
    )
    parser.add_argument("input", help="Source .numbers file path")
    parser.add_argument("output", help="Output .numbers file path (must differ from input)")
    parser.add_argument("--sheet", metavar="NAME", help="Sheet name (default: first sheet)")
    parser.add_argument("--table", metavar="NAME", help="Table name (default: first table)")
    parser.add_argument(
        "--formula",
        nargs=2,
        metavar=("CELL", "FORMULA"),
        action="append",
        required=True,
        help='Cell address and formula, e.g. --formula B2 "=SUM(A1:A10)"',
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
    output_path.parent.mkdir(parents=True, exist_ok=True)

    formula_lines = []
    for cell_addr, formula in args.formula:
        if not formula.startswith("="):
            formula = "=" + formula
        formula_lines.append(
            f'                set value of cell "{esc(cell_addr)}" to "{esc(formula)}"'
        )

    sheet_ref, table_ref = sheet_table_refs(args.sheet, args.table)
    body = (
        f"            tell {sheet_ref}\n"
        f"                tell {table_ref}\n"
        + "\n".join(formula_lines) + "\n"
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
