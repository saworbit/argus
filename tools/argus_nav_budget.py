"""Shared edict-budget verdicts for navigation generation."""

from dataclasses import dataclass


EDICT_CEILING = 600
# Stock Quake starts map allocation after the world and maxclients.
WORLD_AND_CLIENT_SLOTS = 9
# Four bot edicts plus bodies, missiles, backpacks, gibs, and temporary
# entities. This is almost twice the measured busy-match peak overhead.
RUNTIME_RESERVE = 60
TIGHT_SLACK = 20


@dataclass(frozen=True)
class EdictBudget:
    status: str
    waypoints: int
    live_entities: int
    lump_entities: int
    world_and_client_slots: int
    runtime_reserve: int
    total: int
    ceiling: int
    slack: int

    @property
    def can_register(self):
        return self.status != "over-budget"

    def line(self):
        return (
            f"edict budget: status {self.status}; waypoints {self.waypoints}; "
            f"live bsp entities {self.live_entities} of {self.lump_entities}; "
            f"world and client slots {self.world_and_client_slots}; "
            f"runtime reserve {self.runtime_reserve} for four bots and "
            f"dynamic entities; total {self.total} of {self.ceiling}; "
            f"slack {self.slack}"
        )


def assess_edict_budget(waypoints, live_entities, lump_entities):
    total = (waypoints + live_entities + WORLD_AND_CLIENT_SLOTS
             + RUNTIME_RESERVE)
    slack = EDICT_CEILING - total
    if slack < 0:
        status = "over-budget"
    elif slack < TIGHT_SLACK:
        status = "tight"
    else:
        status = "ok"
    return EdictBudget(
        status=status,
        waypoints=waypoints,
        live_entities=live_entities,
        lump_entities=lump_entities,
        world_and_client_slots=WORLD_AND_CLIENT_SLOTS,
        runtime_reserve=RUNTIME_RESERVE,
        total=total,
        ceiling=EDICT_CEILING,
        slack=slack,
    )
