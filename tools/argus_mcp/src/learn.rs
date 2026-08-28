//! Offline stall / lava learning across harvested logs.
//! Writes `src/argus_nav_<map>.costs.json` for navgen to inflate
//! fine-graph costs. Does not write QuakeC.

use crate::config::Config;
use crate::intel::attach_nav;
use crate::parse_arglog::{parse_tape_path, MatchTape, Pos};
use crate::paths::resolve_log;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

const CELL: f64 = 128.0;

#[derive(Debug, Clone, Serialize)]
pub struct LearnedCell {
    pub kind: String,
    pub count: u32,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub logs: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_node: Option<u32>,
    pub hint: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LearnReport {
    pub map: String,
    pub logs_used: Vec<String>,
    pub cells: Vec<LearnedCell>,
    pub headline: String,
    pub next_steps: Vec<crate::intel::NextStep>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub wrote: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostOverlay {
    pub map: String,
    pub version: u32,
    pub cells: Vec<CostCell>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostCell {
    pub kind: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub count: u32,
    pub radius: f64,
    pub cost: f64,
}

pub fn cost_path(cfg: &Config, map: &str) -> std::path::PathBuf {
    cfg.src.join(format!("argus_nav_{map}.costs.json"))
}

/// Kind-aware overlay policy (the 2026-08-19 dm4 negative result:
/// folding hazard-DEFLECTION clusters at radius 128 into navgen
/// amputated the pit floor - lava 9 -> 1 but routefails 164 and a
/// trapped-suicide storm, because deflection cells mark where the
/// brink guard SUCCEEDS; punishing them guts connectivity. Death
/// cells, meanwhile, never reached the overlay at all: the global
/// top-16-by-count truncation let 26-87-count hazard cells crowd out
/// the 1-5-count lava cells every time).
///
/// Policy now: lava DEATH cells go out tight and expensive (they mark
/// killing edges, radius 64 so only boundary-crossing fine edges pay);
/// chronic stalls go out moderate; hazard deflections are REPORTED but
/// never written to the overlay.
fn cell_overlay(kind: &str, count: u32, logs: u32) -> Option<(f64, f64)> {
    // -> (radius, cost)
    match kind {
        "lava" if count >= 2 => Some((64.0, 8.0)),
        "stall" if count >= 4 && logs >= 2 => Some((96.0, 3.0)),
        _ => None,
    }
}

pub fn learn_hotspots(cfg: &Config, map: &str, max_logs: usize) -> Result<LearnReport, String> {
    let map = map.to_ascii_lowercase();
    let logs = pick_logs(cfg, &map, max_logs.max(1))?;
    if logs.is_empty() {
        return Err(format!("no harvested logs mentioning {map}"));
    }

    let hull = crate::cartograph::ingest_bsp(cfg, &map)
        .ok()
        .and_then(|(path, _)| crate::bsp::read_bsp29(&path).ok())
        .and_then(|b| b.hull0);
    let mut cells: BTreeMap<(i32, i32, i32, String), (u32, Pos, u32)> = BTreeMap::new();
    let mut used = Vec::new();
    for path in &logs {
        let tape = match parse_tape_path(path) {
            Ok(t) => t,
            Err(_) => continue,
        };
        if let Some(m) = tape.map.as_deref() {
            if m != map {
                continue;
            }
        }
        used.push(
            path.file_name()
                .and_then(|s| s.to_str())
                .unwrap_or_default()
                .to_string(),
        );
        accumulate(&tape, &mut cells, hull.as_ref());
    }
    if used.is_empty() {
        return Err(format!("logs found but none parsed as map {map}"));
    }

    let mut brief_stub = crate::intel::brief_text("", Some(&map));
    // attach_nav only needs map + empty hotspots we'll fill
    let mut learned: Vec<LearnedCell> = cells
        .into_iter()
        .map(|((_, _, _, kind), (count, p, logs))| {
            let hint = if kind == "lava" {
                "raise cost of links that drop toward this cell; check Argus_MoveHazard".into()
            } else if kind == "stall" {
                "candidate nav link cost bump; possible deflection dither".into()
            } else {
                "hazard deflection cluster; inspect brink heading".into()
            };
            LearnedCell {
                kind,
                count,
                x: p.x,
                y: p.y,
                z: p.z,
                logs,
                nearest_node: None,
                hint,
            }
        })
        .collect();
    // Per-kind budgets, not a global top-N: raw hazard counts run
    // 20-90 per cell while a lethal lava cell may carry only 2-5
    // deaths, so a global sort-and-truncate silently dropped every
    // lava cell (the exact reason the first live overlay contained
    // no death cells at all).
    learned.sort_by(|a, b| b.count.cmp(&a.count));
    let mut budgeted: Vec<LearnedCell> = Vec::new();
    for kind in ["lava", "stall", "hazard"] {
        let cap = match kind {
            "lava" => 8,
            "stall" => 6,
            _ => 4,
        };
        budgeted.extend(
            learned
                .iter()
                .filter(|c| c.kind == kind)
                .take(cap)
                .cloned(),
        );
    }
    let mut learned = budgeted;

    brief_stub.map = Some(map.clone());
    brief_stub.hotspots = learned
        .iter()
        .map(|c| crate::intel::Hotspot {
            kind: c.kind.clone(),
            count: c.count,
            x: c.x,
            y: c.y,
            z: c.z,
            known: None,
            note: None,
            nearest_node: None,
            nearest_dist: None,
            nearest_item: None,
            nearest_item_dist: None,
            cause: None,
            reach_pct: None,
        })
        .collect();
    attach_nav(cfg, &mut brief_stub);
    for (c, h) in learned.iter_mut().zip(brief_stub.hotspots.iter()) {
        c.nearest_node = h.nearest_node;
    }

    let next_steps = crate::intel::suggest_next(&brief_stub, None);
    let overlay = CostOverlay {
        map: map.clone(),
        version: 1,
        cells: learned
            .iter()
            .filter_map(|c| {
                let (radius, cost) = cell_overlay(&c.kind, c.count, c.logs)?;
                Some(CostCell {
                    kind: c.kind.clone(),
                    x: c.x,
                    y: c.y,
                    z: c.z,
                    count: c.count,
                    radius,
                    cost,
                })
            })
            .collect(),
    };
    let wrote = if overlay.cells.is_empty() {
        None
    } else {
        let dest = cost_path(cfg, &map);
        if let Some(parent) = dest.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        match serde_json::to_string_pretty(&overlay) {
            Ok(text) => match std::fs::write(&dest, text) {
                Ok(()) => Some(dest.display().to_string()),
                Err(_) => None,
            },
            Err(_) => None,
        }
    };

    let headline = format!(
        "{map}: learned {} hot cells from {} logs (top count {}){}",
        learned.len(),
        used.len(),
        learned.first().map(|c| c.count).unwrap_or(0),
        if wrote.is_some() {
            format!(", wrote {} cost cells for navgen", overlay.cells.len())
        } else {
            String::new()
        }
    );
    Ok(LearnReport {
        map,
        logs_used: used,
        cells: learned,
        headline,
        next_steps,
        wrote,
    })
}


/// True when a run-log filename names this map as a whole token.
/// Stems are underscore-joined (`ab_dm2_rebirth1.log`,
/// `soak_2026-08-28_1257_003_dm2.log`), so splitting on `_` and
/// comparing whole tokens keeps `lqdm2` out of a `dm2` sweep.
fn log_stem_names_map(file_name: &str, map: &str) -> bool {
    let stem = file_name.strip_suffix(".log").unwrap_or(file_name);
    stem.split(['_', '-', '.']).any(|tok| tok == map)
}

fn pick_logs(cfg: &Config, map: &str, max_logs: usize) -> Result<Vec<std::path::PathBuf>, String> {
    let mut named = Vec::new();
    if cfg.runs.is_dir() {
        let rd = std::fs::read_dir(&cfg.runs).map_err(|e| format!("ARGUS_RUNS: {e}"))?;
        for ent in rd.flatten() {
            let p = ent.path();
            if p.extension().and_then(|s| s.to_str()) != Some("log") || !p.is_file() {
                continue;
            }
            let name = p
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_ascii_lowercase();
            // "lqdm2".contains("dm2") is true: fresher lqdm2 tapes used
            // to displace real dm2 logs before the caller could check
            // the tape's own map name. Match whole stem tokens instead.
            if log_stem_names_map(&name, map) {
                let mtime = ent.metadata().and_then(|m| m.modified()).ok();
                named.push((mtime, p));
            }
        }
    }
    named.sort_by(|a, b| b.0.cmp(&a.0));
    let mut out: Vec<_> = named.into_iter().map(|(_, p)| p).take(max_logs).collect();
    if out.is_empty() {
        if let Ok(p) = resolve_log(cfg, "latest") {
            out.push(p);
        }
    }
    Ok(out)
}

fn accumulate(
    tape: &MatchTape,
    cells: &mut BTreeMap<(i32, i32, i32, String), (u32, Pos, u32)>,
    hull: Option<&crate::bsp::Hull0>,
) {
    let mut seen: BTreeMap<(i32, i32, i32, String), bool> = BTreeMap::new();
    let mut bump = |kind: &str, p: Pos| {
        let key = (
            (p.x / CELL).floor() as i32,
            (p.y / CELL).floor() as i32,
            (p.z / CELL).floor() as i32,
            kind.to_string(),
        );
        let e = cells.entry(key.clone()).or_insert((0, p, 0));
        e.0 += 1;
        if seen.insert(key, true).is_none() {
            e.2 += 1;
        }
    };
    for d in &tape.deaths {
        if d.killer.eq_ignore_ascii_case("world")
            && crate::bsp::death_is_lava(hull, d.pos.x, d.pos.y, d.pos.z)
        {
            bump("lava", d.pos);
        }
    }
    for rec in tape.samples.values() {
        for w in rec.windows(2) {
            if w[1].stalls > w[0].stalls {
                bump("stall", w[1].pos);
            }
        }
    }
    for ev in &tape.events {
        if ev.verb == "hazard" {
            if let Some(p) = ev.pos {
                bump("hazard", p);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::load_for_reads_from;
    use std::collections::HashMap;
    use std::fs;

    #[test]
    fn hazard_deflections_are_reported_but_never_written() {
        let root = std::env::temp_dir().join(format!("argus-learn2-{}", std::process::id()));
        let runs = root.join("runs");
        fs::create_dir_all(&runs).unwrap();
        // a tape where hazard chatter dwarfs the lava deaths - the
        // shape that amputated the dm4 pit floor on 2026-08-19
        let mut tape = String::from("ARGUS init on dm4\n");
        tape.push_str("ARGLOG Reap t 1.0 pos '200 -230 -296' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n");
        for _ in 0..60 {
            tape.push_str("ARGEVT Reap hazard\n");
        }
        tape.push_str("ARGEVT Reap death world pos '80 144 -360'\n");
        tape.push_str("ARGEVT Reap death world pos '82 150 -361'\n");
        fs::write(runs.join("ab_dm4_storm.log"), tape).unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let report = learn_hotspots(&cfg, "dm4", 5).unwrap();
        // the hazard cluster is REPORTED (top count) ...
        assert!(report.cells.iter().any(|c| c.kind == "hazard" && c.count >= 60));
        // ... and the lava cell is not crowded out of the report
        assert!(report.cells.iter().any(|c| c.kind == "lava"));
        // but the OVERLAY carries only the death cells, tight radius
        let wrote = report.wrote.expect("lava cells should write");
        let overlay: CostOverlay =
            serde_json::from_str(&fs::read_to_string(&wrote).unwrap()).unwrap();
        assert!(!overlay.cells.is_empty());
        for c in &overlay.cells {
            assert_ne!(c.kind, "hazard", "deflection cells must never be written");
            if c.kind == "lava" {
                assert!((c.radius - 64.0).abs() < 0.01);
            }
        }
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn learns_lava_cell_from_named_log() {
        let root = std::env::temp_dir().join(format!("argus-learn-{}", std::process::id()));
        let runs = root.join("runs");
        fs::create_dir_all(&runs).unwrap();
        fs::write(
            runs.join("ab_dm4_fake.log"),
            "\
ARGUS init on dm4
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t 2.0 pos '10 10 24' spd 0 yaw 0 mode 0 st 2 gl 0 hp 100 frg 0
ARGEVT Reap death world pos '12.0 260.0 -360.0'
ARGEVT Reap death world pos '14.0 262.0 -358.0'
",
        )
        .unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let report = learn_hotspots(&cfg, "dm4", 5).unwrap();
        assert_eq!(report.map, "dm4");
        assert!(report.cells.iter().any(|c| c.kind == "lava" && c.count >= 2));
        let wrote = report.wrote.expect("should write costs overlay");
        assert!(wrote.ends_with("argus_nav_dm4.costs.json"));
        let overlay: CostOverlay =
            serde_json::from_str(&fs::read_to_string(&wrote).unwrap()).unwrap();
        assert!(overlay.cells.iter().any(|c| c.kind == "lava" && c.cost >= 8.0));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn lqdm2_tapes_do_not_answer_a_dm2_sweep() {
        // #38: `"lqdm2".contains("dm2")` let fresher lqdm2 tapes fill the
        // candidate list and starve learn_hotspots of real dm2 logs.
        assert!(log_stem_names_map("ab_dm2_rebirth1.log", "dm2"));
        assert!(log_stem_names_map("soak_2026-08-28_1257_003_dm2.log", "dm2"));
        assert!(!log_stem_names_map("ab_lqdm2_rebirth1.log", "dm2"));
        assert!(log_stem_names_map("ab_lqdm2_rebirth1.log", "lqdm2"));
    }
}
