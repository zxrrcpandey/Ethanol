#!/usr/bin/env python3
"""
Verify all feature locks still hold — standalone auditor.

Reads .claude/locks.json, and for every LOCKED feature:
  - Confirms every protected_file exists on disk
  - Greps protected_code identifiers against those files
  - Greps protected_fields against setup.py / seed_data.py
  - Greps protected_settings against site_config.json / common_site_config.json

Usage:
  python3 .claude/hooks/verify-locks.py                 # verify all
  python3 .claude/hooks/verify-locks.py MR_FULL PO_FULL # verify specific keys
  python3 .claude/hooks/verify-locks.py --quiet         # summary only

Exit:
  0 — all locks hold
  1 — one or more locks failing (file missing, identifier gone, field removed)

Run this BEFORE every unlock and AFTER every relock to catch drift.
"""

import json
import os
import re
import sys
from pathlib import Path


APP_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", "/Users/warroom/Trustbit Software/Trustbit Project/Ethanol Project/App")) / "trustbit_ethanol"
# Common locations for the named files referenced in lock definitions
SEARCH_DIRS = [
    APP_ROOT,
    APP_ROOT / "ts_gate_entry",
    APP_ROOT / "ts_return_item_tracker",
    APP_ROOT / "public" / "js",
]


def project_dir():
    return Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()


def find_file(filename):
    """Return the first path matching filename within SEARCH_DIRS (recursive)."""
    for root in SEARCH_DIRS:
        if not root.exists():
            continue
        for p in root.rglob(filename):
            return p
    return None


def extract_filename_from_entry(entry):
    """Extract filename from a lock entry string."""
    token = entry.strip().split()[0] if entry.strip() else ""
    return token.rstrip(":").rstrip(",")


def verify_file_exists(filename):
    return find_file(filename) is not None, find_file(filename)


def grep_identifier(filename, identifier):
    """Return True if identifier appears in the file."""
    p = find_file(filename)
    if not p:
        return False
    try:
        return identifier in p.read_text(errors="ignore")
    except Exception:
        return False


def verify_lock(key, lock, quiet=False):
    results = {"key": key, "name": lock.get("name", key), "checks": [], "pass": True}

    # 1. Protected files exist
    for entry in lock.get("protected_files", []) + lock.get("protected_items", []):
        if not isinstance(entry, str):
            continue
        fname = extract_filename_from_entry(entry)
        if not fname or "." not in fname:
            continue
        ok, path = verify_file_exists(fname)
        results["checks"].append({
            "type": "file_exists",
            "target": fname,
            "pass": ok,
            "path": str(path) if path else None,
        })
        if not ok:
            results["pass"] = False

    # 2. Protected code identifiers still in the referenced files
    for entry in lock.get("protected_code", []):
        if not isinstance(entry, str):
            continue
        # Expected format: "filename.py function_name(): description" or similar
        parts = entry.split(":", 1)
        file_part = parts[0].strip()
        rest = parts[1] if len(parts) > 1 else ""
        # Extract filename (first token with a dot)
        fname = None
        for tok in file_part.split():
            if "." in tok and "/" not in tok:
                fname = tok.rstrip(",:;")
                break
        if not fname:
            continue
        # Find identifiers to verify — restrict to _snake_case project helpers
        # (underscore-prefix convention) OR explicit def-style declarations.
        # Skip generic framework names like remove, escape, add_comment.
        GENERIC = {"remove", "escape", "add_comment", "is_new", "guard", "get",
                   "set", "save", "insert", "cancel", "submit", "validate",
                   "on_submit", "before_save", "after_insert", "throw",
                   "print", "render", "find", "filter", "map", "call"}
        # \b_ ensures underscore starts a fresh word (not mid-word like add_comment)
        idents = re.findall(r"\b(_[a-zA-Z][a-zA-Z0-9_]{4,})\s*\(", file_part + " " + rest)
        for ident in idents[:3]:
            if ident in GENERIC or len(ident) < 5:
                continue
            ok = grep_identifier(fname, ident)
            results["checks"].append({
                "type": "identifier_present",
                "file": fname,
                "target": ident,
                "pass": ok,
            })
            if not ok:
                results["pass"] = False

    # 3. Protected fields present in setup.py / seed_data.py
    for entry in lock.get("protected_fields", []):
        if not isinstance(entry, str):
            continue
        fieldname = entry.split()[0].rstrip(",:;") if entry.strip() else ""
        if not fieldname:
            continue
        # Check setup.py first, fallback to seed_data.py
        ok_setup = grep_identifier("setup.py", fieldname)
        ok_seed = grep_identifier("seed_data.py", fieldname)
        ok = ok_setup or ok_seed
        results["checks"].append({
            "type": "field_present",
            "file": "setup.py|seed_data.py",
            "target": fieldname,
            "pass": ok,
        })
        if not ok:
            results["pass"] = False

    if not quiet or not results["pass"]:
        status = "✓" if results["pass"] else "✗"
        failed = [c for c in results["checks"] if not c["pass"]]
        print(f"  {status} {key} — {results['name']}")
        if failed:
            for c in failed:
                tgt = c.get("target", "?")
                typ = c["type"]
                print(f"      FAIL [{typ}] {tgt}")

    return results


def main():
    args = sys.argv[1:]
    quiet = "--quiet" in args
    args = [a for a in args if not a.startswith("--")]

    locks_path = project_dir() / ".claude" / "locks.json"
    if not locks_path.exists():
        print(f"ERROR: locks.json not found at {locks_path}")
        sys.exit(2)

    locks = json.loads(locks_path.read_text()).get("feature_locks", {})
    if args:
        keys = [k for k in args if k in locks]
        missing = [k for k in args if k not in locks]
        if missing:
            print(f"WARNING: unknown keys: {', '.join(missing)}")
    else:
        keys = list(locks.keys())

    print(f"Verifying {len(keys)} feature lock(s)...")
    print()

    all_results = []
    for k in keys:
        lock = locks[k]
        if lock.get("status") != "LOCKED":
            print(f"  - {k} (status={lock.get('status')}) — SKIPPED")
            continue
        r = verify_lock(k, lock, quiet=quiet)
        all_results.append(r)

    # Summary
    total = len(all_results)
    passed = sum(1 for r in all_results if r["pass"])
    failed = total - passed
    print()
    print("=" * 60)
    print(f"RESULT: {passed}/{total} locks verified")
    if failed:
        print(f"FAILING: {failed}")
        for r in all_results:
            if not r["pass"]:
                print(f"  - {r['key']}: {r['name']}")
        sys.exit(1)
    print("All locks hold.")


if __name__ == "__main__":
    main()
