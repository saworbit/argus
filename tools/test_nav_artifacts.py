"""QC/JSON parity, emitted counts and failure-safe maintenance."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import argus_nav_artifacts as artifacts
from argus_nav_slots import require_slots

QC = """void() Argus_Nav_Spawn_test = {
    n0 = Argus_NavNode ('0 0 0');
    n1 = Argus_NavNode ('32 0 0');
    Argus_NavLink (n0, n1);
    Argus_NavLinkLift (n1, n0);
    Argus_NavTactics (n0, 1, n1, n1);
    Argus_NavTactics (n1, 1, world, world);
    dprint ("ARGNAV 2 nodes, 2 links\\n");
};
"""


def document(text=QC):
    return artifacts.canonical_sidecar({'nodes': list(artifacts.qc_graph(text)[0].values()),
        'cover_targets': [[1, 1], [-1, -1]], 'exposure': [1, 1]}, text)


class NavArtifacts(unittest.TestCase):
    def test_ci_rejects_a_stale_banner_or_sidecar(self):
        import argus_ci
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'src').mkdir()
            qc = root / 'src/argus_nav_test.qc'
            graph = Path(str(qc) + '.json')
            qc.write_text(QC, encoding='ascii', newline='\n')
            graph.write_text(json.dumps(document()), encoding='utf-8')
            self.assertEqual(argus_ci.check_nav(root), [])
            qc.write_text(QC.replace('2 nodes, 2 links', '2 nodes, 9 links'), encoding='ascii', newline='\n')
            self.assertTrue(any('ARGNAV' in f for f in argus_ci.check_nav(root)))
            qc.write_text(QC, encoding='ascii', newline='\n')
            doc = document()
            doc['links'].append([1, 0, 1])
            graph.write_text(json.dumps(doc), encoding='utf-8')
            self.assertTrue(any('links differs' in f for f in argus_ci.check_nav(root)))

    def test_independent_typed_edges_survive_and_a_ghost_does_not(self):
        doc = document()
        doc['links'].append([1, 0, 1])
        doc['doorlinks'] = [[1, 0]]
        with self.assertRaisesRegex(ValueError, 'links differs'):
            artifacts.validate_pair(QC, doc)
        repaired = artifacts.canonical_sidecar(doc, QC)
        self.assertEqual(repaired['links'], [[0, 1, 0]])
        self.assertEqual(repaired['liftlinks'], [[1, 0]])
        self.assertEqual(repaired['doorlinks'], [])
        artifacts.validate_pair(QC, repaired)

    def test_count_includes_a_teleporter_once(self):
        text = QC.replace('Argus_NavLinkLift (n1, n0);', 'Argus_NavLink (n1, n0); // teleporter')
        doc = document(text)
        self.assertEqual(doc['teles'], [[1, 0]])
        stale = text.replace('2 nodes, 2 links', '2 nodes, 123 links')
        with self.assertRaisesRegex(ValueError, 'ARGNAV'):
            artifacts.validate_pair(stale, doc)
        self.assertEqual(artifacts.refresh_banner(stale), text)

    def test_missing_typed_or_drop_cover_hops_are_refused(self):
        for text in [QC.replace('n0, 1, n1, n1', 'n0, 1, n1, n0'),
                     QC.replace('Argus_NavLink (n0, n1)', 'Argus_NavLinkDoor (n0, n1)'),
                     QC.replace("'32 0 0'", "'32 0 -32'")]:
            doc = document(text)
            if '-32' in text:
                doc['nodes'][1][2] = -32
            with self.assertRaisesRegex(ValueError, 'cover hop'):
                artifacts.validate_pair(text, doc)

    def test_duplicate_calls_and_displaced_nodes_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'duplicate QC'):
            artifacts.qc_graph(QC.replace('    dprint', '    Argus_NavLink (n0, n1);\n    dprint'))
        doc = document()
        doc['nodes'][0][0] = 10
        with self.assertRaisesRegex(ValueError, 'positions disagree'):
            artifacts.canonical_sidecar(doc, QC)

    def test_second_publication_failure_restores_bytes_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as td:
            qc = Path(td) / 'argus_nav_test.qc'
            sidecar = Path(str(qc) + '.json')
            qc.write_bytes(b'old QC')
            sidecar.write_bytes(b'old JSON')
            original = artifacts.os.replace
            calls = []
            def replace(source, target):
                calls.append(target)
                if len(calls) == 2:
                    raise OSError('second write refused')
                original(source, target)
            with patch.object(artifacts.os, 'replace', side_effect=replace):
                with self.assertRaisesRegex(OSError, 'second write refused'):
                    artifacts.publish_pair(qc, b'old QC', b'old JSON', QC, document())
            self.assertEqual(qc.read_bytes(), b'old QC')
            self.assertEqual(sidecar.read_bytes(), b'old JSON')
            self.assertEqual(set(Path(td).iterdir()), {qc, sidecar})

    def test_failed_reconciliation_does_not_publish_a_bad_cover_hint(self):
        with tempfile.TemporaryDirectory() as td:
            qc = Path(td) / 'argus_nav_test.qc'
            text = QC.replace('n0, 1, n1, n1', 'n0, 1, n1, n0')
            qc.write_text(text, encoding='ascii', newline='\n')
            graph = Path(str(qc) + '.json')
            graph.write_text(json.dumps(document()), encoding='utf-8')
            before = qc.read_bytes(), graph.read_bytes()
            with self.assertRaisesRegex(ValueError, 'cover hop'):
                artifacts.reconcile(qc)
            self.assertEqual((qc.read_bytes(), graph.read_bytes()), before)

    def test_real_emitter_counts_late_links_and_serializes_only_winning_types(self):
        source = Path(__file__).with_name('argus_navgen.py').read_text(encoding='utf-8')
        section = source.split('# ---- 8a. emit QC ----\n', 1)[1].split('print("wrote", OUTQC', 1)[0]
        with tempfile.TemporaryDirectory() as td:
            qc = str(Path(td) / 'argus_nav_test.qc')
            namespace = dict(OUTQC=qc, MAPNAME='test', EMIT_DISPATCHER=False,
                ways=[(0, 0, 0), (32, 0, 0), (64, 0, 0)], pos=lambda w: w,
                links={0: {1: (1, False)}, 1: {0: (1, True)}},
                jump_approach={(1, 0): (0, 0, 0)}, nlinks=123,
                teles=[(2, 0)], rjlinks=[(0, 1)], lifts=[(0, 2)], swims=[],
                trains=[], sprints=[(0, 1)], doorlinks=[], regions=[0, 0, 0],
                exposure=[0, 0, 0], cover_targets=[[-1, -1]] * 3, cam_nodes=[],
                _probe_rejected=[], trace_inputs=[], proven_anchors=[],
                require_slots=require_slots, canonical_sidecar=artifacts.canonical_sidecar,
                validate_pair=artifacts.validate_pair, publish_pair=artifacts.publish_pair,
                existing_bytes=artifacts.existing_bytes, io=io)
            exec(compile(section, 'argus_navgen emission', 'exec'), namespace)
            text = Path(qc).read_text(encoding='ascii')
            doc = json.loads(Path(qc + '.json').read_text(encoding='utf-8'))
            self.assertIn('ARGNAV 3 nodes, 4 links', text)
            self.assertEqual(doc['rjlinks'], [])
            self.assertEqual(doc['sprintlinks'], [])
            self.assertEqual(doc['liftlinks'], [[0, 2]])
            self.assertEqual(doc['teles'], [[2, 0]])
            artifacts.validate_pair(text, doc)


if __name__ == '__main__':
    unittest.main()
