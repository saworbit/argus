#!/usr/bin/env python3
"""Minimal id PAK extractor for the Argus toolchain.

Usage:
    python pak_extract.py <pak> [<pak> ...] --list
    python pak_extract.py <pak> [<pak> ...] --out <dir> <name> [<name> ...]

Names match case-insensitively against the basename (e.g. "dm4.bsp"
matches "maps/dm4.bsp"). Later paks override earlier ones, matching
Quake's own load order.
"""

import argparse
import os
import struct
import sys


def read_directory(path):
    entries = []
    with open(path, "rb") as f:
        magic, dir_ofs, dir_len = struct.unpack("<4sii", f.read(12))
        if magic != b"PACK":
            raise SystemExit(f"{path}: not a PAK file (magic {magic!r})")
        f.seek(dir_ofs)
        for _ in range(dir_len // 64):
            raw_name, ofs, length = struct.unpack("<56sii", f.read(64))
            name = raw_name.split(b"\0", 1)[0].decode("latin-1")
            entries.append((name, ofs, length))
    return entries


def main():
    ap = argparse.ArgumentParser(
        usage="pak_extract.py <pak> [<pak> ...] (--list | --out <dir> <name> [<name> ...])")
    # one positional bucket, split by extension below: argparse cannot
    # hold two variable-length positionals around an optional, and the
    # documented CLI puts the names AFTER --out <dir>
    ap.add_argument("files", nargs="+",
                    help="pak files, then names to extract (or use --names)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--names", nargs="*", default=[])
    args = ap.parse_intermixed_args()

    paks = [f for f in args.files if f.lower().endswith(".pak")]
    names = [f for f in args.files if not f.lower().endswith(".pak")]
    if not paks:
        ap.error("no .pak files given")

    wanted = {n.lower() for n in names} | {n.lower() for n in args.names}
    if not args.list and not wanted:
        ap.error("nothing to extract: give names after --out <dir>, or --names")
    found = {}

    for pak in paks:
        for name, ofs, length in read_directory(pak):
            if args.list:
                print(f"{pak}: {name} ({length} bytes)")
            base = os.path.basename(name.replace("\\", "/")).lower()
            if base in wanted:
                found[base] = (pak, name, ofs, length)

    if args.list:
        return

    if not args.out:
        raise SystemExit("--out required when extracting")
    os.makedirs(args.out, exist_ok=True)

    missing = wanted - set(found)
    for base, (pak, name, ofs, length) in sorted(found.items()):
        with open(pak, "rb") as f:
            f.seek(ofs)
            data = f.read(length)
        dest = os.path.join(args.out, base)
        with open(dest, "wb") as f:
            f.write(data)
        print(f"extracted {name} from {os.path.basename(pak)} -> {dest} ({length} bytes)")

    if missing:
        print(f"NOT FOUND: {', '.join(sorted(missing))}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
