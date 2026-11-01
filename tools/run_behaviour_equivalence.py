"""Bounded diagnostic A/B via the native lab MCP; never launches an engine itself.

Run from the repo: --cohort confirm|mechanism --maps dm2,dm4 --repeats 1,2,...
Requires a previously compiled/staged candidate. Retains native briefs and raw
tapes; parses only the new BHVTIME grammar, never reconstructs ARGLOG metrics.
"""
from argus_validation import require
from argus_source import source_identity
import argparse
import ctypes
import datetime as dt
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'backups/behaviour-equivalence'
MODES = dict(off=0, on=590, compute=591, legacy=592)
TIMING = re.compile(r'^BHVTIME t\s+([\d.]+) frames\s+(\d+) seconds\s+([\d.]+) mean_ms\s+([\d.]+) max_ms\s+([\d.]+) over20\s+(\d+) over50\s+(\d+)$', re.M)


def lab_executable(override=None):
    """Resolve one source-built lab for MCP, CLI calls and receipt hashes."""
    selected = override or os.environ.get('ARGUS_LAB')
    if not selected:
        selected = ROOT / 'tools/argus_mcp/target-stage/release' / (
            'argus-mcp.exe' if os.name == 'nt' else 'argus-mcp')
    return Path(selected).expanduser().resolve()


def lab_cli(executable, *arguments, timeout=45, environment=None, cwd=None, runner=None):
    """Run the selected lab with bounded UTF-8 capture and child cleanup."""
    root = Path(cwd) if cwd is not None else ROOT
    command = [str(lab_executable(executable)), *map(str, arguments)]
    options = dict(cwd=root, env={**os.environ, 'ARGUS_ROOT': str(root), **(environment or {})},
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   text=True, encoding='utf-8', errors='replace')
    if runner is not None:  # Explicit test transport; no real child is owned.
        options.pop('stdout'); options.pop('stderr')
        return runner(command, capture_output=True, timeout=timeout, **options)
    if os.name != 'nt':
        options['start_new_session'] = True
    process = subprocess.Popen(command, **options)
    try:
        out, err = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, out, err)
    except BaseException:
        try:
            if os.name == 'nt':
                if process.poll() is None:
                    cleanup = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                        capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                    if cleanup.returncode:
                        print(f'lab child-tree cleanup failed: {cleanup.stderr!r}', file=sys.stderr)
            else:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
        except Exception as error:
            print(f'lab child-tree cleanup failed: {error!r}', file=sys.stderr)
        finally:
            try:
                if process.poll() is None:
                    process.kill()
            except Exception as error:
                print(f'lab process cleanup failed: {error!r}', file=sys.stderr)
            try: process.communicate(timeout=5)
            except Exception as error: print(f'lab pipe cleanup failed: {error!r}', file=sys.stderr)
        raise
    finally:
        for pipe in (process.stdout, process.stderr):
            try: pipe.close()
            except OSError as error: print(f'lab pipe close failed: {error!r}', file=sys.stderr)


def timing(text):
    rows = [dict(zip(('t', 'frames', 'seconds', 'mean_ms', 'max_ms', 'over20', 'over50'), map(float, row)))
            for row in TIMING.findall(text)]
    require((len(rows) == sum(line.startswith('BHVTIME ') for line in text.splitlines())), 'malformed cadence record')
    require((len(rows) >= 5), 'missing cadence records')
    require((all(row['frames'] > 0 and 5 <= row['seconds'] <= 5.2 for row in rows)), 'bad cadence window')
    return rows[1:]  # pre-registered startup exclusion, irrespective of arm/outcome


def identity(map_name, executable=None):
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(source_sha256=source_identity(ROOT / 'src'), cli_sha256=digest(lab_executable(executable)),
                binary_sha256=digest(ROOT / 'engine/argus/progs.dat'),
                nav_sha256=digest(ROOT / f'src/argus_nav_{map_name}.qc.json'))


def validate_protocol(protocol, maps, repeats, seconds, prefix, cohort):
    require((cohort == 'confirm' and maps == protocol['maps'] == ['dm2', 'dm4']))
    require((repeats == list(range(1, protocol['pairs_per_map'] + 1))))
    require((protocol['pairs_per_map'] == 128 and seconds == protocol['seconds'] == 60))
    require((prefix == protocol['prefix'] and re.fullmatch(r'[a-z0-9_]+', prefix)))
    require((protocol['goal_margin_per_minute'] == 2 and protocol['confidence'] == .90))
    require((protocol['frame_margin_ms'] == 1 and protocol['rounding_allowance_ms'] == .1))
    for map_name in maps:
        require((identity(map_name) == protocol['identities'][map_name]), 'unregistered input identity')
    for relative, expected in protocol['analysis_code_sha256'].items():
        require((hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected), 'study code changed')


def cpu_seconds(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(ctypes.c_ulonglong)] * 4))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    require((handle), ctypes.get_last_error())
    values = [ctypes.c_ulonglong() for _ in range(4)]
    try:
        require((kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in values))), ctypes.get_last_error())
        return (values[2].value + values[3].value) / 10_000_000
    finally:
        kernel.CloseHandle(handle)


class Lab:
    def __init__(self, stderr, environment=None, *, exe=None, timeout=45):
        self.executable = lab_executable(exe)
        self.timeout = timeout
        self.p = subprocess.Popen([str(self.executable)], cwd=ROOT,
            env={**os.environ, 'ARGUS_ROOT': str(ROOT), **(environment or {})}, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8')
        self.records = queue.Queue()
        self.serial = 0
        def reader():
            try:
                for line in self.p.stdout:
                    self.records.put(json.loads(line))
            except (OSError, ValueError) as error:
                print(f'lab output reader failed: {error!r}', file=sys.stderr)
            finally:
                self.records.put(None)
        self.reader = threading.Thread(target=reader, daemon=True)
        try:
            self.reader.start()
            self.request('initialize', dict(protocolVersion='2024-11-05', capabilities={},
                         clientInfo=dict(name='behaviour-equivalence', version='1')))
            self.p.stdin.write(json.dumps(dict(jsonrpc='2.0', method='notifications/initialized')) + '\n')
            self.p.stdin.flush()
        except BaseException:
            finish_lab(self, active=False)
            raise

    def request(self, method, params, timeout=None):
        timeout = self.timeout if timeout is None else timeout
        self.serial += 1
        self.p.stdin.write(json.dumps(dict(jsonrpc='2.0', id=self.serial, method=method, params=params)) + '\n')
        self.p.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'lab request {method} timed out after {timeout}s')
            try:
                response = self.records.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError(f'lab request {method} timed out after {timeout}s') from error
            require((response is not None), 'lab exited')
            if response.get('id') == self.serial:
                return response

    def call(self, tool, **arguments):
        response = self.request('tools/call', dict(name=tool, arguments=arguments))
        require((not response.get('error') and not response.get('result', {}).get('isError')), response)
        data = json.loads(response['result']['content'][0]['text'])
        require((data.get('lab_identity', {}).get('authoritative')), 'stale lab')
        return data

    def close(self):
        try:
            try:
                self.p.stdin.close()
            except (OSError, ValueError):
                pass  # A dead child may already have closed its end of the pipe.
            try:
                self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.p.terminate()
                try:
                    self.p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.p.kill()
                    self.p.wait(timeout=5)
        finally:
            reader = getattr(self, 'reader', None)
            if reader is not None and reader.ident is not None:
                reader.join(timeout=1)
            self.p.stdout.close()


def finish_lab(lab, active=True):
    """Close unconditionally and preserve a failure already being unwound."""
    failed = sys.exc_info()[0] is not None
    try:
        if active and not failed:
            if isinstance(lab, Lab):
                if lab.p.poll() is None:
                    # Teardown is bounded independently of the study timeout.
                    response = Lab.request(lab, 'tools/call',
                        dict(name='match_stop', arguments={}), timeout=2)
                    if response.get('error') or response.get('result', {}).get('isError'):
                        raise RuntimeError(response)
            else:
                lab.call('match_stop')
    except Exception as error:
        print(f'match_stop during teardown failed: {error!r}', file=sys.stderr)
    finally:
        try:
            lab.close()
        except Exception as error:
            if not failed:
                raise
            print(f'lab close during teardown failed: {error!r}', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cohort', choices=('confirm', 'mechanism'), required=True)
    ap.add_argument('--maps', default='dm2,dm4')
    ap.add_argument('--repeats', default='1,2,3,4,5,6,7,8')
    ap.add_argument('--seconds', type=int, default=60)
    ap.add_argument('--output', type=Path, default=OUT)
    ap.add_argument('--prefix', default='bhv1')
    ap.add_argument('--protocol', type=Path)
    args = ap.parse_args()
    maps = args.maps.split(',')
    repeats = list(map(int, args.repeats.split(',')))
    require((set(maps) <= {'dm2', 'dm4'} and len(set(maps)) == len(maps)))
    require((len(set(repeats)) == len(repeats) and 1 <= len(repeats) <= 128))
    require((all(1 <= r <= 128 for r in repeats) and 30 <= args.seconds <= 180))
    require((re.fullmatch(r'[a-z0-9_]+', args.prefix)))
    protocol = json.loads(args.protocol.read_text()) if args.protocol else None
    protocol_sha = hashlib.sha256(args.protocol.read_bytes()).hexdigest() if args.protocol else None
    if protocol:
        validate_protocol(protocol, maps, repeats, args.seconds, args.prefix, args.cohort)
    else:
        require((args.prefix == 'bhv1' and len(repeats) <= 16 and max(repeats) <= 16))
    args.output.mkdir(parents=True, exist_ok=True)
    result_path = args.output / f'{args.cohort}-results.json'
    results = json.loads(result_path.read_text()) if result_path.exists() else []
    if protocol:
        require((all(r.get('protocol_sha256') == protocol_sha for r in results)), 'mixed registration')
    for repeat in repeats:
        for map_name in maps if repeat % 2 else maps[::-1]:
            modes = ['off', 'on'] if args.cohort == 'confirm' else ['off', 'compute', 'legacy', 'on']
            if repeat % 2 == 0:
                modes.reverse()
            for mode in modes:
                name = f'{args.prefix}_{args.cohort}_{map_name}_{mode}{repeat}'
                if any(row['name'] == name for row in results):
                    continue
                require((not (ROOT / f'runs/{name}.log').exists()), 'orphan tape: retain and investigate before retry')
                before = identity(map_name)
                if protocol:
                    require((hashlib.sha256(args.protocol.read_bytes()).hexdigest() == protocol_sha), 'protocol changed')
                    validate_protocol(protocol, maps, repeats, args.seconds, args.prefix, args.cohort)
                active = False
                with (args.output / f'{name}.stderr').open('w') as err:
                    lab = Lab(err)
                    try:
                        started_utc = dt.datetime.now(dt.timezone.utc).isoformat()
                        start = lab.call('match_start', map=map_name, duration_sec=args.seconds + 20, skill=1, run_name=name)
                        active = True
                        deadline = time.monotonic() + 10
                        while True:
                            status = lab.call('match_status')
                            if 'ARGLOG ' in json.dumps(status):
                                break
                            require((status.get('running') and time.monotonic() < deadline), status)
                            time.sleep(.1)
                        lab.call('tune', command='scratch1 591')
                        lab.call('tune', command=f'scratch4 {MODES[mode]}')
                        cpu_start = cpu_seconds(start['pid'])
                        wall_start = time.monotonic()
                        time.sleep(args.seconds)
                        wall = time.monotonic() - wall_start
                        cpu = cpu_seconds(start['pid']) - cpu_start
                        stop = lab.call('match_stop')
                        active = False
                        brief = lab.call('brief_run', log=name, map=map_name)
                        path = ROOT / f'runs/{name}.log'
                        text = path.read_text(errors='replace')
                        require((not any(s in text for s in ('BHVFIX ', 'TACFIX begin', 'BHVRPL begin', 'Host_Error'))))
                        require((('BHVDBG ' in text) == (mode in {'on', 'legacy'})))
                        require((identity(map_name) == before), 'input identity changed during run')
                        row = dict(name=name, cohort=args.cohort, map=map_name, mode=mode,
                            repeat=repeat, requested_seconds=args.seconds, identity=before,
                            wall_seconds=wall, cpu_seconds=cpu, bytes=path.stat().st_size,
                            timing=timing(text), start=start, stop=stop, brief=brief)
                        if protocol:
                            require((brief['map'] == map_name), 'wrong map')
                            require((not any('WRONG MAP' in flag or 'CONTROLLED FIXTURE' in flag
                                           for flag in brief.get('flags', []))), 'invalid ordinary tape')
                            require((58 <= brief['totals']['duration_sec'] <= 64), 'wrong exposure')
                            require((brief['totals']['tick_class'] == 'listen'), 'wrong tick class')
                            row.update(protocol_sha256=protocol_sha, started_utc=started_utc,
                                       stopped_utc=dt.datetime.now(dt.timezone.utc).isoformat())
                        results.append(row)
                        temporary = result_path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(results, indent=2))
                        temporary.replace(result_path)
                        print(json.dumps(dict(name=name, completed=len(results),
                                              stopped_utc=dt.datetime.now(dt.timezone.utc).isoformat())), flush=True)
                    finally:
                        finish_lab(lab, active)


if __name__ == '__main__':
    main()
