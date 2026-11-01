"""Water-route receipts must prove movement and retain the failure control."""
from pathlib import Path
import unittest

from verify_water_route import audit_fixture, inspect_fixture, require_outcome, inspect_decisions, DECISION_LABELS


def receipt(control=False, slow=False):
    positions = ['-279 425 8'] * 4 if control else ['-279 425 8','-250 300 8','-220 180 40','-183 73 80']
    times = [0, .5, 1, 1.5]
    if control: times = [0, .5, 1, 1.5, *[i/2 for i in range(4,37)]]; positions = [positions[0]]*len(times)
    rate = 10 if slow else 72
    rows = ['ARGUS init on e1m5','BHVRPL begin water_route',
            f"WRFIX begin dt_ms {100 if slow else 14} case 1 start '-279 425 8' goal '-183 73 80'"]
    for t,p in zip(times,positions):
        rows.append(f"WRFIX sample t {t} pos '{p}' node '-279 425 -32' grounded 0 wet 3 feet -3 handoffs {int(not control and t>0)} active 1 hp 100 frames {round(t*rate)+1}")
    rows.append(f"WRFIX end completed {int(not control)} seconds {times[-1]} handoffs {int(not control)} active 1 pos '{positions[-1]}' hp 100 frames {round(times[-1]*rate)+1} grounded {int(not control)} feet {-3 if control else -1}")
    return '\n'.join(rows)


class WaterRouteContracts(unittest.TestCase):
    def test_current_goal_identity_requires_corrected_layout(self):
        legacy=receipt()
        self.assertFalse(inspect_fixture(legacy,'e1m5',.0139)['goal_identity_verified'])
        current=legacy.replace('dt_ms 14 case','dt_ms 14 layout 2 case')
        self.assertTrue(inspect_fixture(current,'e1m5',.0139)['goal_identity_verified'])
        with self.assertRaises(AssertionError):
            inspect_fixture(current.replace('layout 2','layout 3'),'e1m5',.0139)

    def test_complete_routes_and_required_negative_at_both_rates(self):
        for control in (False,True):
            for slow in (False,True):
                row=inspect_fixture(receipt(control,slow),'e1m5',.1 if slow else .0139)
                require_outcome(row,control)
                with self.assertRaises(AssertionError): require_outcome(row,not control)
        self.assertTrue(inspect_fixture(receipt().replace('hp 100 frames 109','hp 200 frames 109'),'e1m5',.0139)['completed'])

    def test_partial_wrong_map_rate_geometry_or_quarantine_cannot_pass(self):
        good=receipt()
        for bad in (good+good, good.replace('BHVRPL begin water_route',''),
                    good.replace('ARGUS init on e1m5','ARGUS init on dm3'),
                    good.replace('dt_ms 14','dt_ms 100'),
                    good.replace('start \'-279 425 8\'','start \'0 0 0\''),
                    good+'\nWRFIX unknown 1', good.replace('hp 100','hp 99'),
                    good.replace('active 1','active 0'), good+'\nProgram error'):
            with self.subTest(bad=bad):
                with self.assertRaises(AssertionError): inspect_fixture(bad,'e1m5',.0139)

    def test_completion_requires_final_position_and_continuous_motor_evidence(self):
        for bad in (receipt().replace("active 1 pos '-183 73 80'","active 1 pos '-279 425 8'"),
                    receipt().replace("pos '-250 300 8'","pos '1000 1000 1000'"),
                    receipt().replace('frames 109','frames 2')):
            with self.assertRaises(AssertionError): inspect_fixture(bad,'e1m5',.0139)

    def test_component_receipts_require_every_ordered_decision(self):
        lines=['RDEC begin checks 56',*[f'RDEC check {label} 1' for label in DECISION_LABELS],
               'RDEC end checks 56 failures 0']
        good='\n'.join(lines)
        self.assertEqual(inspect_decisions(good,True),56)
        self.assertEqual(inspect_decisions('',False),0)
        for bad in (good.replace(lines[3],''), good+'\n'+lines[3],
                    good.replace(lines[3],lines[3][:-1]+'0'),good+'\nRDEC malformed',
                    '\n'.join([*lines[:2],lines[3],lines[2],*lines[4:]])):
            with self.assertRaises(AssertionError): inspect_decisions(bad,True)
        with self.assertRaises(AssertionError): inspect_decisions(good,False)

    def test_cold_ride_cannot_substitute_for_the_pin_negative(self):
        cold=dict(case=11,completed=True,seconds=4.2)
        require_outcome(cold,False)
        with self.assertRaises(AssertionError): require_outcome(cold,True)
        for control,elapsed in ((False,4.1),(True,8.8)):
            row=dict(case=12,completed=True,seconds=elapsed)
            require_outcome(row,control)
            with self.assertRaises(AssertionError): require_outcome(row,not control)

    def test_observer_cannot_drive_or_repair_the_actor(self):
        source=Path(__file__).with_name('fixtures').joinpath('water_route.qc').read_text()
        audit_fixture(source)
        for mutation in ('setorigin (wr_bot, wr_target);','wr_bot.ar_node = world;',
                         'Argus_AI ();','walkmove (90, 10);','wr_bot.health = 100;'):
            with self.assertRaises(AssertionError):
                audit_fixture(source.replace('wr_frames = wr_frames + 1;', 'wr_frames = wr_frames + 1;\n'+mutation))
        with self.assertRaises(AssertionError):
            audit_fixture(source.replace('wr_bot.think = SUB_Null;', 'wr_bot.health = 100; wr_bot.think = SUB_Null;'))


if __name__ == '__main__': unittest.main()
