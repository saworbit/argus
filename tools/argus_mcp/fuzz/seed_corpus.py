#!/usr/bin/env python3
"""Build the seed corpora for the lab's cargo-fuzz targets (#849).

    python3 tools/argus_mcp/fuzz/seed_corpus.py --out DIR [--maps DIR ...]

writes DIR/arglog, DIR/bsp and DIR/demo, one directory per fuzz target:

arglog  windows of committed runs/*.log tapes (git ls-files), cut on line
        boundaries so each seed is a well formed slice of a real tape.
bsp     BSP29 maps found under each --maps directory (LibreQuake's free maps
        in CI), each also packed into a PAK as maps/fuzz.bsp, plus a map
        synthesised here.
demo    protocol 15 demos synthesised here. No recorded demo is ever a seed.

id Software maps and demos are licensed data and must never become corpus
files, so a --maps directory inside maps_local/, engine/ or runs/demos/ is
refused and no *.dem file is ever read. Keep the output outside the tree, or
in tools/argus_mcp/fuzz/corpus/, which is ignored.
"""

import argparse
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# licensed content lives here on a lab machine (see .gitignore)
FORBIDDEN = [ROOT / "maps_local", ROOT / "engine", ROOT / "runs" / "demos"]


# ------------------------------------------------------------------ arglog

def tape_seeds(out, tapes, window):
    """Head and middle windows of an evenly spaced sample of committed tapes."""
    names = subprocess.run(["git", "ls-files", "runs/*.log"], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.split()
    names.sort()
    step = max(1, len(names) // tapes) if tapes else len(names) + 1
    written = 0
    for name in names[::step][:tapes]:
        data = (ROOT / name).read_bytes()
        middle = data.find(b"\n", len(data) // 2) + 1
        for tag, start in (("head", 0), ("mid", middle)):
            chunk = data[start:start + window]
            cut = chunk.rfind(b"\n")
            if cut > 0:
                chunk = chunk[:cut + 1]
            if chunk.strip():
                stem = Path(name).stem
                (out / f"{stem}.{tag}.log").write_bytes(chunk)
                written += 1
    return written


# --------------------------------------------------------------------- bsp

def bsp_bytes(ents, lumps):
    """A BSP29 file from an entity string and {lump index: bytes}."""
    lumps = {0: ents.encode() + b"\0", **lumps}
    out = bytearray(4 + 15 * 8)
    struct.pack_into("<i", out, 0, 29)
    for index in range(15):
        body = lumps.get(index, b"")
        struct.pack_into("<ii", out, 4 + index * 8, len(out), len(body))
        out += body
    return bytes(out)


def synthetic_bsp():
    """Floor plane at z 0: hull 0 is empty above and lava below, hull 1 solid below."""
    planes = struct.pack("<3ffi", 0.0, 0.0, 1.0, 0.0, 2)
    nodes = struct.pack("<ihh6h2H", 0, -1, -2, -64, -64, -64, 64, 64, 64, 0, 0)
    leaves = (struct.pack("<ii6h2H4B", -1, 0, -64, -64, 0, 64, 64, 64, 0, 0, 0, 0, 0, 0)
              + struct.pack("<ii6h2H4B", -5, 0, -64, -64, -64, 64, 64, 0, 0, 0, 0, 0, 0, 0))
    clipnodes = struct.pack("<ihh", 0, -1, -2)
    model = struct.pack("<9f4i3i", -64.0, -64.0, -64.0, 64.0, 64.0, 64.0, 0.0, 0.0, 0.0,
                        0, 0, 0, 0, 0, 0, 0)
    ents = ('{\n"classname" "worldspawn"\n"message" "fuzz seed"\n}\n'
            '{\n"classname" "info_player_deathmatch"\n"origin" "0 0 24"\n}\n'
            '{\n"classname" "weapon_rocketlauncher"\n"origin" "32 0 16"\n}\n'
            '{\n"classname" "item_health"\n"spawnflags" "2"\n"origin" "-32 0 16"\n}\n')
    return bsp_bytes(ents, {1: planes, 5: nodes, 9: clipnodes, 10: leaves, 14: model})


def pak_bytes(files):
    """A PACK file holding {name: bytes}."""
    body = bytearray(12)
    directory = bytearray()
    for name, data in files.items():
        directory += struct.pack("<56sii", name.encode(), len(body), len(data))
        body += data
    struct.pack_into("<4sii", body, 0, b"PACK", len(body), len(directory))
    return bytes(body + directory)


def forbidden(path):
    """Inside this checkout's licensed directories, or any maps_local/ at all."""
    path = path.resolve()
    return (any(path == bad or bad in path.parents for bad in FORBIDDEN)
            or any(part.lower() == "maps_local" for part in path.parts))


def map_seeds(out, dirs, limit, max_bytes):
    """Small BSP29 maps from the given directories, raw and packed."""
    found = []
    for directory in dirs:
        if forbidden(directory):
            sys.exit(f"seed_corpus: refusing {directory}: maps_local/, engine/ and "
                     "runs/demos/ hold licensed id content, which is never corpus")
        for path in sorted(directory.rglob("*")):
            if path.suffix.lower() != ".bsp" or not path.is_file():
                continue
            size = path.stat().st_size
            with path.open("rb") as handle:
                version = handle.read(4)
            if size <= max_bytes and version == struct.pack("<i", 29):
                found.append((size, path))
    found.sort()
    seeds = {"synthetic": synthetic_bsp()}
    for _, path in found[:limit]:
        seeds[path.stem.lower()] = path.read_bytes()
    for stem, data in seeds.items():
        (out / f"{stem}.bsp").write_bytes(data)
        pak = pak_bytes({"maps/fuzz.bsp": data, "sound/fuzz.wav": b"RIFF\0\0\0\0WAVE"})
        (out / f"{stem}.pak").write_bytes(pak)
    return 2 * len(seeds)


# -------------------------------------------------------------------- demo

def string(text):
    return text.encode() + b"\0"


def coord(value):
    return struct.pack("<h", int(value * 8))


def angle(degrees):
    return struct.pack("<b", (int(degrees * 256 / 360) + 128) % 256 - 128)


def block(payload, yaw=0.0, pitch=0.0):
    return struct.pack("<i3f", len(payload), pitch, yaw, 0.0) + payload


def update(entity, origin, yaw, skin=None):
    """A fast update: origin, pitch and yaw, and the skin when given."""
    bits = 0x01 | 0x02 | 0x04 | 0x08 | 0x10 | 0x100 | (0x1000 if skin is not None else 0)
    out = bytes([0x80 | (bits & 0x7F), bits >> 8, entity])
    if skin is not None:
        out += bytes([skin])
    return (out + coord(origin[0]) + angle(0) + coord(origin[1]) + angle(yaw)
            + coord(origin[2]))


def signon():
    serverinfo = (bytes([11]) + struct.pack("<i", 15) + bytes([4, 1]) + string("fuzz seed")
                  + string("maps/fuzz.bsp") + string("progs/player.mdl")
                  + string("progs/missile.mdl") + string("progs/grenade.mdl") + b"\0"
                  + string("weapons/r_exp3.wav") + b"\0")
    first = serverinfo + bytes([32, 2, 2]) + bytes([5]) + struct.pack("<h", 1) + bytes([25, 1])
    second = bytearray()
    for slot, name in ((0, "player"), (3, "Reap"), (2, "Omi")):
        second += bytes([13, slot]) + string(name)
    second += bytes([14, 3]) + struct.pack("<h", 2) + bytes([17, 3, 0x4C])
    for entity, model, skin, origin in ((1, 2, 0, (0, 0, 24)), (5, 2, 1, (256, 0, 24)),
                                        (6, 2, 2, (-256, 0, 24)), (9, 3, 0, (0, 64, 40))):
        second += bytes([22]) + struct.pack("<h", entity) + bytes([model, 0, 0, skin])
        for axis in origin:
            second += coord(axis) + angle(0)
    second += bytes([20, 1, 0, 0, 0]) + coord(0) + angle(0) + coord(0) + angle(0) + coord(0) + angle(0)
    second += bytes([29]) + coord(8) + coord(8) + coord(8) + bytes([1, 255, 1])
    second += bytes([12, 0]) + string("m") + bytes([9]) + string("bf\n") + bytes([25, 2, 25, 3])
    return [block(first), block(bytes(second))]


def frame(index):
    t = 1.0 + index * 0.05
    out = bytearray([7]) + struct.pack("<f", t)
    # clientdata: viewheight and weapon bits, then items, health, ammo, weapon
    out += bytes([15]) + struct.pack("<h", 0x0001 | 0x4000) + bytes([22])
    out += struct.pack("<i", 0x2001) + bytes([4]) + struct.pack("<h", 100) + bytes([25, 25, 0, 25, 0, 32])
    out += update(1, (index * 12.0, 0, 24), index * 7.0)
    out += update(5, (256 - index * 15.0, index * 4.0, 24), 180 - index * 9.0, skin=1)
    out += update(6, (-256 + index * 10.0, -index * 6.0, 24), index * 30.0 % 360, skin=2)
    if index % 6 == 0:
        out += update(9, (index * 20.0, 64, 40), 90)
    events = {
        3: bytes([6, 0]) + struct.pack("<h", 5 << 3 | 1) + bytes([1]) + coord(1) + coord(2) + coord(3),
        5: bytes([23, 3]) + coord(10) + coord(20) + coord(30),
        7: bytes([23, 5]) + struct.pack("<h", 5) + b"".join(coord(v) for v in (0, 0, 24, 64, 0, 24)),
        9: bytes([23, 12]) + coord(1) + coord(1) + coord(1) + bytes([4, 8]),
        11: bytes([18]) + coord(5) + coord(5) + coord(5) + bytes([1, 2, 3, 73, 20]),
        13: bytes([19, 10, 5]) + coord(0) + coord(0) + coord(0),
        15: bytes([8]) + string("Omi") + bytes([8]) + string(" was gibbed by ") + bytes([8]) + string("Reap\n"),
        17: bytes([26]) + string("Reap got the Quad Damage\n"),
        19: bytes([3, 6]) + struct.pack("<i", 1) + bytes([10, 0, 12, 0]),
        21: bytes([16]) + struct.pack("<h", 9) + bytes([24, 0, 1]),
        23: bytes([8]) + string("Reap") + bytes([8]) + string(" burst into flames\n"),
        25: bytes([4]) + struct.pack("<i", 15) + bytes([27, 28, 33]),
    }
    out += events.get(index, b"")
    return block(bytes(out), yaw=index * 11.0, pitch=-5.0 + index % 3)


def demo_seeds(out):
    head = b"-1\n" + b"".join(signon())
    frames = b"".join(frame(index) for index in range(40))
    whole = head + frames + block(bytes([30, 2]))
    seeds = {
        "match.dem": whole,
        # a killed engine tears the file mid-block
        "torn.dem": whole[:len(head) + len(frames) // 2 + 7],
        # an unknown svc skips the rest of its block
        "unknown_svc.dem": head + frame(0) + block(bytes([1, 99, 1])) + frame(1),
    }
    for name, data in seeds.items():
        (out / name.replace(".dem", ".seed")).write_bytes(data)
    return len(seeds)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--maps", action="append", default=[], type=Path,
                    help="directory to search for free BSP29 maps (repeatable)")
    ap.add_argument("--tapes", type=int, default=48, help="committed tapes to sample")
    ap.add_argument("--window", type=int, default=16384, help="bytes per tape window")
    ap.add_argument("--max-maps", type=int, default=12)
    ap.add_argument("--max-map-bytes", type=int, default=1 << 20)
    args = ap.parse_args(argv)
    counts = {}
    for target in ("arglog", "bsp", "demo"):
        (args.out / target).mkdir(parents=True, exist_ok=True)
    counts["arglog"] = tape_seeds(args.out / "arglog", args.tapes, args.window)
    counts["bsp"] = map_seeds(args.out / "bsp", args.maps, args.max_maps, args.max_map_bytes)
    counts["demo"] = demo_seeds(args.out / "demo")
    for target, count in counts.items():
        print(f"seed_corpus: {target}: {count} seeds in {args.out / target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
