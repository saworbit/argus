"""Physical entity limits apply to optional and infrastructure promotions."""
from pathlib import Path
import re
import unittest

from argus_nav_budget import STATIC_CLASSES, assess_edict_budget, survives_spawn, waypoint_limits


class WaypointAllocation(unittest.TestCase):
    def test_e1m3_reserve_is_inside_its_180_slots(self):
        limits = waypoint_limits(351)
        self.assertEqual((limits.capacity, limits.decimation, limits.promotion), (180, 172, 172))
        self.assertFalse(limits.admits(172))
        self.assertTrue(limits.admits(172, infrastructure=True))
        self.assertFalse(limits.admits(180, infrastructure=True))

    def test_all_entity_densities_preserve_the_hard_reservation(self):
        for entities in range(601):
            limits = waypoint_limits(entities)
            self.assertLessEqual(limits.decimation, limits.promotion)
            self.assertLessEqual(limits.promotion + limits.infrastructure, limits.capacity)
            if limits.capacity:
                self.assertGreater(limits.decimation, 0)
                self.assertTrue(assess_edict_budget(limits.capacity, entities, entities).can_register)
            self.assertFalse(limits.admits(limits.capacity))
            self.assertFalse(limits.admits(limits.capacity, infrastructure=True))

    def test_roomy_maps_keep_the_existing_optional_and_infrastructure_limits(self):
        limits = waypoint_limits(88)
        self.assertEqual((limits.decimation, limits.promotion, limits.infrastructure), (200, 260, 8))
        self.assertTrue(limits.admits(267, infrastructure=True))
        self.assertFalse(limits.admits(268, infrastructure=True))

    def test_exhausted_map_has_no_decimation_target(self):
        self.assertEqual(waypoint_limits(531).decimation, 0)
        self.assertEqual(waypoint_limits(600).capacity, 0)


class SpawnSurvival(unittest.TestCase):
    def test_self_removing_and_static_classes_hold_no_edict(self):
        self.assertFalse(survives_spawn({"classname": "light"}))
        self.assertFalse(survives_spawn({"classname": "light", "targetname": ""}))
        self.assertTrue(survives_spawn({"classname": "light", "targetname": "t1"}))
        self.assertFalse(survives_spawn({"classname": "info_null"}))
        self.assertFalse(survives_spawn({"classname": "light_flame_small_yellow"}))
        self.assertFalse(survives_spawn({"classname": "func_illusionary"}))

    def test_cartograph_uses_the_same_static_classes(self):
        source = Path(__file__).with_name('argus_mcp') / 'src/cartograph.rs'
        rust = source.read_text(encoding='utf-8')
        static = re.search(r'const STATIC_EDICT_CLASSES: &\[&str\] = &\[(.*?)\];', rust, re.S)
        self.assertIsNotNone(static)
        self.assertCountEqual(re.findall(r'"([^"]+)"', static[1]), STATIC_CLASSES)

    def test_monsters_and_deathmatch_removals_still_count(self):
        self.assertTrue(survives_spawn({"classname": "monster_army"}))
        self.assertTrue(survives_spawn({"classname": "item_health", "spawnflags": "2048"}))
        self.assertTrue(survives_spawn({}))


if __name__ == '__main__':
    unittest.main()
