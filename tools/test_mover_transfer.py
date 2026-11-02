"""A transfer receipt must describe exactly one measured physical task."""
import unittest
import hashlib
import json
from pathlib import Path

from verify_mover_transfer import audit_fixture, inspect_fixture, instrument_arrival


def receipt(frame_ms=14, completed=1):
    return (f'ARGUS init on e1m6\nBHVRPL begin mover_transfer\nMVFIX begin dt_ms {frame_ms}\n'
            f'MVFIX result completed {completed} seconds 4.1 boarded 1 route_retained 1 '
            "dry 1 alive 1 launches 1 bad_launch 0 landed 1 handoff 1 pos '529 1393 344'\n")


def current_receipt(frame_ms=14):
    frames = 288 if frame_ms == 14 else 42
    return ("ARGUS init on e1m6\nBHVRPL begin mover_transfer\n"
            "MVFIX oracle different_node accepted 0\n"
            "MVFIX oracle expected_without_consumption accepted 0\n"
            f"MVFIX begin dt_ms {frame_ms} layout 2 exit '529 1393 344'\n"
            "MVFIX expect step 1 generation 2 from '529 1393 344' to '433 1297 208'\n"
            "MVFIX consumed step 1 generation 2 from '529 1393 344' to '433 1297 208' accepted 1\n"
            "MVFIX landed pos '529 1393 344' world 1 floor 1 dry 1 retained 1\n"
            "MVFIX result completed 1 seconds 4.1 boarded 1 route_retained 1 "
            "dry 1 alive 1 launches 1 bad_launch 0 landed 1 handoff 1 "
            f"exit_consumed 1 frames {frames} node '433 1297 208' generation 2 pos '529 1393 344'\n")


class TransferReceipts(unittest.TestCase):
    def test_corrected_predicates_have_their_own_layout(self):
        legacy=inspect_fixture(current_receipt(),'e1m6',.0139,require_current=True)
        self.assertTrue(legacy['forward_proven'])
        self.assertFalse(legacy['observer_predicates_verified'])
        current=inspect_fixture(current_receipt().replace('layout 2','layout 3'),'e1m6',.0139,require_current=True)
        self.assertTrue(current['forward_proven'] and current['observer_predicates_verified'])

    def test_published_raw_identities_and_proof(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root / 'runs/mover-handoff-v2.results.json').read_text(encoding='utf-8'))
        for row in [*evidence['cases'], evidence['mutation']]:
            raw = root / row['raw']
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), row['raw_sha256'])
            if 'map' in row:
                measured = inspect_fixture(raw.read_text(encoding='utf-8'), row['map'],
                    .1 if row['frame_ms'] == 100 else .0139, require_current=True)
                self.assertTrue(measured['completed'] and measured['forward_proven'])

    def test_both_rates_preserve_physical_outcome(self):
        for rate, ms in ((.0139, 14), (.1, 100)):
            row = inspect_fixture(receipt(ms), 'e1m6', rate)
            self.assertTrue(row['completed'] and row['boarded'] and row['route_retained'])
            self.assertEqual(row['frame_ms'], ms)
            self.assertEqual(row['launches'], 1)
            self.assertFalse(row['forward_proven'])
            self.assertEqual(row['proof'], 'node_difference')

    def test_current_proof_at_both_rates(self):
        for rate, ms in ((.0139, 14), (.1, 100)):
            row = inspect_fixture(current_receipt(ms), 'e1m6', rate, require_current=True)
            self.assertTrue(row['completed'] and row['forward_proven'])
            self.assertEqual(row['fixture_layout'], 'mover-transfer-v2')
            self.assertEqual(row['expected_successor'], (433, 1297, 208))
        padded = current_receipt().replace('dt_ms 14', 'dt_ms  15.0')
        self.assertTrue(inspect_fixture(padded, 'e1m6', .0139, require_current=True)['forward_proven'])

    def test_legacy_is_never_upgraded(self):
        with self.assertRaisesRegex(AssertionError, 'legacy'):
            inspect_fixture(receipt(), 'e1m6', .0139, require_current=True)
        legacy = (Path(__file__).parent / 'fixtures/mover_transfer_v1.qc').read_text(encoding='utf-8')
        self.assertIn('vlen (mv_bot.ar_node.origin - mv_exit) > 1', legacy)
        self.assertNotIn('MoverTransferConsumed', legacy)

    def test_different_node_or_missing_consumption_cannot_prove_handoff(self):
        good = current_receipt()
        for replacement in (
            ('consumed step 1 generation 2', 'consumed step 1 generation 3'),
            ("to '433 1297 208' accepted 1", "to '900 900 900' accepted 1"),
            ('accepted 1\nMVFIX landed', 'accepted 0\nMVFIX landed'),
            ("node '433 1297 208'", "node '900 900 900'"),
            ('world 1 floor 1', 'world 0 floor 1'),
            ('MVFIX landed', 'missing landed'),
            ('different_node accepted 0', 'different_node accepted 1'),
            ('expected_without_consumption accepted 0', 'expected_without_consumption accepted 1'),
            ('frames 288', 'frames 42'),
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(AssertionError):
                    inspect_fixture(good.replace(*replacement), 'e1m6', .0139, require_current=True)

    def test_private_instrumentation_preserves_production_assignment(self):
        source = (Path(__file__).parent.parent / 'src/argus.qc').read_text(encoding='utf-8')
        changed = instrument_arrival(source)
        self.assertEqual(changed.count('self.ar_node = Argus_GetNext (self.ar_node, self);'),
                         source.count('self.ar_node = Argus_GetNext (self.ar_node, self);'))
        self.assertEqual(changed.count('self.ar_node = nx;'), source.count('self.ar_node = nx;'))
        self.assertEqual(changed.count('MoverTransferWillConsume (oldnode);'), 2)
        self.assertEqual(changed.count('MoverTransferConsumed (oldnode, self.ar_node);'), 2)
        with self.assertRaises(AssertionError):
            instrument_arrival(changed)

    def test_failed_control_is_a_measurement_not_a_missing_result(self):
        self.assertFalse(inspect_fixture(receipt(completed=0), 'e1m6', .0139)['completed'])

    def test_landing_alone_cannot_claim_continuing_route_completion(self):
        for field in ('landed', 'handoff', 'route_retained'):
            with self.assertRaises(AssertionError):
                inspect_fixture(receipt().replace(field + ' 1', field + ' 0'), 'e1m6', .0139)

    def test_observer_refuses_actor_mutations_and_steering(self):
        source = (Path(__file__).parent / 'fixtures/mover_transfer.qc').read_text(encoding='utf-8')
        audit_fixture(source)
        for mutation in ('mv_bot.velocity_x = 320;', 'setorigin (mv_bot, mv_exit);',
                         'Argus_AI ();'):
            with self.assertRaises(AssertionError):
                audit_fixture(source.replace('    if (!mv_started || mv_done) return;', mutation))

    def test_duplicate_missing_wrong_map_and_engine_failure_refuse(self):
        good = receipt()
        for text in (good + good, good.replace('MVFIX result', 'missing'),
                     good.replace('begin dt_ms', 'missing'), good.replace('on e1m6', 'on dm3'),
                     good + 'Program error\n', receipt(100)):
            with self.subTest(text=text):
                with self.assertRaises(AssertionError):
                    inspect_fixture(text, 'e1m6', .0139)


if __name__ == '__main__':
    unittest.main()
