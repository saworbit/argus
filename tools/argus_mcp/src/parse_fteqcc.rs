//! Structured diagnostics from fteqcc stdout/stderr.
//!
//! Success is the `Compile finished` line that also mentions `id format`.
//! The process exit code is ignored by the caller.

use regex::Regex;
use serde::Serialize;
use std::sync::OnceLock;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Diagnostic {
    pub severity: String,
    pub file: String,
    pub line: u32,
    pub message: String,
    #[serde(default)]
    pub noise: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FteqccReport {
    pub ok: bool,
    pub success_line: Option<String>,
    pub diagnostics: Vec<Diagnostic>,
    pub raw_tail: Vec<String>,
}

pub fn parse_fteqcc(output: &str) -> FteqccReport {
    let diag_re = diag_re();
    let mut diagnostics = Vec::new();
    let mut success_line = None;
    let mut lines: Vec<&str> = output.lines().collect();
    if lines.is_empty() && !output.is_empty() {
        lines = vec![output];
    }

    for line in &lines {
        let lower = line.to_ascii_lowercase();
        if lower.contains("compile finished") && lower.contains("id format") {
            success_line = Some((*line).trim().to_string());
        }
        if let Some(caps) = diag_re.captures(line) {
            let message = caps[4].trim().to_string();
            diagnostics.push(Diagnostic {
                file: caps[1].to_string(),
                line: caps[2].parse().unwrap_or(0),
                severity: caps[3].to_ascii_lowercase(),
                noise: is_known_noise(&message),
                message,
            });
        }
    }

    let raw_tail = lines
        .iter()
        .rev()
        .take(30)
        .map(|s| s.to_string())
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();

    FteqccReport {
        ok: success_line.is_some(),
        success_line,
        diagnostics,
        raw_tail,
    }
}

pub fn is_known_noise(message: &str) -> bool {
    let m = message.to_ascii_lowercase();
    m.contains("prefixes to denote integers are deprecated")
        || m.contains("defined with name of a global")
        || m.contains("\"float\" keyword used as variable name")
}

fn diag_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)^([^:\r\n]+):(\d+):\s*(warning|error):\s*(.+)$").expect("diag regex")
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn fixture(name: &str) -> String {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("fixtures")
            .join(name);
        fs::read_to_string(path).unwrap()
    }

    #[test]
    fn success_fixture_is_ok() {
        let report = parse_fteqcc(&fixture("compile_ok.txt"));
        assert!(report.ok, "expected ok, got {report:?}");
        let line = report.success_line.expect("success line");
        assert!(line.to_ascii_lowercase().contains("compile finished"));
        assert!(line.to_ascii_lowercase().contains("id format"));
        assert!(report
            .diagnostics
            .iter()
            .any(|d| d.severity == "warning" && d.file == "subs.qc" && d.line == 320 && d.noise));
    }

    #[test]
    fn failure_fixture_is_not_ok() {
        let report = parse_fteqcc(&fixture("compile_fail.txt"));
        assert!(!report.ok);
        assert!(report.success_line.is_none());
        let errors: Vec<_> = report
            .diagnostics
            .iter()
            .filter(|d| d.severity == "error")
            .collect();
        assert!(errors.len() >= 2);
        assert_eq!(errors[0].file, "botlab.qc");
        assert_eq!(errors[0].line, 17);
        assert!(errors[0].message.contains("type mismatch"));
    }

    #[test]
    fn exit_looking_noise_without_success_line_is_failure() {
        let report = parse_fteqcc(&fixture("compile_exit0_no_success.txt"));
        assert!(!report.ok);
        assert!(report.success_line.is_none());
        assert!(report
            .diagnostics
            .iter()
            .any(|d| d.severity == "warning" && d.file == "weapons.qc"));
    }
}
