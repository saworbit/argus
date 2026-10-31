"""Proof nominations fail closed; legacy graph sidecars stay compatible."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from argus_nav_anchors import load_anchors

ROOT=Path(__file__).resolve().parents[1]

class AnchorContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'runs').mkdir()
        self.path=self.root/'proof.json'
        self.doc=json.loads((ROOT/'src/argus_nav_e1m5.proven.json').read_text())
        for row in self.doc['anchor_evidence']:
            shutil.copyfile(ROOT/row['raw'],self.root/row['raw'])
    def load(self,doc):
        self.path.write_text(json.dumps(doc))
        return load_anchors(self.path,'e1m5',self.root)
    def test_real_two_cadence_route_and_legacy_pairs(self):
        self.assertEqual(self.load(self.doc),self.doc['anchors'])
        self.assertEqual(self.load([[[1,2,3],[4,5,6]]]),[])
    def test_metadata_coordinates_and_hash_cannot_be_forged(self):
        variants=[]
        for key,value in [('map','dm3'),('schema','unknown'),('anchors',[[0,0,0]]),
                          ('links',[[self.doc['anchors'][1],self.doc['anchors'][0]]]),
                          ('links',[[[0,0,0],self.doc['anchors'][0]]]),
                          ('anchors',[[True,2,3]]),('anchors',[[1,2,float('inf')]]),
                          ('anchors',self.doc['anchors']*3),('anchor_evidence',self.doc['anchor_evidence'][:1])]:
            bad=copy.deepcopy(self.doc);bad[key]=value;variants.append(bad)
        for key,value in [('raw','../runs/escape.log'),('raw','runs/../escape.log'),
                          ('sha256','0'*64),('ticrate',.05)]:
            bad=copy.deepcopy(self.doc);bad['anchor_evidence'][0][key]=value;variants.append(bad)
        bad=copy.deepcopy(self.doc);bad['anchor_evidence'].append(bad['anchor_evidence'][0]);variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError,AssertionError,FileNotFoundError)):self.load(bad)

if __name__=='__main__':unittest.main()
