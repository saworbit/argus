"""Read the spawn floor contract shared with the Rust cartographer."""
import json
from pathlib import Path


SPAWN_SETTLING = json.loads(
    (Path(__file__).resolve().parent / "argus_mcp/src/spawn_settling.json").read_text(encoding="utf-8")
)
