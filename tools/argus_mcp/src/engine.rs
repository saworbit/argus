//! Dedicated-engine child. Unix pipes stdin. Windows CreateProcess
//! with a new console and no inherited MCP stdio handles.

use crate::config::Config;
use std::path::Path;
use std::sync::{Arc, Mutex};

#[cfg(not(windows))]
use std::process::Stdio;
#[cfg(not(windows))]
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
#[cfg(not(windows))]
use tokio::process::{Child, ChildStdin, Command};

/// Serialises the engine-gated integration tests: each spawns a real
/// dedicated engine on the UDP port, and cargo runs tests in
/// parallel - unserialised, one test's client talks to the other
/// test's engine (observed as a one-in-a-few flaky failure).
pub static ENGINE_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

pub struct EngineChild {
    pub pid: u32,
    stdout: Arc<Mutex<String>>,
    inner: Inner,
}

enum Inner {
    #[cfg(not(windows))]
    Tokio { child: Child, stdin: Option<ChildStdin> },
    #[cfg(windows)]
    Win { handle: SendHandle },
}

/// Process handle. Used only under MatchCtrl's mutex.
#[cfg(windows)]
#[derive(Clone, Copy)]
struct SendHandle(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for SendHandle {}
#[cfg(windows)]
unsafe impl Sync for SendHandle {}

impl EngineChild {
    pub fn spawn(
        cfg: &Config,
        map: &str,
        slots: u32,
        skill: Option<u32>,
        cwd: &Path,
        port: Option<u32>,
        coop: bool,
    ) -> Result<Self, String> {
        validate_map(map)?;
        if slots == 0 || slots > 16 {
            return Err("dedicated_slots must be 1..=16".into());
        }
        if let Some(p) = port {
            if !(1024..=65535).contains(&p) {
                return Err("port must be 1024..=65535".into());
            }
        }
        #[cfg(windows)]
        {
            return spawn_windows(cfg, map, slots, skill, cwd, port, coop);
        }
        #[cfg(not(windows))]
        {
            spawn_unix(cfg, map, slots, skill, cwd, port, coop)
        }
    }

    pub fn id(&self) -> u32 {
        self.pid
    }

    pub fn stdout_buf(&self) -> Arc<Mutex<String>> {
        self.stdout.clone()
    }

    pub fn try_wait(&mut self) -> Result<Option<i32>, String> {
        match &mut self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { child, .. } => child
                .try_wait()
                .map(|s| s.map(|st| st.code().unwrap_or(1)))
                .map_err(|e| format!("wait: {e}")),
            #[cfg(windows)]
            Inner::Win { handle } => win_try_wait(handle.0),
        }
    }

    pub async fn kill(&mut self) -> Result<(), String> {
        match &mut self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { child, .. } => child.kill().await.map_err(|e| format!("kill: {e}")),
            #[cfg(windows)]
            Inner::Win { handle } => win_kill(handle.0),
        }
    }

    pub async fn write_line(&mut self, line: &str) -> Result<(), String> {
        if line.is_empty() || line.contains('\n') || line.contains('\r') {
            return Err("command must be a single non-empty console line".into());
        }
        match &mut self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { stdin, .. } => {
                let stdin = stdin.as_mut().ok_or("match stdin is closed")?;
                stdin
                    .write_all(format!("{line}\n").as_bytes())
                    .await
                    .map_err(|e| format!("write console: {e}"))?;
                stdin.flush().await.map_err(|e| format!("flush console: {e}"))
            }
            #[cfg(windows)]
            Inner::Win { .. } => win_inject(self.pid, line),
        }
    }

    pub fn has_stdin(&self) -> bool {
        match &self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { stdin, .. } => stdin.is_some(),
            #[cfg(windows)]
            Inner::Win { .. } => true,
        }
    }
}

impl Drop for EngineChild {
    fn drop(&mut self) {
        #[cfg(windows)]
        {
            let Inner::Win { handle } = &mut self.inner;
            if !handle.0.is_null() {
                let _ = win_kill(handle.0);
                unsafe {
                    windows_sys::Win32::Foundation::CloseHandle(handle.0);
                }
                handle.0 = std::ptr::null_mut();
            }
        }
    }
}

pub fn validate_map(map: &str) -> Result<(), String> {
    let m = map.trim();
    if m.is_empty() {
        return Err("map is empty; use a short name such as dm4".into());
    }
    if m.contains('/') || m.contains('\\') || m.contains("..") || m.contains(' ') {
        return Err("map must be a short name (dm4), not a path".into());
    }
    if !m
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return Err("map must match [A-Za-z0-9_-]+".into());
    }
    Ok(())
}

#[cfg(not(windows))]
fn spawn_unix(
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    cwd: &Path,
    port: Option<u32>,
    coop: bool,
) -> Result<EngineChild, String> {
    let mut cmd = Command::new(&cfg.engine);
    apply_args(&mut cmd, cfg, map, slots, skill, port, coop);
    cmd.current_dir(cwd)
        .kill_on_drop(true)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("failed to spawn ARGUS_ENGINE: {e}"))?;
    let stdin = child.stdin.take();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let buf = Arc::new(Mutex::new(String::new()));
    pump(stdout, buf.clone());
    pump(stderr, buf.clone());
    let pid = child.id().unwrap_or(0);
    Ok(EngineChild {
        pid,
        stdout: buf,
        inner: Inner::Tokio { child, stdin },
    })
}

#[cfg(not(windows))]
fn apply_args(
    cmd: &mut Command,
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    port: Option<u32>,
    coop: bool,
) {
    cmd.arg("-dedicated")
        .arg(slots.to_string())
        .arg("-basedir")
        .arg(&cfg.basedir)
        .arg("-game")
        .arg(&cfg.game)
        .arg("-condebug")
        .arg("+developer")
        .arg("1");
    if coop {
        cmd.arg("+coop").arg("1").arg("+deathmatch").arg("0");
    } else {
        cmd.arg("+deathmatch").arg("1");
    }
    if let Some(p) = port {
        cmd.arg("-port").arg(p.to_string());
    }
    cmd.arg("+map").arg(map);
    if let Some(s) = skill {
        cmd.arg("+skill").arg(s.to_string());
    }
}

#[cfg(not(windows))]
/// Drain the child's stdout forever. Quake's console is full of high
/// bit bytes (bronze chat, coloured names, map messages), and
/// `next_line` returns Err(InvalidData) on one: the old loop ended
/// there, nothing drained the pipe, and the engine blocked in
/// Sys_Printf once the next 64 KB filled. On Linux this buffer is the
/// only tape source, so that froze the match and lost the tape. Read
/// bytes, convert lossily, and keep draining past an error.
fn pump<T: tokio::io::AsyncRead + Unpin + Send + 'static>(
    stream: Option<T>,
    buf: Arc<Mutex<String>>,
) {
    if let Some(out) = stream {
        tokio::spawn(async move {
            let mut rdr = BufReader::new(out);
            let mut line = Vec::new();
            loop {
                line.clear();
                match rdr.read_until(b'\n', &mut line).await {
                    Ok(0) => break,
                    Ok(_) => {
                        while matches!(line.last(), Some(b'\n') | Some(b'\r')) {
                            line.pop();
                        }
                        if let Ok(mut g) = buf.lock() {
                            g.push_str(&String::from_utf8_lossy(&line));
                            g.push('\n');
                        }
                    }
                    // an error on the pipe is not a reason to stop
                    // draining it; only EOF is
                    Err(_) => continue,
                }
            }
        });
    }
}


/// A hard kill of the MCP server (the client does not close stdio, it
/// terminates the process) never runs Drop, so the dedicated engine
/// survived and held UDP 26000 against the next server. Every engine
/// is assigned to one process-wide Job Object created with
/// KILL_ON_JOB_CLOSE: when this process dies for any reason its
/// handles close, the job closes, and Windows takes the engine with
/// it.
#[cfg(windows)]
fn engine_job() -> windows_sys::Win32::Foundation::HANDLE {
    use std::sync::OnceLock;
    use windows_sys::Win32::System::JobObjects::{
        CreateJobObjectW, SetInformationJobObject,
        JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    static JOB: OnceLock<SendHandle> = OnceLock::new();
    JOB.get_or_init(|| unsafe {
        let h = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if !h.is_null() {
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            SetInformationJobObject(
                h,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const std::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
        }
        SendHandle(h)
    })
    .0
}

#[cfg(windows)]
fn spawn_windows(
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    cwd: &Path,
    port: Option<u32>,
    coop: bool,
) -> Result<EngineChild, String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::System::Threading::{
        CreateProcessW, CREATE_NEW_CONSOLE, CREATE_UNICODE_ENVIRONMENT, PROCESS_INFORMATION,
        STARTF_USESHOWWINDOW, STARTUPINFOW,
    };

    let exe = cfg.engine.display().to_string();
    let portarg = port.map(|p| format!(" -port {p}")).unwrap_or_default();
    let mode_arg = if coop {
        "+coop 1 +deathmatch 0"
    } else {
        "+deathmatch 1"
    };
    let mut args = format!(
        "\"{exe}\" -dedicated {slots} -basedir \"{}\" -game {}{portarg} -condebug +developer 1 {mode_arg} +map {map}",
        cfg.basedir.display(),
        cfg.game
    );
    if let Some(s) = skill {
        if s > 3 {
            return Err("skill must be 0..3".into());
        }
        args.push_str(&format!(" +skill {s}"));
    }

    let mut cmd_wide: Vec<u16> = args.encode_utf16().chain(std::iter::once(0)).collect();
    let cwd_wide: Vec<u16> = cwd.as_os_str().encode_wide().chain(std::iter::once(0)).collect();

    let mut si: STARTUPINFOW = unsafe { std::mem::zeroed() };
    si.cb = std::mem::size_of::<STARTUPINFOW>() as u32;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = 0; // SW_HIDE: console exists, window does not
    let mut pi: PROCESS_INFORMATION = unsafe { std::mem::zeroed() };

    // bInheritHandles = FALSE so the child does not get the MCP JSON-RPC pipe
    // as stdin. CREATE_NEW_CONSOLE gives GetNumberOfConsoleInputEvents a
    // real console. Do not set STARTF_USESTDHANDLES.
    let ok = unsafe {
        CreateProcessW(
            std::ptr::null(),
            cmd_wide.as_mut_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            0,
            CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT,
            std::ptr::null(),
            cwd_wide.as_ptr(),
            &si,
            &mut pi,
        )
    };
    if ok == 0 {
        return Err(format!(
            "failed to spawn ARGUS_ENGINE: {}",
            std::io::Error::last_os_error()
        ));
    }
    unsafe {
        windows_sys::Win32::Foundation::CloseHandle(pi.hThread);
        let job = engine_job();
        if !job.is_null() {
            windows_sys::Win32::System::JobObjects::AssignProcessToJobObject(job, pi.hProcess);
        }
    }
    Ok(EngineChild {
        pid: pi.dwProcessId,
        stdout: Arc::new(Mutex::new(String::new())),
        inner: Inner::Win {
            handle: SendHandle(pi.hProcess),
        },
    })
}

#[cfg(windows)]
fn win_try_wait(handle: windows_sys::Win32::Foundation::HANDLE) -> Result<Option<i32>, String> {
    if handle.is_null() {
        return Ok(Some(0));
    }
    use windows_sys::Win32::Foundation::{WAIT_OBJECT_0, WAIT_TIMEOUT};
    use windows_sys::Win32::System::Threading::{GetExitCodeProcess, WaitForSingleObject};
    const STILL_ACTIVE: u32 = 259;
    let wr = unsafe { WaitForSingleObject(handle, 0) };
    match wr {
        WAIT_TIMEOUT => Ok(None),
        WAIT_OBJECT_0 => {
            let mut code: u32 = 0;
            let ok = unsafe { GetExitCodeProcess(handle, &mut code) };
            if ok == 0 {
                return Err(format!(
                    "GetExitCodeProcess: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if code == STILL_ACTIVE {
                Ok(None)
            } else {
                Ok(Some(code as i32))
            }
        }
        other => Err(format!("WaitForSingleObject: {other}")),
    }
}

#[cfg(windows)]
fn win_inject(pid: u32, line: &str) -> Result<(), String> {
    use windows_sys::Win32::Foundation::{CloseHandle, GENERIC_READ, GENERIC_WRITE, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
    };
    use windows_sys::Win32::System::Console::{
        AttachConsole, FreeConsole, GetStdHandle, SetStdHandle, WriteConsoleInputW, INPUT_RECORD,
        STD_ERROR_HANDLE, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE,
    };

    // Save the MCP JSON-RPC pipes, attach to the child's hidden console,
    // type the line, then restore the pipes so stdio MCP stays intact.
    // The console input buffer must be opened as CONIN$: after
    // AttachConsole, GetStdHandle(STD_INPUT_HANDLE) still returns this
    // process's redirected stdin (the JSON-RPC pipe) - writing console
    // records to it was the "WriteConsoleInputW: invalid handle" failure
    // that left Windows live-tune broken from 0.15 until the 2026-08-27
    // stack sweep finally exercised it end to end.
    unsafe {
        let hin = GetStdHandle(STD_INPUT_HANDLE);
        let hout = GetStdHandle(STD_OUTPUT_HANDLE);
        let herr = GetStdHandle(STD_ERROR_HANDLE);
        let _ = FreeConsole();
        if AttachConsole(pid) == 0 {
            let _ = SetStdHandle(STD_INPUT_HANDLE, hin);
            let _ = SetStdHandle(STD_OUTPUT_HANDLE, hout);
            let _ = SetStdHandle(STD_ERROR_HANDLE, herr);
            return Err(format!(
                "AttachConsole({pid}): {}",
                std::io::Error::last_os_error()
            ));
        }
        let conin: Vec<u16> = "CONIN$\0".encode_utf16().collect();
        let con_in = CreateFileW(
            conin.as_ptr(),
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            std::ptr::null(),
            OPEN_EXISTING,
            0,
            std::ptr::null_mut(),
        );
        if con_in == INVALID_HANDLE_VALUE {
            let err = std::io::Error::last_os_error();
            let _ = FreeConsole();
            let _ = SetStdHandle(STD_INPUT_HANDLE, hin);
            let _ = SetStdHandle(STD_OUTPUT_HANDLE, hout);
            let _ = SetStdHandle(STD_ERROR_HANDLE, herr);
            return Err(format!("CreateFileW(CONIN$): {err}"));
        }
        let mut recs: Vec<INPUT_RECORD> = Vec::new();
        for ch in line.encode_utf16().chain(std::iter::once(b'\r' as u16)) {
            recs.push(key_rec(ch, 1));
            recs.push(key_rec(ch, 0));
        }
        let mut written = 0u32;
        let ok = WriteConsoleInputW(con_in, recs.as_ptr(), recs.len() as u32, &mut written);
        let _ = CloseHandle(con_in);
        let _ = FreeConsole();
        let _ = SetStdHandle(STD_INPUT_HANDLE, hin);
        let _ = SetStdHandle(STD_OUTPUT_HANDLE, hout);
        let _ = SetStdHandle(STD_ERROR_HANDLE, herr);
        if ok == 0 {
            return Err(format!(
                "WriteConsoleInputW: {}",
                std::io::Error::last_os_error()
            ));
        }
    }
    Ok(())
}

#[cfg(windows)]
fn key_rec(ch: u16, down: i32) -> windows_sys::Win32::System::Console::INPUT_RECORD {
    use windows_sys::Win32::System::Console::{
        INPUT_RECORD, INPUT_RECORD_0, KEY_EVENT, KEY_EVENT_RECORD, KEY_EVENT_RECORD_0,
    };
    INPUT_RECORD {
        EventType: KEY_EVENT as u16,
        Event: INPUT_RECORD_0 {
            KeyEvent: KEY_EVENT_RECORD {
                bKeyDown: down,
                wRepeatCount: 1,
                wVirtualKeyCode: 0,
                wVirtualScanCode: 0,
                uChar: KEY_EVENT_RECORD_0 { UnicodeChar: ch },
                dwControlKeyState: 0,
            },
        },
    }
}

#[cfg(windows)]
fn win_kill(handle: windows_sys::Win32::Foundation::HANDLE) -> Result<(), String> {
    if handle.is_null() {
        return Ok(());
    }
    let ok = unsafe { windows_sys::Win32::System::Threading::TerminateProcess(handle, 1) };
    if ok == 0 {
        return Err(format!(
            "TerminateProcess: {}",
            std::io::Error::last_os_error()
        ));
    }
    Ok(())
}

#[cfg(test)]
impl EngineChild {
    pub(crate) fn mock() -> Self {
        #[cfg(windows)]
        {
            Self {
                inner: Inner::Win {
                    handle: SendHandle(std::ptr::null_mut()),
                },
                pid: 0,
                stdout: std::sync::Arc::new(std::sync::Mutex::new(String::new())),
            }
        }
        #[cfg(not(windows))]
        {
            let child = tokio::process::Command::new("sleep")
                .arg("10")
                .kill_on_drop(true)
                .spawn()
                .unwrap();
            Self {
                inner: Inner::Tokio {
                    child,
                    stdin: None,
                },
                pid: 0,
                stdout: std::sync::Arc::new(std::sync::Mutex::new(String::new())),
            }
        }
    }

    #[cfg(windows)]
    pub(crate) fn from_raw(handle: windows_sys::Win32::Foundation::HANDLE, pid: u32) -> Self {
        Self {
            inner: Inner::Win {
                handle: SendHandle(handle),
            },
            pid,
            stdout: std::sync::Arc::new(std::sync::Mutex::new(String::new())),
        }
    }
}

/// Kill an engine by pid without owning its EngineChild. shutdown and
/// match_stop need this because match_run holds the MatchCtrl mutex for
/// the whole match and the child is behind it.
pub fn kill_pid(pid: u32) -> bool {
    if pid == 0 {
        return false;
    }
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::Threading::{OpenProcess, TerminateProcess, PROCESS_TERMINATE};
        let h = OpenProcess(PROCESS_TERMINATE, 0, pid);
        if h.is_null() {
            return false;
        }
        let ok = TerminateProcess(h, 1) != 0;
        CloseHandle(h);
        ok
    }
    #[cfg(not(windows))]
    {
        std::process::Command::new("kill")
            .arg("-9")
            .arg(pid.to_string())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_path_maps() {
        assert!(validate_map("../id1/maps/dm4").is_err());
        assert!(validate_map("maps/dm4").is_err());
        assert!(validate_map("").is_err());
        assert!(validate_map("dm4").is_ok());
        assert!(validate_map("lqdm2").is_ok());
    }

    #[test]
    #[cfg(windows)]
    fn engine_child_drop_terminates_process() {
        let mut cmd = std::process::Command::new("powershell");
        cmd.args(["-NoProfile", "-Command", "Start-Sleep -Seconds 10"]);
        let child = cmd.spawn().expect("spawn powershell");
        let pid = child.id();

        let handle = unsafe {
            windows_sys::Win32::System::Threading::OpenProcess(
                windows_sys::Win32::System::Threading::PROCESS_TERMINATE
                    | windows_sys::Win32::System::Threading::PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                pid,
            )
        };
        assert!(!handle.is_null());

        // Wrap into EngineChild and drop it
        {
            let _ec = EngineChild {
                inner: Inner::Win {
                    handle: SendHandle(handle),
                },
                pid,
                stdout: std::sync::Arc::new(std::sync::Mutex::new(String::new())),
            };
            // _ec drops here, which must invoke win_kill and CloseHandle
        }

        std::thread::sleep(std::time::Duration::from_millis(200));
        let check_handle = unsafe {
            windows_sys::Win32::System::Threading::OpenProcess(
                windows_sys::Win32::System::Threading::PROCESS_QUERY_LIMITED_INFORMATION,
                0,
                pid,
            )
        };
        if !check_handle.is_null() {
            let mut exit_code: u32 = 0;
            unsafe {
                windows_sys::Win32::System::Threading::GetExitCodeProcess(check_handle, &mut exit_code);
                windows_sys::Win32::Foundation::CloseHandle(check_handle);
            }
            assert_ne!(exit_code, 259, "process should have been terminated on drop");
        }
    }

    /// The live-tune inject, exercised for real: spawn the hidden
    /// dedicated engine, type `status` into its console via
    /// AttachConsole + CONIN$, and require the status output in the
    /// log. This path shipped broken from 0.15 (GetStdHandle after
    /// AttachConsole returns the MCP's own pipe, not the console -
    /// "WriteConsoleInputW: invalid handle") and nothing noticed for
    /// twelve days because nothing ran it. Machine-local: skips
    /// without the lab engine. Serialised by nature - it binds the
    /// engine's UDP port, so do not run while a lab match is live.
    #[tokio::test]
    async fn windows_console_inject_reaches_the_engine_if_present() {
        if !cfg!(windows) {
            return;
        }
        // a panic in another engine test poisons the lock; recover so
        // one failure cannot cascade through the whole engine suite
        let _gate = crate::engine::ENGINE_TEST_LOCK
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let Ok(mut cfg) = crate::config::load_for_reads_from(&env, &root) else {
            return;
        };
        if !cfg.engine.exists() {
            eprintln!("SKIPPED {}: no ARGUS_ENGINE on this box", "probe_inject_test");
            return;
        }
        // a temp runs/ so the probe tape never lands in the real one:
        // resolve_latest picks the newest runs/*.log, and a 7 s test
        // tape became what "latest" meant for the next compare
        let tmp_runs = std::env::temp_dir().join(format!("argus-{}-{}", "probe_inject_test", std::process::id()));
        let _ = std::fs::create_dir_all(&tmp_runs);
        cfg.runs = tmp_runs.clone();
        let mut ctrl = crate::match_ctrl::MatchCtrl::default();
        if ctrl
            .start(&cfg, "dm4", Some(30), Some("probe_inject_test"), None, Some(1), None)
            .await
            .is_err()
        {
            eprintln!("SKIPPED probe_inject_test: engine refused to start (port in use?)");
            return; // engine present but refused (port in use): not this test's fault
        }
        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
        let inject = ctrl.command("status").await;
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let log = ctrl.log_text().unwrap_or_default();
        let _ = ctrl.stop(std::time::Duration::from_secs(3)).await;
        inject.expect("console inject must not error");
        assert!(
            log.contains("host:") || log.contains("players:"),
            "status output must reach the log; tail: {}",
            log.chars().rev().take(400).collect::<String>().chars().rev().collect::<String>()
        );
    }
}
