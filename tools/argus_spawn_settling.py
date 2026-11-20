"""Read the spawn floor contract shared with the Rust cartographer."""
import json
import math
from pathlib import Path
import re
import struct


SPAWN_SETTLING = json.loads(
    (Path(__file__).resolve().parent / "argus_mcp/src/spawn_settling.json").read_text(encoding="utf-8")
)

_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def entity_number(entity, key):
    """Read a finite single-precision decimal or the shared zero fallback."""
    fallback = SPAWN_SETTLING["invalid_entity_number"]
    value = entity.get(key, "").strip()
    if not _DECIMAL.fullmatch(value):
        return fallback
    try:
        number, = struct.unpack("<f", struct.pack("<f", float(value)))
    except OverflowError:
        return fallback
    return number if math.isfinite(number) else fallback


def brush_spawnflags(entity):
    """Truncate and saturate like the Rust cast to i32."""
    flags = int(entity_number(entity, "spawnflags"))
    return max(-(2**31), min(2**31 - 1, flags))
