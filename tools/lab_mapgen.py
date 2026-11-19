#!/usr/bin/env python3
"""lab_mapgen.py - purpose-built micro-maps that isolate one bot behaviour.

A structured request (JSON) goes in. A plain-text Quake .map, a generated
texture WAD, a BSP29 compiled by the pinned ericw-tools and a manifest come
out. The lab then treats the BSP like any other map: navgen writes the usual
argus_nav_<map>.qc and .qc.json pair, the mill walks its links in the engine,
and registration wires it into the dispatcher and progs.src only after the
same reach and mill gates every stock map passes.

A lab map is an isolation instrument. A result measured on one supports an
isolation-tier claim only; a claim about stock geometry needs its own run on
real geometry, cited beside the lab tapes (docs/lab-scenarios.md).

usage:
  python tools/lab_mapgen.py check REQUEST.json
  python tools/lab_mapgen.py generate REQUEST.json [--out DIR]
  python tools/lab_mapgen.py compile REQUEST.json [--out DIR]
  python tools/lab_mapgen.py build REQUEST.json [--no-install] [--json]
  python tools/lab_mapgen.py nav REQUEST.json [--qc PATH] [--png PATH]
  python tools/lab_mapgen.py coverage REQUEST.json [--qc PATH] [--json]
  python tools/lab_mapgen.py record REQUEST.json [--nav-out FILE] [--mill FILE]
                                    [--registered yes|no] [--json]
  python tools/lab_mapgen.py tools [--install] [--from-zip ZIP]

check     validate the request and print the planned brush and entity counts
generate  write <map>.map and lab_textures.wad (deterministic, no tools needed)
compile   generate, then run qbsp, vis and light with tools/lab_mapgen_profile.json
build     compile, install the BSP into ARGUS_MAPS and the engine's game maps
          directory, and write the manifest beside the request
nav       run tools/argus_navgen.py on the built BSP (no registration); the lab
          MCP's lab_request uses its own nav_generate path instead
coverage  list the standable floors the generated graph seats no waypoint on;
          lab_request refuses registration while one is uncovered and not
          marked off_graph in the request
record    fold navgen, mill and registration results into the manifest and
          register the scenario in tools/lab_instruments.json
tools     report (or --install) the pinned ericw-tools build

The default output directory is labmaps/<map>/ under the repository root.
Relative output overrides are checkout-relative. --out stays under labmaps/,
nav --qc under ARGUS_SRC and nav --png under ARGUS_RUNS (default runs/).
record --nav-out reads a log under labmaps/ or ARGUS_RUNS.
Paths: ARGUS_ROOT (default: this checkout), ARGUS_MAPS (default maps_local/),
ARGUS_BASEDIR and ARGUS_GAME (engine game directory, default engine/argus),
ARGUS_SRC (default src/), ARGUS_ERICW (a directory holding qbsp, vis and
light, overriding the pinned install).
"""
import hashlib
import json
import math
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

GENERATOR_VERSION = 1
SCHEMA = 1
HERE = Path(__file__).resolve().parent
PROFILE_FILE = HERE / "lab_mapgen_profile.json"

HARD_MAX_BRUSHES = 200
HARD_MAX_ENTITIES = 60
# Protocol 15 sends coordinates as shorts in eighths of a unit, so the
# world must stay inside +-4096. Keep a margin for the hull walls.
COORD_LIMIT = 4000
GRID = 8
SLAB = 16          # floor slab thickness
HULL = 16          # outer hull thickness
STEP = 16          # stair riser, inside the engine's 18u step
WALK_DZ = 18       # a walk edge rises at most this far
DROP_DZ = 200      # navgen's longest one-way drop
JUMP_GAP = 160     # a jump connection's widest gap
JUMP_RISE = 40     # and its highest landing (navgen's JUMPUP)
# argus.qc's plain jump hop: jump velocity, gravity, the run speed (the
# fastest any hop is flown) and the lookahead that fires it
JUMP_VEL = 270.0
JUMP_GRAVITY = 800.0
JUMP_RUN = 320.0
JUMP_LOOKAHEAD = 32
PLAYER_HALF = 16   # half the player box's width
DOOR_HEIGHT = 96
TELEPORTER_SIZE = 64

NAME_RE = re.compile(r"lab_[a-z0-9_]{1,28}")
REGION_RE = re.compile(r"[a-z][a-z0-9_]{0,31}")
FLOOR_KINDS = {"floor", "room", "platform", "walkway", "corridor", "ledge"}
KINDS = FLOOR_KINDS | {"pit", "block", "stairs", "void"}
CONNECTIONS = ("open", "drop", "stairs", "jump", "door", "teleporter")
LIQUIDS = {"lava": "*lavalab", "slime": "*slimelab", "water": "*waterlab"}
AXES = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
CLAIM_TIERS = ("isolation",)

PROMOTION_RULE = (
    "Lab maps are isolation instruments. A result measured on a lab map can "
    "support an isolation-tier claim only. A claim about stock geometry needs "
    "a separate run on real geometry (dm2, dm3, dm4, dm6 or another stock map), "
    "and it cites the lab tapes and the stock tapes together."
)

# Point entities a request may place. Each maps to the z offset of its
# origin above the floor and the xy offset that centres its bounding box
# on the requested point (items.qc sets health and ammo boxes from 0 0 0).
POINT_ENTITIES = {
    "info_player_deathmatch": (24, 0),
    "info_player_start": (24, 0),
    "info_intermission": (64, 0),
    "info_teleport_destination": (24, 0),
    "item_health": (8, -16),
    "item_shells": (8, -16),
    "item_spikes": (8, -16),
    "item_rockets": (8, -16),
    "item_cells": (8, -16),
    "item_armor1": (8, 0),
    "item_armor2": (8, 0),
    "item_armorInv": (8, 0),
    "item_artifact_super_damage": (32, 0),
    "item_artifact_invulnerability": (32, 0),
    "item_artifact_invisibility": (32, 0),
    "item_artifact_envirosuit": (32, 0),
    "weapon_supershotgun": (8, 0),
    "weapon_nailgun": (8, 0),
    "weapon_supernailgun": (8, 0),
    "weapon_grenadelauncher": (8, 0),
    "weapon_rocketlauncher": (8, 0),
    "weapon_lightning": (8, 0),
}
RESERVED_KEYS = {"classname", "origin", "model", "target", "targetname"}

TEX_FLOOR = "lab_floor"
TEX_TRIM = "lab_trim"
TEX_WALL = "lab_wall"
TEX_CEIL = "lab_ceil"
TEX_DOOR = "lab_door"
TEX_SKY = "skylab"
TEX_TRIGGER = "trigger"


class RequestError(ValueError):
    """The request cannot be built; the message names the field."""


# ---------------------------------------------------------------- paths

def repo_root():
    return Path(os.environ.get("ARGUS_ROOT") or HERE.parent).resolve()


def env_path(name, default):
    value = os.environ.get(name)
    return Path(value).resolve() if value else Path(default).resolve()


def maps_dir(root):
    return env_path("ARGUS_MAPS", root / "maps_local")


def src_dir(root):
    return env_path("ARGUS_SRC", root / "src")


def runs_dir(root):
    return env_path("ARGUS_RUNS", root / "runs")


def confined_path(root, value, allowed, flag):
    path = Path(value)
    if ".." in path.parts:
        raise RequestError(f"{flag} cannot use parent traversal: {value}")
    path = Path(root) / path
    if path.is_symlink():
        raise RequestError(f"{flag} cannot be a symlink: {path}")
    try:
        target = path.resolve()
    except RuntimeError as exc:
        raise RequestError(f"{flag} cannot resolve {path}: {exc}") from exc
    if not any(target != folder and target.is_relative_to(folder) for folder in allowed):
        names = " or ".join(str(folder) for folder in allowed)
        raise RequestError(f"{flag} must stay under {names}: {path}")
    return target


def labmaps_dir(root):
    return confined_path(root, "labmaps", (Path(root).resolve(),), "labmaps")


def engine_maps_dir(root):
    base = env_path("ARGUS_BASEDIR", root / "engine")
    return base / (os.environ.get("ARGUS_GAME") or "argus") / "maps"


def rel(root, path):
    """A repository-relative POSIX path when inside the checkout, else absolute."""
    path = Path(path).resolve()
    try:
        return path.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            staged = Path(handle.name)
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt" and path.is_file():
            shutil.copymode(path, staged)
        os.replace(staged, path)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def write_json(path, obj):
    write_text(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- request

def _int(value, where, lo=None, hi=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise RequestError(f"{where} must be a whole number, not {value!r}")
    value = int(value)
    if lo is not None and value < lo:
        raise RequestError(f"{where} must be at least {lo}, not {value}")
    if hi is not None and value > hi:
        raise RequestError(f"{where} must be at most {hi}, not {value}")
    return value


def _snap(value):
    return int(round(value / GRID)) * GRID


def _pair(value, where, lo=None):
    if not (isinstance(value, list) and len(value) == 2):
        raise RequestError(f"{where} must be a list of two numbers")
    return [_snap(_int(v, f"{where}[{i}]", lo=lo)) for i, v in enumerate(value)]


def _clean_text(value, where, limit=400):
    if not isinstance(value, str) or not value.strip():
        raise RequestError(f"{where} must be a non-empty string")
    if any(ch in value for ch in '"\r\n\0'):
        raise RequestError(f"{where} may not hold quotes or line breaks")
    if len(value) > limit:
        raise RequestError(f"{where} is longer than {limit} characters")
    return value


def load_request(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RequestError(f"cannot read {path}: {exc}") from exc
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RequestError(f"{path}: not JSON: {exc}") from exc
    return normalise(request)


def normalise(request):
    """Validate a request and return it with every default filled in.

    The result is what the generator builds and what the source hash covers,
    so two requests that differ only in omitted defaults build the same map.
    """
    if not isinstance(request, dict):
        raise RequestError("the request is a JSON object")
    known = {"schema", "name", "intent", "claim_tier", "claims", "regions", "entities",
             "constraints", "base", "headroom", "notes"}
    unknown = sorted(set(request) - known)
    if unknown:
        raise RequestError(f"unknown request field(s): {', '.join(unknown)}")
    if request.get("schema", SCHEMA) != SCHEMA:
        raise RequestError(f"schema must be {SCHEMA}")
    name = request.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise RequestError("name must match lab_[a-z0-9_]{1,28}: the lab_ prefix keeps "
                           "generated maps apart from stock maps")
    intent = _clean_text(request.get("intent"), "intent", 600)
    tier = request.get("claim_tier", "isolation")
    if tier not in CLAIM_TIERS:
        raise RequestError(f"claim_tier must be one of {', '.join(CLAIM_TIERS)}: {PROMOTION_RULE}")
    claims = request.get("claims", [])
    if not (isinstance(claims, list) and all(isinstance(c, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", c)
                                             for c in claims)):
        raise RequestError("claims is a list of claim ids from tools/lab_claims.json")
    notes = request.get("notes", "")
    if not isinstance(notes, str):
        raise RequestError("notes is a string")

    cons = request.get("constraints", {})
    if not isinstance(cons, dict):
        raise RequestError("constraints is an object")
    known_cons = {"max_brushes", "max_entities", "sky", "teleporters", "liquids", "min_spawns",
                  "margin", "doors"}
    unknown = sorted(set(cons) - known_cons)
    if unknown:
        raise RequestError(f"unknown constraint(s): {', '.join(unknown)}")
    liquids = cons.get("liquids", sorted(LIQUIDS))
    if not (isinstance(liquids, list) and set(liquids) <= set(LIQUIDS)):
        raise RequestError(f"constraints.liquids is a list from {', '.join(sorted(LIQUIDS))}")
    if not isinstance(cons.get("sky", False), bool):
        raise RequestError("constraints.sky is true or false")
    constraints = {
        "max_brushes": _int(cons.get("max_brushes", HARD_MAX_BRUSHES), "constraints.max_brushes",
                            1, HARD_MAX_BRUSHES),
        "max_entities": _int(cons.get("max_entities", HARD_MAX_ENTITIES), "constraints.max_entities",
                             1, HARD_MAX_ENTITIES),
        "sky": cons.get("sky", False),
        "teleporters": _int(cons.get("teleporters", 0), "constraints.teleporters", 0, 8),
        "doors": _int(cons.get("doors", 4), "constraints.doors", 0, 8),
        "liquids": sorted(liquids),
        "min_spawns": _int(cons.get("min_spawns", 2), "constraints.min_spawns", 1, 16),
        "margin": _snap(_int(cons.get("margin", 0), "constraints.margin", 0, 512)),
    }

    regions_in = request.get("regions")
    if not isinstance(regions_in, list) or not regions_in:
        raise RequestError("regions is a non-empty list")
    regions = []
    names = set()
    for i, r in enumerate(regions_in):
        regions.append(_region(r, i, names, constraints))
    by_name = {r["name"]: r for r in regions}
    for r in regions:
        for c in r["connections"]:
            if c["to"] not in by_name:
                raise RequestError(f"region {r['name']}: connection to unknown region {c['to']}")
            if c["to"] == r["name"]:
                raise RequestError(f"region {r['name']}: a connection to itself")

    base_in = request.get("base", {})
    if not isinstance(base_in, dict) or set(base_in) - {"floor_z", "liquid", "liquid_depth"}:
        raise RequestError("base is an object of floor_z, liquid and liquid_depth")
    floors = [r["floor_z"] for r in regions if r["kind"] != "block"]
    floors += [min(r["floor_z"], r["to_z"]) for r in regions if r["kind"] == "stairs"]
    lowest = min(floors) if floors else min(r["floor_z"] for r in regions)
    base = {"floor_z": _int(base_in.get("floor_z", lowest - 64), "base.floor_z", -COORD_LIMIT, COORD_LIMIT)}
    if base["floor_z"] > lowest - SLAB:
        raise RequestError(f"base.floor_z {base['floor_z']} must sit at least {SLAB} below the lowest "
                           f"region floor ({lowest})")
    for r in regions:
        if r["kind"] == "block" and r["floor_z"] < base["floor_z"]:
            raise RequestError(f"region {r['name']}: a block starts at or above base.floor_z "
                               f"({base['floor_z']}), not {r['floor_z']}")
    if "liquid" in base_in:
        _liquid_allowed(base_in["liquid"], "base.liquid", constraints)
        base["liquid"] = base_in["liquid"]
        base["liquid_depth"] = _int(base_in.get("liquid_depth", 32), "base.liquid_depth", 8, 512)
    headroom = _int(request.get("headroom", 192), "headroom", 128, 1024)

    entities_in = request.get("entities", [])
    if not isinstance(entities_in, list):
        raise RequestError("entities is a list")
    entities = [_entity(e, i, by_name) for i, e in enumerate(entities_in)]

    return {
        "schema": SCHEMA,
        "name": name,
        "intent": intent,
        "claim_tier": tier,
        "claims": list(claims),
        "notes": notes,
        "constraints": constraints,
        "base": base,
        "headroom": headroom,
        "regions": regions,
        "entities": entities,
    }


def _liquid_allowed(liquid, where, constraints):
    if liquid not in LIQUIDS:
        raise RequestError(f"{where} must be one of {', '.join(sorted(LIQUIDS))}")
    if liquid not in constraints["liquids"]:
        raise RequestError(f"{where} {liquid} is not in constraints.liquids")


def _region(r, i, names, constraints):
    where = f"regions[{i}]"
    if not isinstance(r, dict):
        raise RequestError(f"{where} is an object")
    known = {"name", "kind", "min", "size", "floor_z", "to_z", "axis", "height", "liquid",
             "liquid_depth", "ceiling", "walls", "connections", "solid_below", "off_graph"}
    unknown = sorted(set(r) - known)
    if unknown:
        raise RequestError(f"{where}: unknown field(s) {', '.join(unknown)}")
    name = r.get("name")
    if not isinstance(name, str) or not REGION_RE.fullmatch(name):
        raise RequestError(f"{where}: name must match [a-z][a-z0-9_]{{0,31}}")
    if name in names:
        raise RequestError(f"{where}: duplicate region name {name}")
    names.add(name)
    where = f"region {name}"
    kind = r.get("kind", "floor")
    if kind not in KINDS:
        raise RequestError(f"{where}: kind must be one of {', '.join(sorted(KINDS))}")
    if kind in FLOOR_KINDS:
        kind = "floor"
    lo = _pair(r.get("min"), f"{where}.min")
    size = _pair(r.get("size"), f"{where}.size", lo=16)
    if size[0] < 16 or size[1] < 16:
        raise RequestError(f"{where}: size must be at least 16 by 16 after snapping to {GRID}")
    for axis in range(2):
        if not (-COORD_LIMIT <= lo[axis] and lo[axis] + size[axis] <= COORD_LIMIT):
            raise RequestError(f"{where}: footprint leaves the +-{COORD_LIMIT} protocol 15 world")
    out = {"name": name, "kind": kind, "min": lo, "size": size,
           "floor_z": _snap(_int(r.get("floor_z", 0), f"{where}.floor_z", -COORD_LIMIT, COORD_LIMIT))}
    if kind == "stairs":
        out["to_z"] = _int(r.get("to_z"), f"{where}.to_z", -COORD_LIMIT, COORD_LIMIT)
        if out["to_z"] == out["floor_z"]:
            raise RequestError(f"{where}: stairs need to_z different from floor_z")
        axis = r.get("axis")
        if axis not in AXES:
            raise RequestError(f"{where}: axis must be one of {', '.join(AXES)} (the direction "
                               "from floor_z towards to_z)")
        out["axis"] = axis
        run = size[0] if axis in ("+x", "-x") else size[1]
        steps = math.ceil(abs(out["to_z"] - out["floor_z"]) / STEP)
        if run / steps < 16:
            raise RequestError(f"{where}: {steps} steps need at least {16 * steps}u of run along {axis}, "
                               f"the footprint gives {run}")
    if kind == "block":
        out["height"] = _int(r.get("height", 64), f"{where}.height", 8, 2048)
    if kind == "pit":
        if "liquid" in r:
            _liquid_allowed(r["liquid"], f"{where}.liquid", constraints)
            out["liquid"] = r["liquid"]
            out["liquid_depth"] = _int(r.get("liquid_depth", 32), f"{where}.liquid_depth", 8, 512)
    elif "liquid" in r:
        raise RequestError(f"{where}: only a pit (or the base) holds liquid")
    if "ceiling" in r:
        if kind in ("void", "block"):
            raise RequestError(f"{where}: a {kind} has no ceiling")
        out["ceiling"] = _int(r["ceiling"], f"{where}.ceiling", 72, 2048)
    out["solid_below"] = bool(r.get("solid_below", False))
    if "off_graph" in r:
        if not isinstance(r["off_graph"], bool):
            raise RequestError(f"{where}.off_graph is true or false")
        if kind != "floor":
            raise RequestError(f"{where}: off_graph exempts a standable floor from the coverage gate; "
                               f"a {kind} is not checked")
        if r["off_graph"]:
            # only when set, so requests without it keep their scenario ids
            out["off_graph"] = True
    walls = r.get("walls")
    if walls is not None:
        if kind == "void":
            raise RequestError(f"{where}: a void has no walls")
        if not isinstance(walls, dict) or set(walls) - {"sides", "height", "thickness"}:
            raise RequestError(f"{where}.walls is an object of sides, height and thickness")
        sides = walls.get("sides", [])
        if not (isinstance(sides, list) and sides and set(sides) <= set(AXES) and len(set(sides)) == len(sides)):
            raise RequestError(f"{where}.walls.sides is a list from {', '.join(AXES)}")
        out["walls"] = {"sides": [s for s in AXES if s in sides],
                        "height": _int(walls.get("height", 64), f"{where}.walls.height", 8, 1024),
                        "thickness": _snap(_int(walls.get("thickness", 16), f"{where}.walls.thickness", 8, 64))}
    conns = r.get("connections", [])
    if not isinstance(conns, list):
        raise RequestError(f"{where}.connections is a list")
    out["connections"] = []
    for j, c in enumerate(conns):
        if not isinstance(c, dict) or set(c) - {"to", "type"}:
            raise RequestError(f"{where}.connections[{j}] is an object of to and type")
        if c.get("type", "open") not in CONNECTIONS:
            raise RequestError(f"{where}.connections[{j}].type must be one of {', '.join(CONNECTIONS)}")
        if not isinstance(c.get("to"), str):
            raise RequestError(f"{where}.connections[{j}].to names a region")
        out["connections"].append({"to": c["to"], "type": c.get("type", "open")})
    return out


def _entity(e, i, by_name):
    where = f"entities[{i}]"
    if not isinstance(e, dict):
        raise RequestError(f"{where} is an object")
    if set(e) - {"classname", "region", "at", "z", "angle", "spawnflags", "keys"}:
        raise RequestError(f"{where}: fields are classname, region, at, z, angle, spawnflags and keys")
    cls = e.get("classname")
    if cls not in POINT_ENTITIES:
        raise RequestError(f"{where}: classname must be one of {', '.join(sorted(POINT_ENTITIES))}")
    region = e.get("region")
    if region not in by_name:
        raise RequestError(f"{where}: region {region!r} is not a region of this request")
    if by_name[region]["kind"] == "void":
        raise RequestError(f"{where}: region {region} is a void with nothing to stand on")
    at = e.get("at", "centre")
    if at in ("centre", "center"):
        at = [0.5, 0.5]
    elif isinstance(at, dict) and set(at) == {"offset"}:
        at = {"offset": _pair(at["offset"], f"{where}.at.offset", lo=0)}
    elif not (isinstance(at, list) and len(at) == 2
              and all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in at)):
        raise RequestError(f"{where}.at is \"centre\", [fx, fy] fractions of the region, or {{\"offset\": [dx, dy]}}")
    out = {"classname": cls, "region": region, "at": at}
    if "z" in e:
        out["z"] = _int(e["z"], f"{where}.z", 0, 512)
    if "angle" in e:
        out["angle"] = _int(e["angle"], f"{where}.angle", -2, 359)
    if "spawnflags" in e:
        out["spawnflags"] = _int(e["spawnflags"], f"{where}.spawnflags", 0, 65535)
    keys = e.get("keys", {})
    if not isinstance(keys, dict):
        raise RequestError(f"{where}.keys is an object of strings")
    clean = {}
    for k, v in keys.items():
        if not (isinstance(k, str) and re.fullmatch(r"[a-z_][a-z0-9_]{0,31}", k)) or k in RESERVED_KEYS:
            raise RequestError(f"{where}.keys: {k!r} is not an allowed key")
        clean[k] = _clean_text(str(v), f"{where}.keys.{k}", 64)
    if clean:
        out["keys"] = clean
    return out


def source_sha256(request):
    """Hash of the normalised request plus the generator version: the map's identity."""
    return sha256_bytes(canonical({"generator": GENERATOR_VERSION, "request": request}).encode("ascii"))


def scenario_id(request):
    return f"{request['name']}-{source_sha256(request)[:10]}"


# ---------------------------------------------------------------- geometry

def footprint(region):
    x0, y0 = region["min"]
    w, d = region["size"]
    return x0, y0, x0 + w, y0 + d


def surface_z(region, x=None, y=None):
    """Standing height on a region at a point (its floor, a block's top, a stair's tread)."""
    kind = region["kind"]
    if kind == "block":
        return region["floor_z"] + region["height"]
    if kind == "stairs" and x is not None:
        steps = stair_steps(region)
        for (sx0, sy0, sx1, sy1, top) in steps:
            if sx0 <= x <= sx1 and sy0 <= y <= sy1:
                return top
        return steps[-1][4]
    return region["floor_z"]


def stair_steps(region):
    """Treads of a stair region as (x0, y0, x1, y1, top_z), first tread first.

    The stair runs along its axis from the edge where it meets floor_z to the
    far edge, whose tread stands at to_z, so it climbs or descends by sign.
    """
    x0, y0, x1, y1 = footprint(region)
    z0, z1 = region["floor_z"], region["to_z"]
    n = math.ceil(abs(z1 - z0) / STEP)
    dx, dy = AXES[region["axis"]]
    run = (x1 - x0) if dx else (y1 - y0)
    out = []
    for i in range(n):
        a = int(round(run * i / n))
        b = int(round(run * (i + 1) / n))
        # one riser from floor_z on the first tread, to_z on the last
        top = z0 + int(round((z1 - z0) * (i + 1) / n))
        if dx > 0:
            box = (x0 + a, y0, x0 + b, y1)
        elif dx < 0:
            box = (x1 - b, y0, x1 - a, y1)
        elif dy > 0:
            box = (x0, y0 + a, x1, y0 + b)
        else:
            box = (x0, y1 - b, x1, y1 - a)
        out.append(box + (top,))
    return out


def shared_edge(a, b):
    """The segment two footprints share, as (axis, coord, lo, hi), or None.

    axis is 'x' when the boundary is a line of constant x.
    """
    ax0, ay0, ax1, ay1 = footprint(a)
    bx0, by0, bx1, by1 = footprint(b)
    ylo, yhi = max(ay0, by0), min(ay1, by1)
    xlo, xhi = max(ax0, bx0), min(ax1, bx1)
    if yhi > ylo:
        if ax1 == bx0:
            return ("x", ax1, ylo, yhi)
        if ax0 == bx1:
            return ("x", ax0, ylo, yhi)
    if xhi > xlo:
        if ay1 == by0:
            return ("y", ay1, xlo, xhi)
        if ay0 == by1:
            return ("y", ay0, xlo, xhi)
    return None


def overlap_area(a, b):
    ax0, ay0, ax1, ay1 = footprint(a)
    bx0, by0, bx1, by1 = footprint(b)
    w = min(ax1, bx1) - max(ax0, bx0)
    d = min(ay1, by1) - max(ay0, by0)
    return w * d if w > 0 and d > 0 else 0


def gap_between(a, b):
    """Horizontal clearance between two footprints that face each other, or None."""
    ax0, ay0, ax1, ay1 = footprint(a)
    bx0, by0, bx1, by1 = footprint(b)
    if min(ay1, by1) > max(ay0, by0):
        if bx0 > ax1:
            return bx0 - ax1
        if ax0 > bx1:
            return ax0 - bx1
    if min(ax1, bx1) > max(ax0, bx0):
        if by0 > ay1:
            return by0 - ay1
        if ay0 > by1:
            return ay0 - by1
    return None


def edge_height(region, edge):
    """Standing height along a shared edge (a stair's first or last tread)."""
    if region["kind"] != "stairs":
        return surface_z(region)
    axis, coord, lo, hi = edge
    mid = (lo + hi) / 2
    x, y = (coord, mid) if axis == "x" else (mid, coord)
    # nudge inside the stair footprint
    x0, y0, x1, y1 = footprint(region)
    x = min(max(x, x0 + 1), x1 - 1)
    y = min(max(y, y0 + 1), y1 - 1)
    return surface_z(region, x, y)


def adjacency(request):
    """Every region pair that touches, overlaps or faces across a gap, with its relation."""
    regions = [r for r in request["regions"]]
    out = []
    for i, a in enumerate(regions):
        for b in regions[i + 1:]:
            row = {"a": a["name"], "b": b["name"]}
            edge = shared_edge(a, b)
            if edge is not None:
                za, zb = edge_height(a, edge), edge_height(b, edge)
                dz = abs(za - zb)
                row.update(relation="edge", length=edge[3] - edge[2], dz=dz,
                           walk="walk" if dz <= WALK_DZ else "drop" if dz <= DROP_DZ else "wall")
                if "void" in (a["kind"], b["kind"]):
                    row["walk"] = "void"
            elif overlap_area(a, b):
                row.update(relation="overlap", area=overlap_area(a, b),
                           dz=abs(surface_z(a) - surface_z(b)))
            else:
                gap = gap_between(a, b)
                if gap is None or gap > 256:
                    continue
                row.update(relation="gap", gap=gap, dz=abs(surface_z(a) - surface_z(b)))
            out.append(row)
    return out


def jump_reach(rise):
    """The widest gap a running jump crosses onto a landing `rise` up, or None.

    The plain hop fires when its 32u lookahead finds no floor, so it takes
    off 32u short of the lip, and the box lands once its 16u half-width is
    over the far edge: the flight runs gap + 16 and must still be at or
    above the landing when it gets there. At the 320 u/s run speed that is
    200u level and 129u at a 40u rise. Above the 45u apex nothing lands.
    """
    disc = JUMP_VEL ** 2 - 2 * JUMP_GRAVITY * rise
    if disc < 0:
        return None
    flight = (JUMP_VEL + math.sqrt(disc)) / JUMP_GRAVITY
    return JUMP_RUN * flight - (JUMP_LOOKAHEAD - PLAYER_HALF)


def check_connections(request):
    """Each declared connection against the geometry; raises on one the layout cannot provide."""
    by_name = {r["name"]: r for r in request["regions"]}
    results = []
    for r in request["regions"]:
        for c in r["connections"]:
            other = by_name[c["to"]]
            kind = c["type"]
            row = {"from": r["name"], "to": other["name"], "type": kind}
            edge = shared_edge(r, other)
            if kind == "teleporter":
                if other["kind"] in ("void",):
                    raise RequestError(f"connection {r['name']} -> {other['name']}: a teleporter needs a floor")
                results.append(row)
                continue
            if kind == "jump":
                gap = gap_between(r, other)
                dz = surface_z(other) - surface_z(r)
                if gap is None or gap > JUMP_GAP or dz > JUMP_RISE:
                    raise RequestError(f"connection {r['name']} -> {other['name']}: a jump needs facing "
                                       f"footprints at most {JUMP_GAP}u apart and a landing at most "
                                       f"{JUMP_RISE}u up (gap {gap}, rise {dz})")
                reach = jump_reach(dz)
                if gap > reach:
                    raise RequestError(f"connection {r['name']} -> {other['name']}: no running jump crosses "
                                       f"a {gap}u gap onto a landing {dz}u up; taking off {JUMP_LOOKAHEAD}u "
                                       f"short of the lip at {JUMP_RUN:.0f} u/s, where the bot's jump fires, "
                                       f"the player box clears the far edge only up to {reach:.0f}u. "
                                       "Narrow the gap or lower the landing")
                row.update(gap=gap, dz=dz)
                results.append(row)
                continue
            if edge is None:
                raise RequestError(f"connection {r['name']} -> {other['name']} ({kind}): the footprints "
                                   "share no edge")
            length = edge[3] - edge[2]
            if length < 32:
                raise RequestError(f"connection {r['name']} -> {other['name']}: the shared edge is "
                                   f"{length}u, narrower than a player")
            za, zb = edge_height(r, edge), edge_height(other, edge)
            dz = za - zb
            row.update(length=length, dz=dz)
            if kind in ("open", "door", "stairs") and abs(dz) > WALK_DZ:
                raise RequestError(f"connection {r['name']} -> {other['name']} ({kind}): the edge steps "
                                   f"{abs(dz)}u, more than the {WALK_DZ}u a walk can climb; use stairs "
                                   "or a drop")
            if kind == "drop" and not (WALK_DZ < dz <= DROP_DZ):
                raise RequestError(f"connection {r['name']} -> {other['name']} (drop): the fall is {dz}u; "
                                   f"a drop falls more than {WALK_DZ} and at most {DROP_DZ} from 'from' to 'to'")
            if kind == "stairs" and "stairs" not in (r["kind"], other["kind"]):
                raise RequestError(f"connection {r['name']} -> {other['name']}: a stairs connection "
                                   "needs a stairs region at one end")
            results.append(row)
    return results


# ---------------------------------------------------------------- brushes

# Outward normal -> two tangents whose cross product is that normal. qbsp
# takes the plane normal as (p0 - p1) x (p2 - p1) and keeps the half-space
# behind it, so (p1 + u, p1, p1 + v) gives an outward face.
_FACES = (
    ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
)
FACE_NAMES = ("+x", "-x", "+y", "-y", "+z", "-z")


class Brush:
    def __init__(self, label, lo, hi, textures):
        lo = tuple(int(v) for v in lo)
        hi = tuple(int(v) for v in hi)
        if any(hi[i] <= lo[i] for i in range(3)):
            raise RequestError(f"brush {label}: empty box {lo} to {hi}")
        if any(abs(v) > COORD_LIMIT + HULL for v in lo + hi):
            raise RequestError(f"brush {label}: leaves the protocol 15 world")
        self.label = label
        self.lo = lo
        self.hi = hi
        if isinstance(textures, str):
            textures = {f: textures for f in FACE_NAMES}
        self.textures = textures

    def planes(self):
        """(normal, p0, p1, p2, texture) for the six faces."""
        out = []
        for (normal, u, v), face in zip(_FACES, FACE_NAMES):
            p1 = tuple(self.hi[i] if normal[i] > 0 else self.lo[i] for i in range(3))
            p0 = tuple(p1[i] + 64 * u[i] for i in range(3))
            p2 = tuple(p1[i] + 64 * v[i] for i in range(3))
            out.append((normal, p0, p1, p2, self.textures[face]))
        return out

    def text(self):
        lines = [f"// {self.label}", "{"]
        for _normal, p0, p1, p2, tex in self.planes():
            lines.append("( {} {} {} ) ( {} {} {} ) ( {} {} {} ) {} 0 0 0 1 1".format(*p0, *p1, *p2, tex))
        lines.append("}")
        return "\n".join(lines)


def slab_textures(top, side, bottom=None):
    tex = {f: side for f in FACE_NAMES}
    tex["+z"] = top
    tex["-z"] = bottom or top
    return tex


def hull_extent(request):
    regions = request["regions"]
    margin = request["constraints"]["margin"]
    x0 = min(footprint(r)[0] for r in regions) - margin
    y0 = min(footprint(r)[1] for r in regions) - margin
    x1 = max(footprint(r)[2] for r in regions) + margin
    y1 = max(footprint(r)[3] for r in regions) + margin
    tops = []
    for r in regions:
        top = surface_z(r)
        if r["kind"] == "stairs":
            top = max(r["floor_z"], r["to_z"])
        if "ceiling" in r:
            top = max(top, r["floor_z"] + r["ceiling"])
        if "walls" in r:
            top = max(top, surface_z(r) + r["walls"]["height"])
        tops.append(top)
    z0 = request["base"]["floor_z"]
    z1 = max(tops) + request["headroom"]
    for v in (x0, y0, x1, y1, z0, z1):
        if abs(v) > COORD_LIMIT:
            raise RequestError(f"the map spans {x0} {y0} {z0} to {x1} {y1} {z1}, outside the "
                               f"+-{COORD_LIMIT} protocol 15 world")
    return x0, y0, z0, x1, y1, z1


def build_brushes(request):
    """World brushes in a fixed order: hull, base liquid, then each region in request order."""
    cons = request["constraints"]
    x0, y0, z0, x1, y1, z1 = hull_extent(request)
    brushes = []
    ceiling = TEX_SKY if cons["sky"] else TEX_CEIL
    brushes.append(Brush("hull floor", (x0 - HULL, y0 - HULL, z0 - HULL), (x1 + HULL, y1 + HULL, z0),
                         slab_textures(TEX_FLOOR, TEX_WALL)))
    brushes.append(Brush("hull ceiling", (x0 - HULL, y0 - HULL, z1), (x1 + HULL, y1 + HULL, z1 + HULL),
                         ceiling))
    brushes.append(Brush("hull wall -x", (x0 - HULL, y0 - HULL, z0), (x0, y1 + HULL, z1), TEX_WALL))
    brushes.append(Brush("hull wall +x", (x1, y0 - HULL, z0), (x1 + HULL, y1 + HULL, z1), TEX_WALL))
    brushes.append(Brush("hull wall -y", (x0, y0 - HULL, z0), (x1, y0, z1), TEX_WALL))
    brushes.append(Brush("hull wall +y", (x0, y1, z0), (x1, y1 + HULL, z1), TEX_WALL))
    base = request["base"]
    if "liquid" in base:
        brushes.append(Brush("base liquid", (x0, y0, z0), (x1, y1, z0 + base["liquid_depth"]),
                             LIQUIDS[base["liquid"]]))
    for r in request["regions"]:
        rx0, ry0, rx1, ry1 = footprint(r)
        kind = r["kind"]
        fz = r["floor_z"]
        label = f"region {r['name']}"
        if kind in ("floor", "pit"):
            bottom = z0 if r["solid_below"] else fz - SLAB
            if fz > z0 and bottom < fz:
                brushes.append(Brush(f"{label} floor", (rx0, ry0, max(bottom, z0)), (rx1, ry1, fz),
                                     slab_textures(TEX_FLOOR, TEX_TRIM)))
            if kind == "pit" and "liquid" in r:
                brushes.append(Brush(f"{label} liquid", (rx0, ry0, fz), (rx1, ry1, fz + r["liquid_depth"]),
                                     LIQUIDS[r["liquid"]]))
        elif kind == "block":
            brushes.append(Brush(f"{label} block", (rx0, ry0, max(fz, z0)), (rx1, ry1, fz + r["height"]),
                                 slab_textures(TEX_TRIM, TEX_WALL)))
        elif kind == "stairs":
            for k, (sx0, sy0, sx1, sy1, top) in enumerate(stair_steps(r)):
                bottom = z0 if r["solid_below"] else min(r["floor_z"], r["to_z"]) - SLAB
                bottom = max(bottom, z0)
                if top > bottom:
                    brushes.append(Brush(f"{label} step {k + 1}", (sx0, sy0, bottom), (sx1, sy1, top),
                                         slab_textures(TEX_FLOOR, TEX_TRIM)))
        if "ceiling" in r:
            cz = fz + r["ceiling"]
            if cz < z1:
                brushes.append(Brush(f"{label} ceiling", (rx0, ry0, cz), (rx1, ry1, min(cz + SLAB, z1)),
                                     slab_textures(TEX_CEIL, TEX_WALL)))
        if "walls" in r:
            w = r["walls"]
            top = surface_z(r) + w["height"]
            if r["kind"] == "stairs":
                top = max(r["floor_z"], r["to_z"]) + w["height"]
            low = min(fz, r.get("to_z", fz)) - SLAB
            t = w["thickness"]
            boxes = {"+x": (rx1 - t, ry0, rx1, ry1), "-x": (rx0, ry0, rx0 + t, ry1),
                     "+y": (rx0, ry1 - t, rx1, ry1), "-y": (rx0, ry0, rx1, ry0 + t)}
            for side in w["sides"]:
                bx0, by0, bx1, by1 = boxes[side]
                brushes.append(Brush(f"{label} wall {side}", (bx0, by0, max(low, z0)), (bx1, by1, min(top, z1)),
                                     TEX_WALL))
    return brushes


# ---------------------------------------------------------------- entities

def entity_origin(request, ent):
    by_name = {r["name"]: r for r in request["regions"]}
    region = by_name[ent["region"]]
    x0, y0, x1, y1 = footprint(region)
    at = ent["at"]
    if isinstance(at, dict):
        x, y = x0 + at["offset"][0], y0 + at["offset"][1]
    else:
        x, y = x0 + (x1 - x0) * at[0], y0 + (y1 - y0) * at[1]
    x, y = int(round(x)), int(round(y))
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        raise RequestError(f"{ent['classname']} in {region['name']}: offset {at} leaves the region")
    zoff, xyoff = POINT_ENTITIES[ent["classname"]]
    z = surface_z(region, x, y) + zoff + ent.get("z", 0)
    return x + xyoff, y + xyoff, z


def occupant(request):
    """An info_intermission in clear air, which also seals the clipping hulls.

    qbsp fills the outside of each hull from entity origins it finds in empty
    space, and a spawn at floor + 24 sits exactly on hull 1's expanded floor,
    which ericw counts as solid. With no occupant the outside of hulls 1 and 2
    stays open and navgen seats waypoints on the roof. 48 above an open floor
    clears the floor in every hull (hull 2 raises it by 24) and, with the
    minimum headroom, the ceiling (hull 2 lowers it by 64); the point also has
    to stand 48u clear of the hull walls and of every block or wall brush.
    """
    x0, y0, _z0, x1, y1, _z1 = hull_extent(request)
    solids = [footprint(r) for r in request["regions"] if r["kind"] == "block"]
    for r in request["regions"]:
        if "walls" in r:
            solids.append(footprint(r))
    candidates = [r for r in request["regions"]
                  if r["kind"] in ("floor", "pit") and "ceiling" not in r and "walls" not in r]
    candidates.sort(key=lambda r: (-(r["size"][0] * r["size"][1]), r["name"]))
    for best in candidates:
        bx0, by0, bx1, by1 = footprint(best)
        x, y = (bx0 + bx1) // 2, (by0 + by1) // 2
        if min(x - x0, x1 - x, y - y0, y1 - y) < 48:
            continue
        if any(sx0 - 48 < x < sx1 + 48 and sy0 - 48 < y < sy1 + 48 for sx0, sy0, sx1, sy1 in solids):
            continue
        z = surface_z(best) + 48
        if "liquid" in best:
            z = best["floor_z"] + best["liquid_depth"] + 48
        return [("classname", "info_intermission"), ("origin", f"{x} {y} {z}"), ("mangle", "20 0 0")]
    raise RequestError("no open region has a centre 48u clear of walls and blocks to hold the hull "
                       "occupant; add an info_intermission entity in clear air")


def build_entities(request):
    """Point and brush entities as ordered key lists; the first is worldspawn."""
    cons = request["constraints"]
    by_name = {r["name"]: r for r in request["regions"]}
    world = [("classname", "worldspawn"), ("wad", "lab_textures.wad"),
             ("message", f"Argus lab {request['name']}"), ("worldtype", "0"), ("sounds", "0"),
             ("light", "200"), ("_lab_generator", f"lab_mapgen v{GENERATOR_VERSION}"),
             ("_lab_source_sha256", source_sha256(request))]
    entities = [{"keys": world, "brushes": None}]
    spawns = 0
    has_start = any(e["classname"] == "info_player_start" for e in request["entities"])
    first_spawn = None
    for ent in request["entities"]:
        x, y, z = entity_origin(request, ent)
        region = by_name[ent["region"]]
        if ent["classname"] == "info_player_deathmatch":
            spawns += 1
            if region["kind"] == "pit" and "liquid" in region:
                raise RequestError(f"a deathmatch spawn sits in the {region['liquid']} of pit {region['name']}")
            first_spawn = first_spawn or (x, y, z, ent.get("angle", 0))
        keys = [("classname", ent["classname"]), ("origin", f"{x} {y} {z}")]
        if "angle" in ent:
            keys.append(("angle", str(ent["angle"])))
        if "spawnflags" in ent:
            keys.append(("spawnflags", str(ent["spawnflags"])))
        for k, v in ent.get("keys", {}).items():
            keys.append((k, v))
        entities.append({"keys": keys, "brushes": None})
    if spawns < cons["min_spawns"]:
        raise RequestError(f"the request places {spawns} info_player_deathmatch, constraints.min_spawns "
                           f"asks for {cons['min_spawns']}")
    if not has_start and first_spawn:
        x, y, z, angle = first_spawn
        entities.append({"keys": [("classname", "info_player_start"), ("origin", f"{x} {y} {z}"),
                                  ("angle", str(angle))], "brushes": None})
    if not any(e["classname"] == "info_intermission" for e in request["entities"]):
        entities.append({"keys": occupant(request), "brushes": None})
    # connection furniture: doors and teleporters
    doors = 0
    teleports = 0
    for r in request["regions"]:
        for c in r["connections"]:
            other = by_name[c["to"]]
            if c["type"] == "door":
                doors += 1
                axis, coord, lo, hi = shared_edge(r, other)
                base = max(edge_height(r, (axis, coord, lo, hi)), edge_height(other, (axis, coord, lo, hi)))
                if axis == "x":
                    box = ((coord - 4, lo, base), (coord + 4, hi, base + DOOR_HEIGHT))
                else:
                    box = ((lo, coord - 4, base), (hi, coord + 4, base + DOOR_HEIGHT))
                brush = Brush(f"door {r['name']} -> {other['name']}", box[0], box[1], TEX_DOOR)
                entities.append({"keys": [("classname", "func_door"), ("angle", "-1"), ("speed", "200"),
                                          ("wait", "3"), ("lip", "8")], "brushes": [brush]})
            elif c["type"] == "teleporter":
                teleports += 1
                tag = f"lab_tele{teleports}"
                cx = (footprint(r)[0] + footprint(r)[2]) // 2
                cy = (footprint(r)[1] + footprint(r)[3]) // 2
                fz = surface_z(r, cx, cy)
                half = TELEPORTER_SIZE // 2
                brush = Brush(f"teleporter {r['name']} -> {other['name']}", (cx - half, cy - half, fz),
                              (cx + half, cy + half, fz + TELEPORTER_SIZE), TEX_TRIGGER)
                entities.append({"keys": [("classname", "trigger_teleport"), ("target", tag)],
                                 "brushes": [brush]})
                ox = (footprint(other)[0] + footprint(other)[2]) // 2
                oy = (footprint(other)[1] + footprint(other)[3]) // 2
                entities.append({"keys": [("classname", "info_teleport_destination"), ("targetname", tag),
                                          ("origin", f"{ox} {oy} {surface_z(other, ox, oy) + 24}"),
                                          ("angle", "0")], "brushes": None})
    if teleports > cons["teleporters"]:
        raise RequestError(f"the request asks for {teleports} teleporter(s), constraints.teleporters "
                           f"allows {cons['teleporters']}")
    if doors > cons["doors"]:
        raise RequestError(f"the request asks for {doors} door(s), constraints.doors allows {cons['doors']}")
    return entities


def plan(request):
    """Everything the .map needs, with every budget checked."""
    adj = adjacency(request)
    conns = check_connections(request)
    brushes = build_brushes(request)
    entities = build_entities(request)
    brush_total = len(brushes) + sum(len(e["brushes"] or []) for e in entities)
    cons = request["constraints"]
    if brush_total > cons["max_brushes"]:
        raise RequestError(f"the layout needs {brush_total} brushes, constraints.max_brushes allows "
                           f"{cons['max_brushes']} (hard cap {HARD_MAX_BRUSHES})")
    if len(entities) > cons["max_entities"]:
        raise RequestError(f"the layout needs {len(entities)} entities with worldspawn, "
                           f"constraints.max_entities allows {cons['max_entities']} (hard cap "
                           f"{HARD_MAX_ENTITIES})")
    return {"brushes": brushes, "entities": entities, "adjacency": adj, "connections": conns,
            "brush_count": brush_total, "entity_count": len(entities), "extent": hull_extent(request)}


def readiness(request, the_plan):
    """What navgen will find, before it runs: spawns, pickups, floor and the edict outlook."""
    spawns = sum(1 for e in request["entities"] if e["classname"] == "info_player_deathmatch")
    pickups = sum(1 for e in request["entities"]
                  if e["classname"].startswith(("item_", "weapon_")))
    floor_area = 0
    for r in request["regions"]:
        if r["kind"] in ("floor", "stairs", "block") or (r["kind"] == "pit" and "liquid" not in r):
            floor_area += r["size"][0] * r["size"][1]
    reasons = []
    if spawns < 2:
        reasons.append("fewer than two deathmatch spawns")
    if not pickups:
        reasons.append("no pickup, so the reach gate has nothing to route to and bots have no errand")
    # world, 8 client slots, map entities; navgen caps waypoints under the
    # 600 ceiling and prints its own budget once it runs
    estimate = 1 + 8 + the_plan["entity_count"]
    return {"spawns": spawns, "pickups": pickups, "standable_area": floor_area,
            "entities_before_waypoints": estimate,
            "waypoint_room": 600 - 60 - estimate,
            "ready": not reasons, "reasons": reasons}


SEAT_RISE = 64     # a waypoint stands at most this far above its floor (navgen seats at +24)
SEAT_WIDTH = 32    # a footprint narrower than the player hull cannot seat a waypoint


def coverage(request, nodes):
    """Which standable floors the generated graph seats a waypoint on.

    A floor region with no waypoint is a pocket: bots that fall or are knocked
    onto it are off the graph, steering at a waypoint they cannot reach by a
    link, and every routed motion there measures that, not the behaviour the
    map was built to isolate. lab_drymix and lab_drymix2 registered with one
    (ledge_s, 58 and 36 per cent of their brink re-entries). A region the
    request marks off_graph is exempt; stairs, blocks, pits and voids are not
    checked, and nor is a footprint too narrow to seat the player hull.
    """
    regions, uncovered, exempt = [], [], []
    for r in request["regions"]:
        if r["kind"] != "floor":
            continue
        x0, y0, x1, y1 = footprint(r)
        if min(r["size"]) < SEAT_WIDTH:
            continue
        z = r["floor_z"]
        seated = sum(1 for n in nodes if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and z <= n[2] <= z + SEAT_RISE)
        regions.append({"name": r["name"], "waypoints": seated})
        if seated == 0:
            (exempt if r.get("off_graph") else uncovered).append(r["name"])
    return {"covered": not uncovered, "uncovered": uncovered, "exempt": exempt, "regions": regions}


def graph_coverage(root, request, qc_path=None):
    qc_path = Path(qc_path) if qc_path else src_dir(root) / f"argus_nav_{request['name']}.qc"
    graph = Path(str(qc_path) + ".json")
    if not graph.is_file():
        raise RuntimeError(f"no graph at {rel(root, graph)}; run navgen first")
    nodes = json.loads(graph.read_text(encoding="utf-8")).get("nodes", [])
    return coverage(request, nodes)


def map_text(request, the_plan):
    src = source_sha256(request)
    lines = [
        f"// Generated by tools/lab_mapgen.py v{GENERATOR_VERSION}; do not hand-edit.",
        f"// Rebuild: python tools/lab_mapgen.py build labmaps/{request['name']}/request.json",
        f"// source sha256 {src}",
        f"// claim tier {request['claim_tier']}: an isolation instrument, never stock-map evidence",
    ]
    for i, ent in enumerate(the_plan["entities"]):
        lines.append(f"// entity {i}")
        lines.append("{")
        for k, v in ent["keys"]:
            lines.append(f'"{k}" "{v}"')
        brushes = the_plan["brushes"] if i == 0 else (ent["brushes"] or [])
        for b in brushes:
            lines.append(b.text())
        lines.append("}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- textures

# Palette indices into the stock Quake palette. The textures are generated
# here, so the BSP carries no third-party art at all.
def _pattern(name, w, h):
    px = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            if name == TEX_FLOOR:
                v = 7 if ((x // 32) + (y // 32)) % 2 else 9
                if x % 32 == 0 or y % 32 == 0:
                    v = 4
            elif name == TEX_TRIM:
                v = 196 if ((x + y) // 8) % 2 else 6
            elif name == TEX_WALL:
                row = y // 16
                v = 19 if (x + (8 if row % 2 else 0)) % 32 else 16
                if y % 16 == 0:
                    v = 16
            elif name == TEX_CEIL:
                v = 11 if (x // 16 + y // 16) % 2 else 12
            elif name == TEX_DOOR:
                v = 74 if (y // 8) % 2 else 77
            elif name == "*lavalab":
                v = 230 + ((x * 3 + y * 5) // 7) % 8
            elif name == "*slimelab":
                v = 56 + ((x + y) // 6) % 6
            elif name == "*waterlab":
                v = 210 + ((x * 2 + y) // 9) % 6
            elif name == TEX_SKY:
                v = 0 if x >= w // 2 else 208 + ((x + y) // 12) % 4
            elif name == TEX_TRIGGER:
                v = 251
            else:
                v = 15
            px[y * w + x] = v
    return bytes(px)


TEXTURES = (
    (TEX_FLOOR, 64, 64), (TEX_TRIM, 64, 64), (TEX_WALL, 64, 64), (TEX_CEIL, 64, 64),
    (TEX_DOOR, 64, 64), ("*lavalab", 64, 64), ("*slimelab", 64, 64), ("*waterlab", 64, 64),
    (TEX_SKY, 256, 128), (TEX_TRIGGER, 16, 16),
)


def _miptex(name, w, h):
    base = _pattern(name, w, h)
    levels = [base]
    for k in (1, 2, 3):
        f = 1 << k
        lw, lh = w // f, h // f
        levels.append(bytes(base[(y * f) * w + x * f] for y in range(lh) for x in range(lw)))
    header = name.encode("ascii").ljust(16, b"\0") + struct.pack("<II", w, h)
    offsets = []
    pos = 40
    for lvl in levels:
        offsets.append(pos)
        pos += len(lvl)
    return header + struct.pack("<4I", *offsets) + b"".join(levels)


def wad_bytes():
    """A deterministic WAD2 holding every texture the generator names."""
    lumps = [(name, _miptex(name, w, h)) for name, w, h in TEXTURES]
    data = bytearray(b"WAD2" + struct.pack("<ii", len(lumps), 0))
    directory = bytearray()
    for name, blob in lumps:
        pos = len(data)
        data += blob
        directory += struct.pack("<iiibbbb", pos, len(blob), len(blob), 0x44, 0, 0, 0)
        directory += name.encode("ascii").ljust(16, b"\0")
    infotable = len(data)
    data += directory
    struct.pack_into("<i", data, 8, infotable)
    return bytes(data)


# ---------------------------------------------------------------- generate

def out_dir_for(root, request, out=None):
    labmaps = labmaps_dir(root)
    out_dir = confined_path(root, out or labmaps / request["name"], (labmaps,), "--out")
    name = request["name"]
    # The compiler and the generator both write fixed-name files here.
    for leaf in ("request.json", "manifest.json", "lab_textures.wad",
                 *(f"{name}.{suffix}" for suffix in ("map", "bsp", "prt", "pts", "lit", "compile.log"))):
        confined_path(root, out_dir / leaf, (out_dir,), "--out")
    return out_dir


def generate(request, out_dir):
    """Write <map>.map and lab_textures.wad; return the plan and file hashes."""
    the_plan = plan(request)
    text = map_text(request, the_plan)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    map_path = out_dir / f"{request['name']}.map"
    write_text(map_path, text)
    wad = wad_bytes()
    (out_dir / "lab_textures.wad").write_bytes(wad)
    return the_plan, {"map": map_path, "map_sha256": sha256_bytes(text.encode("utf-8")),
                      "wad_sha256": sha256_bytes(wad)}


# ---------------------------------------------------------------- ericw-tools

def load_profile():
    return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))


def platform_key():
    system = platform.system().lower()
    if system == "windows":
        return "win64"
    if system == "linux":
        return "linux"
    raise RuntimeError(f"no pinned ericw-tools build for {platform.system()}; set ARGUS_ERICW")


def tools_dir(root, profile=None):
    override = os.environ.get("ARGUS_ERICW")
    if override:
        return Path(override).resolve()
    profile = profile or load_profile()
    asset = profile["ericw_tools"]["assets"][platform_key()]
    stem = asset["name"].rsplit(".zip", 1)[0]
    return (Path(root) / profile["ericw_tools"]["install_dir"] / stem / "bin").resolve()


def tool_path(directory, name):
    exe = directory / (name + (".exe" if os.name == "nt" else ""))
    return exe if exe.is_file() else None


def tools_status(root):
    profile = load_profile()
    directory = tools_dir(root, profile)
    found = {name: tool_path(directory, name) for name in ("qbsp", "vis", "light")}
    return {"version": profile["ericw_tools"]["version"], "dir": rel(root, directory),
            "ready": all(found.values()),
            "tools": {k: (rel(root, v) if v else None) for k, v in found.items()}}


def install_tools(root, from_zip=None):
    """Fetch (or take) the pinned release zip, verify size and SHA-256, and unpack it."""
    profile = load_profile()
    pinned = profile["ericw_tools"]
    asset = pinned["assets"][platform_key()]
    install = Path(root) / pinned["install_dir"]
    downloads = install / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    zip_path = Path(from_zip).resolve() if from_zip else downloads / asset["name"]
    if not zip_path.is_file():
        print(f"downloading {asset['url']} ({asset['size']} bytes)")
        with urllib.request.urlopen(asset["url"], timeout=120) as response:  # noqa: S310 - pinned https URL
            data = response.read()
        zip_path.write_bytes(data)
    data = zip_path.read_bytes()
    if len(data) != asset["size"] or sha256_bytes(data) != asset["sha256"]:
        raise RuntimeError(f"{zip_path} does not match the pinned {asset['name']} "
                           f"(size {len(data)}, sha256 {sha256_bytes(data)}); delete it and retry")
    stem = asset["name"].rsplit(".zip", 1)[0]
    target = install / stem
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename
            if not name.startswith(stem + "/") or ".." in Path(name).parts or Path(name).is_absolute():
                raise RuntimeError(f"{asset['name']}: unexpected member {name}")
        archive.extractall(install)
    if os.name != "nt":
        for tool in ("qbsp", "vis", "light", "bspinfo", "bsputil"):
            path = target / "bin" / tool
            if path.is_file():
                path.chmod(0o755)
    write_json(target / "INSTALLED.json", {"asset": asset["name"], "sha256": asset["sha256"],
                                           "version": pinned["version"], "commit": pinned["commit"]})
    return target


def run_tool(exe, args, cwd, timeout, log):
    proc = subprocess.run([str(exe), *args], cwd=str(cwd), capture_output=True, text=True,
                          timeout=timeout, errors="replace")
    out = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
    log.append(f"$ {exe.name} {' '.join(args)}\n{out}")
    return proc.returncode, out


def compile_map(root, request, out_dir, the_plan=None, files=None):
    """generate, then qbsp, vis and light under the checked-in profile."""
    if the_plan is None or files is None:
        the_plan, files = generate(request, out_dir)
    profile = load_profile()
    directory = tools_dir(root, profile)
    exes = {name: tool_path(directory, name) for name in ("qbsp", "vis", "light")}
    missing = [k for k, v in exes.items() if v is None]
    if missing:
        raise RuntimeError(f"ericw-tools {profile['ericw_tools']['version']} is not installed at "
                           f"{rel(root, directory)} (missing {', '.join(missing)}); run "
                           "python tools/lab_mapgen.py tools --install")
    name = request["name"]
    out_dir = Path(out_dir)
    bsp = out_dir / f"{name}.bsp"
    for stale in (bsp, out_dir / f"{name}.prt", out_dir / f"{name}.pts", out_dir / f"{name}.lit"):
        if stale.exists():
            stale.unlink()
    log = []
    steps = {}
    timeouts = profile.get("timeouts_sec", {})
    for step, args in (("qbsp", profile["qbsp"] + ["-wadpath", str(out_dir), f"{name}.map", f"{name}.bsp"]),
                       ("vis", profile["vis"] + [f"{name}.bsp"]),
                       ("light", profile["light"] + [f"{name}.bsp"])):
        code, out = run_tool(exes[step], args, out_dir, timeouts.get(step, 300), log)
        warnings = sum(1 for line in out.splitlines() if "WARNING" in line.upper())
        steps[step] = {"ok": code == 0, "exit": code, "warnings": warnings}
        if step == "qbsp":
            leak = (out_dir / f"{name}.pts").exists() or "LEAK" in out.upper()
            steps[step]["leak"] = leak
            if code != 0 or leak or not bsp.is_file():
                write_text(out_dir / f"{name}.compile.log", "\n".join(log))
                raise RuntimeError(f"qbsp failed for {name} (exit {code}, leak {leak}); see "
                                   f"{rel(root, out_dir / (name + '.compile.log'))}")
        elif code != 0:
            write_text(out_dir / f"{name}.compile.log", "\n".join(log))
            raise RuntimeError(f"{step} failed for {name} (exit {code}); see "
                               f"{rel(root, out_dir / (name + '.compile.log'))}")
    write_text(out_dir / f"{name}.compile.log", "\n".join(log))
    sys.path.insert(0, str(HERE))
    from argus_bsp import Bsp  # noqa: E402 - tools path set just above
    try:
        compiled = Bsp(bsp)
    except ValueError as error:
        raise RuntimeError(f"{error}; the lab ships BSP29 for vanilla engines") from error
    data = compiled.data
    return {
        "ericw_tools": profile["ericw_tools"]["version"],
        "ericw_commit": profile["ericw_tools"]["commit"],
        "profile_sha256": sha256_file(PROFILE_FILE),
        "steps": steps,
        "bsp": rel(root, bsp),
        "bsp_bytes": len(data),
        "bsp_sha256": sha256_bytes(data),
        "bsp_entities": sum(1 for entity in compiled.entities() if entity),
    }, the_plan, files


# ---------------------------------------------------------------- build

def manifest_core(root, request, the_plan, files):
    return {
        "schema": SCHEMA,
        "scenario_id": scenario_id(request),
        "map": request["name"],
        "intent": request["intent"],
        "claim_tier": request["claim_tier"],
        "claims": request["claims"],
        "promotion_rule": PROMOTION_RULE,
        "generator": {"version": GENERATOR_VERSION, "source_sha256": source_sha256(request),
                      "map_sha256": files["map_sha256"], "wad_sha256": files["wad_sha256"]},
        "counts": {"brushes": the_plan["brush_count"], "entities": the_plan["entity_count"],
                   "max_brushes": request["constraints"]["max_brushes"],
                   "max_entities": request["constraints"]["max_entities"]},
        "extent": list(the_plan["extent"]),
        "regions": [{"name": r["name"], "kind": r["kind"], "min": r["min"], "size": r["size"],
                     "floor_z": r["floor_z"]} for r in request["regions"]],
        "adjacency": the_plan["adjacency"],
        "connections": the_plan["connections"],
        "navgen_readiness": readiness(request, the_plan),
        "files": {"request": f"labmaps/{request['name']}/request.json",
                  "map": rel(root, files["map"])},
    }


def install_bsp(root, request, bsp):
    """Copy the BSP where the cartographer, navgen and the engine look for maps."""
    name = request["name"]
    placed = {}
    for key, directory in (("maps", maps_dir(root)), ("engine", engine_maps_dir(root))):
        directory.mkdir(parents=True, exist_ok=True)
        dest = directory / f"{name}.bsp"
        shutil.copyfile(bsp, dest)
        placed[key] = rel(root, dest)
    return placed


def build(root, request, request_path=None, install=True):
    out_dir = out_dir_for(root, request)
    out_dir.mkdir(parents=True, exist_ok=True)
    canonical_request = out_dir / "request.json"
    if request_path is None or Path(request_path).resolve() != canonical_request.resolve():
        write_json(canonical_request, request)
    the_plan, files = generate(request, out_dir)
    compiled, the_plan, files = compile_map(root, request, out_dir, the_plan, files)
    manifest = manifest_core(root, request, the_plan, files)
    manifest["compile"] = compiled
    if install:
        manifest["install"] = install_bsp(root, request, out_dir / f"{request['name']}.bsp")
    previous = out_dir / "manifest.json"
    if previous.is_file():
        try:
            old = json.loads(previous.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        # nav and registration facts belong to the BSP they were measured on
        if old.get("compile", {}).get("bsp_sha256") == compiled["bsp_sha256"]:
            for key in ("nav", "mill", "registration"):
                if key in old:
                    manifest[key] = old[key]
    write_json(previous, manifest)
    return manifest


def nav_counts(qc_json):
    graph = json.loads(Path(qc_json).read_text(encoding="utf-8"))
    out = {"nodes": len(graph.get("nodes", [])), "links": len(graph.get("links", []))}
    for key in ("jlinks", "doorlinks", "rjlinks", "liftlinks", "telelinks", "swimlinks", "droplinks"):
        if graph.get(key):
            out[key] = len(graph[key])
    return out


def run_navgen(root, request, qc=None, png=None):
    """tools/argus_navgen.py on the built BSP, without registration (the CLI path)."""
    name = request["name"]
    source, runs = src_dir(root), runs_dir(root)
    default_qc = source / f"argus_nav_{name}.qc"
    qc = confined_path(root, qc or default_qc, (source,), "--qc")
    png = confined_path(root, png or runs / f"nav_{name}.png", (runs,), "--png")
    if qc.suffix != ".qc" or png.suffix != ".png":
        raise RequestError("nav --qc needs a .qc path and --png needs a .png path")
    graph = confined_path(root, f"{qc}.json", (source,), "--qc")
    if qc != default_qc and (qc.exists() or graph.exists()):
        raise RequestError(f"--qc refuses to replace a file outside this map's generated pair: {qc}")
    bsp = maps_dir(root) / f"{name}.bsp"
    if not bsp.is_file():
        bsp = out_dir_for(root, request) / f"{name}.bsp"
    if not bsp.is_file():
        raise RuntimeError(f"no BSP for {name}; run build first")
    proc = subprocess.run([sys.executable, str(HERE / "argus_navgen.py"), str(bsp), name, str(qc), str(png),
                           "--no-dispatcher"], cwd=str(root), capture_output=True, text=True,
                          errors="replace", timeout=900)
    text = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise RuntimeError(f"navgen failed for {name}:\n" + "\n".join(text.splitlines()[-30:]))
    return {"qc": str(qc), "stdout": text}


def nav_summary(root, request, qc_path, text=""):
    name = request["name"]
    qc_path = Path(qc_path)
    summary = {"qc": rel(root, qc_path), "graph": rel(root, Path(str(qc_path) + ".json"))}
    summary.update(nav_counts(str(qc_path) + ".json"))
    for line in text.splitlines():
        if line.startswith("edict budget: status "):
            summary["edict_budget"] = line.strip()
            break
    sys.path.insert(0, str(HERE))
    from argus_mapgate import assess_playability  # noqa: E402 - tools path set just above
    bsp = maps_dir(root) / f"{name}.bsp"
    if not bsp.is_file():
        bsp = out_dir_for(root, request) / f"{name}.bsp"
    verdict = assess_playability(bsp, str(qc_path) + ".json")
    summary["playability"] = {"playable": verdict.playable, "spawns": verdict.spawn_count,
                              "pickups": verdict.item_count, "graph_md5": verdict.graph_md5,
                              "reasons": list(verdict.reasons)}
    return summary


def register_scenario(root, manifest):
    """Record the scenario, its tier and the promotion rule in tools/lab_instruments.json."""
    path = Path(root) / "tools" / "lab_instruments.json"
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"schema": 1}
    block = doc.setdefault("lab_scenarios", {})
    block["about"] = ("Generated micro-maps (tools/lab_mapgen.py, the lab_request MCP tool). Each "
                      "isolates one mechanism and is trusted for isolation-tier claims only.")
    block["rule"] = PROMOTION_RULE
    block["docs"] = "docs/lab-scenarios.md"
    scenarios = block.setdefault("scenarios", {})
    nav = manifest.get("nav", {})
    scenarios[manifest["map"]] = {
        "id": manifest["scenario_id"],
        "claim_tier": manifest["claim_tier"],
        "intent": manifest["intent"],
        "claims": manifest["claims"],
        "request": manifest["files"]["request"],
        "manifest": f"labmaps/{manifest['map']}/manifest.json",
        "source_sha256": manifest["generator"]["source_sha256"],
        "bsp_sha256": manifest.get("compile", {}).get("bsp_sha256"),
        "registered": bool(manifest.get("registration", {}).get("registered")),
        "playable": bool(nav.get("playability", {}).get("playable")),
    }
    if "coverage" in manifest:
        scenarios[manifest["map"]]["off_graph_regions"] = manifest["coverage"]["uncovered"]
    doc["lab_scenarios"]["scenarios"] = dict(sorted(scenarios.items()))
    write_json(path, doc)
    return scenarios[manifest["map"]]


def record(root, request, nav_text=None, mill=None, registered=None, qc_path=None):
    out_dir = out_dir_for(root, request)
    path = out_dir / "manifest.json"
    if not path.is_file():
        raise RuntimeError(f"no manifest for {request['name']}; run build first")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    qc_path = Path(qc_path) if qc_path else src_dir(root) / f"argus_nav_{request['name']}.qc"
    if Path(str(qc_path) + ".json").is_file():
        manifest["nav"] = nav_summary(root, request, qc_path, nav_text or "")
        manifest["coverage"] = graph_coverage(root, request, qc_path)
    if mill is not None:
        manifest["mill"] = mill
    if registered is not None:
        sys.path.insert(0, str(HERE))
        from argus_registration import registration  # noqa: E402 - tools path set just above
        src = src_dir(root)
        branch, progs = registration((src / "argus_nav_dispatch.qc").read_text(encoding="utf-8"),
                                     (src / "progs.src").read_text(encoding="utf-8"), request["name"])
        manifest["registration"] = {"registered": bool(branch and progs), "dispatcher": branch,
                                    "progs_src": progs, "requested": registered}
    write_json(path, manifest)
    manifest["scenario"] = register_scenario(root, manifest)
    return manifest


# ---------------------------------------------------------------- cli

def _flag(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise SystemExit(f"{name} needs a value")
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd = args.pop(0)
    root = repo_root()
    as_json = "--json" in args
    if as_json:
        args.remove("--json")
    try:
        if cmd == "tools":
            if "--install" in args:
                target = install_tools(root, _flag(args, "--from-zip"))
                print(f"installed {rel(root, target)}")
            print(json.dumps(tools_status(root), indent=2))
            return 0
        out = _flag(args, "--out")
        qc = _flag(args, "--qc")
        png = _flag(args, "--png")
        nav_out = _flag(args, "--nav-out")
        mill_file = _flag(args, "--mill")
        registered = _flag(args, "--registered")
        install = "--no-install" not in args
        args = [a for a in args if a != "--no-install"]
        if len(args) != 1:
            raise SystemExit(f"usage: lab_mapgen.py {cmd} REQUEST.json (see --help)")
        if out is not None and cmd not in ("generate", "compile"):
            raise RequestError("--out is only available with generate or compile")
        request = load_request(args[0])
        if cmd == "check":
            the_plan = plan(request)
            result = {"ok": True, "scenario_id": scenario_id(request), "brushes": the_plan["brush_count"],
                      "entities": the_plan["entity_count"], "adjacency": the_plan["adjacency"],
                      "connections": the_plan["connections"], "readiness": readiness(request, the_plan)}
        elif cmd == "generate":
            the_plan, files = generate(request, out_dir_for(root, request, out))
            result = {"ok": True, "scenario_id": scenario_id(request), "map": rel(root, files["map"]),
                      "map_sha256": files["map_sha256"], "brushes": the_plan["brush_count"],
                      "entities": the_plan["entity_count"]}
        elif cmd == "compile":
            out_dir = out_dir_for(root, request, out)
            compiled, the_plan, files = compile_map(root, request, out_dir)
            result = manifest_core(root, request, the_plan, files)
            result["compile"] = compiled
        elif cmd == "build":
            result = build(root, request, args[0], install=install)
        elif cmd == "nav":
            done = run_navgen(root, request, qc, png)
            result = nav_summary(root, request, done["qc"], done["stdout"])
        elif cmd == "coverage":
            result = graph_coverage(root, request, qc)
        elif cmd == "record":
            nav_text = None
            if nav_out:
                nav_log = confined_path(root, nav_out, (labmaps_dir(root), runs_dir(root)), "--nav-out")
                nav_text = nav_log.read_text(encoding="utf-8")
            mill = json.loads(Path(mill_file).read_text(encoding="utf-8")) if mill_file else None
            reg = None if registered is None else registered.lower() in ("yes", "true", "1")
            result = record(root, request, nav_text, mill, reg, qc)
        else:
            raise SystemExit(f"unknown command {cmd} (see --help)")
    except RequestError as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc), "kind": "request"}))
        else:
            print(f"request error: {exc}", file=sys.stderr)
        return 2
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc), "kind": "build"}))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
