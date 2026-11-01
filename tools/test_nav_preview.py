"""Optional navigation plotting must never lend a stale image to a new graph."""
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import argus_nav_preview as preview
from argus_nav_preview import generate_preview, file_md5


class NavigationPreviews(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.qc, self.png = self.root/'nav.qc', self.root/'nav.png'
        self.qc.write_bytes(b'new graph QC')
        Path(str(self.qc)+'.json').write_text('{"nodes": [[1,2,3]]}')
        self.png.write_bytes(b'old graph image')
        self.receipt = Path(str(self.png)+'.json')
        # Deliberately retain an earlier successful receipt too.
        self.receipt.write_text('{"schema":"nav-preview-v1","generated":true}')

    def preview(self, render):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            generated = generate_preview(self.qc, self.png, render)
        state = json.loads(self.receipt.read_text())
        self.assertEqual(state['generated'], generated)
        self.assertEqual(state['qc_md5'], file_md5(self.qc))
        self.assertEqual(state['graph_md5'], file_md5(Path(str(self.qc)+'.json')))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         ['nav.png','nav.png.json','nav.qc','nav.qc.json'])
        return state, output.getvalue()

    def test_missing_plotter_invalidates_previous_receipt_and_preserves_graph(self):
        def unavailable(path):
            self.assertFalse(json.loads(self.receipt.read_text())['generated'])
            raise ImportError('matplotlib unavailable')
        state, output = self.preview(unavailable)
        self.assertFalse(state['generated'])
        self.assertNotIn('png_md5', state)
        self.assertEqual(self.png.read_bytes(), b'old graph image')
        self.assertIn('debug plot skipped', output)
        self.assertEqual(self.qc.read_bytes(), b'new graph QC')

    def test_plot_failure_does_not_publish_partial_bytes_or_old_preview(self):
        def failed(path):
            path.write_bytes(b'partial image')
            raise OSError('plot failed')
        state, output = self.preview(failed)
        self.assertFalse(state['generated'])
        self.assertEqual(self.png.read_bytes(), b'old graph image')
        self.assertIn('OSError: plot failed', output)

    def test_success_replaces_old_image_and_receipts_all_current_outputs(self):
        state, output = self.preview(lambda path: path.write_bytes(b'fresh graph image'))
        self.assertTrue(state['generated'])
        self.assertEqual(self.png.read_bytes(), b'fresh graph image')
        self.assertEqual(state['png_md5'], file_md5(self.png))
        self.assertIn('wrote', output)

    def test_empty_plot_is_unavailable(self):
        state, _ = self.preview(lambda path: None)
        self.assertFalse(state['generated'])
        self.assertEqual(self.png.read_bytes(), b'old graph image')

    def test_every_link_family_is_drawn_with_its_shared_style(self):
        from argus_linkstyle import LINK_STYLES, mpl

        class Axes:
            def __init__(self): self.lines = []
            def plot(self, *args, **kw): self.lines.append(kw)
            def scatter(self, *args, **kw): pass

        nav = dict(nodes=[[i*32, 0, 0 if i != 2 else -32] for i in range(11)],
                   links=[[0, 1], [1, 2], [2, 3]], jlinks=[[2, 3]],
                   teles=[[3, 4]], rjlinks=[[4, 5]], liftlinks=[[5, 6]],
                   swimlinks=[[6, 7]], doorlinks=[[7, 8]], trainlinks=[[8, 9]],
                   sprintlinks=[[9, 10]])
        axes = Axes()
        counts = preview.draw_nav_graph(axes, nav)
        self.assertEqual(dict(counts), {kind: 1 for kind in LINK_STYLES})
        self.assertEqual(len(axes.lines), len(LINK_STYLES))
        for kind in LINK_STYLES:
            self.assertTrue(any(all(line[k] == v for k, v in mpl(kind).items())
                                for line in axes.lines), kind)
        self.assertNotEqual(mpl('swim')['ls'], mpl('door')['ls'])

    def test_render_only_keeps_graph_and_compilation_inputs_unchanged(self):
        if importlib.util.find_spec('matplotlib') is None:
            self.skipTest('optional matplotlib is not installed')
        # Enough BSP29 data for a wireframe; it deliberately cannot generate nav.
        bsp = self.root/'fixture.bsp'
        model = struct.pack('<9f7i', 0, 0, -64, 320, 320, 64, 0, 0, 0, *([0]*7))
        lumps = [(124, 0)]*14 + [(124, len(model))]
        bsp.write_bytes(struct.pack('<i', 29) + b''.join(struct.pack('<ii', *row) for row in lumps) + model)
        Path(str(self.qc)+'.json').write_text(json.dumps({
            'nodes': [[0, 0, 24], [128, 0, 24]], 'links': [[0, 1, 0]]}))
        (self.root/'progs.src').write_text('keep compilation list\n')
        (self.root/'argus_nav_dispatch.qc').write_text('keep dispatcher\n')
        inputs = {p: p.read_bytes() for p in self.root.iterdir() if p not in (self.png, self.receipt)}
        script = Path(__file__).resolve().parent/'argus_navgen.py'
        command = [sys.executable, str(script), str(bsp), 'fixture', str(self.qc), str(self.png), '--render-only']
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.png.read_bytes().startswith(b'\x89PNG'))
        self.assertTrue(json.loads(self.receipt.read_text())['generated'])
        self.assertEqual({p: p.read_bytes() for p in inputs}, inputs)
        self.assertEqual(set(self.root.iterdir()), set(inputs) | {self.png, self.receipt})
        result = subprocess.run(command + ['--register'], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual({p: p.read_bytes() for p in inputs}, inputs)

    def test_render_only_refuses_outputs_that_alias_inputs(self):
        for bsp, png in [(self.png, self.png), (self.root/'map.bsp', self.qc)]:
            with self.assertRaisesRegex(ValueError, 'distinct from every input'):
                preview.render_only(bsp, 'fixture', self.qc, png)
        self.assertEqual(self.qc.read_bytes(), b'new graph QC')


if __name__ == '__main__':
    unittest.main()
