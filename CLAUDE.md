# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A Claude Code skill for reading, analyzing, and modifying Apple Numbers spreadsheets entirely through Numbers.app — no third-party Python packages required. Installed by `./install.sh`, which symlinks `skills/numbers/` into `~/.claude/skills/numbers`. See [README.md](README.md) for full installation instructions.

## Repository Structure

```
numbers.skill/
├── .claude-plugin/
│   └── plugin.json             Plugin manifest (name, version)
├── skills/
│   └── numbers/
│       ├── SKILL.md            Skill definition — instructions Claude receives when activated
│       └── scripts/
│           ├── _common.py      Shared helpers: osascript runner, doc handlers, escaping
│           ├── inspect.py      Structure + preview + formulas as JSON (JXA)
│           ├── export_csv.py   Table(s) to CSV (JXA read, stdlib csv write)
│           ├── export.py       Whole document to xlsx/PDF via native export (AppleScript)
│           ├── set_value.py    Writes literal values to cells (AppleScript)
│           ├── set_formula.py  Writes formulas to cells (AppleScript)
│           └── add_rows.py     Appends data rows to a table (AppleScript)
├── tests/
│   ├── make_fixture.py         Builds a sample two-sheet .numbers file via Numbers.app
│   └── smoke_test.py           End-to-end test of every script against the fixture
├── install.sh                  Symlinks skills/numbers into ~/.claude/skills
└── CLAUDE.md
```

## Development Setup

No dependencies to install. Any Python 3.9+ works (scripts use `from __future__ import annotations` for 3.9 compatibility — keep it when adding modules).

Run the end-to-end smoke test (Numbers.app opens and is visible — expected):

```bash
python3 tests/smoke_test.py          # pass --keep to retain the workdir
```

Or test scripts directly against a real `.numbers` file:

```bash
python3 skills/numbers/scripts/inspect.py ~/Desktop/sample.numbers
python3 skills/numbers/scripts/export_csv.py ~/Desktop/sample.numbers --output /tmp/out.csv
python3 skills/numbers/scripts/set_formula.py ~/Desktop/sample.numbers /tmp/out.numbers \
    --formula B2 "=SUM(A1:A10)"
```

After editing the skill, reload it in a running Claude Code session with `/reload-plugins` (no restart needed).

## Architecture

All Numbers interaction is driven through macOS automation — no file format parsing:

- **`inspect.py` and `export_csv.py`** use **JXA** (`osascript -l JavaScript`) for reading. JXA can batch-read an entire row as a native JS array via `table.rows[r].cells.value()` (and `.formula()`), which is significantly faster than calling AppleScript per cell. The JXA source is a string constant; **file paths and sheet/table names are passed as argv, never interpolated into the source** (names containing quotes must not break or inject into the script).

- **`set_value.py`, `set_formula.py`, and `add_rows.py`** use **AppleScript** (via a temp `.applescript` file) for writing, because its save-to-new-path behavior (`save in POSIX file`) is more reliable for mutations. They share the `build_writer_script()` skeleton in `_common.py`.

- **`export.py`** uses Numbers' native `export ... as Microsoft Excel / PDF` AppleScript command — one operation regardless of document size.

### Conventions in `_common.py` (each guards against a real failure mode)

- **Target Numbers by bundle id** (`application id "com.apple.Numbers"`), never by display name — the app bundle can be renamed on disk.
- **Match documents by path, falling back to name (with and without extension)** — some Numbers builds fail to return the `path` property over AppleEvents, and `name of document` omits the extension when Finder hides it. Never use `whose path is ...` filters: they error if any open document is unsaved.
- **Retry `open` with polling** — a cold-launching Numbers can silently drop the first open event, and `open`'s return value is unreliable (sometimes `missing value`).
- **Every osascript call has a timeout** — Numbers blocks AppleEvents while showing a modal dialog (e.g. the password prompt for an encrypted file); without a timeout the scripts would hang forever.
- **Scripts only close documents they opened** — a window the user already had open is never closed.
- **AppleScript values are rendered with `applescript_value()`/`esc()`** — never `repr()`, which emits single-quoted strings AppleScript cannot parse.

## Editing Guidelines

**`SKILL.md`** is the most important file — it is the prompt Claude receives when the skill activates:
- `description` (frontmatter) controls when Claude auto-activates the skill. Changes here directly affect triggering behavior.
- `allowed-tools` (frontmatter) lists tools Claude can use without per-call permission; it is scoped to `python3` and `osascript` deliberately.

**`inspect.py` JSON output** field names (`sheets`, `tables`, `num_rows`, `num_cols`, `header_rows`, `footer_rows`, `headers`, `preview`, `formulas`) are referenced by name in `SKILL.md` and asserted in `tests/smoke_test.py`. Renaming them requires updating all three.

**Versioning**: keep `version` in sync between `SKILL.md` frontmatter and `.claude-plugin/plugin.json`. Patch for script fixes, minor for new scripts or significant `SKILL.md` changes, major for breaking changes to `inspect.py` JSON output shape.

## Test Checklist

`tests/smoke_test.py` covers all of the following except the encrypted-file case;
run it after any script change:

- [ ] `inspect.py` runs on a multi-sheet file and outputs valid JSON
- [ ] `inspect.py --show-formulas` reports formula cells (incl. cross-sheet)
- [ ] `inspect.py` handles a missing file gracefully (clear error, exit 1)
- [ ] `export_csv.py` exports all cell types and computed formula values
- [ ] `export_csv.py --all-tables` writes one CSV per table
- [ ] `export_csv.py` reports a clear error for unknown sheet/table names
- [ ] `set_value.py` writes typed values and formulas recalculate
- [ ] `set_value.py` rejects values starting with `=`
- [ ] `set_formula.py` writes a formula readable via `inspect.py`
- [ ] `set_formula.py` rejects `--output` equal to input path
- [ ] `add_rows.py` appends rows with correct values
- [ ] `export.py` produces non-empty `.xlsx` and `.pdf`, refuses overwrite without `--force`
- [ ] Scripts reuse an already-open document and never close the user's windows
- [ ] Manual only: an encrypted file fails with a clear error (open retry exhausts → exit 1)
