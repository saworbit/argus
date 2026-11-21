"""Shared client for the native lab, used by active study runners and fixtures."""
from argus_validation import require
from argus_source import source_identity
from argus_paths import LabMissing, lab_binary
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


def lab_executable(override=None, *, root=None):
    """Resolve one native lab for MCP, CLI calls and receipt hashes."""
    root = ROOT if root is None else Path(root)
    path = lab_binary(root, override)
    if path is None:
        raise LabMissing(f'{root.resolve()} or PATH')
    return Path(path)


require_lab = lab_executable


def lab_cli(executable, *arguments, timeout=45, environment=None, cwd=None, runner=None):
    """Run the selected lab with bounded UTF-8 capture and child cleanup."""
    root = Path(cwd) if cwd is not None else ROOT
    # A test transport owns no real child, so only a real spawn needs the binary.
    path = (Path(executable).expanduser().resolve() if runner is not None and executable
            else require_lab(executable, root=root))
    command = [str(path), *map(str, arguments)]
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
    return dict(source_sha256=source_identity(ROOT / 'src'), cli_sha256=digest(require_lab(executable)),
                binary_sha256=digest(ROOT / 'engine/argus/progs.dat'),
                nav_sha256=digest(ROOT / f'src/argus_nav_{map_name}.qc.json'))


def cpu_seconds(pid):
    """Return user plus system CPU seconds, or None if the process cannot be measured."""
    if os.name == 'nt':
        return _windows_cpu_seconds(pid)
    if sys.platform.startswith('linux'):
        try:
            stat = Path(f'/proc/{pid}/stat').read_text(encoding='utf-8', errors='replace')
            # The command can contain spaces and parentheses. Fields after the
            # final ')' start at state (field 3); utime and stime are 14 and 15.
            fields = stat.rsplit(')', 1)[1].split()
            ticks = int(fields[11]) + int(fields[12])
            return ticks / os.sysconf('SC_CLK_TCK')
        except (OSError, ValueError, IndexError, ZeroDivisionError):
            return None
    return None


def cpu_elapsed(pid, start):
    """Measure the elapsed CPU time if both samples are available."""
    end = cpu_seconds(pid) if start is not None else None
    return None if end is None else end - start


def _windows_cpu_seconds(pid):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    values = [wintypes.FILETIME() for _ in range(4)]
    try:
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
            return None
        return sum((value.dwHighDateTime << 32) | value.dwLowDateTime for value in values[2:]) / 10_000_000
    finally:
        kernel.CloseHandle(handle)


class Lab:
    def __init__(self, stderr, environment=None, *, exe=None, timeout=45):
        env = {**os.environ, 'ARGUS_ROOT': str(ROOT), **(environment or {})}
        self.executable = require_lab(exe, root=env['ARGUS_ROOT'])
        self.timeout = timeout
        self.p = subprocess.Popen([str(self.executable)], cwd=ROOT,
            env=env, stdin=subprocess.PIPE,
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
                         clientInfo=dict(name='argus-lab-client', version='1')))
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
