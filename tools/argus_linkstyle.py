"""One colour and one line pattern per navigation link meaning.

Every renderer draws a link type the same way: the navgen debug PNG and the
analyze_match plots on a white ground, and the lab GUI
(tools/argus_mcp/src/gui.html) on the brand's dark rock ground. Each meaning
keeps one hue, with one tint per ground. The GUI cannot import this file, so it
carries a copy of the rock column; test_tools_cli.py holds the two in step.

Colour alone cannot keep eight link types apart where any two can meet on a
map, so dashes carry identity too. Measured as OKLab Delta E x100: on rock,
every pair of hues clears 15 for normal vision, but walk/drop (4.2) and
rocket/swim (5.9) collide under deuteranopia, which their dashes resolve. On
white, walk/drop (5.7) is resolved the same way; swim/door sit at 11.7, and no
white-ground renderer draws either today. Sprint shares jump's red, because a
sprint is a jump, and differs by dash alone. Refusals add an X at the far end.
No data colour is orange: rust (#d4531e) is the brand's signature.
"""
from argus_navjson import STEP

# kind: (white-ground colour, rock-ground colour, dash). A dash is an on/off
# sequence in multiples of the line width, matplotlib's convention; the GUI
# scales it by its own line width. None draws solid.
LINK_STYLES = {
    "walk":   ("#2a9d5c", "#22c55e", None),
    "drop":   ("#cc8800", "#eab308", (5, 2.5)),
    "jump":   ("#d62728", "#ef4444", (1, 2)),
    "sprint": ("#d62728", "#ef4444", (1, 2, 1, 2, 5, 2)),
    "rocket": ("#c2389b", "#e879f9", (5, 2, 1, 2)),
    "lift":   ("#6d43c8", "#8b5cf6", None),
    "train":  ("#6d43c8", "#8b5cf6", None),
    "tele":   ("#3a342c", "#e8dfd0", (9, 3)),
    "swim":   ("#0e7490", "#22d3ee", None),
    "door":   ("#6f6555", "#9a8f7e", None),
}

# Waypoints are dots, not lines, so they share a hue family with nothing.
WAYPOINT = ("#1e6bd9", "#60a5fa")

# A refused link is a status, not a type: drawn dashed with an X at the end.
REFUSAL = ("#7f0000", "#fca5a5", (4, 3))


def walk_kind(src, dst):
    """'drop' when a plain link descends more than one step, else 'walk'.

    The same rule as nav_graph.rs link_kind. A one-way link at one level is
    still a walk: navgen's escape stitches and slot-clamp evictions leave many
    of those, and painting them as drops misread the graph.
    """
    return "drop" if src[2] - dst[2] > STEP else "walk"


def mpl(kind, white=True):
    """matplotlib keyword arguments for one link kind."""
    light, dark, dash = LINK_STYLES[kind]
    return {"color": light if white else dark,
            "ls": (0, dash) if dash else "-"}
