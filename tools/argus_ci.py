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

    The two halves have different reach. The byte-identical comparison
    reads only the two tracked progs.dat files, so it runs anywhere,
    including CI. The handoff-hash comparison also needs CLAUDE.md,
    which is machine-local (.gitignore's **/claude*.md) and has never
    existed in a CI checkout - found only by running CI, after this
    passed locally and three reviews. On a tree without CLAUDE.md the
    hash half is skipped outright rather than reported as a failure:
    an absent file is expected here, not a defect. A CLAUDE.md that
    IS present and still malformed, or present and disagreeing with
    the binary, keeps failing exactly as before - that machine has the
    paper trail and it is wrong.
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
    if not (root / "CLAUDE.md").is_file():
        return PartialOk(
            "ship: ok (progs.dat pair matches; handoff hash not checked, "
            "CLAUDE.md is machine-local)")
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


class GitDiffError(Exception):
    """git diff itself failed; the caller turns this into a hard failure."""


def read_changes(changed_files=None, base=None, root=None):
    """[(status_letter, path)] for the diff under test."""
    if changed_files:
        text = Path(changed_files).read_text(encoding="utf-8",
                                             errors="replace")
    else:
        ref = base or "origin/main"
        proc = subprocess.run(
            ["git", "diff", "--name-status", "%s...HEAD" % ref],
            capture_output=True, text=True, cwd=str(root or ROOT))
        if proc.returncode != 0:
            raise GitDiffError(
                "tapes: git diff against %s failed - %s"
                % (ref, proc.stderr.strip() or "no stderr"))
        text = proc.stdout
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


class Skipped(list):
    """A check ran with nothing to check, which is not a clean pass.

    Still a list (empty, so still falsy for "no failures"), but main()
    recognises the type and prints a "skipped" line instead of "ok" -
    a vacuous pass would be false confidence, and this stays honest
    about it while still keeping the return protocol a plain list.
    """
    def __init__(self, reason):
        super().__init__()
        self.reason = reason


class PartialOk(list):
    """A check passed, but only part of it could run here.

    Still an empty list (a genuine pass, not a failure), but main()
    prints the check's own wording instead of the generic "<name>: ok"
    line, so a reader is told plainly which half ran rather than
    mistaking a narrower check for the full one.
    """
    def __init__(self, message):
        super().__init__()
        self.message = message


def check_tapes(root, changed_files=None, base=None, commit_msg="", **_kw):
    """No committed ladder or session tape may be modified, deleted, or renamed.

    Guards #328, where a run-name collision overwrote a committed tape
    twice in one week and destroyed the evidence it held.
    """
    if TAPE_ESCAPE in (commit_msg or ""):
        return []
    try:
        changes = read_changes(changed_files, base, root)
    except GitDiffError as exc:
        return [str(exc)]
    if changed_files is not None and not changes and base is None:
        # A push to main (not a pull request) gives fast.yml an empty
        # changed.txt and no --base to fall back on: there is no
        # changed-file information to check against, and "ok" here
        # would be a vacuous pass on exactly the class of push #328
        # was. Skip honestly instead of claiming a clean result.
        return Skipped("no changed-file list")
    fails = []
    for status, path in changes:
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
            "in the commit message or the pull request title."
            % (path, verb, TAPE_ESCAPE))
    return fails


# ----------------------------------------------------------------- nav

# READ THE .qc, NEVER THE .json. The runtime compiles the .qc and the
# two files do not agree: the json's `links` array keeps entries for
# pairs a later navgen pass reminted under a typed verb, so reading it
# makes e1m2, e1m5 and e1m6 look like they carry degree-zero nodes when
# they do not. #330 reached the same conclusion from the other side.
NAV_VERBS = ("Argus_NavLinkJump", "Argus_NavLinkSprint",
             "Argus_NavLinkRocket", "Argus_NavLinkLift",
             "Argus_NavLinkSwim", "Argus_NavLinkTrain",
             "Argus_NavLinkDoor", "Argus_NavLink")
NAV_LINK_RE = re.compile(
    r"\b(" + "|".join(NAV_VERBS)
    + r")\s*\(\s*n(\d+)\s*,\s*n(\d+)(?:\s*,\s*[-+0-9.]+)?\s*\)")
NAV_NODE_RE = re.compile(r"\bArgus_NavNode\s*\(")
NAV_SLOTS = 8


def check_nav(root, **_kw):
    """Every committed graph obeys the two limits the runtime enforces.

    Guards v3.88, where links past the 8-slot budget were dropped
    silently at load with only a dprint to say so, and v3.70, where
    n150 carried inbound teleporter links and no exit of any kind, so
    every route starting there died instantly.
    """
    fails = []
    for p in sorted((root / "src").glob("argus_nav_*.qc")):
        if p.name == "argus_nav_dispatch.qc":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        nodes = len(NAV_NODE_RE.findall(text))
        if nodes == 0:
            continue
        out = collections.Counter()
        for _verb, src, _dst in NAV_LINK_RE.findall(text):
            out[int(src)] += 1
        over = sorted(i for i, c in out.items() if c > NAV_SLOTS)
        if over:
            fails.append(
                "nav: %s nodes %s exceed the %d-slot runtime budget - "
                "Argus_NavLink drops the surplus silently (v3.88)"
                % (p.name, over[:8], NAV_SLOTS))
        orphans = [i for i in range(nodes) if i not in out]
        if orphans:
            fails.append(
                "nav: %s nodes %s have no outbound edge of any type - "
                "every route starting there dies instantly (v3.70)"
                % (p.name, orphans[:8]))
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
        if isinstance(got, Skipped):
            print("%s: skipped (%s)" % (name, got.reason))
        elif isinstance(got, PartialOk):
            print(got.message)
        elif got:
            fails.extend(got)
        else:
            print("%s: ok" % name)
    for f in fails:
        print(f)
    return 1 if fails else 0


CHECKS = {"ship": check_ship, "tapes": check_tapes, "nav": check_nav}


if __name__ == "__main__":
    sys.exit(main())
