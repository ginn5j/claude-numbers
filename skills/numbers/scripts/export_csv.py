#!/usr/bin/env python3
"""
export_csv.py — Export tables from a .numbers file to CSV via Numbers.app.

Requires macOS with Numbers.app installed. Numbers is launched automatically.

Usage:
    python3 export_csv.py <path-to-file.numbers> [options]

Options:
    --sheet SHEET_NAME      Sheet name (default: first sheet)
    --table TABLE_NAME      Table name (default: first table in selected sheet)
    --all-tables            Export every table (of --sheet, or of all sheets)
    --output PATH           Output CSV path, or directory with --all-tables
                            (default: derived from input filename)
    --close                 Close the document in Numbers after exporting (only
                            closes documents this script opened)

Examples:
    python3 export_csv.py report.numbers
    python3 export_csv.py report.numbers --sheet "Summary" --table "Totals"
    python3 export_csv.py report.numbers --all-tables --output ~/Desktop/csvs
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from _common import JXA_PROLOGUE, close_document, run_osascript

# Sheet/table names are passed as argv ('' = default), never interpolated into
# the script source — names containing quotes or backslashes must not break it.
_JXA = JXA_PROLOGUE + r"""
function run(argv) {
    const filePath = argv[0];
    const sheetName = argv[1];
    const tableName = argv[2];
    const allTables = argv[3] === '1';

    const opened = openDoc(filePath);
    if (!opened.doc) {
        return JSON.stringify({error: 'Could not open ' + filePath + ' in Numbers. ' +
            'If the file is password-protected, remove the password ' +
            '(File > Password > Remove Password) and retry.'});
    }
    const doc = opened.doc;

    // Resolve sheets
    let sheets = [];
    if (sheetName !== '') {
        for (let i = 0; i < doc.sheets.length; i++) {
            if (doc.sheets[i].name() === sheetName) { sheets.push(doc.sheets[i]); break; }
        }
        if (sheets.length === 0) {
            const names = [];
            for (let i = 0; i < doc.sheets.length; i++) names.push(doc.sheets[i].name());
            return JSON.stringify({error: "Sheet '" + sheetName + "' not found. Available: " + names.join(', ')});
        }
    } else if (allTables) {
        for (let i = 0; i < doc.sheets.length; i++) sheets.push(doc.sheets[i]);
    } else {
        sheets.push(doc.sheets[0]);
    }

    const out = [];
    for (let s = 0; s < sheets.length; s++) {
        const sheet = sheets[s];

        // Resolve tables within this sheet
        let tables = [];
        if (allTables) {
            for (let i = 0; i < sheet.tables.length; i++) tables.push(sheet.tables[i]);
        } else if (tableName !== '') {
            for (let i = 0; i < sheet.tables.length; i++) {
                if (sheet.tables[i].name() === tableName) { tables.push(sheet.tables[i]); break; }
            }
            if (tables.length === 0) {
                const names = [];
                for (let i = 0; i < sheet.tables.length; i++) names.push(sheet.tables[i].name());
                return JSON.stringify({error: "Table '" + tableName + "' not found in sheet '" +
                    sheet.name() + "'. Available: " + names.join(', ')});
            }
        } else {
            tables.push(sheet.tables[0]);
        }

        for (let t = 0; t < tables.length; t++) {
            const table = tables[t];
            const rows = [];
            for (let r = 0; r < table.rows.length; r++) {
                const raw = table.rows[r].cells.value();
                rows.push(raw.map(cellValue));
            }
            out.push({sheet_name: sheet.name(), table_name: table.name(), rows: rows});
        }
    }

    return JSON.stringify({_opened_by_script: opened.openedByScript, tables: out});
}
"""


def _to_csv_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else str(value)
    return str(value)


def _safe(name: str) -> str:
    return name.replace("/", "-").replace(" ", "_")


def export_csv(
    path: str,
    sheet_name: str | None = None,
    table_name: str | None = None,
    output_path: str | None = None,
    all_tables: bool = False,
    close_after: bool = False,
) -> list[str]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    result = run_osascript(
        [
            "osascript", "-l", "JavaScript", "-e", _JXA,
            str(file_path), sheet_name or "", table_name or "",
            "1" if all_tables else "0",
        ],
        # Full-table reads can be slow on large tables
        timeout=600,
    )

    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        print(f"ERROR: Unexpected output:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)

    if "error" in data:
        print(f"ERROR: {data['error']}", file=sys.stderr)
        sys.exit(1)

    opened_by_script = data.pop("_opened_by_script", True)
    tables = data["tables"]

    def derived_name(t: dict) -> str:
        return f"{file_path.stem}_{_safe(t['sheet_name'])}_{_safe(t['table_name'])}.csv"

    if output_path:
        out_arg = Path(output_path).expanduser()
        if len(tables) > 1 or out_arg.is_dir():
            out_dir = out_arg.resolve()
            out_dir.mkdir(parents=True, exist_ok=True)
            outs = [out_dir / derived_name(t) for t in tables]
        else:
            out = out_arg.resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            outs = [out]
    else:
        outs = [file_path.parent / derived_name(t) for t in tables]

    written = []
    for t, out in zip(tables, outs):
        with out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in t["rows"]:
                writer.writerow([_to_csv_string(v) for v in row])
        written.append(str(out))

    if close_after:
        if opened_by_script:
            close_document(str(file_path))
        else:
            print(
                "Note: document was already open in Numbers before this script ran; "
                "leaving it open.",
                file=sys.stderr,
            )

    return written


def main():
    parser = argparse.ArgumentParser(
        description="Export tables from a .numbers file to CSV."
    )
    parser.add_argument("path", help="Path to the .numbers file")
    parser.add_argument("--sheet", metavar="SHEET_NAME", help="Sheet name (default: first sheet)")
    parser.add_argument("--table", metavar="TABLE_NAME", help="Table name (default: first table)")
    parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Export every table (of --sheet if given, otherwise of all sheets)",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output CSV path, or directory when exporting multiple tables",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Close the document in Numbers after exporting (only if this script opened it)",
    )
    args = parser.parse_args()

    if args.all_tables and args.table:
        parser.error("--table cannot be combined with --all-tables")

    written = export_csv(
        path=args.path,
        sheet_name=args.sheet,
        table_name=args.table,
        output_path=args.output,
        all_tables=args.all_tables,
        close_after=args.close,
    )
    for path in written:
        print(f"Exported to: {path}")


if __name__ == "__main__":
    main()
