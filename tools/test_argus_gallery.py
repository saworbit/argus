#!/usr/bin/env python3
"""Tests for tools/argus_gallery.py: moment selection, the page and the rulings server."""
import http.client
import http.server
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import argus_gallery  # noqa: E402


def sample(name, t, x=1000, hp=100, spd=200):
    return f"ARGLOG {name} t {t:.1f} pos '{x} 0 24' spd {spd} yaw 0 mode 2 st 0 gl 0 hp {hp} frg 0\n"


def tape(rows):
    return 'ARGUS init on dm4\nARGEVT Reap spawned\nARGEVT Omi spawned\n' + ''.join(rows)


class Moments(unittest.TestCase):
    def test_marks_come_first_then_fire_freezes_then_order_by_time(self):
        rows = []
        for i in range(60):
            t = 1.0 + i * 0.5
            # Reap stands still from t 10 losing health: a freeze under fire
            rows.append(sample('Reap', t, x=1000 if t >= 10 else 1000 + i * 40,
                               hp=100 - max(0, int(t - 10)), spd=0 if t >= 10 else 300))
            # Omi stands still from t 20 at full health: a plain freeze
            rows.append(sample('Omi', t, x=2000 if t >= 20 else 2000 + i * 40, spd=0 if t >= 20 else 300))
        rows.append("ARGUS mark 1 t  25.0 pos '0.0 0.0 24.0' yaw 0 seen 0 dist 900 near Omi\n")
        picked = argus_gallery.moments(tape(rows), limit=12)
        kinds = [m['kind'] for m in picked]
        self.assertIn('mark', kinds)
        self.assertIn('freeze under fire', kinds)
        self.assertEqual([m['t'] for m in picked], sorted(m['t'] for m in picked), 'shown in time order')
        self.assertEqual([m['id'] for m in picked], list(range(1, len(picked) + 1)))
        mark = next(m for m in picked if m['kind'] == 'mark')
        self.assertIn('out of sight, 900u', mark['note'])
        # with room for only one, the mark wins
        only = argus_gallery.moments(tape(rows), limit=1)
        self.assertEqual([m['kind'] for m in only], ['mark'])

    def test_one_clip_covers_a_bots_neighbouring_moments(self):
        rows = [sample('Reap', 1.0 + i * 0.5, spd=0) for i in range(40)]
        rows.append("ARGUS mark 1 t   8.0 pos '0 0 24' yaw 0 seen 1 dist 100 near Reap\n")
        rows.append("ARGUS mark 2 t   9.0 pos '0 0 24' yaw 0 seen 1 dist 100 near Reap\n")
        picked = argus_gallery.moments(tape(rows))
        self.assertEqual(len([m for m in picked if m['kind'] == 'mark']), 1)

    def test_world_deaths_need_the_classifier_to_be_called_unforced(self):
        rows = [sample('Reap', 1.0 + i * 0.5) for i in range(10)]
        rows.append("ARGEVT Reap death world pos '1000 0 24'\n")
        picked = argus_gallery.moments(tape(rows))
        self.assertEqual([m['kind'] for m in picked], ['world death'])
        lava = lambda point: True  # noqa: E731 - every point is lava
        with mock.patch.object(argus_gallery.argus_longi, 'in_hazard', side_effect=lambda p, c: True):
            picked = argus_gallery.moments(tape(rows), contents=lava)
        self.assertEqual([m['kind'] for m in picked], ['unforced world death'])


class Page(unittest.TestCase):
    def test_text_is_escaped_and_missing_clips_say_why(self):
        moments = [dict(id=1, t=3.0, kind='mark', bot='<b>', note='a <script>x</script>', pos=[1, 2, 3],
                        clip=None, clip_error='outside the demo'),
                   dict(id=2, t=9.0, kind='freeze', bot='Reap', note='ok', pos=[0, 0, 0], clip='clip02.webm')]
        html = argus_gallery.page('shane_dm4_x', moments)
        self.assertNotIn('<script>x</script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('No clip: outside the demo', html)
        self.assertIn('src="clip02.webm"', html)
        self.assertEqual(html.count('class="card"'), 2)


class Server(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.gdir = Path(self.td.name)
        (self.gdir / 'index.html').write_text('<html></html>')
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), argus_gallery.make_handler(self.gdir))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.td.cleanup()

    def post(self, body, origin=None, host=None, ctype='application/json'):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Content-Type': ctype}
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        conn.request('POST', '/verdicts', body=body, headers=headers)
        return conn.getresponse().status

    def test_rulings_are_cleaned_saved_and_read_back(self):
        status = self.post(json.dumps({'1': {'verdict': 'broken', 'note': 'stuck'},
                                       '2': {'verdict': 'nonsense', 'note': 7}}))
        self.assertEqual(status, 204)
        saved = json.loads((self.gdir / 'verdicts.json').read_text())
        self.assertEqual(saved['1'], {'verdict': 'broken', 'note': 'stuck'})
        self.assertEqual(saved['2'], {'verdict': None, 'note': '7'})
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', '/verdicts')
        self.assertEqual(json.loads(conn.getresponse().read()), saved)

    def test_a_foreign_origin_and_bad_bodies_are_refused(self):
        self.assertEqual(self.post('{}', origin='http://evil.example'), 403)
        self.assertEqual(self.post('not json'), 400)
        self.assertEqual(self.post('{}', ctype='text/plain'), 415)
        self.assertFalse((self.gdir / 'verdicts.json').exists())

    def test_a_rebound_host_is_refused_for_reads_and_writes(self):
        # DNS rebinding makes Origin equal Host; the Host itself must be ours
        rebound = f'attacker.example:{self.port}'
        self.assertEqual(self.post('{}', origin=f'http://{rebound}', host=rebound), 403)
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', '/verdicts', headers={'Host': rebound})
        self.assertEqual(conn.getresponse().status, 403)
        self.assertFalse((self.gdir / 'verdicts.json').exists())


class Verdicts(unittest.TestCase):
    def test_unruled_moments_are_listed_too(self):
        with tempfile.TemporaryDirectory() as td:
            gdir = argus_gallery.gallery_dir(td, 'stem')
            gdir.mkdir(parents=True)
            (gdir / 'moments.json').write_text(json.dumps({'stem': 'stem', 'moments': [
                dict(id=1, t=3.0, kind='mark', bot='Reap', note='n', pos=[0, 0, 0]),
                dict(id=2, t=5.0, kind='freeze', bot='Omi', note='m', pos=[0, 0, 0])]}))
            (gdir / 'verdicts.json').write_text(json.dumps({'2': {'verdict': 'fine', 'note': ''}}))
            rows = argus_gallery.verdicts(td, 'stem')
            self.assertEqual([r['verdict'] for r in rows], [None, 'fine'])


if __name__ == '__main__':
    unittest.main()
