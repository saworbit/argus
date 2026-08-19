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

pub fn compile_qc(cfg: &Config, install: bool) -> CompileResult {
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

    let output = match Command::new(&cfg.fteqcc)
        .current_dir(&cfg.src)
        .output()
    {
        Ok(o) => o,
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

    let mut text = String::new();
    text.push_str(&String::from_utf8_lossy(&output.stdout));
    if !output.stderr.is_empty() {
        text.push('\n');
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }
    let report = parse_fteqcc(&text);
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

pub fn should_not_copy_on_failure(report: &FteqccReport) -> bool {
    !report.ok
}

#[cfg(test)]
mod tests {
    use crate::parse_fteqcc::parse_fteqcc;
    use std::fs;
    use std::path::PathBuf;

    #[test]
    fn failure_report_means_no_install() {
        let text = fs::read_to_string(
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/compile_fail.txt"),
        )
        .unwrap();
        let report = parse_fteqcc(&text);
        assert!(!report.ok);
        assert!(super::should_not_copy_on_failure(&report));
    }
}
