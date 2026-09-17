#!/usr/bin/env python3
"""Argus repo invariant battery: the static checks CI runs, and that
you can run yourself in about a second before pushing.

Each check guards a defect that has already happened in this tree, and
each is named on the check that catches it. Exit 0 means every
applicable check passed; exit 1 names what did not.

usage:
  argus_ci.py all   [--changed-files F] [--base REF] [--commit-msg M]
  argus_ci.py ship                 the binary and the paper trail agree
  argus_ci.py tapes [--changed-files F]   evidence is append-once
  argus_ci.py nav                  graphs obey the runtime's limits
"""
import argparse
import collections
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- ship

def handoff_md5(root):
    """The single MD5 claimed by CLAUDE.md's current handoff section.

    Returns None when the section is missing or does not hold exactly
    one hash, which the caller reports rather than guessing at.
    """
    p = root / "CLAUDE.md"
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    i = text.find("## State at handoff")
    if i < 0:
        return None
    j = text.find("\n## ", i + 5)
    block = text[i:j] if j > 0 else text[i:]
    found = re.findall(r"MD5\s+([0-9A-Fa-f]{32})", block)
    return found[0].upper() if len(found) == 1 else None


def check_ship(root, **_kw):
    """game/ and engine/ progs.dat agree, and match the handoff hash.

    Guards a ladder leaving an experimental build installed in
    engine/argus - the hazard argus_bis, argus_bb, argus_bb2 and
    argus_ctl exist to route around - and a handoff hash drifting from
    the binary, which the v4.18 note records happening.
    """
    a = root / "game" / "argus" / "progs.dat"
    b = root / "engine" / "argus" / "progs.dat"
    for p in (a, b):
        if not p.is_file():
            return ["ship: %s is missing" % p]
    da, db = a.read_bytes(), b.read_bytes()
    ha = hashlib.md5(da).hexdigest().upper()
    hb = hashlib.md5(db).hexdigest().upper()
    if da != db:
        return ["ship: game/argus/progs.dat (%s) and "
                "engine/argus/progs.dat (%s) differ - an experimental "
                "build is probably still installed" % (ha, hb)]
    claimed = handoff_md5(root)
    if claimed is None:
        return ["ship: CLAUDE.md's handoff section does not hold exactly "
                "one MD5, so the binary cannot be checked against it"]
    if claimed != ha:
        return ["ship: progs.dat is %s but the CLAUDE.md handoff claims "
                "%s - one of the two is stale" % (ha, claimed)]
    return []


# --------------------------------------------------------------- diff

# GitHub's compare API says "modified"; git says "M". Accept both.
_STATUS = {"added": "A", "modified": "M", "removed": "D",
           "renamed": "R", "copied": "C", "changed": "M"}


def read_changes(changed_files=None, base=None):
    """[(status_letter, path)] for the diff under test."""
    if changed_files:
        text = Path(changed_files).read_text(encoding="utf-8",
                                             errors="replace")
    else:
        ref = base or "origin/main"
        text = subprocess.run(
            ["git", "diff", "--name-status", "%s...HEAD" % ref],
            capture_output=True, text=True, cwd=str(ROOT)).stdout
    out = []
    for line in text.splitlines():
        parts = [p for p in line.split("\t") if p]
        if len(parts) < 2:
            continue
        status = parts[0].strip()
        status = _STATUS.get(status.lower(), status[:1].upper())
        # For renames, preserve the old path (what was destroyed)
        path = parts[1].strip() if status == "R" and len(parts) >= 3 else parts[-1].strip()
        out.append((status, path))
    return out


# --------------------------------------------------------------- tapes

# Ladder tapes and session tapes are evidence. mx_* are matrix probes
# and probe_* are diagnostic probes: both are overwritten by design,
# and together they account for 21 of the 22 modifications in the seven
# weeks to 2026-09-17. The 22nd, e768bbd, is why the escape hatch
# exists.
PROTECTED_TAPE = re.compile(r"^runs/(ab|shane)_.*\.log$")
TAPE_ESCAPE = "[tape-rewrite]"


def check_tapes(root, changed_files=None, base=None, commit_msg="", **_kw):
    """No committed ladder or session tape may be modified, deleted, or renamed.

    Guards #328, where a run-name collision overwrote a committed tape
    twice in one week and destroyed the evidence it held.
    """
    if TAPE_ESCAPE in (commit_msg or ""):
        return []
    fails = []
    for status, path in read_changes(changed_files, base):
        if status not in ("M", "D", "R"):
            continue
        if not PROTECTED_TAPE.match(path):
            continue
        if status == "M":
            verb = "modified"
        elif status == "D":
            verb = "deleted"
        else:  # status == "R"
            verb = "renamed"
        fails.append(
            "tapes: %s was %s - committed ladder and session tapes are "
            "append-once evidence (#328). If this is deliberate, put %s "
            "in the commit message." % (path, verb, TAPE_ESCAPE))
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="argus_ci.py",
        description="Argus repo invariant battery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("check", choices=["all", "ship", "tapes", "nav"])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--changed-files")
    ap.add_argument("--base")
    ap.add_argument("--commit-msg", default="")
    args = ap.parse_args(argv)
    root = Path(args.root)

    names = ["ship", "tapes", "nav"] if args.check == "all" else [args.check]
    fails = []
    for name in names:
        fn = CHECKS[name]
        got = fn(root, changed_files=args.changed_files, base=args.base,
                 commit_msg=args.commit_msg)
        if got:
            fails.extend(got)
        else:
            print("%s: ok" % name)
    for f in fails:
        print(f)
    return 1 if fails else 0


CHECKS = {"ship": check_ship, "tapes": check_tapes}


if __name__ == "__main__":
    sys.exit(main())
