//! Dedicated-engine child. Unix pipes stdin. Windows CreateProcess
//! with a new console and no inherited MCP stdio handles.

use crate::config::Config;
use std::path::Path;
use std::sync::{Arc, Mutex};

#[cfg(not(windows))]
use std::process::Stdio;
#[cfg(not(windows))]
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
#[cfg(any(not(windows), test))]
use tokio::process::Command;
#[cfg(not(windows))]
use tokio::process::{Child, ChildStdin};

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
    Tokio {
        child: Box<Child>,
        stdin: Option<ChildStdin>,
    },
    #[cfg(windows)]
    Win { handle: SendHandle },
    #[cfg(test)]
    Fake { control: FakeEngineControl },
}

#[cfg(test)]
struct FakeEngineState {
    running: std::sync::atomic::AtomicBool,
    killed: std::sync::atomic::AtomicBool,
    quit_requested: std::sync::atomic::AtomicBool,
    stdout: Arc<Mutex<String>>,
    /// The clock the controller would have launched a real engine on.
    clock: Mutex<Option<EngineClock>>,
}

#[cfg(test)]
#[derive(Clone)]
pub(crate) struct FakeEngineControl {
    pid: u32,
    state: Arc<FakeEngineState>,
}

#[cfg(test)]
impl FakeEngineControl {
    pub(crate) fn new(output: impl Into<String>) -> Self {
        static NEXT_FAKE_PID: std::sync::atomic::AtomicU32 =
            std::sync::atomic::AtomicU32::new(4_000_000);
        Self {
            pid: NEXT_FAKE_PID.fetch_add(1, std::sync::atomic::Ordering::SeqCst),
            state: Arc::new(FakeEngineState {
                running: std::sync::atomic::AtomicBool::new(true),
                killed: std::sync::atomic::AtomicBool::new(false),
                quit_requested: std::sync::atomic::AtomicBool::new(false),
                stdout: Arc::new(Mutex::new(output.into())),
                clock: Mutex::new(None),
            }),
        }
    }

    /// Record the clock a real launch would have used.
    pub(crate) fn note_clock(&self, clock: EngineClock) {
        *self.state.clock.lock().expect("fake clock lock poisoned") = Some(clock);
    }

    /// The clock this engine was launched on, once a controller took it.
    pub(crate) fn launched_clock(&self) -> Option<EngineClock> {
        *self.state.clock.lock().expect("fake clock lock poisoned")
    }

    pub(crate) fn complete(&self) {
        self.state
            .running
            .store(false, std::sync::atomic::Ordering::SeqCst);
    }

    pub(crate) fn is_running(&self) -> bool {
        self.state.running.load(std::sync::atomic::Ordering::SeqCst)
    }

    pub(crate) fn was_killed(&self) -> bool {
        self.state.killed.load(std::sync::atomic::Ordering::SeqCst)
    }

    pub(crate) fn quit_requested(&self) -> bool {
        self.state
            .quit_requested
            .load(std::sync::atomic::Ordering::SeqCst)
    }

    fn kill(&self) {
        self.state
            .killed
            .store(true, std::sync::atomic::Ordering::SeqCst);
        self.complete();
    }
}

#[cfg(test)]
fn fake_engines() -> &'static Mutex<std::collections::HashMap<u32, std::sync::Weak<FakeEngineState>>>
{
    static ENGINES: std::sync::OnceLock<
        Mutex<std::collections::HashMap<u32, std::sync::Weak<FakeEngineState>>>,
    > = std::sync::OnceLock::new();
    ENGINES.get_or_init(|| Mutex::new(std::collections::HashMap::new()))
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
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn spawn(
        cfg: &Config,
        map: &str,
        slots: u32,
        skill: Option<u32>,
        cwd: &Path,
        port: Option<u16>,
        coop: bool,
        clock: EngineClock,
        roster: EngineRoster,
    ) -> Result<Self, String> {
        let map = crate::paths::map_name(map)?;
        let map = map.as_str();
        if slots == 0 || slots > 16 {
            return Err("dedicated_slots must be 1..=16".into());
        }
        if let Some(p) = port {
            if !(1024..=65535).contains(&p) {
                return Err("port must be 1024..=65535".into());
            }
        }
        let actual_port = port.unwrap_or(crate::match_ctrl::DEFAULT_PORT);
        // The engine can survive a failed bind. Refuse a currently occupied
        // socket before starting it, so no helper attaches to another match.
        check_port_available(actual_port)?;
        #[cfg(windows)]
        {
            spawn_windows(cfg, map, slots, skill, cwd, port, coop, clock, roster)
        }
        #[cfg(not(windows))]
        {
            spawn_unix(cfg, map, slots, skill, cwd, port, coop, clock, roster)
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
            #[cfg(test)]
            Inner::Fake { control } => Ok((!control.is_running()).then_some(0)),
        }
    }

    pub async fn kill(&mut self) -> Result<(), String> {
        match &mut self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { child, .. } => child.kill().await.map_err(|e| format!("kill: {e}")),
            #[cfg(windows)]
            Inner::Win { handle } => win_kill(handle.0),
            #[cfg(test)]
            Inner::Fake { control } => {
                control.kill();
                Ok(())
            }
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
                stdin
                    .flush()
                    .await
                    .map_err(|e| format!("flush console: {e}"))
            }
            #[cfg(windows)]
            Inner::Win { .. } => win_inject(self.pid, line).await,
            #[cfg(test)]
            Inner::Fake { control } => {
                if line == "quit" {
                    control
                        .state
                        .quit_requested
                        .store(true, std::sync::atomic::Ordering::SeqCst);
                    control.complete();
                }
                Ok(())
            }
        }
    }

    pub fn has_stdin(&self) -> bool {
        match &self.inner {
            #[cfg(not(windows))]
            Inner::Tokio { stdin, .. } => stdin.is_some(),
            #[cfg(windows)]
            Inner::Win { .. } => true,
            #[cfg(test)]
            Inner::Fake { .. } => true,
        }
    }
}

impl Drop for EngineChild {
    fn drop(&mut self) {
        #[cfg(windows)]
        {
            match &mut self.inner {
                Inner::Win { handle } => {
                    if !handle.0.is_null() {
                        let _ = win_kill(handle.0);
                        unsafe {
                            windows_sys::Win32::Foundation::CloseHandle(handle.0);
                        }
                        handle.0 = std::ptr::null_mut();
                    }
                }
                #[cfg(test)]
                Inner::Fake { .. } => {}
            }
        }
        #[cfg(test)]
        if matches!(self.inner, Inner::Fake { .. }) {
            fake_engines()
                .lock()
                .expect("fake engine registry lock poisoned")
                .remove(&self.pid);
        }
    }
}

pub(crate) fn check_port_available(port: u16) -> Result<(), String> {
    if port < 1024 {
        return Err("port must be 1024..=65535".into());
    }
    let probe = std::net::UdpSocket::bind((std::net::Ipv4Addr::UNSPECIFIED, port))
        .map_err(|e| format!("engine UDP port {port} is unavailable: {e}"))?;
    drop(probe);
    // QuakeSpasm binds the address gethostbyname gives for the local host,
    // not the wildcard, and on Windows a wildcard probe succeeds while an
    // engine holds that address (#832). Probe each hostname address too.
    for addr in hostname_ipv4s() {
        let probe = std::net::UdpSocket::bind((addr, port)).map_err(|e| {
            format!("engine UDP port {port} is unavailable on {addr} (an engine holds it): {e}")
        })?;
        drop(probe);
    }
    Ok(())
}

/// The IPv4 addresses the local hostname resolves to, as WinQuake's
/// gethostbyname lookup sees them. Empty when the name cannot be resolved.
fn hostname_ipv4s() -> Vec<std::net::Ipv4Addr> {
    use std::net::ToSocketAddrs;
    let Ok(name) = std::env::var("COMPUTERNAME").or_else(|_| std::env::var("HOSTNAME")) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    if let Ok(addrs) = (name.as_str(), 0).to_socket_addrs() {
        for addr in addrs {
            if let std::net::IpAddr::V4(v4) = addr.ip() {
                if !v4.is_unspecified() && !out.contains(&v4) {
                    out.push(v4);
                }
            }
        }
    }
    out
}

pub fn validate_map(map: &str) -> Result<(), String> {
    crate::paths::map_name(map).map(|_| ())
}

#[cfg(not(windows))]
#[allow(clippy::too_many_arguments)]
fn spawn_unix(
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    cwd: &Path,
    port: Option<u16>,
    coop: bool,
    clock: EngineClock,
    roster: EngineRoster,
) -> Result<EngineChild, String> {
    let mut cmd = Command::new(&cfg.engine);
    apply_args(&mut cmd, cfg, map, slots, skill, port, coop, clock, roster);
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
        inner: Inner::Tokio {
            child: Box::new(child),
            stdin,
        },
    })
}

/// The dedicated server's frame period, in seconds.
///
/// Quake's dedicated main loop sleeps until `sys_ticrate` has elapsed
/// before it calls `Host_Frame`, so this cvar gates the entire server
/// tick. The engine default of 0.05 ran every lab tape at about 19 Hz
/// while every human session is a listen server at about 71 Hz - a
/// factor of nearly four on every per-frame constant in bot physics
/// and on the aim spring's integrator, which is why a tape and a
/// played session were never the same game. Measured on dm4,
/// 2026-09-15, with the telemetry-cadence estimator
/// (`tools/argus_tick.py`): the default reads a mean ARGLOG gap of
/// 0.5134 (about 19 Hz) and this value reads 0.5080, inside the
/// 0.506 to 0.509 band every human tape sits in.
///
/// This refutes the v4.09 note that "sys_ticrate does nothing to the
/// dedicated tick"; it does everything to it.
///
/// See docs/plans/2026-09-14-regression-analysis-and-recovery.md.
pub const PLAYED_TICRATE: &str = "0.0139";

/// The tick rate this launch will use.
///
/// `PLAYED_TICRATE` unless `ARGUS_TICRATE` overrides it, which exists
/// for one job: measuring what the rate itself does to a build, by
/// running the same progs at the old 0.05 and comparing. It is not a
/// setting anyone should leave on - every brief states the class it
/// actually ran at, and `compare_band` voids a verdict across two.
pub fn ticrate() -> String {
    std::env::var("ARGUS_TICRATE").unwrap_or_else(|_| PLAYED_TICRATE.to_string())
}

/// The frame every fixed-clock match runs: 14.25 ms, the wall-clock lab's own
/// measured rate (70.2 Hz with `host_speeds`; the loop waits at least
/// `PLAYED_TICRATE` and the sleep rounds it up). The fixed clock screens for
/// the lab, so it runs the lab's frame. 13.9 ms, the human's listen-server
/// frame, was the first default and failed its registered validation on dm4
/// (more lava deaths and routefails than the wall clock); 14.25 ms passed a
/// registered confirmation on fresh seeds on dm4 and dm2
/// (docs/fixed-clock.md).
pub const FIXED_FRAME: &str = "0.01425";

/// The fixed clock's frame for this launch: `FIXED_FRAME` unless
/// `ARGUS_FIXED_FRAME` overrides it. Like `ARGUS_TICRATE`, the override
/// exists to measure what the frame length itself does (the wall-clock lab
/// averages 14.25 ms against the fixed 13.9), and every tape records the
/// frame it ran in its `ARGUS clock` line.
pub fn fixed_frame() -> String {
    std::env::var("ARGUS_FIXED_FRAME")
        .ok()
        .filter(|v| v.parse::<f64>().is_ok_and(|f| (0.005..=0.1).contains(&f)))
        .unwrap_or_else(|| FIXED_FRAME.to_string())
}

/// How the engine's clock runs for one launch.
///
/// `Played` is the ordinary server: the dedicated loop waits for
/// `sys_ticrate` of wall time per frame, so a 185 s match takes 185 s.
///
/// `Fixed` is the lab clock. `host_framerate` pins every frame at
/// `FIXED_FRAME` whatever the wall clock did, so the physics runs the lab's
/// measured rate exactly, and `sys_ticrate 0.001` with `host_maxfps 1000` lets the
/// loop run a frame per millisecond instead of waiting. Measured on this rig
/// (2026-11-15) at about 6.5 times real time per engine. Two consequences:
///
/// - It repeats. The engine draws QC random() from the C library stream
///   and calls rand() once per main-loop pass ("keep the random time
///   dependent"); with one pass per frame that is one draw per frame, so a
///   given progs, map and seed produce the same match every time. `seed`
///   reaches QC as `saved4`, which Argus_Init burns as that many draws.
///   (`sys_ticrate 0`, which runs about twice as fast, busy-loops and
///   draws thousands of times between frames, so it never repeats.)
/// - It ends on game time. `+timelimit` makes the bots end the match at the
///   requested length, so every fixed tape is exactly as long as asked.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum EngineClock {
    #[default]
    Played,
    Fixed {
        seed: u32,
        limit_sec: Option<u32>,
    },
}

impl EngineClock {
    pub fn fixed(seed: u32) -> Self {
        EngineClock::Fixed {
            seed,
            limit_sec: None,
        }
    }

    pub fn is_fixed(&self) -> bool {
        matches!(self, EngineClock::Fixed { .. })
    }

    /// The same clock with the match length it must end at.
    pub fn with_limit(self, limit: Option<u32>) -> Self {
        match self {
            EngineClock::Fixed { seed, .. } => EngineClock::Fixed {
                seed,
                limit_sec: limit,
            },
            played => played,
        }
    }

    /// The console arguments that set this clock, in launch order.
    pub fn args(&self) -> Vec<String> {
        match *self {
            EngineClock::Played => vec!["+sys_ticrate".into(), ticrate()],
            EngineClock::Fixed { seed, limit_sec } => {
                let mut args = vec![
                    "+sys_ticrate".to_string(),
                    "0.001".into(),
                    "+host_framerate".into(),
                    fixed_frame(),
                    "+host_maxfps".into(),
                    "1000".into(),
                    "+saved4".into(),
                    seed.to_string(),
                ];
                if let Some(limit) = limit_sec {
                    args.push("+timelimit".into());
                    args.push(format!("{:.6}", f64::from(limit) / 60.0));
                }
                args
            }
        }
    }
}

#[derive(Clone, Copy, Default)]
pub(crate) enum EngineRoster {
    #[default]
    Standard,
    FixedRoute,
}

impl EngineRoster {
    fn args(self) -> &'static [&'static str] {
        match self {
            Self::Standard => &[],
            Self::FixedRoute => &["+scratch1", "3843"],
        }
    }
}

#[cfg(any(not(windows), test))]
#[allow(clippy::too_many_arguments)]
fn apply_args(
    cmd: &mut Command,
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    port: Option<u16>,
    coop: bool,
    clock: EngineClock,
    roster: EngineRoster,
) {
    cmd.arg("-dedicated")
        .arg(slots.to_string())
        .arg("-basedir")
        .arg(&cfg.basedir)
        .arg("-game")
        .arg(&cfg.game)
        .arg("-condebug")
        .arg("+developer")
        .arg("1")
        .args(clock.args());
    if coop {
        cmd.arg("+coop").arg("1").arg("+deathmatch").arg("0");
    } else {
        cmd.arg("+deathmatch").arg("1");
    }
    cmd.arg("-port")
        .arg(port.unwrap_or(crate::match_ctrl::DEFAULT_PORT).to_string());
    if let Some(s) = skill {
        cmd.arg("+skill").arg(s.to_string());
    }
    // Map loading runs QC and spawns the roster before later commands.
    cmd.args(roster.args()).arg("+map").arg(map);
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
        CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
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

#[cfg(any(windows, test))]
#[allow(clippy::too_many_arguments)]
/// Build the dedicated engine's command line. Split out of
/// `spawn_windows` so a test can assert on it without spawning a
/// process: the tick-rate flag is the one argument the whole lab's
/// comparability rests on.
fn windows_args(
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    port: Option<u16>,
    coop: bool,
    clock: EngineClock,
    roster: EngineRoster,
) -> Result<String, String> {
    // CreateProcessW receives the full executable path separately.
    const ARGV0: &str = "argus-engine";
    let port = port.unwrap_or(crate::match_ctrl::DEFAULT_PORT);
    let mode_arg = if coop {
        "+coop 1 +deathmatch 0"
    } else {
        "+deathmatch 1"
    };
    let tick = clock.args().join(" ");
    let mut startup =
        format!("-dedicated {slots} -port {port} -condebug +developer 1 {tick} {mode_arg}");
    if let Some(s) = skill {
        if s > 3 {
            return Err("skill must be 0..3".into());
        }
        startup.push_str(&format!(" +skill {s}"));
    }
    for arg in roster.args() {
        startup.push(' ');
        startup.push_str(arg);
    }
    startup.push_str(&format!(" +map {map}"));

    // QuakeSpasm 0.96.3's COM_InitArgv keeps 255 bytes of space-joined argv
    // for stuffcmds. The engine reads -basedir and -game from the full argv,
    // so put their variable-length values after the last startup command.
    const QUAKE_CMDLINE_BYTES: usize = 255;
    if ARGV0.len() + 1 + startup.len() > QUAKE_CMDLINE_BYTES {
        return Err(format!(
            "Windows startup commands through '+map {map}' exceed QuakeSpasm's {QUAKE_CMDLINE_BYTES}-byte command limit"
        ));
    }
    Ok(format!(
        "{ARGV0} {startup} -basedir \"{}\" -game {}",
        cfg.basedir.display(),
        cfg.game
    ))
}

#[cfg(windows)]
#[allow(clippy::too_many_arguments)]
fn spawn_windows(
    cfg: &Config,
    map: &str,
    slots: u32,
    skill: Option<u32>,
    cwd: &Path,
    port: Option<u16>,
    coop: bool,
    clock: EngineClock,
    roster: EngineRoster,
) -> Result<EngineChild, String> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::System::Threading::{
        CreateProcessW, PROCESS_INFORMATION, STARTF_USESHOWWINDOW, STARTUPINFOW,
    };

    let args = windows_args(cfg, map, slots, skill, port, coop, clock, roster)?;

    let exe_wide: Vec<u16> = cfg
        .engine
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();
    let mut cmd_wide: Vec<u16> = args.encode_utf16().chain(std::iter::once(0)).collect();
    let cwd_wide: Vec<u16> = cwd
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();

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
            exe_wide.as_ptr(),
            cmd_wide.as_mut_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            0,
            engine_creation_flags(),
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

/// Creation flags for a lab engine on Windows.
///
/// ABOVE_NORMAL_PRIORITY_CLASS keeps a ladder in the played tick class when
/// another job holds the CPU: on 2026-11-13 a busy machine pushed every tape
/// in two rounds to `dedicated_fast` at normal priority, and raising the same
/// engines to AboveNormal kept them in the listen class with full game time
/// (#786). It is one class above normal, not High, so the desktop stays usable.
#[cfg(windows)]
fn engine_creation_flags() -> u32 {
    use windows_sys::Win32::System::Threading::{
        ABOVE_NORMAL_PRIORITY_CLASS, CREATE_NEW_CONSOLE, CREATE_UNICODE_ENVIRONMENT,
    };
    CREATE_NEW_CONSOLE | CREATE_UNICODE_ENVIRONMENT | ABOVE_NORMAL_PRIORITY_CLASS
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

/// Private executable entry point. Never expose this as an MCP tool.
pub fn console_helper(args: impl Iterator<Item = String>) -> Result<(), String> {
    let args: Vec<_> = args.collect();
    if args.len() != 3 || args[0] != crate::build_identity::BUILD_SOURCE {
        return Err("console helper requires a matching source build, PID and one line".into());
    }
    let pid: u32 = args[1].parse().map_err(|_| "invalid console PID")?;
    if pid == 0 || pid == u32::MAX || args[2].is_empty() || args[2].contains(['\r', '\n']) {
        return Err("invalid console PID or line".into());
    }
    #[cfg(windows)]
    {
        console_inject_attached(pid, &args[2])
    }
    #[cfg(not(windows))]
    {
        Err("console helper is Windows-only".into())
    }
}

#[cfg(windows)]
async fn win_inject(pid: u32, line: &str) -> Result<(), String> {
    let executable =
        std::env::current_exe().map_err(|e| format!("console helper executable: {e}"))?;
    // Cargo's library harness is in deps/. Its sibling executable is built by
    // cargo test; the fingerprint argument refuses an older helper image.
    #[cfg(test)]
    let executable = executable
        .parent()
        .and_then(Path::parent)
        .ok_or("test executable directory")?
        .join("argus-mcp.exe");
    // `cargo test --lib` builds no binary, so a fresh target directory, or
    // one whose CLI predates the source, fails here in every thread count
    // (#805). Say so rather than report a bare os error 2.
    #[cfg(test)]
    if !executable.is_file() {
        return Err(format!(
            "console helper {} is missing; cargo test --lib does not build it, \
             so run cargo build --bin argus-mcp first",
            executable.display()
        ));
    }
    let mut command = tokio::process::Command::new(executable);
    command
        .args([
            "internal-win-inject",
            crate::build_identity::BUILD_SOURCE,
            &pid.to_string(),
            line,
        ])
        .creation_flags(windows_sys::Win32::System::Threading::CREATE_NO_WINDOW);
    // A bound, not a delay: the helper exits as soon as its line is written.
    // 5 s was not enough for a fresh process to start on a loaded machine
    // (#836), and a refused inject fails a live tune or match command.
    let result = crate::python_helper::capture(
        &mut command,
        "Windows console helper",
        std::time::Duration::from_secs(15),
    )
    .await?;
    if !result.status.success() {
        let stderr = String::from_utf8_lossy(&result.stderr);
        let hint = if stderr.contains("matching source build") {
            "; the helper binary was built from different source, so rebuild it \
             with cargo build --bin argus-mcp"
        } else {
            ""
        };
        return Err(format!(
            "console helper exited {}: {}{hint}",
            result.status,
            stderr.trim()
        ));
    }
    Ok(())
}

#[cfg(windows)]
fn console_inject_attached(pid: u32, line: &str) -> Result<(), String> {
    if std::env::args().nth(1).as_deref() != Some("internal-win-inject") {
        return Err("console attachment is allowed only in the private helper process".into());
    }

    use windows_sys::Win32::Foundation::{
        CloseHandle, GENERIC_READ, GENERIC_WRITE, INVALID_HANDLE_VALUE,
    };
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING,
    };
    use windows_sys::Win32::System::Console::{
        AttachConsole, FreeConsole, GetStdHandle, SetStdHandle, WriteConsoleInputW, INPUT_RECORD,
        STD_ERROR_HANDLE, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE,
    };

    // Only this short-lived helper attaches. Restore its own captured handles
    // so an error can reach its parent; the lab never changes its console.
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
            let error = std::io::Error::last_os_error();
            let _ = SetStdHandle(STD_INPUT_HANDLE, hin);
            let _ = SetStdHandle(STD_OUTPUT_HANDLE, hout);
            let _ = SetStdHandle(STD_ERROR_HANDLE, herr);
            return Err(format!("AttachConsole({pid}): {}", error));
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
        let write_error = std::io::Error::last_os_error();
        let _ = CloseHandle(con_in);
        let _ = FreeConsole();
        let _ = SetStdHandle(STD_INPUT_HANDLE, hin);
        let _ = SetStdHandle(STD_OUTPUT_HANDLE, hout);
        let _ = SetStdHandle(STD_ERROR_HANDLE, herr);
        if ok != 0 && written != recs.len() as u32 {
            return Err(format!(
                "WriteConsoleInputW wrote {written} of {} records",
                recs.len()
            ));
        }
        if ok == 0 {
            return Err(format!("WriteConsoleInputW: {}", write_error));
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
                    child: Box::new(child),
                    stdin: None,
                },
                pid: 0,
                stdout: std::sync::Arc::new(std::sync::Mutex::new(String::new())),
            }
        }
    }

    pub(crate) fn fake(control: FakeEngineControl) -> Self {
        fake_engines()
            .lock()
            .expect("fake engine registry lock poisoned")
            .insert(control.pid, Arc::downgrade(&control.state));
        Self {
            pid: control.pid,
            stdout: control.state.stdout.clone(),
            inner: Inner::Fake { control },
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
    #[cfg(test)]
    if let Some(state) = fake_engines()
        .lock()
        .expect("fake engine registry lock poisoned")
        .get(&pid)
        .and_then(std::sync::Weak::upgrade)
    {
        state
            .killed
            .store(true, std::sync::atomic::Ordering::SeqCst);
        state
            .running
            .store(false, std::sync::atomic::Ordering::SeqCst);
        return true;
    }
    #[cfg(windows)]
    unsafe {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::Threading::{
            OpenProcess, TerminateProcess, PROCESS_TERMINATE,
        };
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
    #[test]
    fn console_helper_refuses_bad_build_pid_or_line_before_attachment() {
        let build = crate::build_identity::BUILD_SOURCE;
        for args in [
            vec![],
            vec!["old", "1", "status"],
            vec![build, "0", "status"],
            vec![build, "4294967295", "status"],
            vec![build, "bad", "status"],
            vec![build, "1", ""],
            vec![build, "1", "status\nquit"],
            vec![build, "1", "status\rquit"],
            vec![build, "1", "status", "extra"],
        ] {
            assert!(super::console_helper(args.into_iter().map(str::to_string)).is_err());
        }
    }

    #[cfg(windows)]
    #[test]
    fn console_attachment_refuses_the_parent_process() {
        let error = super::console_inject_attached(std::process::id(), "status").unwrap_err();
        assert!(error.contains("private helper process"), "{error}");
    }

    #[cfg(windows)]
    #[tokio::test]
    #[allow(clippy::await_holding_lock)]
    async fn windows_parallel_inject_keeps_markers_and_parent_handles_separate() {
        use windows_sys::Win32::System::Console::{
            GetStdHandle, STD_ERROR_HANDLE, STD_INPUT_HANDLE, STD_OUTPUT_HANDLE,
        };
        let _gate = super::ENGINE_TEST_LOCK
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        // Real matches write the process-wide live-match state that the
        // fake-match server tests assert on, so hold their lock too.
        let _live = crate::match_ctrl::live_test_lock_async().await;
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            &root,
        )
        .unwrap();
        if !cfg.engine.is_file() {
            eprintln!("SKIPPED parallel console injection: no local engine");
            return;
        }
        let temp = crate::test_support::TestDir::new("parallel-console").unwrap();
        cfg.runs = temp.path().join("runs");
        let handles = || unsafe {
            [
                GetStdHandle(STD_INPUT_HANDLE) as usize,
                GetStdHandle(STD_OUTPUT_HANDLE) as usize,
                GetStdHandle(STD_ERROR_HANDLE) as usize,
            ]
        };
        let before = handles();
        let mut left = crate::match_ctrl::MatchCtrl::on_port(26018);
        let mut right = crate::match_ctrl::MatchCtrl::on_port(26019);
        left.start(
            &cfg,
            "dm4",
            Some(30),
            Some("inject_left"),
            None,
            Some(2),
            None,
        )
        .await
        .unwrap();
        right
            .start(
                &cfg,
                "dm4",
                Some(30),
                Some("inject_right"),
                None,
                Some(2),
                None,
            )
            .await
            .unwrap();
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let send = |mut ctrl: crate::match_ctrl::MatchCtrl, side: &'static str| async move {
            let mut error = None;
            for index in 0..20 {
                if let Err(e) = ctrl
                    .command(&format!("echo inject_{side}_659_{index}"))
                    .await
                {
                    error = Some(e);
                    break;
                }
            }
            (ctrl, error)
        };
        let ((mut left, left_error), (mut right, right_error)) =
            tokio::join!(send(left, "left"), send(right, "right"));
        // a deadline, not a delay (#836)
        let received = tokio::time::timeout(std::time::Duration::from_secs(20), async {
            loop {
                if left
                    .log_text()
                    .unwrap_or_default()
                    .contains("inject_left_659_19")
                    && right
                        .log_text()
                        .unwrap_or_default()
                        .contains("inject_right_659_19")
                {
                    break;
                }
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            }
        })
        .await;
        let left_log = left.log_text().unwrap_or_default();
        let right_log = right.log_text().unwrap_or_default();
        let (stopped_left, stopped_right) = tokio::join!(
            left.stop(std::time::Duration::from_secs(2)),
            right.stop(std::time::Duration::from_secs(2))
        );
        assert!(stopped_left.is_ok() && stopped_right.is_ok());
        assert!(
            left_error.is_none() && right_error.is_none(),
            "{left_error:?} {right_error:?}"
        );
        assert!(
            received.is_ok(),
            "console marker deadline; left: {} right: {}",
            crate::paths::tail_lines(&left_log, 8).join("\n"),
            crate::paths::tail_lines(&right_log, 8).join("\n")
        );
        for index in 0..20 {
            assert!(left_log.contains(&format!("inject_left_659_{index}")));
            assert!(right_log.contains(&format!("inject_right_659_{index}")));
        }
        assert!(!left_log.contains("inject_right_659_") && !right_log.contains("inject_left_659_"));
        assert_eq!(
            handles(),
            before,
            "console helper changed the parent's standard handles"
        );
    }

    #[test]
    fn port_contract_busy_udp_is_refused_before_engine_spawn() {
        let socket = std::net::UdpSocket::bind("0.0.0.0:0").unwrap();
        let port = socket.local_addr().unwrap().port();
        let temp = crate::test_support::TestDir::new("busy-engine-port").unwrap();
        let mut cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([(
                "ARGUS_ROOT".into(),
                temp.path().display().to_string(),
            )]),
            temp.path(),
        )
        .unwrap();
        cfg.engine = temp.path().join("must-not-spawn.exe");
        let result = super::EngineChild::spawn(
            &cfg,
            "dm4",
            4,
            Some(2),
            temp.path(),
            Some(port),
            false,
            super::EngineClock::Played,
            super::EngineRoster::Standard,
        );
        let error = match result {
            Err(error) => error,
            Ok(_) => panic!("engine started on a busy UDP port"),
        };
        assert!(
            error.contains(&format!("UDP port {port} is unavailable")),
            "{error}"
        );
        drop(socket);
        assert!(super::check_port_available(port).is_ok());
        assert!(super::check_port_available(0).is_err());
    }

    use super::*;

    fn tick_cfg() -> Config {
        let tmp = std::env::temp_dir().join("argus-tick-args");
        Config {
            root: tmp.clone(),
            src: tmp.join("src"),
            progs: tmp.join("lq1/progs.dat"),
            fteqcc: tmp.join("fteqcc.exe"),
            engine: tmp.join("engine.exe"),
            basedir: tmp.join("basedir"),
            python: tmp.join("python.exe"),
            game: "argus".into(),
            maps: tmp.join("maps"),
            runs: tmp.join("runs"),
        }
    }

    #[cfg(windows)]
    #[test]
    fn windows_engines_start_one_priority_class_above_normal() {
        use windows_sys::Win32::System::Threading::{
            ABOVE_NORMAL_PRIORITY_CLASS, CREATE_NEW_CONSOLE, HIGH_PRIORITY_CLASS,
            REALTIME_PRIORITY_CLASS,
        };
        let flags = engine_creation_flags();
        assert_ne!(flags & ABOVE_NORMAL_PRIORITY_CLASS, 0);
        assert_ne!(flags & CREATE_NEW_CONSOLE, 0);
        assert_eq!(flags & (HIGH_PRIORITY_CLASS | REALTIME_PRIORITY_CLASS), 0);
    }

    #[test]
    fn startup_skill_precedes_map_on_both_spawn_paths() {
        let cfg = tick_cfg();
        for skill in 0..=3 {
            for coop in [false, true] {
                let windows = windows_args(
                    &cfg,
                    "dm3",
                    8,
                    Some(skill),
                    None,
                    coop,
                    EngineClock::Played,
                    EngineRoster::Standard,
                )
                .unwrap();
                let mut cmd = Command::new("x");
                apply_args(
                    &mut cmd,
                    &cfg,
                    "dm3",
                    8,
                    Some(skill),
                    None,
                    coop,
                    EngineClock::Played,
                    EngineRoster::Standard,
                );
                let unix = cmd
                    .as_std()
                    .get_args()
                    .map(|s| s.to_string_lossy())
                    .collect::<Vec<_>>()
                    .join(" ");
                for args in [windows, unix] {
                    assert!(
                        args.find(&format!("+skill {skill}")).unwrap()
                            < args.find("+map dm3").unwrap(),
                        "{args}"
                    );
                }
            }
        }
    }

    #[test]
    fn absent_startup_skill_keeps_inherited_configuration() {
        let cfg = tick_cfg();
        let windows = windows_args(
            &cfg,
            "dm3",
            8,
            None,
            None,
            false,
            EngineClock::Played,
            EngineRoster::Standard,
        )
        .unwrap();
        let mut cmd = Command::new("x");
        apply_args(
            &mut cmd,
            &cfg,
            "dm3",
            8,
            None,
            None,
            false,
            EngineClock::Played,
            EngineRoster::Standard,
        );
        let unix = cmd
            .as_std()
            .get_args()
            .map(|s| s.to_string_lossy())
            .collect::<Vec<_>>()
            .join(" ");
        for args in [windows, unix] {
            assert!(!args.contains("+skill"), "{args}");
            assert!(args.contains("+map dm3"), "{args}");
        }
    }

    /// The whole lab is only comparable to a played session if it runs
    /// the same tick. Both spawn paths carry the flag, always.
    #[test]
    #[cfg(not(windows))]
    fn every_unix_launch_pins_the_played_tick_rate() {
        let cfg = tick_cfg();
        let mut cmd = Command::new("x");
        apply_args(
            &mut cmd,
            &cfg,
            "dm4",
            8,
            None,
            None,
            false,
            EngineClock::Played,
            EngineRoster::Standard,
        );
        let joined: Vec<String> = cmd
            .as_std()
            .get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        let joined = joined.join(" ");
        assert!(joined.contains("+sys_ticrate 0.0139"), "{joined}");
    }

    #[test]
    #[cfg(windows)]
    fn every_windows_launch_pins_the_played_tick_rate() {
        let cfg = tick_cfg();
        let args = windows_args(
            &cfg,
            "dm4",
            8,
            None,
            None,
            false,
            EngineClock::Played,
            EngineRoster::Standard,
        )
        .expect("args");
        assert!(args.contains("+sys_ticrate 0.0139"), "{args}");
        let coop = windows_args(
            &cfg,
            "e1m2",
            4,
            Some(1),
            Some(26011),
            true,
            EngineClock::Played,
            EngineRoster::Standard,
        )
        .expect("args");
        assert!(coop.contains("+sys_ticrate 0.0139"), "{coop}");
        assert!(
            coop.contains("-port 26011") && coop.contains("+coop 1"),
            "{coop}"
        );
    }

    #[test]
    fn the_fixed_clock_pins_frame_seed_and_limit_before_the_map() {
        let cfg = tick_cfg();
        let clock = EngineClock::fixed(7).with_limit(Some(185));
        let windows = windows_args(
            &cfg,
            "dm4",
            8,
            Some(2),
            None,
            false,
            clock,
            EngineRoster::Standard,
        )
        .unwrap();
        let mut cmd = Command::new("x");
        apply_args(
            &mut cmd,
            &cfg,
            "dm4",
            8,
            Some(2),
            None,
            false,
            clock,
            EngineRoster::Standard,
        );
        let unix = cmd
            .as_std()
            .get_args()
            .map(|s| s.to_string_lossy())
            .collect::<Vec<_>>()
            .join(" ");
        for args in [windows, unix] {
            for want in [
                "+sys_ticrate 0.001",
                "+host_framerate 0.01425",
                "+host_maxfps 1000",
                "+saved4 7",
                "+timelimit 3.083333",
            ] {
                assert!(args.contains(want), "{want} missing: {args}");
                assert!(args.find(want).unwrap() < args.find("+map dm4").unwrap());
            }
            assert!(!args.contains("+sys_ticrate 0.0139"), "{args}");
        }
        assert_eq!(EngineClock::Played.with_limit(Some(9)), EngineClock::Played);
        assert!(!EngineClock::fixed(1)
            .args()
            .iter()
            .any(|a| a == "+timelimit"));
    }

    #[test]
    fn windows_startup_map_fits_with_long_and_short_game_names() {
        let mut cfg = tick_cfg();
        cfg.engine = r"C:\argus\engine\quakespasm.exe".into();
        cfg.basedir = r"C:\argus\engine".into();
        let clock = EngineClock::fixed(84).with_limit(Some(10));
        for game in ["w697_ctl", "motioncheck_walkway697_ctl4b"] {
            cfg.game = game.into();
            let args = windows_args(
                &cfg,
                "dm4",
                8,
                Some(2),
                None,
                false,
                clock,
                EngineRoster::Standard,
            )
            .unwrap();
            assert!(args.contains(&format!("-game {game}")), "{args}");
            // COM_InitArgv rebuilds cmdline from unquoted argv and keeps 255 bytes.
            let cmdline = args.replace('"', "");
            let visible = &cmdline[..cmdline.len().min(255)];
            assert!(visible.contains("+map dm4"), "{game}: {visible}");
        }
    }

    #[test]
    fn windows_rejects_startup_commands_that_exceed_the_engine_limit() {
        let map = "a".repeat(255);
        let error = windows_args(
            &tick_cfg(),
            &map,
            8,
            Some(2),
            None,
            false,
            EngineClock::Played,
            EngineRoster::Standard,
        )
        .unwrap_err();
        assert!(error.contains("255-byte command limit"), "{error}");
    }

    #[test]
    fn only_benchmark_launches_request_a_solo_roster_before_loading_the_map() {
        let cfg = tick_cfg();
        for roster in [EngineRoster::Standard, EngineRoster::FixedRoute] {
            let windows = windows_args(
                &cfg,
                "e1m8",
                4,
                Some(2),
                None,
                false,
                EngineClock::Played,
                roster,
            )
            .unwrap();
            let mut cmd = Command::new("x");
            apply_args(
                &mut cmd,
                &cfg,
                "e1m8",
                4,
                Some(2),
                None,
                false,
                EngineClock::Played,
                roster,
            );
            let unix = cmd
                .as_std()
                .get_args()
                .map(|arg| arg.to_string_lossy())
                .collect::<Vec<_>>()
                .join(" ");
            for args in [windows, unix] {
                match roster {
                    EngineRoster::Standard => assert!(!args.contains("+scratch1"), "{args}"),
                    EngineRoster::FixedRoute => {
                        assert!(args.contains("+scratch1 3843 +map e1m8"), "{args}")
                    }
                }
            }
        }
    }

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
    // The raw process is deliberately transferred to EngineChild by PID and
    // native handle; EngineChild's Drop is the behavior this test exercises.
    #[allow(clippy::zombie_processes)]
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
                windows_sys::Win32::System::Threading::GetExitCodeProcess(
                    check_handle,
                    &mut exit_code,
                );
                windows_sys::Win32::Foundation::CloseHandle(check_handle);
            }
            assert_ne!(
                exit_code, 259,
                "process should have been terminated on drop"
            );
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
    // The process-global lock intentionally spans the live-engine awaits so
    // no other integration test can bind or inject into the same engine.
    #[allow(clippy::await_holding_lock)]
    async fn windows_console_inject_reaches_the_engine_if_present() {
        if !cfg!(windows) {
            return;
        }
        // a panic in another engine test poisons the lock; recover so
        // one failure cannot cascade through the whole engine suite
        let _gate = crate::engine::ENGINE_TEST_LOCK
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        // Real matches write the process-wide live-match state that the
        // fake-match server tests assert on, so hold their lock too.
        let _live = crate::match_ctrl::live_test_lock_async().await;
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let Ok(mut cfg) = crate::config::load_for_reads_from(&env, &root) else {
            return;
        };
        if !cfg.engine.exists() {
            eprintln!("SKIPPED probe_inject_test: no ARGUS_ENGINE on this box");
            return;
        }
        // a temp runs/ so the probe tape never lands in the real one:
        // resolve_latest picks the newest runs/*.log, and a 7 s test
        // tape became what "latest" meant for the next compare
        // TestDir removes it on drop, so a pass, a failure and a panic all
        // leave %TEMP% as they found it (#861)
        let tmp_runs = crate::test_support::TestDir::new("probe_inject_test")
            .expect("create the probe's temp runs dir");
        cfg.runs = tmp_runs.path().to_path_buf();
        // its own port: the default 26000 belongs to whatever ladder is
        // running, and an engine that binds a busy port starts happily
        // and then answers nothing, so this test failed as a port race
        // rather than as a statement about console injection
        let mut ctrl = crate::match_ctrl::MatchCtrl::on_port(26019);
        if ctrl
            .start(
                &cfg,
                "dm4",
                Some(30),
                Some("probe_inject_test"),
                None,
                Some(1),
                None,
            )
            .await
            .is_err()
        {
            eprintln!("SKIPPED probe_inject_test: engine refused to start (port in use?)");
            return; // engine present but refused (port in use): not this test's fault
        }
        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
        let inject = ctrl.command("status").await;
        // wait for the reply with a deadline rather than a fixed 2 s (#836)
        let _ = tokio::time::timeout(std::time::Duration::from_secs(20), async {
            loop {
                let log = ctrl.log_text().unwrap_or_default();
                if log.contains("host:") || log.contains("players:") {
                    break;
                }
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            }
        })
        .await;
        let log = ctrl.log_text().unwrap_or_default();
        let _ = ctrl.stop(std::time::Duration::from_secs(3)).await;
        inject.expect("console inject must not error");
        assert!(
            log.contains("host:") || log.contains("players:"),
            "status output must reach the log; tail: {}",
            log.chars()
                .rev()
                .take(400)
                .collect::<String>()
                .chars()
                .rev()
                .collect::<String>()
        );
    }
}
