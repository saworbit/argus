use crate::config::Config;
use crate::parse_fteqcc::{parse_fteqcc, FteqccReport};
use serde::Serialize;
use std::fs;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct CompileResult {
    pub ok: bool,
    pub success_line: Option<String>,
    pub diagnostics: Vec<crate::parse_fteqcc::Diagnostic>,
    pub raw_tail: Vec<String>,
    pub progs_bytes: Option<u64>,
    pub installed_to: Vec<String>,
    pub new_errors: usize,
    pub new_warnings: usize,
    pub noise_warnings: usize,
}

/// Extra tool: compile a given source directory. Does not install unless
/// `install` is true (the native `compile_qc` still owns the lab copy).
pub fn compile_qc_dir(cfg: &Config, src: &std::path::Path, install: bool) -> CompileResult {
    let mut tmp = cfg.clone();
    tmp.src = src.to_path_buf();
    if let Some(parent) = src.parent() {
        tmp.progs = parent.join("lq1").join("progs.dat");
    }
    compile_qc(&tmp, install)
}

/// One compile at a time. compile_qc unlinks cfg.progs before it spawns
/// fteqcc and installs from it afterwards, and rmcp runs tool calls
/// concurrently: two overlapping compiles ran two fteqccs in the same
/// src/, and the second's unlink could delete the first's freshly
/// written progs.dat between the write and the install copy. Either a
/// spurious "no progs.dat written" or the wrong bytes installed under a
/// green report, both silent. Covers the CLI paths (ship, cycle, soak)
/// too, since they all land here.
static COMPILE_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

pub fn compile_qc(cfg: &Config, install: bool) -> CompileResult {
    let _serialised = COMPILE_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    if let Err(e) = fs::create_dir_all(cfg.root.join("lq1")) {
        return CompileResult {
            ok: false,
            success_line: None,
            diagnostics: Vec::new(),
            raw_tail: vec![format!("could not create lq1/: {e}")],
            progs_bytes: None,
            installed_to: Vec::new(),
            new_errors: 0,
            new_warnings: 0,
            noise_warnings: 0,
        };
    }

    // Unlink old progs.dat before compiling so a failed compile never leaves
    // or re-installs a stale binary from a previous run.
    if cfg.progs.exists() {
        let _ = fs::remove_file(&cfg.progs);
    }
    let start_time = std::time::SystemTime::now();

    let mut cmd = Command::new(&cfg.fteqcc);
    cmd.current_dir(&cfg.src)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return CompileResult {
                ok: false,
                success_line: None,
                diagnostics: Vec::new(),
                raw_tail: vec![format!("failed to spawn ARGUS_FTEQCC: {e}")],
                progs_bytes: None,
                installed_to: Vec::new(),
                new_errors: 0,
                new_warnings: 0,
                noise_warnings: 0,
            };
        }
    };

    let stdout_reader = child.stdout.take().map(|mut r| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            let _ = std::io::Read::read_to_end(&mut r, &mut buf);
            buf
        })
    });
    let stderr_reader = child.stderr.take().map(|mut r| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            let _ = std::io::Read::read_to_end(&mut r, &mut buf);
            buf
        })
    });

    let timeout = std::time::Duration::from_secs(90);
    let poll_start = std::time::Instant::now();
    let mut timed_out = false;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => {
                if poll_start.elapsed() >= timeout {
                    timed_out = true;
                    let _ = child.kill();
                    let _ = child.wait();
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return CompileResult {
                    ok: false,
                    success_line: None,
                    diagnostics: Vec::new(),
                    raw_tail: vec![format!("failed waiting for fteqcc: {e}")],
                    progs_bytes: None,
                    installed_to: Vec::new(),
                    new_errors: 0,
                    new_warnings: 0,
                    noise_warnings: 0,
                };
            }
        }
    }

    let out_bytes = stdout_reader.and_then(|h| h.join().ok()).unwrap_or_default();
    let err_bytes = stderr_reader.and_then(|h| h.join().ok()).unwrap_or_default();

    if timed_out {
        return CompileResult {
            ok: false,
            success_line: None,
            diagnostics: Vec::new(),
            raw_tail: vec!["compile_qc timed out after 90s (fteqcc hung or src/ is huge)".to_string()],
            progs_bytes: None,
            installed_to: Vec::new(),
            new_errors: 1,
            new_warnings: 0,
            noise_warnings: 0,
        };
    }

    let mut text = String::new();
    text.push_str(&String::from_utf8_lossy(&out_bytes));
    if !err_bytes.is_empty() {
        text.push('\n');
        text.push_str(&String::from_utf8_lossy(&err_bytes));
    }
    let mut report = parse_fteqcc(&text);
    if report.ok {
        let freshly_written = match fs::metadata(&cfg.progs) {
            Ok(m) => {
                if let Ok(mod_time) = m.modified() {
                    mod_time + std::time::Duration::from_secs(2) >= start_time
                } else {
                    true
                }
            }
            Err(_) => false,
        };
        if !freshly_written {
            report.ok = false;
            report.raw_tail.push("fteqcc reported success line but progs.dat was not written".into());
        }
    }
    finish(cfg, install, report)
}

fn finish(cfg: &Config, install: bool, report: FteqccReport) -> CompileResult {
    let mut installed_to = Vec::new();
    let mut progs_bytes = None;
    let new_errors = report
        .diagnostics
        .iter()
        .filter(|d| d.severity == "error")
        .count();
    let noise_warnings = report
        .diagnostics
        .iter()
        .filter(|d| d.severity == "warning" && d.noise)
        .count();
    let new_warnings = report
        .diagnostics
        .iter()
        .filter(|d| d.severity == "warning" && !d.noise)
        .count();
    if report.ok {
        if let Ok(meta) = fs::metadata(&cfg.progs) {
            progs_bytes = Some(meta.len());
        }
        if install {
            for dest in cfg.install_paths() {
                if let Some(parent) = dest.parent() {
                    let _ = fs::create_dir_all(parent);
                }
                match fs::copy(&cfg.progs, &dest) {
                    Ok(_) => installed_to.push(dest.display().to_string()),
                    Err(e) => {
                        return CompileResult {
                            ok: false,
                            success_line: report.success_line,
                            diagnostics: report.diagnostics,
                            raw_tail: {
                                let mut t = report.raw_tail;
                                t.push(format!("copy to {} failed: {e}", dest.display()));
                                t
                            },
                            progs_bytes,
                            installed_to,
                            new_errors,
                            new_warnings,
                            noise_warnings,
                        };
                    }
                }
            }
        }
    }
    CompileResult {
        ok: report.ok,
        success_line: report.success_line,
        diagnostics: report.diagnostics,
        raw_tail: report.raw_tail,
        progs_bytes,
        installed_to,
        new_errors,
        new_warnings,
        noise_warnings,
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    #[test]
    fn unwritten_progs_fails_and_never_installs() {
        let tmp = std::env::temp_dir().join(format!("argus-compile-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&tmp);
        fs::create_dir_all(tmp.join("lq1")).unwrap();
        fs::create_dir_all(tmp.join("install")).unwrap();

        let cfg = crate::config::Config {
            root: tmp.clone(),
            src: tmp.join("src"),
            progs: tmp.join("lq1/progs.dat"),
            fteqcc: tmp.join("fteqcc.exe"),
            engine: tmp.join("engine.exe"),
            basedir: tmp.join("basedir"),
            python: tmp.join("python.exe"),
            game: "id1".into(),
            maps: tmp.join("maps"),
            runs: tmp.join("runs"),
        };

        // If report claims ok but cfg.progs does not exist, finish should not copy
        let report = crate::parse_fteqcc::FteqccReport {
            ok: false, // flagged false by compile_qc when file wasn't written
            success_line: Some("Compile finished".into()),
            diagnostics: Vec::new(),
            raw_tail: vec!["fteqcc reported success line but progs.dat was not written".into()],
        };
        let result = super::finish(&cfg, true, report);
        assert!(!result.ok);
        assert!(result.installed_to.is_empty());
        assert!(!tmp.join("install/progs.dat").exists());

        let _ = fs::remove_dir_all(&tmp);
    }
}
