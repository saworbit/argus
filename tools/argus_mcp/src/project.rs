//! What an LLM needs to see of the Argus tree without grepping.

use crate::cartograph::list_maps;
use crate::config::Config;
use crate::match_ctrl::list_runs;
use serde::Serialize;
use std::fs;

#[derive(Debug, Clone, Serialize)]
pub struct ProjectView {
    pub headline: String,
    pub protocol: String,
    pub next: String,
    pub live_vs_compile: String,
    pub ready: bool,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub missing: Vec<String>,
    pub qc: Vec<QcFile>,
    pub maps: Vec<String>,
    pub recent_runs: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct QcFile {
    pub path: String,
    pub bytes: u64,
    pub argus_fns_hint: String,
}

/// Inspect vocabulary for `see what=...`. Keep in sync with server.rs.
pub fn see_vocab() -> serde_json::Value {
    serde_json::json!({
        "see": {
            "project": "this tree: QC files, maps, how to see/adjust/test",
            "help": "this vocabulary",
            "lab": "dashboard (config, maps, recent runs, recommend)",
            "map": "cartograph brief (name=dm4): control, islands, door cuts, corridor misses. detail=full for every entity",
            "recipe": "match_run / compare_runs line for a map",
            "node": "name=dm4:56  waypoint, out/in links including rocket/lift/swim",
            "path": "name=dm4:56-72 or dm4:quad->lg  BFS walk/drop/jump/tele/rocket/lift/swim",
            "item": "name=dm4:quad  control item + snapped node",
            "fn": "Argus function source, plus calls and callers",
            "file": "name=argus.qc:120-180  a source slice",
            "search": "name=CONTENT_LAVA  grep Argus QC",
            "const": "AR_* constants (name=AR_JUMPVEL or a substring)",
            "live": "last ARGLOG sample per bot (running or last match)",
            "bot": "deep tape: events, deaths, nearest node/item (name=Reap or latest:Reap)",
            "timeline": "ARGEVT stream (name=Reap or ab_dm4_parity:Omi)",
            "around": "name=dm4:200,-900,24  nearest node and control",
            "plan": "GOAP plan events (name=latest or a run)",
            "status": "live dedicated child. Pass since_line for an incremental tail",
            "run": "brief a harvested log (name=ab_dm4_water or latest)",
            "last": "what this session last opened, plus last experiment",
            "knobs": "live cvars vs compile-time constants",
        },
        "resources": [
            "argus://project",
            "argus://lab",
            "argus://knobs",
            "argus://last",
            "argus://quality",
            "argus://help",
            "argus://map/{name}",
            "argus://fn/{name}",
            "argus://run/{name}",
            "argus://const/{name}",
            "argus://path/{spec}",
            "argus://search/{needle}",
        ],
        "adjust": {
            "live": "tune command=\"skill 3\" (next respawn). Also fraglimit, timelimit, map, developer, status.",
            "not_live": "edit src/*.qc then experiment. AR_* and personalities need compile_qc.",
        },
        "test": {
            "experiment": "compile + short match + duration-scaled compare to baseline",
            "matrix_experiment": "one compile, then a short probe on each known map",
            "probe": "compile + short match + brief (no compare)",
            "compare_runs": "A/B two harvested logs. log_b=latest against shipped baseline.",
        }
    })
}

pub fn project_view(cfg: &Config) -> ProjectView {
    let mut qc = Vec::new();
    let files: &[(&str, &str)] = &[
        ("argus.qc", "physics, hazard, combat, skill, spawn, die"),
        ("argus_nav.qc", "router, jump links, BFS"),
        ("argus_nav_dispatch.qc", "per-map spawn dispatcher (hand-maintained)"),
        ("defs.qc", "client-builtin shim, modelindex, intermission globals"),
        ("items.qc", "weapon_touch FL_CLIENT guard admits ar_isbot"),
        ("combat.qc", "T_Damage knockback admits ar_isbot"),
        ("weapons.qc", "W_FireLightning makevectors"),
        ("world.qc", "worldspawn + StartFrame hooks"),
        ("client.qc", "stock player path; declarations moved to defs.qc"),
    ];
    for (name, hint) in files {
        let p = cfg.src.join(name);
        if let Ok(meta) = fs::metadata(&p) {
            qc.push(QcFile {
                path: format!("src/{name}"),
                bytes: meta.len(),
                argus_fns_hint: (*hint).into(),
            });
        }
    }
    // only maps the lab can actually work with (a BSP on disk or a
    // nav graph); the fifty pak-only campaign maps used to spend
    // half this response saying nothing
    let all = list_maps(cfg).unwrap_or_default();
    let pak_only = all.iter().filter(|m| m.path.is_none() && !m.has_nav).count();
    let mut maps: Vec<String> = all
        .into_iter()
        .filter(|m| m.path.is_some() || m.has_nav)
        .map(|m| {
            format!(
                "{} ({}{})",
                m.name,
                if m.path.is_some() { "bsp" } else { "pak-only" },
                if m.has_nav { ", nav" } else { "" },
            )
        })
        .collect();
    if pak_only > 0 {
        maps.push(format!("(+{pak_only} pak-only maps without nav; lab_status lists them)"));
    }
    let recent_runs: Vec<String> = list_runs(cfg)
        .unwrap_or_default()
        .into_iter()
        .take(6)
        .map(|r| {
            if let Some(n) = r.note {
                format!("{} ({n})", r.name)
            } else {
                r.name
            }
        })
        .collect();

    let report = crate::config::Config::report();
    let missing: Vec<String> = report
        .entries
        .iter()
        .filter(|e| e.required && !e.exists)
        .map(|e| e.key.clone())
        .collect();
    let ready = missing.is_empty() && cfg.require_ready().is_ok();
    let next = if !missing.is_empty() {
        format!("config incomplete; set {} then config_check", missing.join(", "))
    } else if maps.iter().any(|m| m.starts_with("dm4")) {
        "see what=map name=dm4, or after a QC edit: experiment map=dm4 duration_sec=30".into()
    } else {
        "see what=lab, then cartograph a map".into()
    };

    ProjectView {
        headline: "Argus is a vanilla QuakeC deathmatch bot. This MCP is the lab. QC cannot load files.".into(),
        protocol: "Do not invent a shell pipeline. see what=map name=dm4 to look. see what=fn name=Argus_HazardSteer to read QC. After an edit: experiment map=dm4 duration_sec=30 skill=2. Several maps: matrix_experiment. Live: tune command=\"skill 3\". Incremental log: see what=status then since_line=<next_line>. Trust next_steps.".into(),
        next,
        live_vs_compile: "Live: tune skill/fraglimit/map (skill at next respawn). Windows injects via AttachConsole. Not live: edit src/*.qc then experiment. AR_* needs compile.".into(),
        ready,
        missing,
        qc,
        maps,
        recent_runs,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn vocab_covers_project_and_last() {
        let v = see_vocab();
        let see = v.get("see").unwrap();
        for key in ["project", "last", "run", "status", "fn", "map", "live", "knobs", "path", "search", "timeline", "plan"] {
            assert!(see.get(key).is_some(), "missing see.{key}");
        }
        let res = v.get("resources").unwrap().as_array().unwrap();
        let joined: Vec<_> = res.iter().filter_map(|x| x.as_str()).collect();
        assert!(joined.iter().any(|s| s.contains("argus://path/")));
        assert!(joined.iter().any(|s| s.contains("argus://search/")));
    }

    #[test]
    fn views_real_tree_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src/argus.qc");
        if !path.exists() {
            return;
        }
        let root = path.parent().unwrap().parent().unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = crate::config::load_for_reads_from(&env, root).unwrap();
        let view = project_view(&cfg);
        assert!(view.qc.iter().any(|f| f.path == "src/argus.qc"));
        assert!(
            view.next.contains("experiment")
                || view.next.contains("map")
                || view.next.contains("config")
        );
        assert!(view.live_vs_compile.contains("experiment"));
        assert!(view.protocol.contains("Do not invent a shell pipeline"));
    }
}
