use crate::config::Config;
use crate::intel::{brief_path, compare_briefs, CompareReport, MatchBrief};
use crate::parse_arglog::{parse_arglog_path, MatchSummary};
use crate::paths::{resolve_input, resolve_log, resolve_output, tail_lines};
use serde::Serialize;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct AnalyzeResult {
    pub ok: bool,
    pub out_png: String,
    pub log_a: MatchSummary,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub log_b: Option<MatchSummary>,
    pub brief_a: MatchBrief,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub brief_b: Option<MatchBrief>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub compare: Option<CompareReport>,
    pub stdout_tail: Vec<String>,
}

pub fn analyze_match(
    cfg: &Config,
    bsp: &str,
    log_a: &str,
    out_png: &str,
    log_b: Option<&str>,
    nav_json: Option<&str>,
) -> Result<AnalyzeResult, String> {
    let bsp_path = resolve_input(cfg, bsp)?;
    let log_a_path = resolve_log(cfg, log_a)?;
    let out_png_path = resolve_output(cfg, out_png);
    if let Some(parent) = out_png_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let log_b_path = match log_b {
        Some(p) => Some(resolve_log(cfg, p)?),
        None => None,
    };
    let nav_path = match nav_json {
        Some(p) => Some(resolve_input(cfg, p)?),
        None => None,
    };

    let script = cfg.analyze_script();
    if !script.exists() {
        return Err(format!(
            "ARGUS_ROOT tools/analyze_match.py missing: {}",
            script.display()
        ));
    }

    let mut cmd = Command::new(&cfg.python);
    cmd.arg(&script).arg(&bsp_path).arg(&log_a_path);
    if let Some(b) = &log_b_path {
        cmd.arg(b);
    }
    cmd.arg(&out_png_path);
    if let Some(n) = &nav_path {
        cmd.arg(n);
    }

    let output = cmd
        .output()
        .map_err(|e| format!("failed to spawn ARGUS_PYTHON: {e}"))?;
    let mut text = String::from_utf8_lossy(&output.stdout).into_owned();
    if !output.stderr.is_empty() {
        text.push('\n');
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }

    let summary_a = parse_arglog_path(&log_a_path).map_err(|e| e.to_string())?;
    let summary_b = match &log_b_path {
        Some(p) => Some(parse_arglog_path(p).map_err(|e| e.to_string())?),
        None => None,
    };
    let brief_a = brief_path(&log_a_path, None)?;
    let brief_b = match &log_b_path {
        Some(p) => Some(brief_path(p, None)?),
        None => None,
    };
    let compare = brief_b
        .as_ref()
        .map(|b| compare_briefs(brief_a.clone(), b.clone()));

    Ok(AnalyzeResult {
        ok: output.status.success(),
        out_png: out_png_path.display().to_string(),
        log_a: summary_a,
        log_b: summary_b,
        brief_a,
        brief_b,
        compare,
        stdout_tail: tail_lines(&text, 40),
    })
}
