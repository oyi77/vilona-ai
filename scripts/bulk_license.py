"""Bulk-register Vilona AI licenses via the admin API.

Reads a CSV file with one MT5 account per row and POSTs to /license/register.
Uses only the existing admin endpoint — no new server code, no DB access.

CSV columns (header required):
    account,plan,slots,expires,note
Only `account` is mandatory; the rest fall back to plan=basic, slots=1,
expires=None (lifetime), note="".

Usage:
    vilona_LICENSE_URL=http://localhost:8301 \
    vilona_LICENSE_ADMIN_TOKEN=<secret> \
    python scripts/bulk_license.py --apply users.csv

Or:
    python scripts/bulk_license.py --apply --url http://localhost:8301 \
        --token <secret> users.csv

Without `--apply`, runs in DRY-RUN mode and prints what would be POSTed.
Token is read only from `vilona_LICENSE_ADMIN_TOKEN` env or `--token`; the
script never auto-loads `.env`.

Skips blank/comment lines, rejects duplicate accounts, validates ISO expiry.
Continues on per-row errors and prints a summary.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REQUIRED_COLS = {"account"}
OPTIONAL_COLS = {"plan", "slots", "expires", "note"}
ALLOWED_COLS = REQUIRED_COLS | OPTIONAL_COLS


def _validate_expiry(value: str, lineno: int, errs: list[str]) -> str:
    if not value:
        return ""  # lifetime
    # Accept YYYY-MM-DD (treated as UTC end-of-day) or full RFC-3339 / ISO-8601.
    fmts = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S")
    for fmt in fmts:
        try:
            datetime.strptime(value, fmt)
            return value
        except ValueError:
            pass
    errs.append(f"line {lineno}: invalid ISO-8601 expires={value!r}")
    return value


def _parse_row(row: dict, lineno: int, seen: set[str], errs: list[str]) -> dict:
    account = (row.get("account") or "").strip()
    if not account or account.startswith("#"):
        return {}
    if account in seen:
        errs.append(f"line {lineno}: duplicate account={account}")
        return {}
    seen.add(account)

    body: dict = {"account": account}
    if v := (row.get("plan") or "").strip():
        body["plan"] = v
    if v := (row.get("slots") or "").strip():
        try:
            n = int(v)
            if n <= 0:
                errs.append(f"line {lineno}: slots must be >= 1, got {n}")
                return {}
            body["slots"] = n
        except ValueError:
            errs.append(f"line {lineno}: invalid integer slots={v!r}")
            return {}
    if v := (row.get("expires") or "").strip():
        _validate_expiry(v, lineno, errs)
        body["expires"] = v
    if v := (row.get("note") or "").strip():
        body["note"] = v
    return body


def _check_csv(path: str) -> tuple[list[dict], list[str]]:
    """Parse + validate CSV; return (rows, errors) without making HTTP calls."""
    errs: list[str] = []
    rows: list[dict] = []
    seen: set[str] = set()
    if not Path(path).is_file():
        errs.append(f"file not found: {path}")
        return rows, errs

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            errs.append("empty CSV (no header)")
            return rows, errs
        header = set(reader.fieldnames)
        missing = REQUIRED_COLS - header
        if missing:
            errs.append(f"missing required column(s): {', '.join(sorted(missing))}")
            return rows, errs
        unknown = header - ALLOWED_COLS
        if unknown:
            errs.append(f"unknown column(s): {', '.join(sorted(unknown))}")
        for lineno, row in enumerate(reader, start=2):
            body = _parse_row(row, lineno, seen, errs)
            if body:
                rows.append(body)
    return rows, errs


def _run(args: argparse.Namespace) -> int:
    rows, errs = _check_csv(args.csv_path)
    if errs:
        for e in errs:
            print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if not rows:
        print("No valid rows to process.")
        return 0

    if not args.apply:
        print(f"DRY-RUN: would POST {len(rows)} license(s) to {args.url}/license/register")
        for b in rows:
            print(f"  account={b['account']} plan={b.get('plan', 'basic')} "
                  f"slots={b.get('slots', 1)} expires={b.get('expires') or 'lifetime'}")
        print("\nRe-run with --apply to execute.")
        return 0

    if not args.token:
        print("ERROR: admin token required (--token or vilona_LICENSE_ADMIN_TOKEN)", file=sys.stderr)
        return 2

    ok, fail = 0, 0
    for b in rows:
        try:
            r = requests.post(
                f"{args.url.rstrip('/')}/license/register",
                json=b,
                headers={"X-Admin-Token": args.token},
                timeout=10,
            )
            if r.status_code == 200:
                ok += 1
                print(f"OK   account={b['account']}")
            else:
                fail += 1
                print(f"FAIL account={b['account']} -> {r.status_code} {r.text[:120]}", file=sys.stderr)
        except requests.RequestException as e:
            fail += 1
            print(f"FAIL account={b['account']}: {e}", file=sys.stderr)

    print(f"\nDone. ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


def _self_check() -> int:
    """Verify parser behaviour without any network calls."""
    import tempfile

    good = "account,plan,slots,expires,note\n111,basic,1,2026-12-31,ok\n222\n"
    dup = "account\n111\n111\n"
    bad_expiry = "account,expires\n333,31-12-2026\n"
    blank = "account\n   \n# comment\n"
    bad_slots = "account,slots\n444,0\n"
    bad_header = "foo,bar\n555,1\n"

    with tempfile.TemporaryDirectory() as tmp:
        cases = {
            "good.csv": (good, 0, 2),
            "dup.csv": (dup, 1, 1),
            "bad_expiry.csv": (bad_expiry, 1, 1),
            "blank.csv": (blank, 0, 0),
            "bad_slots.csv": (bad_slots, 1, 0),
            "bad_header.csv": (bad_header, 1, 0),
        }
        for name, (content, want_errs, want_rows) in cases.items():
            p = Path(tmp) / name
            p.write_text(content)
            rows, errs = _check_csv(str(p))
            status = "OK  " if (len(errs) == want_errs and len(rows) == want_rows) else "FAIL"
            print(f"{status} {name}: rows={len(rows)} (want {want_rows}) errs={len(errs)} (want {want_errs})")
            if status == "FAIL":
                for e in errs:
                    print(f"     {e}")
                return 1
    print("self-check passed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_path", nargs="?", help="CSV file with account[,plan,slots,expires,note] rows")
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually POST to the server. Without this flag, dry-run only.",
    )
    ap.add_argument(
        "--url",
        default=os.getenv("vilona_LICENSE_URL", "http://127.0.0.1:8301"),
        help="License server base URL (default: local admin endpoint)",
    )
    ap.add_argument(
        "--token",
        default=os.getenv("vilona_LICENSE_ADMIN_TOKEN", ""),
        help="Admin token (X-Admin-Token header); required for --apply",
    )
    ap.add_argument(
        "--self-check", action="store_true",
        help="Run internal parser self-check and exit.",
    )
    args = ap.parse_args()

    if args.self_check:
        return _self_check()

    if not args.csv_path:
        ap.error("csv_path required (or use --self-check)")
    if args.apply and args.url.startswith("http://") and "127.0.0.1" not in args.url and "localhost" not in args.url:
        print(f"WARNING: --apply over plaintext HTTP to non-local host {args.url!r} — token will be sent in clear. "
              "Use HTTPS in production.", file=sys.stderr)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
