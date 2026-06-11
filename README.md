# numbers.skill

A Claude Code skill for reading, analyzing, and modifying Apple Numbers spreadsheets.

## What it does

Mention any `.numbers` file in conversation and Claude automatically:

- Inspects the file structure — sheets, tables, headers, and a data preview
- Reads and summarizes data from specific tables
- Reads existing formulas (`--show-formulas`)
- Modifies cell values (text, numbers, booleans)
- Writes formulas (`=SUM`, `=AVERAGE`, cross-sheet references, etc.)
- Appends rows of data to tables
- Exports tables to CSV, or whole documents to Excel (.xlsx) and PDF

All operations go through Numbers.app via AppleScript — no third-party packages required.

> **Note:** Numbers.app opens and is briefly visible during every operation. This is a macOS limitation; there is no headless path for `.numbers` files.

## Requirements

- macOS with Numbers.app installed
- Python 3 (built into macOS — no `pip install` needed)
- Claude Code

## Installation

Symlink the skill directory into `~/.claude/skills/`. Changes to the repo are picked
up automatically without reinstalling.

```bash
mkdir -p ~/.claude/skills
ln -s "/path/to/numbers.skill/skills/numbers" ~/.claude/skills/numbers
```

No restart required. If Claude Code is already running, run `/reload-plugins` to pick
up the skill immediately. The skill is also invocable directly as `/numbers`.

## Usage

Just describe what you want — Claude handles the rest:

```
Look at ~/Documents/budget.numbers and tell me the totals in column C
```
```
Export the Sales table from Q3_report.numbers to CSV
```
```
Convert tracker.numbers to Excel
```
```
In tracker.numbers, update Alice's Q3 value to 320 and add a SUM formula at the bottom
```
```
Add a row for the new hire to staff.numbers
```

Claude runs `inspect.py` first to understand the file structure, then performs the
requested operation and saves any changes to a new file — the original is never
overwritten.

## Bundled scripts

The skill includes six Python scripts Claude uses internally. You can also run them
directly.

### inspect.py — show file structure

```bash
python3 skills/numbers/scripts/inspect.py ~/Desktop/file.numbers
python3 skills/numbers/scripts/inspect.py ~/Desktop/file.numbers --preview-rows 10
python3 skills/numbers/scripts/inspect.py ~/Desktop/file.numbers --show-formulas
```

Outputs JSON describing every sheet, table, column headers, and a data preview.
`--show-formulas` adds the formula text of every formula cell.

### set_value.py — write literal values

```bash
python3 skills/numbers/scripts/set_value.py input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --value B2 42.5 --value C2 "Updated" --value D2 true
```

Values are auto-typed (numbers, booleans, text); `--text` forces text.

### set_formula.py — write formulas

```bash
python3 skills/numbers/scripts/set_formula.py input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --formula B10 "=SUM(B2:B9)" \
  --formula C10 "=AVERAGE(C2:C9)"
```

### add_rows.py — append rows

```bash
python3 skills/numbers/scripts/add_rows.py input.numbers output.numbers \
  --sheet "Sheet 1" --table "Table 1" \
  --row '["Eve", "North", 50]'
```

### export_csv.py — export tables to CSV

```bash
python3 skills/numbers/scripts/export_csv.py ~/Desktop/file.numbers
python3 skills/numbers/scripts/export_csv.py ~/Desktop/file.numbers --sheet "Summary" --table "Totals"
python3 skills/numbers/scripts/export_csv.py ~/Desktop/file.numbers --all-tables --output ~/Desktop/csvs
```

### export.py — export the document to Excel or PDF

```bash
python3 skills/numbers/scripts/export.py ~/Desktop/file.numbers --format xlsx
python3 skills/numbers/scripts/export.py ~/Desktop/file.numbers --format pdf
```

Uses Numbers' native export — fast even for very large documents.

## Testing

An end-to-end smoke test builds a fixture spreadsheet through Numbers.app and
exercises every script against it (Numbers opens visibly while it runs):

```bash
python3 tests/smoke_test.py
```

## Limitations

- **Numbers.app required** — opens visually for every read and write operation.
- **No encrypted files** — remove the password first via File > Password > Remove Password.
- **Large tables are slow over cell reads** — use `export.py` (native export) for big documents.

## Contributing

See [CLAUDE.md](CLAUDE.md) for development setup, editing guidelines, and the test
checklist.
