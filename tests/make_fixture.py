#!/usr/bin/env python3
"""
make_fixture.py — Create a small two-sheet .numbers fixture via Numbers.app.

The fixture has:
  - Sheet "Data" with table "Sales" (6 rows x 3 cols, header row, SUM formula
    in C6, "Total" label in A6)
  - Sheet "Summary" with table "Totals" (cross-sheet SUM formula in B2)

Usage:
    python3 tests/make_fixture.py /path/to/fixture.numbers
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "numbers" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _common import esc, run_applescript  # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tests/make_fixture.py /path/to/fixture.numbers", file=sys.stderr)
        sys.exit(2)

    out = Path(sys.argv[1]).expanduser().resolve()
    if out.exists():
        print(f"ERROR: Output already exists: {out}", file=sys.stderr)
        sys.exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)

    script = f"""
tell application id "com.apple.Numbers"
    activate
    set newDoc to make new document
    tell newDoc
        set name of sheet 1 to "Data"
        tell sheet 1
            set name of table 1 to "Sales"
            tell table "Sales"
                set row count to 6
                set column count to 3
                set value of cell "A1" to "Name"
                set value of cell "B1" to "Region"
                set value of cell "C1" to "Amount"
                set value of cell "A2" to "Alice"
                set value of cell "B2" to "East"
                set value of cell "C2" to 100
                set value of cell "A3" to "Bob"
                set value of cell "B3" to "West"
                set value of cell "C3" to 80
                set value of cell "A4" to "Cara"
                set value of cell "B4" to "East"
                set value of cell "C4" to 120
                set value of cell "A5" to "Dan"
                set value of cell "B5" to "South"
                set value of cell "C5" to 60
                set value of cell "A6" to "Total"
                set value of cell "C6" to "=SUM(C2:C5)"
            end tell
        end tell
        make new sheet with properties {{name:"Summary"}}
        tell sheet "Summary"
            set name of table 1 to "Totals"
            tell table "Totals"
                set value of cell "A1" to "Metric"
                set value of cell "B1" to "Value"
                set value of cell "A2" to "Total Sales"
                set value of cell "B2" to "=SUM(Data::Sales::C2:C5)"
            end tell
        end tell
        save newDoc in POSIX file "{esc(str(out))}"
    end tell
    close newDoc saving no
end tell
"""
    run_applescript(script)
    print(f"Fixture created: {out}")


if __name__ == "__main__":
    main()
