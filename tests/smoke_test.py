#!/usr/bin/env python3
"""
smoke_test.py — End-to-end smoke test for the Numbers skill scripts.

Drives the real Numbers.app, which opens and is visible while this runs.
Creates a fixture document in a temporary directory under $HOME, exercises
every bundled script against it, and prints PASS/FAIL per check.

Usage:
    python3 tests/smoke_test.py [--keep]

Options:
    --keep    Keep the temporary working directory after the run
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "numbers" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _common import close_document  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))


def run_script(script, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *[str(a) for a in args]],
        capture_output=True,
        text=True,
    )


def inspect(path, *extra):
    r = run_script("inspect.py", path, *extra)
    if r.returncode != 0:
        return r, None
    try:
        return r, json.loads(r.stdout)
    except json.JSONDecodeError:
        return r, None


def total_row(table):
    return next((row for row in table["preview"] if row and row[0] == "Total"), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the workdir afterwards")
    opts = ap.parse_args()

    # Under $HOME, not /tmp — Numbers' path handling is flakier outside user dirs
    workdir = Path(tempfile.mkdtemp(prefix=".numbers-skill-smoke-", dir=Path.home()))
    print(f"Workdir: {workdir}")
    fixture = workdir / "fixture.numbers"
    docs_to_close = [fixture]

    try:
        r = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "make_fixture.py"), str(fixture)],
            capture_output=True,
            text=True,
        )
        check("make_fixture creates fixture", r.returncode == 0 and fixture.exists(), r.stderr.strip())
        if not fixture.exists():
            return

        # --- inspect: structure ---
        r, data = inspect(fixture, "--preview-rows", "10")
        check("inspect exits 0 with JSON", data is not None, r.stderr.strip())
        if data:
            names = [s["name"] for s in data["sheets"]]
            check("inspect sees both sheets", names == ["Data", "Summary"], str(names))
            sales = data["sheets"][0]["tables"][0]
            check("Sales headers", sales["headers"] == ["Name", "Region", "Amount"], str(sales["headers"]))
            check(
                "Sales size",
                sales["num_rows"] == 6 and sales["num_cols"] == 3,
                f"{sales['num_rows']}x{sales['num_cols']}",
            )
            check(
                "header row from table property",
                sales["has_header_row"] is True and sales["header_rows"] == 1,
                f"header_rows={sales.get('header_rows')}",
            )
            check(
                "first data row",
                sales["preview"][0][:2] == ["Alice", "East"] and float(sales["preview"][0][2]) == 100,
                str(sales["preview"][0]),
            )
            total = total_row(sales)
            check(
                "SUM formula evaluates to 360",
                total is not None and abs(float(total[2]) - 360) < 0.001,
                str(total),
            )

        # --- inspect: --show-formulas ---
        r, data = inspect(fixture, "--show-formulas")
        found_sum = found_cross = False
        if data:
            sales = data["sheets"][0]["tables"][0]
            found_sum = any(
                f["cell"] == "C6" and "SUM" in f["formula"].upper()
                for f in sales.get("formulas", [])
            )
            totals = data["sheets"][1]["tables"][0]
            found_cross = any("SUM" in f["formula"].upper() for f in totals.get("formulas", []))
        check("--show-formulas finds C6 SUM", found_sum, r.stderr.strip())
        check("--show-formulas finds cross-sheet formula", found_cross)

        # --- export_csv: single table ---
        sales_csv = workdir / "sales.csv"
        r = run_script("export_csv.py", fixture, "--sheet", "Data", "--table", "Sales", "--output", sales_csv)
        content = sales_csv.read_text() if sales_csv.exists() else ""
        check(
            "export_csv writes CSV",
            r.returncode == 0 and content.startswith("Name,Region,Amount"),
            r.stderr.strip() or content[:80],
        )
        check(
            "export_csv data and computed formula",
            "Alice,East,100" in content and "Total,,360" in content,
            content[:200],
        )

        # --- export_csv: --all-tables ---
        csv_dir = workdir / "csvs"
        r = run_script("export_csv.py", fixture, "--all-tables", "--output", csv_dir)
        files = sorted(p.name for p in csv_dir.glob("*.csv")) if csv_dir.exists() else []
        check("--all-tables exports every table", r.returncode == 0 and len(files) == 2, str(files))

        # --- error handling ---
        r = run_script("export_csv.py", fixture, "--sheet", "Nope")
        check("unknown sheet is a clear error", r.returncode == 1 and "not found" in r.stderr, r.stderr.strip())

        r = run_script("inspect.py", workdir / "missing.numbers")
        check(
            "missing file is a clear error",
            r.returncode == 1 and "not found" in r.stderr.lower(),
            r.stderr.strip(),
        )

        # --- set_value ---
        v1 = workdir / "v1.numbers"
        docs_to_close.append(v1)
        r = run_script(
            "set_value.py", fixture, v1,
            "--sheet", "Data", "--table", "Sales",
            "--value", "A2", "Alicia", "--value", "C2", "999",
        )
        check("set_value exits 0", r.returncode == 0 and v1.exists(), r.stderr.strip())
        r, data = inspect(v1, "--preview-rows", "10")
        if data:
            sales = data["sheets"][0]["tables"][0]
            check(
                "set_value wrote text and number",
                sales["preview"][0][0] == "Alicia" and float(sales["preview"][0][2]) == 999,
                str(sales["preview"][0]),
            )
            total = total_row(sales)
            check(
                "formulas recalculated after set_value",
                total is not None and abs(float(total[2]) - 1259) < 0.001,
                str(total),
            )
        else:
            check("set_value output inspectable", False, r.stderr.strip())

        r = run_script("set_value.py", fixture, workdir / "x.numbers", "--value", "B2", "=SUM(A1:A2)")
        check("set_value rejects '=' input", r.returncode == 1 and "set_formula" in r.stderr, r.stderr.strip())

        # --- set_formula ---
        v2 = workdir / "v2.numbers"
        docs_to_close.append(v2)
        r = run_script(
            "set_formula.py", v1, v2,
            "--sheet", "Data", "--table", "Sales",
            "--formula", "C6", "=AVERAGE(C2:C5)",
        )
        check("set_formula exits 0", r.returncode == 0 and v2.exists(), r.stderr.strip())
        r, data = inspect(v2, "--preview-rows", "10")
        if data:
            sales = data["sheets"][0]["tables"][0]
            total = total_row(sales)
            check(
                "AVERAGE formula evaluates",
                total is not None and abs(float(total[2]) - 314.75) < 0.001,
                str(total),
            )
        else:
            check("set_formula output inspectable", False, r.stderr.strip())

        r = run_script("set_formula.py", fixture, fixture, "--formula", "B2", "=1+1")
        check("set_formula rejects output == input", r.returncode == 1, r.stderr.strip())

        # --- add_rows ---
        v3 = workdir / "v3.numbers"
        docs_to_close.append(v3)
        r = run_script(
            "add_rows.py", v2, v3,
            "--sheet", "Data", "--table", "Sales",
            "--row", '["Eve", "North", 50]',
        )
        check("add_rows exits 0", r.returncode == 0 and v3.exists(), r.stderr.strip())
        r, data = inspect(v3, "--preview-rows", "20")
        if data:
            sales = data["sheets"][0]["tables"][0]
            last = sales["preview"][-1] if sales["preview"] else None
            check(
                "appended row present",
                sales["num_rows"] == 7 and last is not None and last[0] == "Eve" and float(last[2]) == 50,
                f"rows={sales['num_rows']} last={last}",
            )
        else:
            check("add_rows output inspectable", False, r.stderr.strip())

        # --- export (native) ---
        xlsx = workdir / "fixture.xlsx"
        r = run_script("export.py", fixture, "--format", "xlsx", "--output", xlsx)
        check(
            "export to xlsx",
            r.returncode == 0 and xlsx.exists() and xlsx.stat().st_size > 0,
            r.stderr.strip(),
        )
        pdf = workdir / "fixture.pdf"
        r = run_script("export.py", fixture, "--format", "pdf", "--output", pdf)
        check(
            "export to pdf",
            r.returncode == 0 and pdf.exists() and pdf.stat().st_size > 0,
            r.stderr.strip(),
        )
        r = run_script("export.py", fixture, "--format", "pdf", "--output", pdf)
        check("export refuses to overwrite without --force", r.returncode == 1, r.stderr.strip())

    finally:
        for doc in docs_to_close:
            try:
                close_document(str(doc))
            except SystemExit:
                pass

        failed = [name for name, ok in RESULTS if not ok]
        print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
        if opts.keep or failed:
            print(f"Workdir kept: {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
