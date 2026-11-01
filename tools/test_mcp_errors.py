"""Wire checks for a source-built lab: ARGUS_LAB selects the executable."""
import json
from pathlib import Path
import tempfile
import unittest

from run_behaviour_equivalence import Lab, finish_lab


class McpErrors(unittest.TestCase):
    def lab(self, root):
        stderr = tempfile.TemporaryFile(mode='w+', encoding='utf-8')
        self.addCleanup(stderr.close)
        lab = Lab(stderr, environment={'ARGUS_ROOT': str(root),
            'ARGUS_MAPS': str(root / 'maps_local'), 'ARGUS_SRC': str(root / 'src'),
            'ARGUS_RUNS': str(root / 'runs')}, timeout=5)
        self.addCleanup(finish_lab, lab, active=False)
        return lab

    def rpc_error(self, lab, method, params, code, kind):
        response = lab.request(method, params)
        self.assertEqual(response['error']['code'], code, response)
        body = response['error']['data']
        self.assertEqual(body['kind'], kind, response)
        self.assertTrue(body['error'])
        self.assertTrue(body['hint'])

    def test_unconfigured_surfaces_keep_a_config_hint(self):
        with tempfile.TemporaryDirectory() as td:
            lab = self.lab(Path(td) / 'absent')
            # First application call remains the documented project inspection.
            response = lab.request('tools/call', {'name': 'see', 'arguments': {'what': 'project'}})
            self.assertTrue(response['result']['isError'], response)
            body = json.loads(response['result']['content'][0]['text'])
            self.assertEqual(body['kind'], 'unconfigured')
            self.assertIn('ARGUS_ROOT', body['hint'])
            for name, arguments in [('orient', {}), ('review_run', {'log': 'absent'}),
                                    ('review_ab', {'log_b': 'absent'}), ('review_map', {'bsp': 'dm4'})]:
                self.rpc_error(lab, 'prompts/get', {'name': name, 'arguments': arguments}, -32603, 'unconfigured')
            self.rpc_error(lab, 'resources/read', {'uri': 'argus://project'}, -32603, 'unconfigured')
            self.assertIn('result', lab.request('resources/read', {'uri': 'argus://help'}))

    def test_missing_and_corrupt_data_have_different_codes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'src').mkdir()
            (root / 'maps_local').mkdir()
            (root / 'maps_local' / 'broken.bsp').write_bytes(b'broken BSP')
            lab = self.lab(root)
            lab.request('tools/call', {'name': 'see', 'arguments': {'what': 'project'}})
            self.rpc_error(lab, 'resources/read', {'uri': 'argus://map/absent'}, -32002, 'not_found')
            self.rpc_error(lab, 'resources/read', {'uri': 'argus://map/broken'}, -32603, 'internal')
            self.rpc_error(lab, 'prompts/get', {'name': 'review_map', 'arguments': {'bsp': 'absent'}}, -32602, 'bad_args')
            self.rpc_error(lab, 'prompts/get', {'name': 'review_map', 'arguments': {'bsp': 'broken'}}, -32603, 'internal')
            self.rpc_error(lab, 'prompts/get', {'name': 'review_run', 'arguments': {'log': 'absent'}}, -32602, 'bad_args')
            self.rpc_error(lab, 'resources/read', {'uri': 'argus://graph/broken/not-a-hash'}, -32602, 'bad_args')


if __name__ == '__main__':
    unittest.main()
