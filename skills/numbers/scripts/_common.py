"""Shared helpers for the Numbers skill scripts.

All Numbers interaction goes through osascript (AppleScript or JXA), using a
few hard-won conventions:

- Numbers is targeted by bundle id (com.apple.Numbers), never by display name —
  the app bundle can be renamed on disk, which breaks name-based targeting.
- Documents are matched by path when the `path` property is readable, falling
  back to filename — some Numbers builds fail to return `path` over
  AppleEvents entirely.
- `open` is retried with polling: when Numbers is cold-launching, the first
  open event can be silently dropped, and its return value is unreliable.
- Every osascript call has a timeout: Numbers blocks AppleEvents while showing
  a modal dialog (e.g. the password prompt for an encrypted file), which would
  otherwise hang the calling script forever.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

NUMBERS_BUNDLE_ID = "com.apple.Numbers"

OSASCRIPT_TIMEOUT = 120

TIMEOUT_HINT = (
    "Numbers did not respond within {timeout} seconds. It is likely showing a "
    "modal dialog. For password-protected files: open the file in Numbers, "
    "remove the password (File > Password > Remove Password), save, and retry."
)

OPEN_FAILED_HINT = (
    "Could not open the file in Numbers. If the file is password-protected, "
    "remove the password (File > Password > Remove Password) and retry."
)


def run_osascript(args: list[str], timeout: int = OSASCRIPT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run an osascript command with a timeout, exiting clearly if Numbers hangs."""
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"ERROR: {TIMEOUT_HINT.format(timeout=timeout)}", file=sys.stderr)
        sys.exit(1)


def run_applescript(script: str, timeout: int = OSASCRIPT_TIMEOUT) -> None:
    """Execute an AppleScript from a temp file; print its stdout; exit on failure."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".applescript", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        tmp_path = f.name

    try:
        result = run_osascript(["osascript", tmp_path], timeout=timeout)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"ERROR: AppleScript failed:\n{result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    if result.stdout.strip():
        print(result.stdout.strip())


def esc(s: str) -> str:
    """Escape a string for use inside an AppleScript double-quoted literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def applescript_value(value) -> str:
    """Render a Python value as an AppleScript literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return f'"{esc(str(value))}"'


def sheet_table_refs(sheet_name: str | None, table_name: str | None) -> tuple[str, str]:
    sheet_ref = f'sheet "{esc(sheet_name)}"' if sheet_name else "sheet 1"
    table_ref = f'table "{esc(table_name)}"' if table_name else "table 1"
    return sheet_ref, table_ref


# AppleScript handlers shared by the write/export scripts. findTargetDoc matches
# by path when readable, by document name otherwise — the name may be reported
# with or without the file extension (Finder's hide-extension attribute), so
# both forms are accepted. openTargetDoc retries the open because a
# cold-launching Numbers can drop the first open event; it returns
# {document, openedByScript}.
APPLESCRIPT_DOC_HANDLERS = """
on findTargetDoc(targetPath, targetName, targetStem)
    tell application id "com.apple.Numbers"
        repeat with d in documents
            set matched to false
            try
                if (POSIX path of (path of d)) is targetPath then set matched to true
            on error
                try
                    set docName to name of d
                    if docName is targetName or docName is targetStem then set matched to true
                end try
            end try
            if matched then return d
        end repeat
    end tell
    return missing value
end findTargetDoc

on openTargetDoc(targetPath, targetName, targetStem)
    set theDoc to my findTargetDoc(targetPath, targetName, targetStem)
    if theDoc is not missing value then return {theDoc, false}
    tell application id "com.apple.Numbers"
        activate
        repeat with attempt from 1 to 5
            open (POSIX file targetPath)
            repeat 10 times
                set theDoc to my findTargetDoc(targetPath, targetName, targetStem)
                if theDoc is not missing value then exit repeat
                delay 0.2
            end repeat
            if theDoc is not missing value then exit repeat
        end repeat
    end tell
    if theDoc is missing value then ¬
        error "Could not open " & targetPath & " in Numbers. If the file is password-protected, remove the password (File > Password > Remove Password) and retry."
    return {theDoc, true}
end openTargetDoc
"""


def build_writer_script(
    input_path: str,
    output_path: str,
    body: str,
    close_after: bool,
) -> str:
    """AppleScript skeleton shared by the write scripts: open or reuse the input
    document, run `body` inside it, save to the output path, and optionally
    close — but only if this script opened the document, so a window the user
    already had open is left alone."""
    out = Path(output_path)
    close_block = ""
    if close_after:
        close_block = f"""
    if openedByScript then
        -- After save-as the document carries the output path/name
        set savedDoc to my findTargetDoc("{esc(output_path)}", "{esc(out.name)}", "{esc(out.stem)}")
        if savedDoc is not missing value then
            tell application id "com.apple.Numbers" to close savedDoc saving no
        end if
    end if
"""

    inp = Path(input_path)
    return f"""{APPLESCRIPT_DOC_HANDLERS}

on run
    set openResult to my openTargetDoc("{esc(input_path)}", "{esc(inp.name)}", "{esc(inp.stem)}")
    set sourceDoc to item 1 of openResult
    set openedByScript to item 2 of openResult

    tell application id "com.apple.Numbers"
        tell sourceDoc
{body}
        end tell
        -- Save to the output path (never overwrites the input)
        save sourceDoc in POSIX file "{esc(output_path)}"
    end tell
{close_block}end run
"""


def close_document(path: str) -> None:
    """Close the document for `path` in Numbers without saving. No-op if not open."""
    p = Path(path)
    script = f"""{APPLESCRIPT_DOC_HANDLERS}

on run
    set theDoc to my findTargetDoc("{esc(str(p))}", "{esc(p.name)}", "{esc(p.stem)}")
    if theDoc is not missing value then
        tell application id "com.apple.Numbers" to close theDoc saving no
    end if
end run
"""
    run_osascript(["osascript", "-e", script])


# JXA equivalents of the document handlers, prepended to the read scripts.
# Same conventions: bundle-id targeting, path-then-name matching (the document
# name may omit the file extension), open retry.
JXA_PROLOGUE = r"""
function findDoc(app, targetPath, targetName, targetStem) {
    for (let i = 0; i < app.documents.length; i++) {
        const d = app.documents[i];
        let p = null;
        try { p = d.path(); } catch (e) {}
        if (p !== null && p !== undefined) {
            if (String(p) === targetPath) return d;
            continue;
        }
        try {
            const n = d.name();
            if (n === targetName || n === targetStem) return d;
        } catch (e) {}
    }
    return null;
}

function openDoc(filePath) {
    const app = Application('com.apple.Numbers');
    app.activate();
    const fileName = filePath.split('/').pop();
    const fileStem = fileName.replace(/\.[^.]*$/, '');
    let doc = findDoc(app, filePath, fileName, fileStem);
    if (doc) return {app: app, doc: doc, openedByScript: false};
    for (let attempt = 0; attempt < 5 && !doc; attempt++) {
        try { app.open(Path(filePath)); } catch (e) {}
        for (let poll = 0; poll < 10 && !doc; poll++) {
            doc = findDoc(app, filePath, fileName, fileStem);
            if (!doc) delay(0.2);
        }
    }
    return {app: app, doc: doc, openedByScript: true};
}

function cellValue(v) {
    if (v === null || v === undefined) return null;
    if (v instanceof Date) return v.toISOString();
    return v;
}
"""

JXA_OPEN_ERROR = (
    "Could not open {path} in Numbers. If the file is password-protected, "
    "remove the password (File > Password > Remove Password) and retry."
)
