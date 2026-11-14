"""GUI text boundaries and browser rendering, without a live lab server."""
import html
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from urllib.parse import unquote
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'tools/argus_mcp/src/gui.html'


def browser():
    candidates = [os.environ.get('ARGUS_GUI_BROWSER'), shutil.which('google-chrome'),
                  shutil.which('chromium'), shutil.which('chromium-browser'),
                  'C:/Program Files/Google/Chrome/Application/chrome.exe',
                  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe']
    return next((str(p) for p in candidates if p and Path(p).is_file()), None)


def kill_tree(proc):
    """Kill a browser and every process it started, so no child keeps the pipes open."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if proc.poll() is None:
        proc.kill()


def run_browser(command, *, timeout=25, attempts=2):
    """Run headless Chrome, and once more if it stalls (#817).

    The page work takes a few seconds, but on the CI runner the first launch
    has hung for the whole timeout with no output. One stall is retried with
    a note. A stall on every attempt fails with Chrome's stderr from each,
    which is what a real GUI hang looks like.
    """
    notes = []
    for attempt in range(1, attempts + 1):
        group = ({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt'
                 else {'start_new_session': True})
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, encoding='utf-8', errors='replace', **group)
        try:
            out, err = proc.communicate(timeout=timeout)
            return proc.returncode, out, err
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            try:
                _out, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                err = '(output pipes still open after the kill)'
            notes.append(f'attempt {attempt}: no result after {timeout} s; stderr: {err[-1500:]}')
            print(f'note: headless browser stalled for {timeout} s on attempt {attempt} (#817)',
                  file=sys.stderr)
    raise AssertionError('headless browser stalled on every attempt (#817)\n' + '\n'.join(notes))


def browser_receipt(page=None, *, scale=1, screenshot=None):
    payload = '<img src=x onerror="window.__xss=1">'
    status = dict(ready=True, root='C:/argus', basedir='C:/argus/engine', game='argus',
                  installs=[payload], maps=[dict(name=payload, has_bsp=False, has_nav=True)],
                  backups=[dict(id=payload, files=payload)])
    setup = '''window.__xss=0; window.confirm=()=>false;
window.__observed=new Set();
window.ResizeObserver=class extends ResizeObserver {
 observe(node,...rest){window.__observed.add(node);super.observe(node,...rest);}
 unobserve(node){window.__observed.delete(node);super.unobserve(node);}
};
window.__status=STATUS;
window.fetch=async(path)=>({ok:true,headers:new Headers({'content-type':'application/json'}),
 json:async()=>String(path).startsWith('/api/status')?window.__status:
 String(path).startsWith('/api/map/')?{headline:PAYLOAD,graph_cuts:{weak:PAYLOAD},edicts_est:PAYLOAD}:{ok:false}});
'''.replace('STATUS', json.dumps(status)).replace('PAYLOAD', json.dumps(payload))
    proof = '''(async()=>{
 const check=(condition,message)=>{if(!condition)throw Error(message);};
 await refresh();
 check(!document.querySelector('#cfg img,#maps img,#backs img'),'status markup parsed');
 check(document.getElementById('cfg').textContent.includes(PAYLOAD),'install path lost');
 check(document.querySelector('#maps strong').textContent===PAYLOAD,'map name lost');
 document.querySelector('#maps li').click();
 await pick(PAYLOAD);
 check(!document.querySelector('#sel img'),'map brief markup parsed');
 check(document.getElementById('sel').textContent.includes(PAYLOAD),'headline lost');
 const attack='0);window.__xss=1;//';
 const node={id:1,band:PAYLOAD,pos:[0,0,24],out:[{to:7,kind:PAYLOAD}],
  inn:[{from:attack,kind:'walk'}],nearby_control:[PAYLOAD],refusals:0,cost_mult:1};
 populateInspector(node);
 check(!document.querySelector('#inspector-card img'),'inspector markup parsed');
 check(!document.querySelector('#insp-in [onclick],#insp-out [onclick]'),'inline edge handler');
 window.selectNodeById=id=>window.__clicked=id;
 document.querySelector('#insp-out .link-pill').click();
 check(window.__clicked===7,'outgoing edge handler lost');
 document.querySelector('#insp-in .link-pill').click();
 check(window.__clicked===attack,'edge data evaluated');
 check(linkStyle('__proto__')===UNKNOWN_LINK,'prototype used as link metadata');
 check(window.__xss===0,'server field executed');
 window.__status.installs=['C:/argus/engine/argus/progs.dat'];
 window.__status.maps=[{name:'dm4',has_bsp:true,has_nav:true,dispatcher:true}];
 window.__status.backups=[{id:'fixture_backup',files:4}];
 await refresh();
 selected='dm4';
 replaceContent(document.getElementById('sel'),element('strong','dm4'),element('span','1 island','pill'));
 document.getElementById('brief').textContent='Private rendering fixture. No engine or API writes.';
 populateInspector({...node,band:'lower',nearby_control:['quad'],out:[{to:7,kind:'jump'}],inn:[{from:2,kind:'walk'}]});
 await new Promise(resolve=>setTimeout(resolve,100));
 const frames=[...document.querySelectorAll('.chamfer')].filter(n=>n.offsetWidth&&n.offsetHeight);
 for(const frame of frames){
  const style=getComputedStyle(frame),inside=getComputedStyle(frame,'::before');
  const cut=parseFloat(style.getPropertyValue('--cut'));
  check(Math.abs(cut-.06*Math.min(frame.offsetWidth,frame.offsetHeight))<.1,'wrong chamfer depth '+frame.tagName+'#'+frame.id+' '+cut+' '+frame.offsetWidth+'x'+frame.offsetHeight);
  check(style.clipPath.startsWith('polygon(')&&inside.clipPath.startsWith('polygon('),'missing chamfer border polygon');
  check(inside.content!== 'none'&&inside.backgroundImage!=='none','missing inner frame');
  if(frame.matches('section')){
   const heading=frame.querySelector('h2').getBoundingClientRect(),box=frame.getBoundingClientRect();
   check(heading.left-box.left+heading.top-box.top>=cut,'section heading clipped by chamfer');
  }
 }
 check([...window.__observed].every(node=>node.isConnected),'removed frame still observed');
 return {pass:true,frames:frames.length,scale:devicePixelRatio,width:innerWidth};
})().then(result=>{const p=document.createElement('pre');p.id='gui-test-result';p.hidden=true;p.textContent=JSON.stringify(result);document.body.appendChild(p);})
 .catch(error=>{const p=document.createElement('pre');p.id='gui-test-result';p.textContent=JSON.stringify({pass:false,error:String(error)});document.body.appendChild(p);});
'''.replace('PAYLOAD', json.dumps(payload))
    page = page if page is not None else PAGE.read_text(encoding='utf-8')
    page = page.replace('<script>', '<script>' + setup.replace('</', r'<\/') + '</script><script>', 1)
    page = page.replace('</body>', '<script>' + proof.replace('</', r'<\/') + '</script></body>')
    with tempfile.TemporaryDirectory(prefix='argus-gui-') as td:
        root = Path(td); path = root / 'fixture.html'; path.write_text(page, encoding='utf-8')
        command = [browser(), '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
                   '--disable-extensions', '--disable-background-networking', '--disable-dev-shm-usage',
                   '--user-data-dir=' + str(root / 'profile'), f'--window-size={1920//scale},{1600//scale}',
                   '--force-device-scale-factor=' + str(scale), '--virtual-time-budget=3000', '--dump-dom']
        if screenshot is not None: command.append('--screenshot=' + str(Path(screenshot).resolve()))
        command.append(path.as_uri())
        returncode, stdout, stderr = run_browser(command)
        if returncode: raise AssertionError(stderr[-3000:])
        match = re.search(r'<pre id="gui-test-result"[^>]*>(.*?)</pre>', stdout, re.S)
        if not match: raise AssertionError('browser did not finish GUI checks: ' + stderr[-1000:] + stdout[-2000:])
        receipt = json.loads(html.unescape(match[1]))
        if not receipt.get('pass'): raise AssertionError(receipt)
        return receipt


class GuiRendering(unittest.TestCase):
    def test_inline_favicon_matches_the_source_svg(self):
        page = PAGE.read_text(encoding='utf-8')
        match = re.search(r'<link\s+rel="icon"[^>]*href="data:image/svg\+xml,([^"]+)"', page)
        self.assertIsNotNone(match, 'GUI inline favicon missing')
        inline = ET.fromstring(unquote(match[1]))
        source = ET.parse(ROOT / 'docs/brand/favicon.svg').getroot()
        self.assertEqual(ET.tostring(inline), ET.tostring(source),
                         'update the GUI favicon data URI from docs/brand/favicon.svg')

    def test_a_stalled_browser_is_retried_once_and_its_children_are_killed(self):
        # A stand-in browser that stalls on its first launch with a child
        # holding the output pipes, then answers on the second (#817).
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / 'stalled-once'
            script = (
                'import pathlib, subprocess, sys, time\n'
                f'm = pathlib.Path({str(marker)!r})\n'
                'if not m.exists():\n'
                '    m.write_text("x")\n'
                '    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
                '    time.sleep(60)\n'
                'print("answered")\n')
            started = time.monotonic()
            with unittest.mock.patch('sys.stderr', new=io.StringIO()) as noted:
                code, out, _err = run_browser([sys.executable, '-c', script], timeout=3)
            # Killing only the parent leaves the child holding the pipes for
            # the full 10 s drain, so a quick return proves the tree died.
            self.assertLess(time.monotonic() - started, 9)
            self.assertEqual((code, out.strip()), (0, 'answered'))
            self.assertIn('stalled for 3 s on attempt 1 (#817)', noted.getvalue())

    def test_a_browser_that_stalls_every_time_fails_with_both_attempts(self):
        stall = [sys.executable, '-c', 'import sys, time; print("loading", file=sys.stderr, flush=True); time.sleep(60)']
        with unittest.mock.patch('sys.stderr', new=io.StringIO()):
            with self.assertRaises(AssertionError) as caught:
                run_browser(stall, timeout=2)
        message = str(caught.exception)
        self.assertIn('stalled on every attempt (#817)', message)
        self.assertIn('attempt 2: no result after 2 s', message)
        self.assertIn('loading', message)

    @unittest.skipUnless(browser(), 'no Chromium browser installed')
    def test_server_fields_are_text_and_edge_handlers_keep_data(self):
        for scale in (1, 2):
            with self.subTest(scale=scale): self.assertTrue(browser_receipt(scale=scale)['pass'])


if __name__ == '__main__':
    unittest.main()
