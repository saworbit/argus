//! Durable records for the lab's experiment and comparison tools.

use crate::{build_identity, config::Config, intel::CompareReport, match_ctrl::MatchRunResult};
use chrono::Utc;
use rmcp::model::{CallToolResponse, JsonObject};
use rmcp::ErrorData;
use serde::Serialize;
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

#[derive(Clone)]
pub(crate) struct Receipt {
    dir: PathBuf,
}

/// Use the lab spine's receipt reader so the CLI and MCP agree on outcomes.
pub(crate) async fn search(cfg: &Config, selector: &str) -> Result<Vec<Value>, String> {
    let selector = selector.trim().to_ascii_lowercase();
    let is_filter = |value: &str| {
        matches!(
            value,
            "completed" | "failed" | "incomplete" | "unfinished" | "invalid" | "inconclusive"
        )
    };
    let (map, filter) = match selector.split_once(':') {
        Some((map, filter)) if !map.is_empty() && is_filter(filter) => (map, filter),
        Some(_) => return Err("use a receipt filter such as name=dm2:failed".into()),
        None if is_filter(&selector) => ("", selector.as_str()),
        None => (selector.as_str(), ""),
    };
    if cfg.python.as_os_str().is_empty() {
        return Err("receipt search needs ARGUS_PYTHON".into());
    }
    let mut command = tokio::process::Command::new(&cfg.python);
    command
        .arg("-B")
        .arg(cfg.root.join("tools").join("argus_lab.py"))
        .args(["receipts", "--json", "--runs"])
        .arg(&cfg.runs)
        .current_dir(&cfg.root);
    if !map.is_empty() {
        command.arg("--map").arg(crate::paths::map_name(map)?);
    }
    match filter {
        "" => {}
        "inconclusive" => {
            command.arg("--inconclusive");
        }
        status => {
            command.arg("--status").arg(status);
        }
    }
    let output = crate::python_helper::capture(
        &mut command,
        "argus_lab.py receipts (ARGUS_PYTHON)",
        std::time::Duration::from_secs(30),
    )
    .await?;
    if !output.status.success() {
        return Err(format!(
            "receipt search exited {}: {}",
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("invalid receipt search output: {e}"))
}

pub(crate) struct MatchAttempt {
    name: String,
    logs: Vec<(PathBuf, Option<LogStamp>)>,
}

type LogStamp = (std::time::SystemTime, u64);

impl MatchAttempt {
    pub(crate) fn new(runs: &Path, name: &str) -> Self {
        let mut logs = Vec::new();
        if crate::paths::valid_run_name(name) {
            for path in [
                runs.join(name).join("failed_harvest.log"),
                runs.join(format!("{name}.log")),
            ] {
                let before = log_stamp(&path);
                logs.push((path, before));
            }
        }
        Self {
            name: name.into(),
            logs,
        }
    }

    fn new_failure_log(&self) -> Option<&Path> {
        self.logs.iter().find_map(|(path, before)| {
            log_stamp(path)
                .is_some_and(|stamp| Some(stamp) != *before)
                .then_some(path.as_path())
        })
    }
}

fn log_stamp(path: &Path) -> Option<LogStamp> {
    let meta = fs::metadata(path).ok()?;
    Some((meta.modified().ok()?, meta.len()))
}

impl Receipt {
    pub(crate) fn start(tool: &str, args: Option<&JsonObject>) -> io::Result<Option<Self>> {
        let fields: &[&str] = match tool {
            "experiment" => &[
                "map",
                "duration_sec",
                "compile",
                "skill",
                "deathmatch",
                "baseline",
                "run_name",
                "detail",
                "repeats",
                "primary",
            ],
            "campaign_experiment" => &[
                "map",
                "duration_sec",
                "compile",
                "skill",
                "seat",
                "run_name",
            ],
            "matrix_experiment" => &["maps", "duration_sec", "compile", "skill"],
            "compare_runs" => &["log_a", "log_b", "map", "detail", "format"],
            _ => return Ok(None),
        };
        let arguments: JsonObject = fields
            .iter()
            .chain(&["question"])
            .filter_map(|&key| Some((key.to_string(), args?.get(key)?.clone())))
            .collect();
        let cfg = Config::load_for_reads().map_err(io::Error::other)?;
        let context = json!({
            "schema": 1,
            "tool": tool,
            "arguments": arguments,
            "lab_identity": build_identity::inspect(&cfg),
            "git_head": git(&cfg.root, &["rev-parse", "HEAD"]),
            "source_status": git(&cfg.root, &["status", "--porcelain", "--", "src", "tools/argus_mcp"]),
        });
        Self::create(&cfg.runs, tool, context).map(Some)
    }

    fn create(runs: &Path, tool: &str, mut context: Value) -> io::Result<Self> {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let start = Utc::now();
        let parent = runs.join("receipts");
        fs::create_dir_all(&parent)?;
        let dir = loop {
            let dir = parent.join(format!(
                "{}-{tool}-{}-{}",
                start.format("%Y%m%dT%H%M%S%.9fZ"),
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed),
            ));
            match fs::create_dir(&dir) {
                Ok(()) => break dir,
                Err(e) if e.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(e),
            }
        };
        let receipt = Self { dir };
        context["started_at"] = json!(start.to_rfc3339());
        receipt.write("request.json", &context)?;
        Ok(receipt)
    }

    pub(crate) fn path(&self) -> &Path {
        &self.dir
    }

    pub(crate) fn write(&self, name: &str, value: &impl Serialize) -> io::Result<()> {
        let mut bytes = serde_json::to_vec_pretty(value)?;
        bytes.push(b'\n');
        self.write_bytes(name, &bytes)
    }

    fn write_bytes(&self, name: &str, bytes: &[u8]) -> io::Result<()> {
        let path = self.dir.join(name);
        let temp = self.dir.join(format!("{name}.tmp"));
        let mut file = File::options().write(true).create_new(true).open(&temp)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        fs::rename(temp, path)
    }

    pub(crate) fn record_match(
        &self,
        number: usize,
        attempted: &MatchAttempt,
        result: &Result<MatchRunResult, String>,
    ) -> io::Result<()> {
        let stem = format!("match-{number:02}");
        let source = result
            .as_ref()
            .map(|run| Path::new(&run.log_path))
            .ok()
            .or_else(|| attempted.new_failure_log());
        let archive = source.map(|path| self.copy_tape(&stem, path)).transpose();
        self.write(
            &format!("{stem}.json"),
            &json!({
                "run_name": attempted.name,
                "match": result.as_ref().ok(),
                "error": result.as_ref().err(),
                "archive": archive.as_ref().ok().and_then(Option::as_ref),
                "archive_error": archive.err().map(|e| e.to_string()),
            }),
        )
    }

    pub(crate) fn record_comparison(
        &self,
        name: &str,
        comparison: &Result<CompareReport, String>,
    ) -> io::Result<()> {
        let body = match comparison {
            Ok(report) => json!({
                "report": report,
                "controls": report.tape_paths.controls.iter().map(PathBuf::as_path).map(tape_reference).collect::<Vec<_>>(),
                "candidates": report.tape_paths.candidates.iter().map(PathBuf::as_path).map(tape_reference).collect::<Vec<_>>(),
            }),
            Err(error) => json!({"error": error}),
        };
        self.write(name, &body)
    }

    fn copy_tape(&self, stem: &str, source: &Path) -> io::Result<Value> {
        let log_name = format!("{stem}.log");
        let bytes = fs::read(source)?;
        let hash = format!("{:x}", md5::compute(&bytes));
        self.write_bytes(&log_name, &bytes)?;
        let nav = self.copy_navigation(stem, source, &hash);
        Ok(json!({
            "log": log_name,
            "log_md5": hash,
            "navigation": nav.as_ref().ok().and_then(Option::as_ref),
            "navigation_error": nav.err().map(|e| e.to_string()),
        }))
    }

    fn copy_navigation(&self, stem: &str, source: &Path, hash: &str) -> io::Result<Option<String>> {
        match fs::read(source.with_extension("nav.json")) {
            Ok(bytes) => {
                let nav: Value = serde_json::from_slice(&bytes)?;
                if nav["log_md5"].as_str() != Some(hash) {
                    return Err(io::Error::other(
                        "navigation receipt does not match this tape",
                    ));
                }
                let name = format!("{stem}.nav.json");
                self.write_bytes(&name, &bytes)?;
                Ok(Some(name))
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(e),
        }
    }

    pub(crate) fn finish(&self, response: &Result<CallToolResponse, ErrorData>) -> io::Result<()> {
        let (status, outcome) = match response {
            Ok(CallToolResponse::Complete(result)) => {
                let output = result
                    .structured_content
                    .as_ref()
                    .and_then(|v| v.get("data").cloned())
                    .or_else(|| {
                        let text = &result.content.first()?.as_text()?.text;
                        Some(serde_json::from_str(text).unwrap_or_else(|_| json!(text)))
                    })
                    .unwrap_or(Value::Null);
                let failed = result.is_error == Some(true) || output["ok"].as_bool() == Some(false);
                (if failed { "failed" } else { "completed" }, output)
            }
            Err(error) => ("failed", json!(error)),
            Ok(_) => ("incomplete", Value::Null),
        };
        self.write(
            "result.json",
            &json!({
                "status": status,
                "finished_at": Utc::now().to_rfc3339(),
                "output": outcome,
            }),
        )
    }
}

fn tape_reference(path: &Path) -> Value {
    match fs::read(path) {
        Ok(bytes) => json!({"path": path, "log_md5": format!("{:x}", md5::compute(bytes))}),
        Err(error) => json!({"path": path, "error": error.to_string()}),
    }
}

fn git(root: &Path, args: &[&str]) -> Option<String> {
    let mut command = std::process::Command::new("git");
    command.arg("-C").arg(root).args(args);
    let output = crate::child_process::output_with_windows_loader_retry(&mut command).ok()?;
    output.status.success().then(|| {
        String::from_utf8_lossy(&output.stdout)
            .trim_end()
            .to_owned()
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::TestDir;

    #[tokio::test]
    async fn search_uses_saved_outcomes_from_the_configured_runs_directory() {
        let work = TestDir::new("receipt-search").unwrap();
        let mut cfg = Config::load_for_reads().unwrap();
        cfg.root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        cfg.runs = work.path().to_path_buf();
        let failed = Receipt::create(
            &cfg.runs,
            "experiment",
            json!({"schema": 1, "tool": "experiment", "arguments": {"map": "dm4"}}),
        )
        .unwrap();
        failed
            .write(
                "result.json",
                &json!({"status": "failed", "output": {"error": "launch refused"}}),
            )
            .unwrap();
        let unsettled = Receipt::create(
            &cfg.runs,
            "experiment",
            json!({"schema": 1, "tool": "experiment", "arguments": {"map": "dm2"}}),
        )
        .unwrap();
        unsettled
            .write("result.json", &json!({"status": "completed"}))
            .unwrap();
        unsettled
            .write(
                "comparison.json",
                &json!({"report": {
                    "b": {"map": "dm2"}, "verdict": "parity", "primary": "engagements",
                    "stats": [{"name": "engagements", "sprt": "continue"}]
                }}),
            )
            .unwrap();

        let rows = search(&cfg, "failed").await.unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["error"], "launch refused");
        let rows = search(&cfg, "DM2:inconclusive").await.unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["status"], "completed");
        assert_eq!(
            rows[0]["comparisons"][0]["unresolved"][0]["call"],
            "continue"
        );
        assert!(search(&cfg, "dm4:inconclusive").await.unwrap().is_empty());
        assert!(search(&cfg, "dm2:typo").await.is_err());
    }

    #[test]
    fn failed_run_keeps_new_output_and_leaves_prior_tapes_out() {
        let work = TestDir::new("receipt").unwrap();
        let receipt = Receipt::create(work.path(), "experiment", json!({})).unwrap();
        let tape = work.path().join("repeat.log");
        fs::write(&tape, "older tape").unwrap();
        let blocked = MatchAttempt::new(work.path(), "repeat");
        receipt
            .record_match(1, &blocked, &Err("launch refused".into()))
            .unwrap();
        assert!(!receipt.path().join("match-01.log").exists());

        let failed = MatchAttempt::new(work.path(), "repeat");
        let output = b"new failed engine output";
        fs::write(&tape, output).unwrap();
        let nav = json!({"log_md5": format!("{:x}", md5::compute(output))});
        fs::write(tape.with_extension("nav.json"), nav.to_string()).unwrap();
        receipt
            .record_match(2, &failed, &Err("wrong map".into()))
            .unwrap();
        fs::write(&tape, "later run").unwrap();
        assert_eq!(
            fs::read(receipt.path().join("match-02.log")).unwrap(),
            output
        );
        assert_eq!(
            fs::read_to_string(receipt.path().join("match-02.nav.json")).unwrap(),
            nav.to_string()
        );
        let error: Value =
            serde_json::from_slice(&fs::read(receipt.path().join("match-02.json")).unwrap())
                .unwrap();
        assert_eq!(error["error"], "wrong map");
        assert_eq!(error["archive"]["log"], "match-02.log");
    }

    #[test]
    fn failed_and_inconclusive_calls_get_distinct_receipts() {
        use rmcp::model::{CallToolResult, ContentBlock};

        let work = TestDir::new("receipt").unwrap();
        let first = Receipt::create(work.path(), "experiment", json!({"schema": 1})).unwrap();
        assert!(first.path().join("request.json").is_file());
        assert!(!first.path().join("result.json").exists());
        first
            .finish(&Err(ErrorData::invalid_params("invalid duration", None)))
            .unwrap();
        let failed: Value =
            serde_json::from_slice(&fs::read(first.path().join("result.json")).unwrap()).unwrap();
        assert_eq!(failed["status"], "failed");
        assert_eq!(failed["output"]["message"], "invalid duration");

        let second = Receipt::create(work.path(), "experiment", json!({"schema": 1})).unwrap();
        let output =
            json!({"ok": true, "compare": {"verdict": "mixed", "stats": [{"sprt": "continue"}]}});
        second
            .finish(&Ok(CallToolResult::success(vec![ContentBlock::text(
                output.to_string(),
            )])
            .into()))
            .unwrap();
        let saved: Value =
            serde_json::from_slice(&fs::read(second.path().join("result.json")).unwrap()).unwrap();
        assert_eq!(saved["output"], output);
        assert_ne!(first.path(), second.path());
    }
}
