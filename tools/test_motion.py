"""Reject incomplete observer proofs and intermediate engine poses."""
import hashlib
import json
from pathlib import Path
import unittest

from verify_motion import LABELS, inspect_contracts, inspect_demo_alignment


def contracts():
    return ('BHVRPL begin motion_observer\n'+
        ''.join(f'MOCHECK {name} 1\n' for name in LABELS)+
        f'MOCHECK end checks {len(LABELS)} failures 0\n')


def trajectory(offset=0):
    times=[i*.014 for i in range(110)]
    positions=[[i*3.,0.,24.] for i in range(110)]
    raw='ARGMOT begin layout 2\n'+''.join(
        f"ARGMOT Carmack ms {t*1000:.1f} pos '{p[0]+offset} 0 24' wish 0 cause coast ctx '0 0 1' hp 100 ground worldspawn\n"
        for t,p in zip(times,positions))
    return raw,dict(tracks=[dict(name='Carmack',kind='player',t=times,pos=positions)])


class MotionObserver(unittest.TestCase):
    def test_all_passive_contracts_are_required(self):
        good=contracts()
        self.assertEqual(inspect_contracts(good),12)
        for text in (good+good,good.replace('basis_preserved 1','basis_preserved 0'),
                good.replace('MOCHECK disabled_fields 1\n',''),good.replace('failures 0','failures 1')):
            with self.assertRaises(AssertionError):inspect_contracts(text)

    def test_finalized_positions_allow_only_wire_rounding(self):
        raw,exported=trajectory(.1)
        self.assertEqual(inspect_demo_alignment(raw,exported,'Carmack')['paired'],110)

    def test_intermediate_poses_and_old_phase_are_rejected(self):
        raw,exported=trajectory(3)
        with self.assertRaises(AssertionError):inspect_demo_alignment(raw,exported,'Carmack')
        raw,_=trajectory()
        with self.assertRaises(AssertionError):inspect_demo_alignment(raw.replace('layout 2','layout 1'),exported,'Carmack')

    def test_missing_exposure_identity_and_duplicate_times_are_rejected(self):
        raw,exported=trajectory()
        for text,data,name in ((raw,exported,'player'),(raw,dict(tracks=[]),'Carmack'),
                (raw+raw,exported,'Carmack'),('ARGMOT begin layout 2\n'+raw.splitlines()[1]+'\n',exported,'Carmack')):
            with self.assertRaises(AssertionError):inspect_demo_alignment(text,data,name)

    def test_published_raw_bytes_and_demo_alignment(self):
        root=Path(__file__).resolve().parents[1]
        receipt=json.loads((root/'runs/motion-observer-v2.results.json').read_text(encoding='utf-8'))
        for row in receipt['artifacts']:
            self.assertEqual(hashlib.sha256((root/row['path']).read_bytes()).hexdigest(),row['sha256'])
        proof=receipt['demo_alignment']
        text=(root/proof['raw']).read_text(encoding='utf-8')
        tracks=json.loads((root/proof['tracks']).read_text(encoding='utf-8'))
        self.assertEqual(inspect_demo_alignment(text,tracks,proof['name']),proof['result'])
        for row in receipt['contracts']:
            self.assertEqual(inspect_contracts((root/row).read_text(encoding='utf-8')),12)
        self.assertNotIn('ARGMOT ',(root/receipt['disabled_raw']).read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
