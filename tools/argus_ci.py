#!/usr/bin/env python3
"""Argus repo invariant battery: the static checks CI runs, and that
you can run yourself in about a second before pushing.

Each check guards a defect that has already happened in this tree, and
each is named on the check that catches it. Exit 0 means every
applicable check passed; exit 1 names what did not.

usage:
  argus_ci.py all   [--changed-files F] [--base REF] [--commit-msg M]
  argus_ci.py ship                 the binary and the paper trail agree
  argus_ci.py eol                  committed LF text blobs contain no CRLF
  argus_ci.py tapes [--changed-files F]   evidence is append-once
  argus_ci.py nav                  runtime limits, QC/JSON edges, banners and cover hops
  argus_ci.py links                tracked documentation paths and anchors resolve
  argus_ci.py dashes               tracked prose and sources contain no en or em dashes
"""
import argparse
import collections
import hashlib
import html
import json
from html.parser import HTMLParser
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

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


# ------------------------------------------------------------------ eol

def check_eol(root, **_kw):
    """LF-designated text must be LF in Git, not only in the worktree.

    Hosting APIs can create blobs directly and bypass Git's clean filter.
    ``git ls-files --eol`` reports the index blob separately from the
    checked-out file, so this catches that drift even when checkout has
    already presented a normalized LF worktree.
    """
    proc = subprocess.run(
        ["git", "ls-files", "--eol", "-z"],
        capture_output=True, cwd=str(root))
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        return ["eol: git ls-files failed - %s" % (detail or "no stderr")]

    fails = []
    for record in proc.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
        except ValueError:
            return ["eol: git ls-files returned a malformed record"]
        fields = metadata.decode("ascii", errors="replace").split()
        index_eol = fields[0] if fields else ""
        attributes = " ".join(fields[2:])
        if "eol=lf" not in attributes or index_eol not in ("i/crlf", "i/mixed"):
            continue
        path = raw_path.decode("utf-8", errors="replace")
        fails.append(
            "eol: %s is stored with CRLF in Git despite eol=lf - "
            "normalize the committed blob, not only the worktree" % path)
    return fails


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
PROTECTED_TAPE = re.compile(r"^runs/(ab|shane)_.*(?:\.log|\.nav\.json)$")
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

# The runtime compiles QC. Check its limits and require the sidecar to
# describe those same emitted edges, including typed families (#653).
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
    """Every committed graph obeys runtime limits and artifact parity.

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
        try:
            from argus_nav_artifacts import validate_pair
            document = json.loads(Path(str(p) + '.json').read_text(encoding='utf-8'))
            validate_pair(text, document)
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            fails.append(f'nav: {p.name}: {error}')
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


# ---------------------------------------------------------------- links


def markdown_prose(text):
    """Exclude fenced examples and HTML comments from link/heading inspection."""
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if match:
            run = match[1]
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            lines.append("")
        else:
            lines.append(line if fence is None else "")
    return re.sub(r"<!--.*?-->", lambda m: "\n" * m[0].count("\n"), "\n".join(lines), flags=re.S)


class _HtmlAnchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value is not None and (key == "id" or tag == "a" and key == "name"):
                self.anchors.add(value)


def _setext_text(line):
    """A structural block before an underline is not a setext heading."""
    if not line.strip() or line.expandtabs(4).startswith("    "):
        return False
    if re.match(r"^ {0,3}(?:#{1,6}(?:\s|$)|>|(?:[-+*]|\d{1,9}[.)])(?:\s|$))", line):
        return False
    return not re.fullmatch(r" {0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})", line)


def markdown_anchors(text):
    """GitHub-style heading slugs (including duplicates) and explicit HTML IDs."""
    prose = markdown_prose(text)
    parser = _HtmlAnchors()
    parser.feed(prose)
    used = set()
    previous = ""
    for line in prose.splitlines():
        heading = re.match(r"^ {0,3}(?:>\s*)*#{1,6}\s+(.+?)\s*#*\s*$", line)
        title = heading[1] if heading else None
        if re.fullmatch(r" {0,3}(?:=+|-+)\s*", line) and _setext_text(previous):
            title = previous.strip()
        if title is not None:
            title = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", title)
            title = html.unescape(re.sub(r"<[^>]*>", "", title)).lower().strip()
            slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
            candidate, suffix = slug, 0
            while candidate in used:
                suffix += 1
                candidate = slug + "-" + str(suffix)
            used.add(candidate)
        previous = line
    return used | parser.anchors


def _link_destination(text):
    text = text.lstrip()
    if text.startswith("<"):
        end = text.find(">")
        return text[1:end] if end >= 0 else ""
    depth, escaped, end = 0, False, 0
    for end, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif char.isspace() and depth == 0:
            break
    else:
        end = len(text)
    return re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~\\])", r"\1", text[:end])


class _HtmlLinks(HTMLParser):
    """Raw-HTML src, srcset and href values, so a README banner's <picture>
    sources are held to the same rule as Markdown image syntax."""

    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        for key, value in attrs:
            if not value:
                continue
            if key in ("src", "href"):
                self.found.append((line, value.strip()))
            elif key == "srcset":
                for candidate in value.split(","):
                    if candidate.strip():
                        self.found.append((line, candidate.split()[0]))


def markdown_links(text):
    """Read inline/image destinations, reference definitions and raw-HTML
    src/srcset/href values, excluding code."""
    prose = markdown_prose(text)
    prose = re.sub(r"(`+).*?\1", lambda m: "\n" * m[0].count("\n"), prose, flags=re.S)
    for match in re.finditer(r"!?\[(?:\\.|[^\]\\\n])*\]\(", prose):
        yield prose.count("\n", 0, match.start()) + 1, _link_destination(prose[match.end():])
    for match in re.finditer(r"(?m)^ {0,3}\[[^\]\n]+\]:[ \t]*(.*)$", prose):
        yield prose.count("\n", 0, match.start()) + 1, _link_destination(match[1])
    parser = _HtmlLinks()
    parser.feed(prose)
    parser.close()
    yield from parser.found


def check_links(root, **_kw):
    """Check tracked Markdown relative paths/fragments; leave archived plans alone."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                             capture_output=True, text=True, encoding="utf-8")
    if tracked.returncode:
        return ["links: git ls-files failed: " + tracked.stderr.strip()]
    paths = [Path(name) for name in tracked.stdout.split("\0") if name
             and Path(name).suffix.lower() == ".md"
             and not name.startswith(("backups/", "docs/plans/"))]
    fails, anchors = [], {}
    for relative in paths:
        source = root/relative
        if not source.is_file():
            fails.append("links: tracked Markdown is missing: " + str(relative))
            continue
        for line, destination in markdown_links(source.read_text(encoding="utf-8")):
            destination = html.unescape(destination)
            if not destination or destination.startswith(("/", "\\")):
                continue
            try:
                parsed = urlsplit(destination)
            except ValueError:
                fails.append(f"links: {relative}:{line}: invalid destination {destination}")
                continue
            if parsed.scheme or parsed.netloc:
                continue
            target = (source.parent/unquote(parsed.path)).resolve() if parsed.path else source.resolve()
            location = f"links: {relative}:{line}: {destination}"
            if not target.exists():
                fails.append(location + " (missing path)")
            elif parsed.fragment:
                if target.is_dir():
                    target = target/"README.md"
                if not target.is_file():
                    fails.append(location + " (fragment has no document)")
                    continue
                if target not in anchors:
                    anchors[target] = markdown_anchors(target.read_text(encoding="utf-8", errors="replace"))
                if unquote(parsed.fragment) not in anchors[target]:
                    fails.append(location + " (missing fragment)")
    return fails


def check_dashes(root, **_kw):
    """Enforce the two-codepoint editorial rule on tracked prose and code."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root,
                             capture_output=True, text=True, encoding="utf-8")
    if tracked.returncode:
        return ["dashes: git ls-files failed: " + tracked.stderr.strip()]
    fails = []
    for name in tracked.stdout.split("\0"):
        path = Path(name)
        if not name or not (path.suffix.lower() == ".md"
                            or name.startswith("src/") and path.suffix == ".qc"
                            or name.startswith("tools/") and path.suffix == ".py"
                            or name.startswith("tools/argus_mcp/src/")):
            continue
        try:
            text = (root/path).read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            fails.append(f"dashes: {name}: cannot read tracked text: {error}")
            continue
        for number, line in enumerate(text.splitlines(), 1):
            found = sorted({f"U+{ord(c):04X}" for c in line if c in "\u2013\u2014"})
            if found:
                fails.append(f"dashes: {name}:{number}: {', '.join(found)}: "
                             f"no en or em dashes; use words or punctuation: {line}")
    return fails


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="argus_ci.py",
        description="Argus repo invariant battery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("check", choices=["all", *CHECKS])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--changed-files")
    ap.add_argument("--base")
    ap.add_argument("--commit-msg", default="")
    args = ap.parse_args(argv)
    root = Path(args.root)

    names = list(CHECKS) if args.check == "all" else [args.check]
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


CHECKS = {"ship": check_ship, "eol": check_eol,
          "tapes": check_tapes, "nav": check_nav, "links": check_links,
          "dashes": check_dashes}


if __name__ == "__main__":
    sys.exit(main())
