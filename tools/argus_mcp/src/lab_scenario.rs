//! lab_request: a structured request in, a registered lab micro-map out.
//!
//! tools/lab_mapgen.py owns the request schema, the .map, the generated
//! texture WAD, the pinned ericw-tools compile and the manifest. This module
//! runs it, then takes the map down the same road a stock map travels:
//! `navgen::nav_generate` writes the `argus_nav_<map>.qc` and `.qc.json` pair,
//! the mill walks every link in the real engine, and
//! `nav_sync::register_maps` wires the map into the dispatcher and progs.src
//! only through the first-registration reach and mill gate. The scenario is
//! then recorded in tools/lab_instruments.json.
//!
//! A lab map is an isolation instrument (docs/lab-scenarios.md). Nothing here
//! can promote a lab result to a stock-map claim: tools/argus_lab.py refuses a
//! supported or fixed claim that names a stock map on lab tapes alone.

use crate::config::Config;
use serde::Serialize;
use std::ffi::OsStr;
use std::path::Path;
use std::time::Duration;

/// Generate, compile (qbsp, vis, light) and install. Small maps take seconds;
/// the bound is for a cold disk and a slow light pass.
const BUILD_DEADLINE: Duration = Duration::from_secs(900);
const RECORD_DEADLINE: Duration = Duration::from_secs(120);
/// The mill walks at most 80 links an engine session.
const MILL_CHUNK: usize = 80;

pub const PROMOTION_RULE: &str = "Lab maps are isolation instruments. A result measured on a lab map can support an isolation-tier claim only. A claim about stock geometry needs a separate run on real geometry (dm2, dm3, dm4, dm6 or another stock map), and it cites the lab tapes and the stock tapes together.";

#[derive(Debug, Clone, Serialize)]
pub struct Stage {
    pub name: String,
    pub ok: bool,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LabRequestReport {
    pub ok: bool,
    pub map: String,
    pub scenario_id: Option<String>,
    pub registered: bool,
    pub stages: Vec<Stage>,
    pub manifest: serde_json::Value,
    pub promotion_rule: String,
    pub next_steps: Vec<String>,
}

#[derive(Debug, Clone, Copy)]
pub struct LabRequestOptions {
    /// Walk the generated links in the engine before registration.
    pub mill: bool,
    /// Ask for registration (the gate still decides).
    pub register: bool,
}

impl Default for LabRequestOptions {
    fn default() -> Self {
        Self {
            mill: true,
            register: true,
        }
    }
}

/// The request's map name, checked before anything touches the disk.
pub fn request_map(request: &serde_json::Value) -> Result<String, String> {
    if !request.is_object() {
        return Err("the request is a JSON object (docs/lab-scenarios.md)".into());
    }
    let name = request
        .get("name")
        .and_then(|v| v.as_str())
        .ok_or("the request needs a name, lab_<words>")?;
    let map = crate::paths::map_name(name)?;
    if map != name {
        return Err(format!("name {name}: use the canonical {map}"));
    }
    if !map.starts_with("lab_") || map.len() <= 4 {
        return Err(format!(
            "name {name}: generated maps are named lab_<words> so they can never shadow a stock map"
        ));
    }
    Ok(map)
}

fn stage(stages: &mut Vec<Stage>, name: &str, ok: bool, detail: impl Into<String>) {
    stages.push(Stage {
        name: name.into(),
        ok,
        detail: detail.into(),
    });
}

fn tail(text: &str, lines: usize) -> String {
    let all: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    all[all.len().saturating_sub(lines)..].join(" | ")
}

/// Run tools/lab_mapgen.py with the lab's own paths, and read its JSON.
async fn run_mapgen(
    cfg: &Config,
    args: &[&OsStr],
    deadline: Duration,
) -> Result<serde_json::Value, String> {
    let script = cfg.root.join("tools").join("lab_mapgen.py");
    if !script.is_file() {
        return Err(format!("missing {}", script.display()));
    }
    let mut command = tokio::process::Command::new(&cfg.python);
    command
        .arg(&script)
        .args(args)
        .current_dir(&cfg.root)
        .env("ARGUS_ROOT", &cfg.root)
        .env("ARGUS_MAPS", &cfg.maps)
        .env("ARGUS_BASEDIR", &cfg.basedir)
        .env("ARGUS_GAME", &cfg.game)
        .env("ARGUS_SRC", &cfg.src);
    let output =
        crate::python_helper::capture(&mut command, "tools/lab_mapgen.py (ARGUS_PYTHON)", deadline)
            .await?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let value: serde_json::Value = serde_json::from_str(stdout.trim()).map_err(|e| {
        format!(
            "lab_mapgen.py printed no JSON ({e}): {}",
            tail(&format!("{stdout}\n{stderr}"), 6)
        )
    })?;
    if value.get("ok") == Some(&serde_json::Value::Bool(false)) {
        return Err(value
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("lab_mapgen.py failed")
            .to_string());
    }
    if !output.status.success() {
        return Err(format!(
            "lab_mapgen.py exited {}: {}",
            output.status,
            tail(&stderr, 6)
        ));
    }
    Ok(value)
}

/// Ordinary and jump link counts of the generated graph, for the mill.
fn link_counts(cfg: &Config, map: &str) -> (usize, usize) {
    let path = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let Ok(text) = std::fs::read_to_string(path) else {
        return (0, 0);
    };
    let Ok(graph) = serde_json::from_str::<serde_json::Value>(&text) else {
        return (0, 0);
    };
    let jumps = graph["jlinks"].as_array().map_or(0, |v| v.len());
    let links = graph["links"].as_array().map_or(0, |v| v.len());
    (links.saturating_sub(jumps), jumps)
}

async fn mill(cfg: &Config, map: &str, stages: &mut Vec<Stage>) -> serde_json::Value {
    let (walks, jumps) = link_counts(cfg, map);
    let mut out = serde_json::json!({"confirm": true, "passes": []});
    for (kind, total, jumps_only) in [("walk", walks, false), ("jump", jumps, true)] {
        let mut skip = 0;
        while skip < total {
            let mut ctrl = crate::match_ctrl::MatchCtrl::default();
            let result = crate::netclient::probe_links_confirmed(
                cfg, map, MILL_CHUNK, skip, false, jumps_only, true, &mut ctrl,
            )
            .await;
            match result {
                Ok(report) => {
                    let clean = report.failed == 0 && report.teleport_failures == 0;
                    stage(
                        stages,
                        &format!("mill {kind} {skip}+"),
                        clean,
                        format!(
                            "{} probed, {} passed ({} on the confirming walk), {} failed, {} teleport failures",
                            report.probed,
                            report.passed,
                            report.confirmed,
                            report.failed,
                            report.teleport_failures
                        ),
                    );
                    if let Some(passes) = out["passes"].as_array_mut() {
                        passes.push(serde_json::json!({
                            "kind": kind,
                            "skip": skip,
                            "probed": report.probed,
                            "passed": report.passed,
                            "confirmed": report.confirmed,
                            "failed": report.failed,
                            "teleport_failures": report.teleport_failures,
                            "graph_md5": report.graph_md5,
                            "failed_links": report.failed_links.iter().map(|f| format!(
                                "n{}->n{} {}", f.a, f.b, f.note
                            )).collect::<Vec<_>>(),
                        }));
                    }
                }
                Err(e) => {
                    stage(stages, &format!("mill {kind} {skip}+"), false, e);
                    break;
                }
            }
            skip += MILL_CHUNK;
        }
    }
    out
}

/// The whole road: generate, compile, install, navgen, mill, register, record.
pub async fn lab_request(
    cfg: &Config,
    request: &serde_json::Value,
    opts: LabRequestOptions,
) -> Result<LabRequestReport, String> {
    let map = request_map(request)?;
    let dir = cfg.root.join("labmaps").join(&map);
    std::fs::create_dir_all(&dir).map_err(|e| format!("create {}: {e}", dir.display()))?;
    let request_path = dir.join("request.json");
    // an unchanged request keeps its file, and with it the author's key order
    let same = read_request(&request_path).is_ok_and(|held| &held == request);
    if !same {
        let text = serde_json::to_string_pretty(request).map_err(|e| e.to_string())? + "\n";
        std::fs::write(&request_path, text)
            .map_err(|e| format!("write {}: {e}", request_path.display()))?;
    }

    let mut stages = Vec::new();
    let mut report = LabRequestReport {
        ok: false,
        map: map.clone(),
        scenario_id: None,
        registered: false,
        stages: Vec::new(),
        manifest: serde_json::Value::Null,
        promotion_rule: PROMOTION_RULE.into(),
        next_steps: Vec::new(),
    };

    let build_args: [&OsStr; 3] = [
        OsStr::new("build"),
        request_path.as_os_str(),
        OsStr::new("--json"),
    ];
    let manifest = match run_mapgen(cfg, &build_args, BUILD_DEADLINE).await {
        Ok(m) => {
            stage(
                &mut stages,
                "build",
                true,
                format!(
                    "{} brushes, {} entities, BSP {} bytes",
                    m["counts"]["brushes"], m["counts"]["entities"], m["compile"]["bsp_bytes"]
                ),
            );
            m
        }
        Err(e) => {
            stage(&mut stages, "build", false, e.clone());
            report.stages = stages;
            report.next_steps = vec![format!("Fix the request and call lab_request again: {e}")];
            return Ok(report);
        }
    };
    report.scenario_id = manifest["scenario_id"].as_str().map(str::to_owned);
    report.manifest = manifest;

    let nav = crate::navgen::nav_generate(cfg, &map, &map, None, None, false).await?;
    let nav_text = nav.stdout_tail.join("\n");
    stage(
        &mut stages,
        "navgen",
        nav.ok,
        nav.edict_budget
            .clone()
            .unwrap_or_else(|| tail(&nav_text, 4)),
    );
    let nav_log = dir.join("navgen.log");
    let _ = std::fs::write(&nav_log, &nav_text);

    let mut mill_record = serde_json::Value::Null;
    if nav.ok && opts.mill {
        mill_record = mill(cfg, &map, &mut stages).await;
    }
    let mill_path = dir.join("mill.json");
    let _ = std::fs::write(
        &mill_path,
        serde_json::to_string_pretty(&mill_record).unwrap_or_default(),
    );

    let mut gate = String::new();
    if nav.ok && opts.register {
        match crate::nav_sync::register_maps(cfg, vec![map.clone()]).await {
            Ok(r) => {
                report.registered = true;
                stage(&mut stages, "register", true, r.headline);
            }
            Err(e) => {
                gate = e.clone();
                stage(&mut stages, "register", false, e);
            }
        }
    }

    let registered_flag = if report.registered { "yes" } else { "no" };
    let mut record_args: Vec<&OsStr> = vec![
        OsStr::new("record"),
        request_path.as_os_str(),
        OsStr::new("--nav-out"),
        nav_log.as_os_str(),
        OsStr::new("--registered"),
        OsStr::new(registered_flag),
        OsStr::new("--json"),
    ];
    if !mill_record.is_null() {
        record_args.push(OsStr::new("--mill"));
        record_args.push(mill_path.as_os_str());
    }
    match run_mapgen(cfg, &record_args, RECORD_DEADLINE).await {
        Ok(m) => {
            stage(
                &mut stages,
                "record",
                true,
                "manifest and lab_instruments.json scenario written",
            );
            report.manifest = m;
        }
        Err(e) => stage(&mut stages, "record", false, e),
    }

    report.ok = stages.iter().all(|s| s.ok);
    report.next_steps = next_steps(&map, report.registered, nav.ok, &gate);
    report.stages = stages;
    Ok(report)
}

fn next_steps(map: &str, registered: bool, nav_ok: bool, gate: &str) -> Vec<String> {
    let mut steps = Vec::new();
    if !nav_ok {
        steps.push(format!(
            "navgen failed on {map}: read labmaps/{map}/navgen.log, adjust the request and call lab_request again"
        ));
        return steps;
    }
    if registered {
        steps.push(format!(
            "Compile with compile_qc install=false into a private ARGUS_SRC and ARGUS_PROGS, stage a scratch ARGUS_GAME, then ladder control against candidate on {map} (docs/lab-scenarios.md#running-a-ladder)"
        ));
    } else {
        steps.push(format!(
            "{map} stays experimental until the gate passes: {gate}. A rerun of lab_request regenerates the graph and walks it again"
        ));
    }
    steps.push(format!(
        "Pre-register the primary metric before the tapes exist; see what=map name={map} shows the generated graph"
    ));
    steps.push(
        "A lab-map result supports an isolation-tier claim only: run the same change on a stock map before a claim names one"
            .into(),
    );
    steps
}

/// The request file a CLI caller names, read as JSON.
pub fn read_request(path: &Path) -> Result<serde_json::Value, String> {
    let text =
        std::fs::read_to_string(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{}: not JSON: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_are_lab_prefixed_and_canonical() {
        let ok = serde_json::json!({"name": "lab_voidcorner"});
        assert_eq!(request_map(&ok).unwrap(), "lab_voidcorner");
        for bad in [
            serde_json::json!({"name": "dm4"}),
            serde_json::json!({"name": "lab_"}),
            serde_json::json!({"name": "lab-corner"}),
            serde_json::json!({"name": "LAB_Corner"}),
            serde_json::json!({"intent": "no name"}),
            serde_json::json!(["not", "an", "object"]),
        ] {
            assert!(request_map(&bad).is_err(), "{bad} was accepted");
        }
    }

    #[test]
    fn next_steps_carry_the_promotion_rule_either_way() {
        for registered in [true, false] {
            let steps = next_steps("lab_x", registered, true, "the mill refused 1 link");
            assert!(
                steps.iter().any(|s| s.contains("isolation-tier")),
                "{steps:?}"
            );
        }
        let failed = next_steps("lab_x", false, false, "");
        assert_eq!(failed.len(), 1);
        assert!(failed[0].contains("navgen.log"));
    }

    #[tokio::test]
    async fn a_refused_request_reports_the_build_stage_without_touching_the_graph() {
        let dir = crate::test_support::TestDir::new("lab-request-refused").unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join("tools")).unwrap();
        std::fs::create_dir_all(root.join("src")).unwrap();
        // a stand-in generator that refuses every request the way the real one does
        std::fs::write(
            root.join("tools/lab_mapgen.py"),
            "import json\nprint(json.dumps({'ok': False, 'error': 'name must match', 'kind': 'request'}))\nraise SystemExit(2)\n",
        )
        .unwrap();
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            root,
        )
        .unwrap();
        if !cfg.python.is_file() {
            eprintln!("SKIPPED lab_request refusal: no python");
            return;
        }
        let request = serde_json::json!({"name": "lab_refused", "intent": "x"});
        let report = lab_request(&cfg, &request, LabRequestOptions::default())
            .await
            .unwrap();
        assert!(!report.ok);
        assert_eq!(report.stages.len(), 1);
        assert_eq!(report.stages[0].name, "build");
        assert!(report.stages[0].detail.contains("name must match"));
        assert!(root.join("labmaps/lab_refused/request.json").is_file());
        assert!(!root.join("src/argus_nav_lab_refused.qc").exists());
    }
}
