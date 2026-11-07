#!/usr/bin/env python3
"""Keep every launcher language table in parity with the offline build's UI.

This replaces the language-file hunks the offline patches used to carry.
Upstream re-translates `launcher/lang/*.json` constantly, so a static patch
against those files failed on almost every re-translation. The patches in
`offline/patches/` now touch Rust only; right after `git am`, the release
workflow runs this script, which applies the key operations stored as data in
`lang-overrides.json` (next to this script):

- drop every key listed under "delete", whenever a table has it;
- add every missing key under "add", using that language's entry from the
  data. A language the data does not know (a new upstream language) falls
  back to the "en" entry, which is the English key itself; the launcher's
  lookup also falls back to English, so the fallback still renders right.

The key sets of all tables stay identical, the invariant upstream's own files
keep. Idempotent: a second run rewrites nothing. Tables are rewritten with
`json.dumps(..., ensure_ascii=False, indent=2)` plus a trailing newline, which
round-trips upstream's own layout byte for byte.

Usage: python3 offline/lang-sync.py [--lang-dir launcher/lang] [--overrides FILE]
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Apply the offline build's language-table key operations.")
    parser.add_argument("--lang-dir", default="launcher/lang",
                        help="language table directory, relative to the repo root")
    parser.add_argument("--overrides", default=str(here / "lang-overrides.json"),
                        help="the add/delete key data (default: beside this script)")
    parser.add_argument("--root", default=str(here.parent),
                        help="the repo root (default: the parent of offline/)")
    args = parser.parse_args()

    lang_dir = Path(args.root).resolve() / args.lang_dir
    if not lang_dir.is_dir():
        print(f"lang-sync: no language directory at {lang_dir}", file=sys.stderr)
        return 1
    tables = sorted(lang_dir.glob("*.json"))
    if not tables:
        print(f"lang-sync: no language tables inside {lang_dir}", file=sys.stderr)
        return 1
    data = json.loads(Path(args.overrides).read_text(encoding="utf-8"))
    adds: dict = data.get("add", {})
    deletes: list = data.get("delete", [])

    touched = 0
    keysets = set()
    for path in tables:
        text = path.read_text(encoding="utf-8")
        table = json.loads(text)
        dropped = [key for key in deletes if key in table]
        added = 0
        for key, translations in adds.items():
            if key in table:
                continue
            table[key] = translations.get(path.stem, translations.get("en", key))
            added += 1
        if dropped or added:
            for key in dropped:
                del table[key]
            path.write_text(
                json.dumps(table, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            touched += 1
            print(f"lang-sync: {path.name}: -{len(dropped)} +{added}")
        keysets.add(frozenset(table))
    if len(keysets) != 1:
        print("lang-sync: language tables left with differing key sets",
              file=sys.stderr)
        return 1
    print(f"lang-sync: {touched} table(s) updated; all {len(tables)} tables in parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
