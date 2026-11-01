"""Reject missing physical camera witnesses and bounded-blend failures."""
from pathlib import Path
import hashlib
import json
import unittest
from verify_camera_chase import inspect_fixture, instrument_camera


def receipt(ms=14):
    return ('ARGUS init on e1m6\nBHVRPL begin camera_chase\n'
        f'CAMFIX begin dt_ms {ms} layout 1\n'
        "CAMFIX result candidates 8 blocked 8 basis_error 0 position_error 0 distance 16 position '0 0 0' expected '0 0 0'\n")


class CameraChase(unittest.TestCase):
    def test_published_controls_keep_raw_identities(self):
        root = Path(__file__).resolve().parents[1]
        evidence = json.loads((root/'runs/camera-chase-v1.results.json').read_text(encoding='utf-8'))
        for row in evidence['cases'] + evidence['negative_controls']:
            raw = root/row['raw']
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), row['raw_sha256'])
            if row['failed_control']:
                with self.assertRaises(AssertionError):
                    inspect_fixture(raw.read_text(encoding='utf-8'),row['ticrate'])
            else:
                self.assertEqual(inspect_fixture(raw.read_text(encoding='utf-8'),row['ticrate'])['blocked'],8)

    def test_two_cadences_and_failed_sweep(self):
        for rate, ms in ((.0139,14),(.1,100)):
            self.assertEqual(inspect_fixture(receipt(ms),rate)['blocked'],8)

    def test_missing_basis_or_blend_proof_is_refused(self):
        good = receipt()
        for text in (good+good,good.replace('candidates 8','candidates 1'),
                good.replace('blocked 8','blocked 7'),good.replace('basis_error 0','basis_error 2'),
                good.replace('position_error 0','position_error 30'),good.replace('on e1m6','on dm3'),
                good.replace('layout 1','layout 2'),
                good.replace('CAMFIX result','missing')):
            with self.assertRaises(AssertionError): inspect_fixture(text,.0139)

    def test_private_observation_keeps_real_trace(self):
        source = (Path(__file__).resolve().parents[1]/'src/argus_cam.qc').read_text(encoding='utf-8')
        changed = instrument_camera(source)
        self.assertEqual(changed.count('traceline ('),source.count('traceline ('))
        self.assertEqual(changed.count('CameraChaseCandidate (trace_fraction);'),1)
        with self.assertRaises(AssertionError): instrument_camera(changed)


if __name__ == '__main__': unittest.main()
