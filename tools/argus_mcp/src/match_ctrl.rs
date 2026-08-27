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

    pub async fn shutdown(&mut self) {
        let _ = self.stop(Duration::from_secs(2)).await;
        if let Some(mut live) = self.live.take() {
            let _ = live.child.kill().await;
        }
    }
}

fn format_match_fail(log_path: &str, text: &str, why: &str) -> String {
    let tail = tail_nonempty(text, 8);
    let tail_s = if tail.is_empty() {
        String::new()
    } else {
        format!(" tail: {}", tail.join(" | "))
    };
    format!(
        "match produced no ARGLOG ({} is {} bytes). {why}.{tail_s}",
        log_path,
        text.len()
    )
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
    let Some(p) = st.log_path.as_deref() else {
        return;
    };
    let path = PathBuf::from(p);
    let mut text = if path.is_file() {
        std::fs::read_to_string(&path).ok()
    } else {
        None
    };
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
    let _ = std::fs::write(&live.harvested, &body);
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
