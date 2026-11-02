"""Keep native negative controls distinct from missing or synthetic evidence."""
from pathlib import Path
import hashlib
import json
import unittest

from verify_mover_forecast import audit_fixture, inspect_fixture, instrument_forecast


def receipt(case, slow=False):
    forecast = int(case in (1, 5))
    wet, depth, contents = (2, 48, -3) if case == 5 else (0, 0, -1)
    state, gap = (2, 16) if case == 4 else (0, 0)
    return ('ARGUS init on e1m6\nBHVRPL begin mover_forecast\n'
        f'MCFIX begin dt_ms  {100 if slow else 15}.0 layout 1 case {case}\n'
        f'MCFIX result case {case} forecast {forecast} jump 0 invalid_jump 0 checks 0 refused 0 accepted 0 alive 1 retained 1 '
        f'wetlevel {wet} depth {depth} dry_floor 0 world_floor 0 state {state} '
        f'dock_gap {gap} blocked {int(case == 2)} target_contents {contents} '
        f"frames {16 if slow else 106} seconds  1.5 predicted '550 1400 320' pos '600 1400 344' "
        f"pool_floor {-112 if case == 5 else 0} pool_surface {-64 if case == 5 else 0} final_gap {14.5 if case == 4 else gap}\n")


class ForecastControls(unittest.TestCase):
    def test_corrected_predicates_have_their_own_layout(self):
        self.assertFalse(inspect_fixture(receipt(1),1,.0139)['observer_predicates_verified'])
        self.assertTrue(inspect_fixture(receipt(1).replace('layout 1','layout 2'),1,.0139)['observer_predicates_verified'])

    def test_published_controls_and_raw_identities(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root/'runs/mover-forecast-v1.results.json').read_text(encoding='utf-8'))
        self.assertEqual(len(evidence['cases']), 10)
        self.assertEqual(len({r['binary_sha256'] for r in evidence['cases']}), 1)
        self.assertEqual({(r['case'], r['ticrate']) for r in evidence['cases']},
                         {(case, rate) for case in range(1, 6) for rate in (.0139, .1)})
        for row in [*evidence['cases'], *evidence['mutations']]:
            raw = root/row['raw']
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), row['raw_sha256'])
            if 'mutation' not in row:
                self.assertTrue(inspect_fixture(raw.read_text(encoding='utf-8'),
                    row['case'], row['ticrate'])['retained'])

    def test_each_real_control_contract_at_both_rates(self):
        for case in range(1, 6):
            for slow in (False, True):
                row = inspect_fixture(receipt(case, slow), case, .1 if slow else .0139)
                self.assertTrue(row['alive'] and row['retained'])
                self.assertEqual(row['forecast'], case in (1, 5))

    def test_invalid_launch_or_always_refuse_cannot_pass(self):
        for text, case in [(receipt(1).replace('forecast 1', 'forecast 0'), 1),
                (receipt(2).replace('forecast 0', 'forecast 1'), 2),
                (receipt(3).replace('invalid_jump 0', 'invalid_jump 1'), 3),
                (receipt(4).replace('state 2', 'state 0'), 4),
                (receipt(4).replace('final_gap 14.5', 'final_gap 16'), 4),
                (receipt(2).replace('blocked 1', 'blocked 0'), 2)]:
            with self.subTest(text=text):
                with self.assertRaises(AssertionError): inspect_fixture(text, case, .0139)

    def test_wet_entry_is_never_dry_floor_proof(self):
        for before, after in [('wetlevel 2', 'wetlevel 0'), ('depth 48', 'depth 0'),
                ('target_contents -3', 'target_contents -1'), ('dry_floor 0', 'dry_floor 1')]:
            with self.subTest(after=after):
                with self.assertRaises(AssertionError):
                    inspect_fixture(receipt(5).replace(before, after), 5, .0139)

    def test_missing_wrong_map_rate_or_dead_actor_refused(self):
        good = receipt(2)
        for text in (good + good, good.replace('MCFIX result', 'missing'),
                good.replace('on e1m6', 'on dm3'), good.replace('frames 106', 'frames 16'),
                good.replace('alive 1', 'alive 0'), good.replace('retained 1', 'retained 0')):
            with self.assertRaises(AssertionError): inspect_fixture(text, 2, .0139)

    def test_fixture_cannot_steer_after_setup(self):
        source = (Path(__file__).parent/'fixtures/mover_forecast.qc').read_text(encoding='utf-8')
        audit_fixture(source)
        for statement in ('mc_bot.velocity_x = 320;', 'setorigin (mc_bot, mc_seed);'):
            with self.assertRaises(AssertionError):
                audit_fixture(source.replace('    if (mc_done) return;', statement))
        with self.assertRaises(AssertionError):
            audit_fixture(source.replace('    retained =', '    Argus_AI ();\n    retained ='))

    def test_wrapper_keeps_the_production_forecast_body(self):
        source = (Path(__file__).parent.parent/'src/argus.qc').read_text(encoding='utf-8')
        changed = instrument_forecast(source)
        start = source.index('float(float yaw, float spd) Argus_MoverGapJumpOK =')
        end = source.index('\n};', start) + 3
        body = source[start:end].replace('Argus_MoverGapJumpOK', 'Argus_MoverGapJumpCore', 1)
        self.assertIn(body, changed)
        with self.assertRaises(AssertionError): instrument_forecast(changed)

    def test_live_launch_requires_a_same_frame_acceptance(self):
        good = receipt(2).replace('jump 0 invalid_jump', 'jump 1 invalid_jump')
        with self.assertRaises(AssertionError): inspect_fixture(good, 2, .0139)
        decision = "MCFIX decision frame 3 allowed 1 yaw 200 speed 140 pos '657 1441 344'\n"
        launch = 'MCFIX launch frame 3 accepted 1\n'
        good = good.replace('MCFIX result', decision + launch + 'MCFIX result').replace(
            'checks 0 refused 0 accepted 0', 'checks 1 refused 0 accepted 1')
        self.assertTrue(inspect_fixture(good, 2, .0139)['jump'])
        with self.assertRaises(AssertionError):
            inspect_fixture(good.replace('accepted 1', 'accepted 2'), 2, .0139)
        with self.assertRaises(AssertionError):
            inspect_fixture(good.replace('launch frame 3', 'launch frame 4'), 2, .0139)


if __name__ == '__main__':
    unittest.main()
