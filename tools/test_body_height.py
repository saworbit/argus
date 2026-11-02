"""Physical escape receipts must not accept forged geometry or ownership."""
from pathlib import Path
import unittest
from verify_body_height import CASES,PHYSICAL,audit_fixture,inspect_fixture


def receipt(map_name='e1m6',slow=False):
    rows=['ARGUS init on '+map_name,'BHVRPL begin body_height',
          'BHFIX begin dt_ms '+('100' if slow else '14')+' layout 1']
    if map_name=='dm3':
        for label in CASES:
            rows.extend([f'BHCASE {label} initialfit 1 finalfit 1 distance {3 if label=="same_floor" else 0} dodge 0 firing 1',
                         f'BHCHECK {label} 1'])
    rows.extend(['BHENTRY beforefit 1 upperfit 1 afterfit 1 movement 0',
                 'BHCHECK entry_bodies_fit 1','BHCHECK entry_kept 1'])
    initial='338.1 125.9 -200' if map_name=='dm3' else '-157.1 833 -232'
    final='640 190 -200' if map_name=='dm3' else '-40 833 -232'
    rows.extend([f"BHPOSE t 0 pos '{initial}' active 1 hp 100",
                 *[f'BHCHECK {n} 1' for n in PHYSICAL[2:]],
                 f"BHRESULT completed 1 seconds 1 frames {11 if slow else 73} pos '{final}' hp 82 grounded 1 worldfloor 1 wet 0 lost 0 discontinuous 0",
                 f'BHFIX end checks {len(CASES)+len(PHYSICAL) if map_name=="dm3" else len(PHYSICAL)} failures 0'])
    # Keep the terminal near a real sampled pose.
    middle='490 160 -200' if map_name=='dm3' else final
    rows.insert(rows.index('BHCHECK physical_exit 1'),f"BHPOSE t 0.5 pos '{middle}' active 1 hp 82")
    return '\n'.join(rows)


class BodyHeightContracts(unittest.TestCase):
    def test_maps_and_profiles_need_real_entry_and_supported_escape(self):
        for m in ('dm3','e1m6'):
            for slow in (False,True):
                self.assertFalse(inspect_fixture(receipt(m,slow),m,.1 if slow else .0139)['failures'])

    def test_a_check_cannot_hide_an_invalid_body_or_lost_task(self):
        good=receipt()
        for bad in (good.replace('upperfit 1','upperfit 0'),
                    good.replace('afterfit 1','afterfit 0'),
                    good.replace('movement 0','movement 3'),
                    good.replace('active 1 hp 82','active 0 hp 82'),
                    good.replace('worldfloor 1','worldfloor 0'),
                    good.replace('grounded 1','grounded 0'),
                    good.replace('wet 0','wet 3'),
                    good.replace('lost 0','lost 1'),
                    good.replace('discontinuous 0','discontinuous 1')):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):
                inspect_fixture(bad,'e1m6',.0139)
        good=receipt('dm3')
        with self.assertRaises(AssertionError):
            inspect_fixture(good.replace('distance 3 dodge','distance 0 dodge'),'dm3',.0139)

    def test_wrong_map_cadence_duplicate_and_malformed_measurements_refuse(self):
        good=receipt()
        for bad in (good+good,good.replace('ARGUS init on e1m6','ARGUS init on dm3'),
                    good.replace('dt_ms 14','dt_ms 100'),
                    good.replace('BHCHECK physical_exit 1',''),
                    good+'\nBHPOSE nonsense',
                    good.replace('frames 73','frames 11'),good+'\nHost_Error: failure'):
            with self.subTest(bad=bad),self.assertRaises(AssertionError):
                inspect_fixture(bad,'e1m6',.0139)

    def test_passive_observer_refuses_actor_writes_and_decision_calls(self):
        text=Path(__file__).with_name('fixtures').joinpath('body_height.qc').read_text()
        audit_fixture(text)
        for line in ('setorigin (bh_bot, bh_target);','bh_bot.health = 100;',
                     'Argus_AI ();','walkmove (0, 32);','BodyHeightBefore ();'):
            with self.assertRaises(AssertionError):
                audit_fixture(text.replace('    bh_frames = bh_frames + 1;',line))
        with self.assertRaises(AssertionError):
            audit_fixture(text.replace('    bh_checks = bh_checks + 1;','    bh_bot.health = 100;'))


if __name__=='__main__':unittest.main()
