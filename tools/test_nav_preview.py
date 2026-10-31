"""Optional navigation plotting must never lend a stale image to a new graph."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


if __name__ == '__main__':
    unittest.main()
