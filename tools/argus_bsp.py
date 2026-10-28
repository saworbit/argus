"""Shared Quake BSP hull-0 reader for offline telemetry and graph inspection."""
from pathlib import Path
import struct


def load_classifier(bsp_path):
    """Return contents(x, y, z) from the world model hull-0 BSP tree.

    Opening errors propagate so each caller retains its own missing-BSP policy.
    This point classifier does not perform player-hull collision tests.
    """
    data = Path(bsp_path).read_bytes()

    def lump(index):
        off, length = struct.unpack_from("<ii", data, 4 + index * 8)
        return data[off : off + length]

    raw = lump(1)
    planes = [struct.unpack_from("<4f", raw, i * 20) for i in range(len(raw) // 20)]
    raw = lump(5)
    nodes = [struct.unpack_from("<i8h2H", raw, i * 24) for i in range(len(raw) // 24)]
    raw = lump(10)
    leaves = [struct.unpack_from("<2i6h2H4B", raw, i * 28) for i in range(len(raw) // 28)]
    root = struct.unpack_from("<9f7i", lump(14), 0)[9]

    def contents(x, y, z):
        node = root
        while node >= 0:
            plane = planes[nodes[node][0]]
            side = plane[0] * x + plane[1] * y + plane[2] * z - plane[3]
            node = nodes[node][1] if side >= 0 else nodes[node][2]
        return leaves[-1 - node][0]

    return contents
