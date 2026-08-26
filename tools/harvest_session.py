#!/usr/bin/env python3
"""Harvest a play session into the runs/ archive: tape plus demo.

The pipeline's ingestion step. A session launched from C:\\argus with
-condebug writes qconsole.log to the working directory, and a session
launched with `+record <name> <map>` writes <name>.dem to the game
dir. This stamps both into runs/ under one stem so the tape and its
demo stay paired:

    runs/shane_<map>_<date>[_<tag>].log
    runs/demos/shane_<map>_<date>[_<tag>].dem

The map is read from the tape's last confirmed SpawnServer (a refused
spawn falls through to the fallback map - the mx_lqdm2 lesson). Runs
are never overwritten: a stem collision appends b, c, ...

Usage: python tools/harvest_session.py [--tag v373] [--dry-run]
"""
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMEDIR = ROOT / "engine" / "argus"


def session_map(text):
    """Last SpawnServer that was not refused."""
    confirmed = None
    pending = None
    for line in text.splitlines():
        m = re.match(r"SpawnServer: (\w+)", line)
        if m:
            pending = m.group(1).lower()
            continue
        if line.startswith("Couldn't spawn server maps/"):
            pending = None
    if pending:
        confirmed = pending
    return confirmed or "unknown"


def unique(path):
    if not path.exists():
        return path
    for suffix in "bcdefgh":
        cand = path.with_stem(path.stem + suffix)
        if not cand.exists():
            return cand
    raise SystemExit(f"too many collisions for {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="", help="build tag, e.g. v373")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # the launch template cds to engine\ so the log usually lands
    # there; agent-driven launches from the root land it at the root.
    # Freshest wins.
    cands = [p for p in (ROOT / "qconsole.log",
                         ROOT / "engine" / "qconsole.log") if p.exists()]
    if not cands:
        raise SystemExit("no qconsole.log at C:/argus or C:/argus/engine "
                         "- was the session launched with -condebug?")
    tape = max(cands, key=lambda p: p.stat().st_mtime)
    text = tape.read_text(encoding="latin-1", errors="replace")
    mapname = session_map(text)
    stamp = dt.date.today().isoformat()
    tag = f"_{args.tag}" if args.tag else ""
    stem = f"shane_{mapname}_{stamp}{tag}"

    dest_log = unique(ROOT / "runs" / f"{stem}.log")
    moves = [(tape, dest_log, "copy")]

    demo_dir = ROOT / "runs" / "demos"
    demos = sorted(GAMEDIR.glob("*.dem"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    # the freshest demo belongs to this session; older ones (previous
    # sessions never harvested) keep their own age-ordered stems
    for i, d in enumerate(demos):
        if d.stat().st_mtime < tape.stat().st_mtime - 3 * 3600:
            break  # stale leftovers stay put
        suffix = "" if i == 0 else f"_extra{i}"
        moves.append((d, unique(demo_dir / f"{dest_log.stem}{suffix}.dem"),
                      "move"))

    for src, dst, verb in moves:
        print(f"{verb}: {src} -> {dst}")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if verb == "move":
                shutil.move(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
    if not moves:
        print("nothing to harvest")
    print(f"map={mapname} stem={dest_log.stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
