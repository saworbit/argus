use crate::config::Config;
use crate::diagnose::{diagnose_log, log_has_tape, tail_nonempty};
use crate::engine::{validate_map, EngineChild};
use crate::intel::{brief_text, brief_text_hull, MatchBrief};
use crate::parse_arglog::{parse_arglog, MatchSummary};
use crate::paths::{default_run_name, valid_run_name};
use serde::Serialize;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

pub const DURATION_MIN: u32 = 10;
pub const DURATION_MAX: u32 = 600;

#[derive(Debug, Clone, Serialize)]
pub struct MatchStatus {
    pub running: bool,
    pub run_name: Option<String>,
    pub map: Option<String>,
    pub pid: Option<u32>,
    pub elapsed_sec: Option<u64>,
    pub remaining_sec: Option<u64>,
    pub log_path: Option<String>,
    pub recent_lines: Vec<String>,
    #[serde(default)]
    pub next_line: u32,
    pub exit_code: Option<i32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub live_headline: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub next_steps: Option<Vec<crate::intel::NextStep>>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MatchRunResult {
    pub ok: bool,
    pub run_name: String,
    pub map: String,
    pub log_path: String,
    pub elapsed_sec: u64,
    pub exit_code: Option<i32>,
    pub summary: MatchSummary,
    pub brief: MatchBrief,
}

struct LiveMatch {
    child: EngineChild,
    run_name: String,
    map: String,
    run_dir: PathBuf,
    harvested: PathBuf,
    started: Instant,
    duration: Option<Duration>,
    stdout: Arc<Mutex<String>>,
    last_exit: Option<i32>,
}

#[derive(Default)]
pub struct MatchCtrl {
    live: Option<LiveMatch>,
    last: Option<MatchStatus>,
    /// engine UDP port override, so two controllers can run two
    /// dedicated children side by side (the 2026-08-18 paired-run
    /// forensics proved the engines coexist on 26010/26011)
    port: Option<u32>,
}

impl MatchCtrl {
    /// A controller bound to its own engine port, for parallel work.
    pub fn on_port(port: u32) -> Self {
        MatchCtrl { port: Some(port), ..Default::default() }
    }

    /// Reap a dead child so the next start is not blocked by a zombie slot.
    pub fn reap(&mut self) {
        let _ = self.status();
    }

    pub fn status(&mut self) -> MatchStatus {
        self.status_since(None)
    }

    pub fn status_since(&mut self, since_line: Option<u32>) -> MatchStatus {
        if let Some(live) = self.live.as_mut() {
            match live.child.try_wait() {
                Ok(Some(code)) => {
                    live.last_exit = Some(code);
                    let harvested = harvest(live);
                    let (recent, next_line) = recent_lines_since(live, since_line);
                    let elapsed = live.started.elapsed().as_secs();
                    let mut snap = MatchStatus {
                        running: false,
                        run_name: Some(live.run_name.clone()),
                        map: Some(live.map.clone()),
                        pid: None,
                        elapsed_sec: Some(elapsed),
                        remaining_sec: None,
                        log_path: Some(harvested),
                        recent_lines: recent,
                        next_line,
                        exit_code: live.last_exit,
                        live_headline: None,
                        next_steps: None,
                    };
                    decorate_status(&mut snap);
                    self.last = Some(snap.clone());
                    self.live = None;
                    return snap;
                }
                Ok(None) => {}
                Err(_) => {}
            }
            let elapsed = live.started.elapsed();
            let remaining = live.duration.map(|d| d.saturating_sub(elapsed).as_secs());
            let (recent, next_line) = recent_lines_since(live, since_line);
            let mut snap = MatchStatus {
                running: true,
                run_name: Some(live.run_name.clone()),
                map: Some(live.map.clone()),
                pid: Some(live.child.id()),
                elapsed_sec: Some(elapsed.as_secs()),
                remaining_sec: remaining,
                log_path: Some(live.harvested.display().to_string()),
                recent_lines: recent,
                next_line,
                exit_code: None,
                live_headline: None,
                next_steps: None,
            };
            decorate_status(&mut snap);
            return snap;
        }
        self.last.clone().unwrap_or(MatchStatus {
            running: false,
            run_name: None,
            map: None,
            pid: None,
            elapsed_sec: None,
            remaining_sec: None,
            log_path: None,
            recent_lines: Vec::new(),
            next_line: 0,
            exit_code: None,
            live_headline: None,
            next_steps: None,
        })
    }

    pub async fn start(
        &mut self,
        cfg: &Config,
        map: &str,
        duration_sec: Option<u32>,
        run_name: Option<&str>,
        dedicated_slots: Option<u32>,
        skill: Option<u32>,
    ) -> Result<MatchStatus, String> {
        self.reap();
        if self.live.is_some() {
            let name = self
                .live
                .as_ref()
                .map(|l| l.run_name.clone())
                .unwrap_or_default();
            return Err(format!(
                "match already running: {name}. match_stop first, or wait."
            ));
        }
        validate_map(map)?;
        if let Some(msg) = unharvested_session(cfg) {
            return Err(msg);
        }
        if let Some(d) = duration_sec {
            if !(DURATION_MIN..=DURATION_MAX).contains(&d) {
                return Err(format!(
                    "duration_sec must be {DURATION_MIN}..={DURATION_MAX}"
                ));
            }
        }
        if let Some(s) = skill {
            if s > 3 {
                return Err("skill must be 0..3".into());
            }
        }
        let name = match run_name {
            Some(n) => {
                if !valid_run_name(n) {
                    return Err(
                        "run_name must match [A-Za-z0-9._-]+ and contain no path separators"
                            .into(),
                    );
                }
                n.to_string()
            }
            None => default_run_name(),
        };
        let slots = dedicated_slots.unwrap_or(8);
        let run_dir = cfg.runs.join(&name);
        std::fs::create_dir_all(&run_dir).map_err(|e| format!("create run dir: {e}"))?;
        let harvested = cfg.runs.join(format!("{name}.log"));

        let child = EngineChild::spawn(cfg, map, slots, skill, &run_dir, self.port)?;
        let stdout = child.stdout_buf();
        self.live = Some(LiveMatch {
            child,
            run_name: name,
            map: map.to_string(),
            run_dir,
            harvested,
            started: Instant::now(),
            duration: duration_sec.map(|s| Duration::from_secs(s as u64)),
            stdout,
            last_exit: None,
        });
        Ok(self.status())
    }

    pub async fn command(&mut self, line: &str) -> Result<(), String> {
        let live = self.live.as_mut().ok_or("no match is running")?;
        live.child.write_line(line).await
    }

    pub async fn stop(&mut self, timeout: Duration) -> Result<MatchStatus, String> {
        if self.live.is_none() {
            return Ok(self.status());
        }
        if let Some(live) = self.live.as_mut() {
            if live.child.has_stdin() {
                let _ = live.child.write_line("quit").await;
            }
        }
        let deadline = Instant::now() + timeout;
        loop {
            if let Some(live) = self.live.as_mut() {
                match live.child.try_wait() {
                    Ok(Some(code)) => {
                        live.last_exit = Some(code);
                        break;
                    }
                    Ok(None) if Instant::now() >= deadline => {
                        let _ = live.child.kill().await;
                        // one more wait so harvest sees a settled log
                        tokio::time::sleep(Duration::from_millis(200)).await;
                        if let Ok(Some(code)) = live.child.try_wait() {
                            live.last_exit = Some(code);
                        } else {
                            live.last_exit = Some(1);
                        }
                        break;
                    }
                    Ok(None) => {
                        tokio::time::sleep(Duration::from_millis(100)).await;
                    }
                    Err(e) => return Err(e),
                }
            } else {
                break;
            }
        }
        Ok(self.status())
    }

    pub async fn stop_matching(
        &mut self,
        run_name: Option<&str>,
        pid: Option<u32>,
        timeout: Duration,
    ) -> Result<MatchStatus, String> {
        if let Some(live) = &self.live {
            if let Some(r) = run_name {
                if live.run_name != r {
                    return Ok(self.status());
                }
            }
            if let Some(p) = pid {
                if live.child.id() != p {
                    return Ok(self.status());
                }
            }
        } else {
            return Ok(self.status());
        }
        self.stop(timeout).await
    }

    pub fn log_text(&self) -> Option<String> {
        if let Some(live) = &self.live {
            let q = live.run_dir.join("qconsole.log");
            if q.is_file() {
                if let Ok(t) = std::fs::read_to_string(q) {
                    if !t.trim().is_empty() {
                        return Some(t);
                    }
                }
            }
            return live.stdout.try_lock().ok().map(|g| g.clone());
        }
        if let Some(st) = &self.last {
            if let Some(p) = &st.log_path {
                let path = PathBuf::from(p);
                if path.is_file() {
                    return std::fs::read_to_string(path).ok();
                }
            }
        }
        None
    }

    pub async fn run(
        &mut self,
        cfg: &Config,
        map: &str,
        duration_sec: u32,
        run_name: Option<&str>,
        dedicated_slots: Option<u32>,
        skill: Option<u32>,
    ) -> Result<MatchRunResult, String> {
        self.start(cfg, map, Some(duration_sec), run_name, dedicated_slots, skill)
            .await?;
        // (start() runs the un-harvested-session guard)
        if let Err(e) = self.await_healthy(Duration::from_secs(10)).await {
            let _ = self.stop(Duration::from_secs(2)).await;
            return Err(e);
        }
        let limit = Duration::from_secs(duration_sec as u64);
        loop {
            let st = self.status();
            if !st.running {
                break;
            }
            if st.elapsed_sec.unwrap_or(0) >= limit.as_secs() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
        let st = self.stop(Duration::from_secs(5)).await?;
        // qconsole.log can lag a tick after TerminateProcess
        tokio::time::sleep(Duration::from_millis(250)).await;
        let log_path = st.log_path.clone().unwrap_or_default();
        let text = read_log_retry(&log_path, 6);
        if let Some(why) = diagnose_log(&text) {
            if !log_has_tape(&text) {
                return Err(format_match_fail(&log_path, &text, &why));
            }
        }
        if !log_has_tape(&text) {
            let why = diagnose_log(&text)
                .unwrap_or_else(|| "server may have died at spawn".into());
            return Err(format_match_fail(&log_path, &text, &why));
        }
        Ok(MatchRunResult {
            ok: true,
            run_name: st.run_name.unwrap_or_default(),
            map: map.to_string(),
            log_path,
            elapsed_sec: st.elapsed_sec.unwrap_or(0),
            exit_code: st.exit_code,
            summary: parse_arglog(&text),
            brief: brief_text_hull(cfg, &text, Some(map)),
        })
    }

    /// Fail fast if the dedicated child dies before the first ARGLOG.
    ///
    /// Every error return kills the child first: `running` can read
    /// false while a hung engine process is still alive (observed
    /// 2026-08-27, a startup-hung quakespasm survived the "exited
    /// before ARGLOG" error and held port 26000, failing every later
    /// match until it was killed by hand). An abandoned match must
    /// never leave a child behind.
    async fn await_healthy(&mut self, budget: Duration) -> Result<(), String> {
        let deadline = Instant::now() + budget;
        loop {
            let st = self.status();
            if let Some(text) = self.log_text() {
                if log_has_tape(&text) {
                    return Ok(());
                }
                if let Some(why) = diagnose_log(&text) {
                    if !st.running {
                        self.kill_live().await;
                        return Err(format_match_fail(
                            st.log_path.as_deref().unwrap_or(""),
                            &text,
                            &why,
                        ));
                    }
                }
            }
            if !st.running {
                let text = self.log_text().unwrap_or_default();
                let why = diagnose_log(&text)
                    .unwrap_or_else(|| "dedicated child exited before ARGLOG".into());
                self.kill_live().await;
                return Err(format_match_fail(
                    st.log_path.as_deref().unwrap_or(""),
                    &text,
                    &why,
                ));
            }
            if Instant::now() >= deadline {
                // still running, no tape yet: let the timed run continue
                return Ok(());
            }
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    }

    /// Kill the live child outright, if any. The error paths use this
    /// so an abandoned match never orphans an engine on the port.
    async fn kill_live(&mut self) {
        if let Some(mut live) = self.live.take() {
            let _ = live.child.kill().await;
            let harvested = harvest(&live);
            let elapsed = live.started.elapsed().as_secs();
            let mut snap = MatchStatus {
                running: false,
                run_name: Some(live.run_name.clone()),
                map: Some(live.map.clone()),
                pid: None,
                elapsed_sec: Some(elapsed),
                remaining_sec: None,
                log_path: Some(harvested),
                recent_lines: Vec::new(),
                next_line: 0,
                exit_code: live.last_exit.or(Some(1)),
                live_headline: None,
                next_steps: None,
            };
            decorate_status(&mut snap);
            self.last = Some(snap);
        }
    }

    pub async fn shutdown(&mut self) {
        let _ = self.stop(Duration::from_secs(2)).await;
        self.kill_live().await;
    }
}

fn format_match_fail(log_path: &str, text: &str, why: &str) -> String {
    let tail = tail_nonempty(text, 8);
    let tail_s = if tail.is_empty() {
        String::new()
    } else {
        format!(" tail: {}", tail.join(" | "))
    };
    format!("{why}; tape at {log_path}.{tail_s}")
}

fn read_log_retry(path: &str, attempts: u32) -> String {
    for i in 0..attempts {
        if let Ok(t) = std::fs::read_to_string(path) {
            if log_has_tape(&t) || i + 1 == attempts {
                return t;
            }
        }
        std::thread::sleep(Duration::from_millis(120));
    }
    String::new()
}

fn decorate_status(st: &mut MatchStatus) {
    let Some(path_s) = &st.log_path else {
        return;
    };
    let path = PathBuf::from(path_s);
    let mut text = std::fs::read_to_string(&path).ok();
    if text.as_ref().map(|t| t.trim().is_empty()).unwrap_or(true) {
        if let (Some(parent), Some(stem)) = (path.parent(), path.file_stem()) {
            let q = parent.join(stem).join("qconsole.log");
            if q.is_file() {
                text = std::fs::read_to_string(q).ok();
            }
        }
    }
    let Some(text) = text else {
        return;
    };
    if !log_has_tape(&text) {
        return;
    }
    let brief = brief_text(&text, st.map.as_deref());
    st.live_headline = Some(brief.headline);
    if !brief.next_steps.is_empty() {
        st.next_steps = Some(brief.next_steps);
    }
}

fn harvest(live: &LiveMatch) -> String {
    let qconsole = live.run_dir.join("qconsole.log");
    let mut body = if qconsole.exists() {
        std::fs::read_to_string(&qconsole).unwrap_or_default()
    } else {
        String::new()
    };
    if body.trim().is_empty() {
        if let Ok(g) = live.stdout.try_lock() {
            if !g.is_empty() {
                body = g.clone();
            }
        }
    }

    let existing_has_tape = if live.harvested.is_file() {
        std::fs::read_to_string(&live.harvested)
            .map(|t| log_has_tape(&t))
            .unwrap_or(false)
    } else {
        false
    };

    let new_has_tape = log_has_tape(&body);

    // If an existing log already has a valid tape and the new body does not,
    // do not clobber the valid tape! Preserve the existing good tape.
    if existing_has_tape && !new_has_tape {
        if !body.trim().is_empty() {
            let fail_path = live.run_dir.join("failed_harvest.log");
            let _ = std::fs::write(&fail_path, &body);
        }
        return live.harvested.display().to_string();
    }

    // Do not write an empty body if the harvested file doesn't need to be created empty
    if !body.trim().is_empty() || !live.harvested.exists() {
        if let Err(e) = std::fs::write(&live.harvested, &body) {
            eprintln!("failed to write harvest log {}: {e}", live.harvested.display());
        }
    }

    live.harvested.display().to_string()
}

fn recent_lines_since(live: &LiveMatch, since_line: Option<u32>) -> (Vec<String>, u32) {
    let qconsole = live.run_dir.join("qconsole.log");
    let mut text = std::fs::read_to_string(&qconsole).unwrap_or_default();
    if text.trim().is_empty() {
        if let Ok(g) = live.stdout.try_lock() {
            text = g.clone();
        }
    }
    let all: Vec<&str> = text.lines().collect();
    let total = all.len() as u32;
    match since_line {
        None | Some(0) => {
            let start = all.len().saturating_sub(40);
            (
                all[start..].iter().map(|s| (*s).to_string()).collect(),
                total,
            )
        }
        Some(n) => {
            let start = (n as usize).min(all.len());
            let end = (start + 80).min(all.len());
            (
                all[start..end].iter().map(|s| (*s).to_string()).collect(),
                end as u32,
            )
        }
    }
}

pub fn list_runs(cfg: &Config) -> Result<Vec<RunEntry>, String> {
    let mut entries = Vec::new();
    let rd = std::fs::read_dir(&cfg.runs).map_err(|e| format!("ARGUS_RUNS: {e}"))?;
    for ent in rd.flatten() {
        let path = ent.path();
        if path.extension().and_then(|s| s.to_str()) != Some("log") {
            continue;
        }
        if !path.is_file() {
            continue;
        }
        let meta = ent.metadata().ok();
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or_default()
            .to_string();
        let note = crate::intel::known_log_note(&name).map(|s| s.to_string());
        entries.push(RunEntry {
            name,
            path: path.display().to_string(),
            bytes: meta.as_ref().map(|m| m.len()).unwrap_or(0),
            mtime_unix: meta
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs()),
            note,
        });
    }
    entries.sort_by(|a, b| b.mtime_unix.cmp(&a.mtime_unix));
    Ok(entries)
}

#[derive(Debug, Clone, Serialize)]
pub struct RunEntry {
    pub name: String,
    pub path: String,
    pub bytes: u64,
    pub mtime_unix: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// The harvest-first ritual, enforced structurally: a play session
/// leaves qconsole.log in a launch directory and session demos in
/// the game dir, and the NEXT engine launch truncates the former (a
/// lab capture once clobbered a session tape this way - it was
/// already archived, by luck). Since 2026-08-27 the harvester MOVES
/// its inputs, so any leftover means an un-harvested session and
/// every match starter refuses until it is harvested or deleted.
pub fn unharvested_session(cfg: &Config) -> Option<String> {
    let mut hits: Vec<String> = Vec::new();
    for p in [cfg.root.join("qconsole.log"), cfg.basedir.join("qconsole.log")] {
        if let Ok(text) = std::fs::read_to_string(&p) {
            if text.contains("SpawnServer:") {
                hits.push(p.display().to_string());
            }
        }
    }
    let gamedir = cfg.basedir.join(&cfg.game);
    if let Ok(rd) = std::fs::read_dir(&gamedir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.extension().map(|x| x == "dem").unwrap_or(false) {
                hits.push(p.display().to_string());
            }
        }
    }
    if hits.is_empty() {
        None
    } else {
        Some(format!(
            "un-harvested play session in the launch dirs: {}. Run `python tools/harvest_session.py --tag vNNN` FIRST (a new engine launch truncates qconsole.log), or delete the leftovers if they are worthless.",
            hits.join(", ")
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn harvest_preserves_existing_tape_when_new_body_empty_or_tapeless() {
        let tmp = std::env::temp_dir().join(format!("argus-harvest-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(&tmp).unwrap();

        let harvested_path = tmp.join("exp_dm4.log");
        let valid_tape = "Quake 1.09\nARGLOG 100 0.1 1.0\nARGEVT 1.0 \"bot1 goal quad\"\nARGEVT 20.0 match_end\n";
        std::fs::write(&harvested_path, valid_tape).unwrap();

        let run_dir = tmp.join("exp_dm4");
        std::fs::create_dir_all(&run_dir).unwrap();
        std::fs::write(run_dir.join("qconsole.log"), "Engine crashed or empty output\n").unwrap();

        let live = LiveMatch {
            child: EngineChild::mock(),
            run_name: "exp_dm4".into(),
            map: "dm4".into(),
            run_dir: run_dir.clone(),
            harvested: harvested_path.clone(),
            started: Instant::now(),
            duration: None,
            stdout: Arc::new(Mutex::new(String::new())),
            last_exit: None,
        };

        let result_path = harvest(&live);
        assert_eq!(result_path, harvested_path.display().to_string());

        // Verify the valid tape was preserved intact
        let content = std::fs::read_to_string(&harvested_path).unwrap();
        assert_eq!(content, valid_tape, "harvest must NOT overwrite valid ARGLOG tape with empty/failed output");

        // Verify failure was saved aside
        let fail_path = run_dir.join("failed_harvest.log");
        assert!(fail_path.is_file(), "failed output should be saved to failed_harvest.log");

        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[tokio::test]
    async fn stop_matching_filters_by_run_name_and_pid() {
        let tmp = std::env::temp_dir().join(format!("argus-stop-match-test-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(tmp.join("exp_dm4")).unwrap();

        let run_dir = tmp.join("exp_dm4");
        let harvested = tmp.join("exp_dm4.log");

        #[cfg(windows)]
        let child = {
            let mut cmd = std::process::Command::new("powershell");
            cmd.args(["-NoProfile", "-Command", "Start-Sleep -Seconds 10"]);
            let child = cmd.spawn().expect("spawn powershell");
            let pid = child.id();
            const SYNCHRONIZE: u32 = 0x00100000;
            let handle = unsafe {
                windows_sys::Win32::System::Threading::OpenProcess(
                    windows_sys::Win32::System::Threading::PROCESS_TERMINATE
                        | windows_sys::Win32::System::Threading::PROCESS_QUERY_LIMITED_INFORMATION
                        | SYNCHRONIZE,
                    0,
                    pid,
                )
            };
            EngineChild::from_raw(handle, pid)
        };

        #[cfg(not(windows))]
        let child = EngineChild::mock();

        let live_pid = child.id();
        let mut ctrl = MatchCtrl::default();
        ctrl.live = Some(LiveMatch {
            child,
            run_name: "exp_dm4".into(),
            map: "dm4".into(),
            run_dir,
            harvested,
            started: Instant::now(),
            duration: None,
            stdout: Arc::new(Mutex::new(String::new())),
            last_exit: None,
        });

        // Mismatched run_name does not stop
        let st1 = ctrl.stop_matching(Some("exp_other"), None, Duration::from_millis(50)).await.unwrap();
        assert!(st1.running, "mismatched run_name must not stop live match");
        assert!(ctrl.live.is_some());

        // Mismatched pid does not stop
        let st2 = ctrl.stop_matching(None, Some(live_pid + 1000), Duration::from_millis(50)).await.unwrap();
        assert!(st2.running, "mismatched pid must not stop live match");
        assert!(ctrl.live.is_some());

        // Matching run_name stops the match
        let st3 = ctrl.stop_matching(Some("exp_dm4"), None, Duration::from_millis(500)).await.unwrap();
        assert!(!st3.running, "matching run_name must stop the match");
        assert!(ctrl.live.is_none());

        let _ = std::fs::remove_dir_all(&tmp);
    }
}
