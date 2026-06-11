#!/usr/bin/env python3
"""
inspect.py — Output the structure of a .numbers file as JSON via Numbers.app.

Requires macOS with Numbers.app installed. Numbers is launched automatically.

Usage:
    python3 inspect.py <path-to-file.numbers> [--preview-rows N] [--show-formulas] [--close]

Options:
    --preview-rows N   Number of data rows to include in output (default: 3)
    --show-formulas    Scan every cell and report formulas per table
    --close            Close the document in Numbers after inspecting (only
                       closes documents this script opened, never the user's)
"""

import argparse
import json
import sys
from pathlib import Path

from _common import OSASCRIPT_TIMEOUT, JXA_PROLOGUE, close_document, run_osascript

# JXA — batch .value()/.formula() calls read entire rows at once, which is far
# faster than per-cell AppleScript. The file path and options are passed as
# argv, never interpolated into the script source.
_JXA = JXA_PROLOGUE + r"""
function run(argv) {
    const filePath = argv[0];
    const previewRows = parseInt(argv[1] || '3');
    const showFormulas = argv[2] === '1';

    const opened = openDoc(filePath);
    if (!opened.doc) {
        return JSON.stringify({error: 'Could not open ' + filePath + ' in Numbers. ' +
            'If the file is password-protected, remove the password ' +
            '(File > Password > Remove Password) and retry.'});
    }
    const doc = opened.doc;

    function colLetter(n) {  // 0 -> A, 25 -> Z, 26 -> AA
        let s = '';
        n += 1;
        while (n > 0) {
            const r = (n - 1) % 26;
            s = String.fromCharCode(65 + r) + s;
            n = Math.floor((n - 1) / 26);
        }
        return s;
    }

    const result = {
        _opened_by_script: opened.openedByScript,
        path: filePath,
        sheet_count: doc.sheets.length,
        sheets: []
    };

    for (let si = 0; si < doc.sheets.length; si++) {
        const sheet = doc.sheets[si];
        const sheetData = { index: si, name: sheet.name(), tables: [] };

        for (let ti = 0; ti < sheet.tables.length; ti++) {
            const table = sheet.tables[ti];
            const numRows = table.rows.length;
            const numCols = table.columns.length;
            const headerRows = table.headerRowCount();
            const footerRows = table.footerRowCount();

            const headers = [];
            if (headerRows > 0 && numRows > 0) {
                const rawHeaders = table.rows[0].cells.value();
                for (let c = 0; c < rawHeaders.length; c++) {
                    const v = rawHeaders[c];
                    headers.push((v !== null && v !== undefined) ? String(v) : '');
                }
            }

            const startRow = headerRows;
            const endRow = Math.min(startRow + previewRows, numRows - footerRows);

            const preview = [];
            for (let r = startRow; r < endRow; r++) {
                const raw = table.rows[r].cells.value();
                preview.push(raw.map(cellValue));
            }

            const tableData = {
                index: ti,
                name: table.name(),
                num_rows: numRows,
                num_cols: numCols,
                header_rows: headerRows,
                footer_rows: footerRows,
                has_header_row: headerRows > 0,
                headers: headers,
                preview: preview
            };

            if (showFormulas) {
                const formulas = [];
                for (let r = 0; r < numRows; r++) {
                    const rowFormulas = table.rows[r].cells.formula();
                    for (let c = 0; c < rowFormulas.length; c++) {
                        const f = rowFormulas[c];
                        if (f !== null && f !== undefined && f !== '') {
                            formulas.push({ cell: colLetter(c) + (r + 1), formula: String(f) });
                        }
                    }
                }
                tableData.formulas = formulas;
            }

            sheetData.tables.push(tableData);
        }

        result.sheets.push(sheetData);
    }

    return JSON.stringify(result, null, 2);
}
"""


def inspect_document(
    path: str,
    preview_rows: int = 3,
    show_formulas: bool = False,
    close_after: bool = False,
) -> dict:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    if file_path.suffix.lower() != ".numbers":
        print(f"WARNING: File does not have a .numbers extension: {file_path}", file=sys.stderr)

    result = run_osascript(
        [
            "osascript", "-l", "JavaScript", "-e", _JXA,
            str(file_path), str(preview_rows), "1" if show_formulas else "0",
        ],
        # The full-table formula scan can be slow on large tables
        timeout=600 if show_formulas else OSASCRIPT_TIMEOUT,
    )

    if result.returncode != 0:
        print(f"ERROR: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    output = result.stdout.strip()
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        print(f"ERROR: Unexpected output from Numbers:\n{output}", file=sys.stderr)
        sys.exit(1)

    if "error" in data:
        print(f"ERROR: {data['error']}", file=sys.stderr)
        sys.exit(1)

    opened_by_script = data.pop("_opened_by_script", True)
    if close_after:
        if opened_by_script:
            close_document(str(file_path))
        else:
            print(
                "Note: document was already open in Numbers before this script ran; "
                "leaving it open.",
                file=sys.stderr,
            )

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a .numbers file and output its structure as JSON."
    )
    parser.add_argument("path", help="Path to the .numbers file")
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=3,
        metavar="N",
        help="Number of data rows to include in preview (default: 3)",
    )
    parser.add_argument(
        "--show-formulas",
        action="store_true",
        help="Scan every cell and report formulas per table",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Close the document in Numbers after inspecting (only if this script opened it)",
    )
    args = parser.parse_args()

    result = inspect_document(args.path, args.preview_rows, args.show_formulas, args.close)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
