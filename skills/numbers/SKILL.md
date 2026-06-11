---
name: numbers
description: Read, analyze, and manipulate Apple Numbers spreadsheets (.numbers files). Use when the user mentions a .numbers file, wants to inspect/edit/export Numbers data, modify cells, write formulas, read table values, or work with any Apple Numbers document — even if they just provide a path ending in .numbers.
version: 2.1.0
allowed-tools: Bash(python3:*), Bash(osascript:*), Read, Write, Glob
---

# Apple Numbers Skill

This skill reads, analyzes, and modifies Apple Numbers spreadsheets entirely through
Numbers.app via AppleScript and JXA (JavaScript for Automation). No third-party
packages are required — only macOS with Numbers.app installed and Python 3 (stdlib).

**Numbers.app will open and be briefly visible during every operation.** This is
expected behavior.

## Requirements

- macOS with Numbers.app installed
- Python 3 (stdlib only — no pip installs)

## Core Workflow

Every task follows the same three-phase sequence: **inspect → modify → save**.

### Phase 1: Inspect First, Always

Run `inspect.py` before reading or modifying anything. It opens the file in Numbers,
reads the structure, and returns JSON describing all sheets, tables, headers, and a
data preview.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/inspect.py" /path/to/file.numbers
```

Sample output:

```json
{
  "path": "/path/to/file.numbers",
  "sheet_count": 2,
  "sheets": [
    {
      "index": 0,
      "name": "Sheet 1",
      "tables": [
        {
          "index": 0,
          "name": "Table 1",
          "num_rows": 10,
          "num_cols": 5,
          "header_rows": 1,
          "footer_rows": 0,
          "has_header_row": true,
          "headers": ["Name", "Q1", "Q2", "Q3", "Q4"],
          "preview": [
            ["Alice", 100, 200, 150, 300],
            ["Bob", 80, 120, 90, 210]
          ]
        }
      ]
    }
  ]
}
```

Use `name` fields (not indexes) in all subsequent operations — names are stable;
indexes shift if sheets or tables are added or removed.

- `--preview-rows N` shows more data rows (default: 3). Footer rows are excluded.
- `--show-formulas` scans every cell and adds a `formulas` list per table, e.g.
  `[{"cell": "B10", "formula": "=SUM(B2:B9)"}]`. Use it to audit or explain
  existing formulas; `preview` always shows computed values, not formula text.
- `--close` closes the document afterwards (only if this script opened it).

### Phase 2: Modify with the Bundled Scripts

Prefer the bundled scripts — they handle document reuse, saving, escaping, and
Numbers quirks. Reach for handwritten AppleScript only when no script covers the
operation (see "Custom AppleScript" below).

| Task                              | Script          |
| --------------------------------- | --------------- |
| Write literal values to cells     | `set_value.py`  |
| Write formulas to cells           | `set_formula.py`|
| Append rows of data               | `add_rows.py`   |
| Export a table to CSV             | `export_csv.py` |
| Export whole document to xlsx/PDF | `export.py`     |

All write scripts take `input output` paths, save to the new path, and **never
overwrite the original**.

### Phase 3: Derive Output Path

If the user has not specified an output path, derive one by appending `_modified`
before the extension:

```python
from pathlib import Path
original = Path("/path/to/file.numbers")
output = original.with_stem(original.stem + "_modified")
# → /path/to/file_modified.numbers
```

Always tell the user the exact path of the saved file.

## Script Reference

### set_value.py — literal values

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/set_value.py" \
  input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --value B2 42.5 \
  --value C2 "Updated" \
  --value D2 true
```

- `--value` auto-types: integers and decimals become numbers, `true`/`false`
  become booleans, everything else is text. Repeat for multiple cells.
- `--text CELL VALUE` forces text (use for values like `007` or literal `true`).
- Values starting with `=` are rejected — use `set_formula.py` for formulas.

### set_formula.py — formulas

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/set_formula.py" \
  input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --formula B10 "=SUM(B2:B9)" \
  --formula C10 "=AVERAGE(C2:C9)"
```

- `--formula` can be repeated. Cell addresses use A1 notation.
- For cross-sheet references use `::`, e.g. `=SUM(Sheet2::Table1::B:B)`.

### add_rows.py — append data rows

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/add_rows.py" \
  input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --row '["Eve", "North", 50]' \
  --row '["Frank", "South", 75]'
```

- Each `--row` is a JSON array: strings, numbers, booleans, or `null` (leaves
  the cell empty). The table grows to fit; columns are added if a row is wider.

### export_csv.py — table(s) to CSV

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/export_csv.py" \
  /path/to/file.numbers --sheet "Sheet 1" --table "Table 1" --output out.csv
```

- `--sheet`/`--table` default to the first sheet/table.
- `--all-tables` exports every table (one CSV each); `--output` is then a directory.
- `--output` defaults to a filename derived from the file, sheet, and table names.

### export.py — whole document to Excel or PDF

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/export.py" /path/to/file.numbers --format xlsx
python3 "${CLAUDE_SKILL_DIR}/scripts/export.py" /path/to/file.numbers --format pdf --output out.pdf
```

Uses Numbers' native export — a single operation regardless of table size, so
prefer it over `export_csv.py` for very large documents or when the user wants
Excel/PDF. All sheets are included. `--force` overwrites an existing output.

### Common flags

- Write scripts close the saved document by default; pass `--no-close` to keep
  it open in Numbers.
- Read scripts leave the document open by default; pass `--close` to close it.
- No script ever closes a window the user already had open.

## Custom AppleScript for Everything Else

For operations the scripts don't cover (renaming sheets/tables, deleting rows,
creating tables), write targeted AppleScript via `osascript`. Follow these rules —
each one guards against a real failure mode:

1. **Target Numbers by bundle id** — `tell application id "com.apple.Numbers"`.
   The app's display name can differ from "Numbers" (renamed bundle), which
   breaks name-based targeting.
2. **Never use `first document whose path is ...`** — the `whose` filter errors
   if *any* open document is unsaved. Loop over `documents` with a `try` block
   instead. Also note `name of document` may omit the file extension.
3. **Never overwrite the original** — save to a new path with `save in POSIX file`.
4. **AppleScript strings are double-quoted only** — escape `"` as `\"` and `\`
   as `\\`. Single quotes are not string delimiters in AppleScript.

**Writing literal values:**

```bash
osascript << 'EOF'
tell application id "com.apple.Numbers"
  open POSIX file "/path/to/file.numbers"
  tell front document
    tell sheet "Sheet 1"
      tell table "Table 1"
        set value of cell "B2" to 42.5
        set value of cell "C2" to "Updated"
        set value of cell "D2" to true
      end tell
    end tell
    save in POSIX file "/path/to/output.numbers"
  end tell
end tell
EOF
```

**Creating sheets and tables:**

```bash
osascript << 'EOF'
tell application id "com.apple.Numbers"
  open POSIX file "/path/to/file.numbers"
  tell front document
    make new sheet with properties {name:"Summary"}
    tell sheet "Summary"
      -- new sheets come with a default "Table 1"; add more if needed:
      make new table with properties {name:"Totals", row count:5, column count:3, header row count:1}
    end tell
    save in POSIX file "/path/to/output.numbers"
  end tell
end tell
EOF
```

**For generated scripts** (many cells, conditional logic), build the AppleScript
in Python and render every value with a helper — never `repr()`, which produces
single-quoted strings that AppleScript cannot parse:

```python
import subprocess

def as_applescript(value):
    """Render a Python value as an AppleScript literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'

cells = [("B2", 42), ("C2", "Updated"), ("D2", True)]

cell_lines = "\n".join(
    f'        set value of cell "{addr}" to {as_applescript(val)}'
    for addr, val in cells
)

script = f"""
tell application id "com.apple.Numbers"
  open POSIX file "/path/to/file.numbers"
  tell front document
    tell sheet "Sheet 1"
      tell table "Table 1"
{cell_lines}
      end tell
    end tell
    save in POSIX file "/path/to/output.numbers"
  end tell
end tell
"""

result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}")
else:
    print("Saved to: /path/to/output.numbers")
```

## Reading Formula Results

After saving a file with formulas, run `inspect.py` (with `--preview-rows`) on the
output file to read the computed values — Numbers recalculates on save, and the
`preview` values reflect the evaluated result. To see the formula text itself,
add `--show-formulas`.

## Closing Documents

Scripts only close documents they themselves opened, so a window the user already
had open is never touched. To close everything:

```bash
osascript -e 'tell application id "com.apple.Numbers" to close every document saving no'
```

## Known Limitations

- **Numbers.app is always required.** There is no headless path — Numbers opens
  visually for every read and write operation.
- **Encrypted files cannot be opened.** The scripts fail with a clear error after
  retrying; tell the user to open the file in Numbers, remove the password
  (File > Password > Remove Password), save, then retry.
- **Slow for large tables.** Cell reads go row-by-row; for very large documents
  prefer `export.py` (native export, one operation).
- **Formula strings must begin with `=`.** Numbers identifies formulas by the
  leading equals sign; a string without it stores literal text — and conversely,
  any string value starting with `=` becomes a formula.
- **Footer rows.** `add_rows.py` appends after footer rows if the table has any.
