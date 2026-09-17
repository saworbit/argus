# CI fast lane and invariant battery implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the CI into an always-on fast lane and a path-filtered
deep lane, and add three hard repo invariants that CI does not
currently check.

**Architecture:** Thin CI, fat tool. All static checks live in one
committed `tools/argus_ci.py` that runs locally in about a second; the
workflows only invoke it. This matches the idiom the tree already
keeps with `argus_reach.py`, `argus_review.py` and
`test_tools_cli.py`.

**Tech Stack:** Python 3 standard library only, GitHub Actions,
`unittest` via the existing `tools/test_tools_cli.py`.

**Spec:** `docs/specs/2026-09-17-ci-fast-lane-design.md`

## Global constraints

- NO NEW DEPENDENCIES. Python 3 standard library only. The tree keeps
  its dependency list short on purpose (corpus.rs refused sqlite for
  this reason) and CI uses first-party actions only.
- NO GAME CODE CHANGES. This plan touches `tools/` and
  `.github/workflows/` and nothing else. `src/`, `game/` and
  `engine/` are read but never written.
- EDITORIAL RULE, enforced across the whole tree: Australian English,
  sentence case headings, and NO em-dashes and NO en-dashes anywhere,
  including in tool output strings, code comments and commit
  messages. Use a spaced hyphen.
- Every check exits 0 on pass and 1 on fail, and prints the reason on
  failure with the defect it guards against named.
- ALL THREE CHECKS MUST PASS ON THE TREE AS IT STANDS. They were each
  verified passing on 2026-09-17. A check that fails on day one is a
  bug in the check, not a finding.
- fteqw pin: `f937b9d88f71fc4429db5fe56c6a98d922711b2e` (2026-06-04).
  This is the commit both the lab rig and CI's cached fteqcc were
  already built from, so pinning is a no-op behaviourally.

---

### Task 1: The tool skeleton and the ship check

**Files:**
- Create: `tools/argus_ci.py`
- Test: `tools/test_tools_cli.py` (append to `TestToolsCLI`)

**Interfaces:**
- Consumes: nothing.
- Produces: `tools/argus_ci.py` with subcommands `ship`, `tapes`,
  `nav`, `all`; flags `--changed-files PATH`, `--base REF`,
  `--commit-msg TEXT`; exit 0 pass, 1 fail. Internal functions later
  tasks extend: `handoff_md5(root) -> str|None`,
  `check_ship(root) -> list[str]`, `read_changes(path, base) ->
  list[tuple[str, str]]`, and a `CHECKS` dict mapping name to
  callable.

- [ ] **Step 1: Write the failing tests**

Append to the `TestToolsCLI` class in `tools/test_tools_cli.py`:

```python
    def test_argus_ci_help(self):
        res = self.run_tool("argus_ci.py", "--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Argus repo invariant battery", res.stdout)

    def test_argus_ci_ship_passes_on_the_tree(self):
        res = self.run_tool("argus_ci.py", "ship")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("ship: ok", res.stdout)

    def test_argus_ci_ship_catches_a_mismatched_pair(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            (root / "game" / "argus" / "progs.dat").write_bytes(b"aaaa")
            (root / "engine" / "argus" / "progs.dat").write_bytes(b"bbbb")
            (root / "CLAUDE.md").write_text(
                "## State at handoff (test)\n\nMD5 "
                "74B87337454200D4D33F80C4663DC5E5\n", encoding="utf-8")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 1)
            self.assertIn("differ", res.stdout)

    def test_argus_ci_ship_catches_a_stale_handoff_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "game" / "argus").mkdir(parents=True)
            (root / "engine" / "argus").mkdir(parents=True)
            for p in ("game", "engine"):
                (root / p / "argus" / "progs.dat").write_bytes(b"aaaa")
            (root / "CLAUDE.md").write_text(
                "## State at handoff (test)\n\nMD5 "
                "00000000000000000000000000000000\n", encoding="utf-8")
            res = self.run_tool("argus_ci.py", "ship", "--root", str(root))
            self.assertEqual(res.returncode, 1)
            self.assertIn("handoff claims", res.stdout)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tools/test_tools_cli.py TestToolsCLI.test_argus_ci_help -v`

Expected: FAIL. `run_tool` shells out to a file that does not exist,
so the return code is 2 and stdout is empty.

- [ ] **Step 3: Write the tool**

Create `tools/argus_ci.py`:

```python
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
        out.append((status, parts[-1].strip()))
    return out


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


CHECKS = {"ship": check_ship}


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify the ship ones pass**

Run:
`python3 tools/test_tools_cli.py TestToolsCLI.test_argus_ci_help TestToolsCLI.test_argus_ci_ship_passes_on_the_tree TestToolsCLI.test_argus_ci_ship_catches_a_mismatched_pair TestToolsCLI.test_argus_ci_ship_catches_a_stale_handoff_hash -v`

Expected: 4 tests, all PASS. `test_argus_ci_ship_passes_on_the_tree`
passing is the claim that matters: the check is green on the real
tree.

- [ ] **Step 5: Verify by hand against the real tree**

Run: `python3 tools/argus_ci.py ship`

Expected: prints `ship: ok`, exit 0. Confirm the hash it is agreeing
with is the handoff's, by running:
`grep -m1 -oE 'MD5 [0-9A-F]{32}' CLAUDE.md`

- [ ] **Step 6: Commit**

```bash
git add tools/argus_ci.py tools/test_tools_cli.py
git commit -m "Add the repo invariant battery with its ship check

The binary and the paper trail can disagree and nothing notices. Both
game/argus/progs.dat and engine/argus/progs.dat are tracked, and four
scratch mod dirs exist precisely because a ladder can modify the
tracked one. The check asserts the two are byte-identical and that
their MD5 is the one CLAUDE.md's handoff section claims."
```

---

### Task 2: The tapes check

**Files:**
- Modify: `tools/argus_ci.py` (add `check_tapes`, register in `CHECKS`)
- Test: `tools/test_tools_cli.py` (append to `TestToolsCLI`)

**Interfaces:**
- Consumes: `read_changes(changed_files, base)` and the `CHECKS` dict
  from Task 1.
- Produces: `check_tapes(root, changed_files=None, base=None,
  commit_msg="", **kw) -> list[str]`, registered as `CHECKS["tapes"]`.

- [ ] **Step 1: Write the failing tests**

Append to `TestToolsCLI`:

```python
    def _changed_file(self, root, lines):
        p = Path(root) / "changed.txt"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(p)

    def test_argus_ci_tapes_allows_additions(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, [
                "A\truns/ab_dm4_newladder1.log",
                "A\truns/shane_dm2_2026-09-17.log",
            ])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)
            self.assertIn("tapes: ok", res.stdout)

    def test_argus_ci_tapes_exempts_mx_and_probe(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, [
                "M\truns/mx_dm2.log",
                "M\truns/probe_dm2.log",
            ])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_tapes_rejects_an_overwritten_ladder_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["M\truns/ab_dm2_doortype2.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)
            self.assertIn("ab_dm2_doortype2.log", res.stdout)
            self.assertIn("append-once", res.stdout)

    def test_argus_ci_tapes_rejects_a_deleted_session_tape(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["D\truns/shane_dm4_2026-08-29_v405.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)
            self.assertIn("deleted", res.stdout)

    def test_argus_ci_tapes_accepts_the_github_status_words(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["modified\truns/ab_dm2_doortype2.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf)
            self.assertEqual(res.returncode, 1)

    def test_argus_ci_tapes_escape_hatch(self):
        with tempfile.TemporaryDirectory() as td:
            cf = self._changed_file(td, ["M\truns/ab_dm4_unstick.log"])
            res = self.run_tool("argus_ci.py", "tapes", "--changed-files", cf,
                                "--commit-msg", "Re-run the ladder [tape-rewrite]")
            self.assertEqual(res.returncode, 0, res.stdout)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`python3 tools/test_tools_cli.py -v -k tapes`

Expected: FAIL. `argparse` accepts `tapes` but `CHECKS["tapes"]` raises
`KeyError`, so the return code is 1 with a traceback rather than the
expected message.

- [ ] **Step 3: Implement the check**

Add to `tools/argus_ci.py`, above the `main` definition:

```python
# --------------------------------------------------------------- tapes

# Ladder tapes and session tapes are evidence. mx_* are matrix probes
# and probe_* are diagnostic probes: both are overwritten by design,
# and together they account for 21 of the 22 modifications in the seven
# weeks to 2026-09-17. The 22nd, e768bbd, is why the escape hatch
# exists.
PROTECTED_TAPE = re.compile(r"^runs/(ab|shane)_.*\.log$")
TAPE_ESCAPE = "[tape-rewrite]"


def check_tapes(root, changed_files=None, base=None, commit_msg="", **_kw):
    """No committed ladder or session tape may be modified or deleted.

    Guards #328, where a run-name collision overwrote a committed tape
    twice in one week and destroyed the evidence it held.
    """
    if TAPE_ESCAPE in (commit_msg or ""):
        return []
    fails = []
    for status, path in read_changes(changed_files, base):
        if status not in ("M", "D"):
            continue
        if not PROTECTED_TAPE.match(path):
            continue
        verb = "modified" if status == "M" else "deleted"
        fails.append(
            "tapes: %s was %s - committed ladder and session tapes are "
            "append-once evidence (#328). If this is deliberate, put %s "
            "in the commit message." % (path, verb, TAPE_ESCAPE))
    return fails
```

Then change the registry line to:

```python
CHECKS = {"ship": check_ship, "tapes": check_tapes}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tools/test_tools_cli.py -v -k tapes`

Expected: 6 tests, all PASS.

- [ ] **Step 5: Verify against real history**

Confirm the exemptions match what the repo actually did. Run:

```bash
git log --since=2026-08-01 --diff-filter=M --pretty=format: --name-only -- 'runs/*.log' \
  | grep 'runs/' | sed 's|runs/||' \
  | awk '{ if ($0 ~ /^(mx_|probe_)/) e++; else o++ } END { print "exempt:", e, " protected:", o }'
```

Expected: `exempt: 21  protected: 1`. The 1 is `ab_dm4_unstick.log`
from `e768bbd`, the legitimate re-run the escape hatch is for.

- [ ] **Step 6: Commit**

```bash
git add tools/argus_ci.py tools/test_tools_cli.py
git commit -m "Refuse to overwrite a committed ladder or session tape

#328 destroyed a committed tape twice in one week through a run-name
collision. A tape is evidence and is append-once. mx_ and probe_ tapes
are exempt because they are overwritten by design, which covers 21 of
the 22 modifications in the seven weeks to 2026-09-17; the 22nd was a
legitimate ladder re-run, so [tape-rewrite] in the commit message
stands the check down."
```

---

### Task 3: The nav check

**Files:**
- Modify: `tools/argus_ci.py` (add `check_nav`, register in `CHECKS`)
- Test: `tools/test_tools_cli.py` (append to `TestToolsCLI`)

**Interfaces:**
- Consumes: the `CHECKS` dict from Task 1.
- Produces: `check_nav(root, **kw) -> list[str]`, registered as
  `CHECKS["nav"]`, plus module constants `NAV_LINK_RE`, `NAV_NODE_RE`
  and `NAV_SLOTS`.

- [ ] **Step 1: Write the failing tests**

Append to `TestToolsCLI`:

```python
    def _nav_qc(self, root, name, body):
        d = Path(root) / "src"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")

    def test_argus_ci_nav_passes_on_the_tree(self):
        res = self.run_tool("argus_ci.py", "nav")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("nav: ok", res.stdout)

    def test_argus_ci_nav_accepts_a_healthy_graph(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_nav_catches_an_over_budget_node(self):
        links = "\n".join("    Argus_NavLink (n0, n%d);" % i
                          for i in range(1, 11))
        nodes = "\n".join("    n%d = Argus_NavNode ('%d 0 0');" % (i, i * 64)
                          for i in range(0, 11))
        back = "\n".join("    Argus_NavLink (n%d, n0);" % i
                         for i in range(1, 11))
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc",
                         nodes + "\n" + links + "\n" + back + "\n")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 1)
            self.assertIn("8-slot", res.stdout)

    def test_argus_ci_nav_catches_a_no_exit_orphan(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    n2 = Argus_NavNode ('128 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
    Argus_NavLink (n1, n2);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 1)
            self.assertIn("no outbound edge", res.stdout)

    def test_argus_ci_nav_counts_typed_links_as_exits(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_toy.qc", """
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('64 0 0');
    n2 = Argus_NavNode ('128 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLink (n1, n0);
    Argus_NavLink (n1, n2);
    Argus_NavLinkRocket (n2, n0);
""")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)

    def test_argus_ci_nav_skips_the_dispatcher(self):
        with tempfile.TemporaryDirectory() as td:
            self._nav_qc(td, "argus_nav_dispatch.qc",
                         "void() Argus_NavLoad = { };\n")
            res = self.run_tool("argus_ci.py", "nav", "--root", td)
            self.assertEqual(res.returncode, 0, res.stdout)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 tools/test_tools_cli.py -v -k nav`

Expected: FAIL with a `KeyError` on `CHECKS["nav"]`.

- [ ] **Step 3: Implement the check**

Add to `tools/argus_ci.py`, above the `main` definition:

```python
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
    r"\b(" + "|".join(NAV_VERBS) + r")\s*\(\s*n(\d+)\s*,\s*n(\d+)\s*\)")
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
```

Then change the registry line to:

```python
CHECKS = {"ship": check_ship, "tapes": check_tapes, "nav": check_nav}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 tools/test_tools_cli.py -v -k nav`

Expected: 7 tests, all PASS. `test_argus_ci_nav_passes_on_the_tree` is
the load-bearing one.

- [ ] **Step 5: Run the whole battery and the whole suite**

Run: `python3 tools/argus_ci.py all --changed-files /dev/null`

Expected: three `ok` lines, exit 0.

Run: `python3 tools/test_tools_cli.py`

Expected: OK, with the pre-existing 23 tests plus the 17 added across
Tasks 1 to 3.

- [ ] **Step 6: Commit**

```bash
git add tools/argus_ci.py tools/test_tools_cli.py
git commit -m "Audit every committed nav graph against the runtime's limits

Ten of eleven graphs had no CI scrutiny at all, because the reach gate
needs a BSP and id content cannot live in CI. The 8-slot budget and
the no-exit orphan test are pure graph properties that need no map.
Both are read from the .qc and never the .json: the json keeps entries
for pairs a later pass reminted under a typed verb, which makes e1m2,
e1m5 and e1m6 look like they carry degree-zero nodes when they do
not."
```

---

### Task 4: The fast lane

**Files:**
- Create: `.github/workflows/fast.yml`
- Modify: `.github/workflows/compile.yml` (remove the `lab` job, add
  the `pull_request` path filter)

**Interfaces:**
- Consumes: `tools/argus_ci.py all --changed-files` from Tasks 1 to 3.
- Produces: two workflows. `fast` runs on every push to main and every
  PR. `compile` runs on every push to main and only on PRs touching
  the deep lane's inputs.

- [ ] **Step 1: Create the fast workflow**

Create `.github/workflows/fast.yml`:

```yaml
name: fast

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  invariants:
    name: repo invariants
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Collect the changed-file list
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          # fetch-depth 0 against a 198 MB .git would cost more than
          # this whole job; one compare call fetches no history at all
          : > changed.txt
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            gh api --paginate \
              "repos/${{ github.repository }}/compare/${{ github.event.pull_request.base.sha }}...${{ github.event.pull_request.head.sha }}" \
              --jq '.files[] | "\(.status)\t\(.filename)"' > changed.txt
          fi
          wc -l < changed.txt

      - name: Run the invariant battery
        run: |
          python3 tools/argus_ci.py all \
            --changed-files changed.txt \
            --commit-msg "${{ github.event.pull_request.title }}"

  lab:
    name: lab test suite (rust)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Cache cargo
        uses: actions/cache@v6
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            tools/argus_mcp/target
          key: cargo-${{ runner.os }}-${{ hashFiles('tools/argus_mcp/Cargo.lock') }}
      - name: Run the lab suite
        # machine-local fixtures (maps_local BSPs, runs/demos) self-skip;
        # the committed runs/*.log regression tapes run in full
        run: cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib

      - name: Run Python developer CLI tests
        run: python3 tools/test_tools_cli.py
```

- [ ] **Step 2: Gate the deep lane**

In `.github/workflows/compile.yml`, replace the `on:` block with:

```yaml
on:
  push:
    branches: [main]
  pull_request:
    # main stays UNFILTERED on purpose. PRs here merge minutes apart,
    # so a merge commit's tree is not always the PR head's tree, and
    # main is the branch every install is cut from.
    paths:
      - 'src/**'
      - 'game/**'
      - 'tools/argus_reach.py'
      - '.github/workflows/compile.yml'
```

Then delete the entire `lab:` job from `compile.yml`, which has moved
to `fast.yml`. Leave `quakec:` and `smoke:` exactly as they are.

- [ ] **Step 3: Verify the YAML parses and the jobs are where expected**

Run:

```bash
python3 -c "
import yaml, sys
for f in ('.github/workflows/fast.yml', '.github/workflows/compile.yml'):
    d = yaml.safe_load(open(f))
    print(f, '->', sorted(d['jobs']))
"
```

Expected:

```
.github/workflows/fast.yml -> ['invariants', 'lab']
.github/workflows/compile.yml -> ['quakec', 'smoke']
```

If `yaml` is not installed, use
`python3 -c "import json,subprocess;print(subprocess.run(['gh','workflow','list'],capture_output=True,text=True).stdout)"`
after pushing instead, and read the job names off the run.

- [ ] **Step 4: Verify the battery runs the way CI will run it**

Run:

```bash
git diff --name-status origin/main...HEAD > /tmp/changed.txt
python3 tools/argus_ci.py all --changed-files /tmp/changed.txt
```

Expected: three `ok` lines, exit 0.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/fast.yml .github/workflows/compile.yml
git commit -m "Split the CI into a fast lane and a path-filtered deep lane

21 per cent of commits since 1 September touch no tested code and
still paid the full 2.5 minutes. The invariants and the lab suite move
to a fast lane that always runs; the QuakeC compile and the 90 s
botmatch now run on PRs only when src, game, the reach gate or the
workflow itself changed. Main stays unfiltered, because PRs here merge
minutes apart so a merge commit's tree is not always the PR head's,
and main is the branch every install is cut from.

Fallout worth having: dependabot cargo bumps stop running a QuakeC
compile and a botmatch to validate a Rust dependency."
```

---

### Task 5: The advisory layer and the toolchain pin

**Files:**
- Modify: `.github/workflows/compile.yml` (`quakec` clone and cache
  key; `smoke` gains a summary step and an artifact upload)

**Interfaces:**
- Consumes: `tools/argus_review.py summary <log>`, already committed.
- Produces: a job summary on every deep-lane run, and a `smoke-tape`
  artifact holding `smoke.log`.

- [ ] **Step 1: Pin the compiler**

In `.github/workflows/compile.yml`, replace the `Cache fteqcc` and
`Build fteqcc from fteqw git` steps with:

```yaml
      - name: Cache fteqcc
        id: cache-fteqcc
        uses: actions/cache@v6
        with:
          path: fteqw/engine/release/fteqcc
          # the SHA is IN the key on purpose: before this, a fixed key
          # meant the compiler was whatever landed in the cache first,
          # and an eviction moved it with nothing said
          key: fteqcc-${{ runner.os }}-f937b9d88f71fc4429db5fe56c6a98d922711b2e

      - name: Build fteqcc from fteqw git
        if: steps.cache-fteqcc.outputs.cache-hit != 'true'
        run: |
          # apt's fteqcc is years too old for this tree (setup_rig.sh
          # gotcha list); build the modern one from source, pinned to
          # the commit the lab rig ships from
          sudo apt-get update -qq
          sudo apt-get install -y -qq build-essential zlib1g-dev
          git clone -q https://github.com/fte-team/fteqw.git
          git -C fteqw checkout -q f937b9d88f71fc4429db5fe56c6a98d922711b2e
          make -C fteqw/engine qcc-rel
```

Note the `--depth 1` is gone: a shallow clone cannot check out an
arbitrary commit.

- [ ] **Step 2: Report the smoke tape instead of discarding it**

In the `smoke` job of `.github/workflows/compile.yml`, after the
`Directed-reach gate (free-content map)` step, add:

```yaml
      - name: Report the smoke tape (advisory, never fails)
        if: always()
        run: |
          # the job already runs a real 90 s botmatch and then throws
          # everything away except "did it crash". This reads it with
          # the lab's own battery. ADVISORY ON PURPOSE: all five
          # committed lqdm2 tapes read zero freezes, but they predate
          # the tick pin, so CI has no baseline at the rate it runs
          # until these accumulate
          {
            echo '## lqdm2 smoke tape'
            echo '```'
            python3 tools/argus_review.py summary smoke.log 2>&1 | head -40 || true
            echo '```'
          } >> "$GITHUB_STEP_SUMMARY"

      - name: Upload the smoke tape
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: smoke-tape
          path: smoke.log
          if-no-files-found: warn
```

- [ ] **Step 3: Verify the reporting command locally against a real tape**

Run: `python3 tools/argus_review.py summary runs/ab_lqdm2_rebirth1.log | head -40`

Expected: a summary block ending with a freeze line reading
`no freezes (6s+ at <20 u/s)`. This is the shape CI will paste into
the job summary.

- [ ] **Step 4: Verify the YAML still parses**

Run:

```bash
python3 -c "
import yaml
d = yaml.safe_load(open('.github/workflows/compile.yml'))
print(sorted(d['jobs']))
print([s.get('name', s.get('uses')) for s in d['jobs']['smoke']['steps']])
"
```

Expected: `['quakec', 'smoke']`, and the smoke step list ends with
`Report the smoke tape (advisory, never fails)` and
`Upload the smoke tape`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/compile.yml
git commit -m "Read the smoke tape, and choose the compiler deliberately

The smoke job runs a real 90 s botmatch and then throws away
everything except whether it crashed. It now reads the tape with
argus_review.py into the job summary and uploads it, advisory only:
all five committed lqdm2 tapes read zero freezes, but they predate the
tick pin, so CI has no baseline at the rate it actually runs until
these accumulate. Ten of them is the bar for promoting the freeze
check to a hard gate.

The fteqw clone is also pinned to f937b9d8, the commit both the lab
rig and CI's cached compiler were already built from. A depth-1 clone
under a fixed cache key meant the compiler was whatever landed in the
cache first."
```

---

### Task 6: Verify the split behaves on real PRs

**Files:** none. This is an observation task and it runs AFTER the
branch is merged, because `paths:` filters are evaluated against the
workflow file on the PR's own branch and the honest test is a fresh PR
against the changed main.

- [ ] **Step 1: Open a docs-only PR**

Create a branch, touch `docs/specs/2026-09-17-ci-fast-lane-design.md`
with a one-line clarification, push and open a PR.

Expected: `fast` runs and completes in about 35 s. `compile` DOES NOT
RUN AT ALL and shows no check on the PR.

- [ ] **Step 2: Open a QC PR**

Create a branch, make a comment-only edit to `src/argus.qc`, push and
open a PR.

Expected: both `fast` and `compile` run. Total wall clock about 146 s,
unchanged, with the three invariants reported in parallel.

- [ ] **Step 3: Confirm the advisory summary rendered**

On the QC PR's `compile` run, open the `smoke` job and confirm the
job summary carries an `## lqdm2 smoke tape` block with a freeze line,
and that a `smoke-tape` artifact is attached to the run.

- [ ] **Step 4: Record the result**

Append the observed numbers to the spec's "Expected effect" table as
an "observed" column, and note whether the deep lane ran on exactly
one of the two PRs.

```bash
git add docs/specs/2026-09-17-ci-fast-lane-design.md
git commit -m "Record what the CI split actually did on two probe PRs"
```

---

## Notes for the implementer

- **The `ship` check runs unconditionally, and that is a deliberate
  simplification of the spec.** The spec proposed gating it on
  `progs.dat` or CLAUDE.md being in the diff, to avoid firing on a QC
  PR whose binary is legitimately stale (the shipped workflow is a QC
  PR then a separate install PR, #399 then #400). That gate turns out
  to be unnecessary: `check_ship` reads only committed files, so on a
  QC-only PR neither binary nor CLAUDE.md has changed, they still
  agree with each other, and it passes. Gating it would have added a
  branch that could only ever suppress a true finding. It fires
  exactly when one of the three files moves without the others, which
  is the defect.
- **Do not add a byte-compare of CI's build against the committed
  one.** It was designed and refuted: the same compiler commit emits
  908230 bytes in CI against 908238 on the lab rig, because the
  shallow clone shortens the version banner and shifts every offset
  after it. Removing `--depth 1` in Task 5 narrows that gap but does
  not close it, and nothing here depends on it closing.
- **`main` is not branch-protected.** Every check in this plan is a
  signal rather than a guarantee until it is. That is one setting and
  it is deliberately out of scope here.
- **The success measure is that the failure rate rises** from its
  current 0.5 per cent. A red build that means something beats a green
  one that never speaks.
