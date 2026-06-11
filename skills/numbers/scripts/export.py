#!/usr/bin/env python3
"""
export.py — Export a whole .numbers document to Excel (.xlsx) or PDF.

Uses Numbers.app's native export, which is a single operation regardless of
table size — much faster than per-cell reads for large documents. All sheets
are included.

Usage:
    python3 export.py <path-to-file.numbers> --format xlsx [options]
    python3 export.py <path-to-file.numbers> --format pdf [options]

Options:
    --format {xlsx,pdf}     Output format (required)
    --output PATH           Output path (default: input filename with new extension)
    --force                 Overwrite the output file if it exists
    --close                 Close the document in Numbers after exporting (only
                            closes documents this script opened)
"""

import argparse
import sys
from pathlib import Path

from _common import APPLESCRIPT_DOC_HANDLERS, esc, run_applescript

FORMATS = {
    "xlsx": ("Microsoft Excel", ".xlsx"),
    "pdf": ("PDF", ".pdf"),
}


def main():
    parser = argparse.ArgumentParser(
        description="Export a .numbers document to Excel (.xlsx) or PDF via Numbers.app."
    )
    parser.add_argument("path", help="Path to the .numbers file")
    parser.add_argument(
        "--format",
        required=True,
        choices=sorted(FORMATS),
        help="Output format",
    )
    parser.add_argument("--output", metavar="PATH", help="Output path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it exists",
    )
    parser.add_argument(
        "--close",
        action="store_true",
        help="Close the document in Numbers after exporting (only if this script opened it)",
    )
    args = parser.parse_args()

    file_path = Path(args.path).expanduser().resolve()
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    as_format, ext = FORMATS[args.format]
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = file_path.with_suffix(ext)

    if output_path == file_path:
        print("ERROR: Output path must differ from input path.", file=sys.stderr)
        sys.exit(1)
    if output_path.exists():
        if not args.force:
            print(
                f"ERROR: Output already exists: {output_path} (pass --force to overwrite)",
                file=sys.stderr,
            )
            sys.exit(1)
        output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    close_block = ""
    if args.close:
        close_block = (
            "    if openedByScript then\n"
            '        tell application id "com.apple.Numbers" to close sourceDoc saving no\n'
            "    end if\n"
        )

    script = f"""{APPLESCRIPT_DOC_HANDLERS}

on run
    set openResult to my openTargetDoc("{esc(str(file_path))}", "{esc(file_path.name)}", "{esc(file_path.stem)}")
    set sourceDoc to item 1 of openResult
    set openedByScript to item 2 of openResult

    tell application id "com.apple.Numbers"
        export sourceDoc to POSIX file "{esc(str(output_path))}" as {as_format}
    end tell
{close_block}end run
"""

    # Native export of a large document can take a while
    run_applescript(script, timeout=600)
    print(f"Exported to: {output_path}")


if __name__ == "__main__":
    main()
