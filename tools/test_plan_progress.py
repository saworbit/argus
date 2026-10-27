"""Fail-closed evidence tests for shared plan recognition and physical escape."""
import subprocess
import sys
import unittest
from pathlib import Path

from check_plan_progress import LABELS, EDGE_LABELS, check_contract, check_physical, check_physical_edges, audit_physical_edges
from verify_plan_progress import physical_schedule


def contract():
    return '\n'.join(['BHVRPL begin plan_fixture', 'PLANFIX begin dm2',
        *(f'PLANFIX check {label} 1' for label in LABELS),
        'PLANFIX alternative weapon_rocketlauncher elapsed 1.2',
        'PLANFIX end checks 18 ok 1', 'PLANFIX cleanup owned_engine_pending_stop'])


def physical(success=True):
    rows = ['BHVRPL begin plan_fixture',
            "PEFIX begin dm2 case 2 start '0 0 0' solid 0 respawn 15 actor_solid 0"]
    if success:
        for i, x in enumerate((0, 80, 160, 240)):
            rows.append(f"PEFIX sample t {i * .2:.1f} pos '{x} 0 0' released {int(i > 0)} chosen {int(i > 1)} escaped {int(x > 220)} mode 2 goal weapon_rocketlauncher hp 100 frames {i * 14 + 1}")
    else:
        for i in range(62):
            rows.append(f"PEFIX sample t {i * .2:.1f} pos '0 0 0' released 0 chosen 0 escaped 0 mode 1 goal item_armor2 hp 100 frames {i * 14 + 1}")
    return '\n'.join(rows + [f'PEFIX end ok {int(success)}', 'PEFIX cleanup owned_engine_pending_stop'])


def physical_edge(case=4):
    coop = case == 3
    goal, seconds = (200, 23) if coop else (800, 30)
    rows = ['BHVRPL begin plan_physical_edges',
            f"PMFIX begin {'dm2' if coop else 'e1m2'} case {case} coop {int(coop)} dm {int(not coop)} pace {160 if case==4 else 320} start '0 0 0' goal '{goal} 0 0' solid 0"]
    if case == 6:
        rows.append("PMFIX door model *27 speed 20 from '0 0 0' to '0 0 128'")
    for i in range(seconds * 5 + 1):
        t = i / 5
        x = max(0, t - 21) * 100 if coop else -25 * t if t <= 4 else -100 + (t - 4) * 900 / 26
        if coop and t == 1: rows.append('PMFIX rest t 1 until 21')
        if coop and t == 21: rows += ['PMFIX gate t 21', 'PMFIX retry t 21 deadline 21']
        if not coop and t in (4, 9, 14, 19, 24):
            rows.append(f"PMFIX leg t {t} pos '{x} 0 0' node '{x} 0 0'")
        if t == seconds: rows.append(f"PMFIX contact t {t} pos '{goal} 0 0' active 1")
        rows.append(f"PMFIX sample t {t} pos '{x} 0 0' active {int(not coop or t < 1 or t >= 21)} stacked {int(coop)} hp 100 frames {i * 14 + 1}")
        if case == 6:
            z = min(128, max(0, (t-12)*20))
            rows.append(f"PMFIX mover t {t} pos '0 0 {z}' state {1 if t<=12 else 2 if z<128 else 0} speed 20")
    return '\n'.join(rows + ['PMFIX end ok 1 lost 0 bad 0', 'PMFIX cleanup owned_engine_pending_stop'])


class EvidenceTests(unittest.TestCase):
    def test_default_physics_gate_excludes_unsupported_motor_override(self):
        default=physical_schedule('all')
        self.assertNotIn(4,[row[2] for row in default])
        self.assertEqual({row[0] for row in default if row[2]==6},
                         {'current','deadline_control','opening_control'})
        for part in ('coop','normal','mover','mover-control','mover-release','half','deadline-control'):
            rows=physical_schedule(part)
            self.assertEqual(len(rows),1)
            self.assertLessEqual(rows[0][3],45)
        self.assertEqual(physical_schedule('half')[0][2],4)
        self.assertEqual(physical_schedule('deadline-control')[0][2],4)

    def test_physical_observer_cannot_drive_or_award_progress(self):
        source = Path(__file__).with_name('fixtures').joinpath('plan_physical_edges.qc').read_text()
        audit_physical_edges(source)
        anchor = '    pm_frames = pm_frames + 1;'
        for mutation in ('self.ar_goal = pm_goal;', 'setorigin (self, pm_start);',
                         'Argus_PlanObserve (FALSE, pm_lastleg);', 'walkmove (90, 10);',
                         'Argus_TacticReset ();', 'pm_contact = time;'):
            with self.assertRaises(AssertionError):
                audit_physical_edges(source.replace(anchor, anchor + '\n' + mutation))
        with self.assertRaises(AssertionError):
            audit_physical_edges(source.replace(anchor, anchor+'\n    pm_door.speed = 40;'))

    def test_real_contact_and_detour_evidence(self):
        self.assertTrue(check_physical_edges(physical_edge(), 4)['success'])
        self.assertTrue(check_physical_edges(physical_edge(3), 3)['success'])

    def test_mover_requires_matching_engine_movement_at_shipped_pace(self):
        text = physical_edge(6)
        self.assertTrue(check_physical_edges(text, 6)['success'])
        for bad in (text.replace('pace 320', 'pace 160'),
                    text.replace('speed 20', 'speed 40'),
                    text.replace('model *27', 'model *99'),
                    text.replace("mover t 0.2 pos '0 0 0'", "mover t 0.2 pos '0 0 1000'"),
                    '\n'.join(s for s in text.splitlines() if not s.startswith('PMFIX door')),
                    '\n'.join(s for s in text.splitlines() if not s.startswith('PMFIX mover'))):
            self.assertNotEqual(bad, text)
            with self.assertRaises(AssertionError):check_physical_edges(bad, 6)

    def test_mover_control_must_fail_at_old_deadline_after_real_opening(self):
        lines=[]
        for line in physical_edge(6).splitlines():
            if line.startswith('PMFIX contact'):continue
            if line.startswith(('PMFIX sample', 'PMFIX mover', 'PMFIX leg')):
                if float(line.split(' t ')[1].split()[0])>20.2:continue
            if line.startswith('PMFIX sample t 20.2 '):line=line.replace('active 1','active 0')
            lines.append(line.replace('end ok 1 lost 0','end ok 0 lost 1'))
        text='\n'.join(lines)
        self.assertFalse(check_physical_edges(text,6,deadline_control=True)['success'])
        for bad in (text.replace('t 20.2 ', 't 22.2 '),
                    text.replace('end ok 0 lost 1','end ok 0 lost 0')):
            with self.assertRaises(AssertionError):check_physical_edges(bad,6,deadline_control=True)

    def test_physical_edge_oracle_rejects_false_evidence(self):
        text = physical_edge()
        for bad in (text.replace('PMFIX contact', 'PMFIX selection'),
                    'BHVRPL begin plan_physical_edges',
                    text.replace('solid 0', 'solid 1'),
                    text.replace('PMFIX cleanup owned_engine_pending_stop', ''),
                    text.replace('node', 'unreached'),
                    text.replace("pos '-100.0 0 0'", "pos '1000 0 0'"),
                    text.replace('hp 100', 'hp 90')):
            with self.subTest(bad=bad[-100:]), self.assertRaises(AssertionError):
                check_physical_edges(bad, 4)

    def test_coop_requires_real_rest_and_fresh_retry(self):
        text = physical_edge(3)
        for bad in (text.replace('until 21', 'until 20'),
                    text.replace('deadline 21', 'deadline 0'),
                    text.replace('active 0 stacked 1', 'active 1 stacked 1'),
                    text.replace('stacked 1', 'stacked 0'),
                    text.replace('PMFIX gate t 21', 'PMFIX gate t 10'),
                    '\n'.join(line for line in text.splitlines() if 'sample t 10.' not in line)):
            with self.subTest(bad=bad[-100:]), self.assertRaises(AssertionError):
                check_physical_edges(bad, 3)

    def test_complete_contract_and_real_failure(self):
        self.assertFalse(check_contract(contract(), 'dm2')['failures'])
        failed = contract().replace('failed_plan_released 1', 'failed_plan_released 0').replace('checks 18 ok 1', 'checks 18 ok 0')
        self.assertEqual(check_contract(failed, 'dm2')['failures'], ['failed_plan_released'])

    def test_contract_rejects_corrupted_receipts(self):
        line = f'PLANFIX check {LABELS[0]} 1\n'
        for bad in (contract().replace(line, ''), contract().replace(line, line * 2),
                    contract().replace(LABELS[0], LABELS[1], 1),
                    contract().replace('PLANFIX cleanup owned_engine_pending_stop', ''),
                    contract().replace('failed_plan_released 1', 'failed_plan_released 0'),
                    contract().replace('BHVRPL begin plan_fixture', ''),
                    'BHVRPL begin plan_fixture'):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                check_contract(bad, 'dm2')
        with self.assertRaises(AssertionError):
            check_contract(contract(), 'dm4')

    def test_edge_mode_requires_every_ordered_check_and_reports_failure(self):
        labels = LABELS[:-2] + EDGE_LABELS + LABELS[-2:]
        receipt = contract().replace(
            f'PLANFIX check {LABELS[-2]}',
            ''.join(f'PLANFIX check {label} 1\n' for label in EDGE_LABELS)
            + f'PLANFIX check {LABELS[-2]}').replace('checks 18', f'checks {len(labels)}')
        self.assertEqual(check_contract(receipt, 'dm2', edges=True)['checks'], len(labels))
        failed = receipt.replace('two_node_cycle_not_progress 1', 'two_node_cycle_not_progress 0').replace('ok 1', 'ok 0')
        self.assertEqual(check_contract(failed, 'dm2', edges=True)['failures'], ['two_node_cycle_not_progress'])
        for bad in (contract(), receipt.replace(f'PLANFIX check {EDGE_LABELS[0]} 1\n', ''),
                    receipt.replace(EDGE_LABELS[0], EDGE_LABELS[1], 1)):
            with self.assertRaises(AssertionError):
                check_contract(bad, 'dm2', edges=True)

    def test_physical_success_and_bounded_negative_control(self):
        result = check_physical(physical(), 2)
        self.assertTrue(result['success'])
        self.assertEqual(result['final_horizontal_distance'], 240)
        self.assertFalse(check_physical(physical(False), 2)['success'])

    def test_requires_actual_continuous_displacement(self):
        for bad in (physical().replace("'240 0 0'", "'200 0 0'"),
                    physical().replace("'160 0 0'", "'800 0 0'"),
                    physical().replace('chosen 1', 'chosen 0'),
                    physical().replace('weapon_rocketlauncher', 'worldspawn')):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                check_physical(bad, 2)

    def test_requires_premise_safety_order_and_cleanup(self):
        for bad in (physical().replace('respawn 15', 'respawn 10'),
                    physical().replace('actor_solid 0', 'actor_solid 1'),
                    physical().replace('hp 100', 'hp 90'),
                    physical().replace('frames 15', 'frames 1'),
                    physical().replace('PEFIX cleanup owned_engine_pending_stop', ''),
                    physical().replace('PEFIX end ok 1', 'PEFIX end ok 0'),
                    'BHVRPL begin plan_fixture'):
            with self.subTest(bad=bad), self.assertRaises(AssertionError):
                check_physical(bad, 2)

    def test_help_does_not_start_lab_or_create_outputs(self):
        tool = Path(__file__).with_name('verify_plan_progress.py')
        result = subprocess.run([sys.executable, str(tool), '--help'], capture_output=True,
                                text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--output', result.stdout)
        self.assertIn('half', result.stdout)
        self.assertIn('deadline-control', result.stdout)
        self.assertIn('mover-control', result.stdout)

    def test_existing_or_production_output_is_refused_before_lab(self):
        root = Path(__file__).resolve().parents[1]
        tool = root / 'tools/verify_plan_progress.py'
        for target in (root / 'backups', root / 'src'):
            result = subprocess.run([sys.executable, str(tool), '--output', str(target)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertIn('new directory beneath backups', result.stderr)

    def test_physical_subset_requires_its_mode_before_lab(self):
        tool = Path(__file__).with_name('verify_plan_progress.py')
        result = subprocess.run([sys.executable, str(tool), '--physical-part', 'normal',
                                 '--output', 'backups/not-created-by-help-test'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires --mode physical-edges', result.stderr)


if __name__ == '__main__':
    unittest.main()
