//! Lab intelligence: brief a run, compare A/B, apply Argus quality bars.

use crate::config::Config;
use crate::parse_arglog::{parse_tape, parse_tape_path, DeathEvent, MatchTape, Pos};
use crate::paths::resolve_log;
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Verdict {
    Improved,
    Parity,
    Mixed,
    Regressed,
}

#[derive(Debug, Clone, Serialize)]
pub struct Totals {
    pub duration_sec: f64,
    pub stalls: i32,
    pub goals: i32,
    pub frags: i32,
    pub deaths: i32,
    pub player_kills: i32,
    pub world_deaths: i32,
    pub lava_deaths: i32,
    pub engages: u32,
    pub hazards: u32,
    pub abandons: u32,
    pub routefails: u32,
    pub weapons: u32,
    pub cover: usize,
    pub avg_speed: f64,
    pub kd_spread: i32,
    pub all_frags_positive: bool,
    /// "contents" when hull 0 classified the deaths, "z_fallback" otherwise.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub lava_rule: Option<String>,
    /// statues: 6 s+ at under 20 u/s (the freeze detector, now a gate
    /// - the west-pad statues rode green verdicts for three tapes)
    pub freezes: u32,
    pub freeze_max_sec: f64,
    /// freezes during which the bot lost 10+ hp: a bot being shot
    /// while standing still, the worst class a human can witness
    pub freeze_underfire: u32,
    /// typed-hop success accounting: lift/train waits vs actual
    /// boardings (ARGEVT board). A wait storm with zero boards means
    /// a pad or gate is geometrically broken, not merely slow.
    pub mover_waits: u32,
    pub boards: u32,
    /// Present only when the tape carries human tracks (names with
    /// ARGLOG rows but no spawned/respawn). Every figure above is
    /// then BOT-only - bands, gates and flags are statements about
    /// the build, and a human's lava swims or idle spells are review
    /// data, not defects. The human's numbers live here instead.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub human: Option<HumanTracks>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HumanTracks {
    pub names: Vec<String>,
    pub deaths: i32,
    pub world_deaths: i32,
    pub lava_deaths: i32,
    /// kills the human scored on players/bots (their frag row is in
    /// `bots` like any track; this is death-event-derived)
    pub kills: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct Hotspot {
    pub kind: String,
    pub count: u32,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub known: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_node: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_dist: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_item: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_item_dist: Option<f64>,
    /// Geometric neighbourhood from the atlas: "door", "plat_column"
    /// or "lava_edge" - the classification every forensics session
    /// used to reconstruct by hand from raw coordinates ("'2640 -57
    /// 152', that is the stair-lip class"). Absent when no geometry
    /// matches or the atlas is unavailable.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cause: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModeShare {
    pub seeking: f64,
    pub combat: f64,
    pub routed: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct MatchBrief {
    pub map: Option<String>,
    pub totals: Totals,
    pub mode_share: ModeShare,
    pub bots: Vec<crate::parse_arglog::BotStats>,
    pub events: BTreeMap<String, u32>,
    pub hotspots: Vec<Hotspot>,
    pub flags: Vec<String>,
    pub kills: BTreeMap<String, u32>,
    pub goals: BTreeMap<String, u32>,
    pub weapons: BTreeMap<String, u32>,
    pub next_steps: Vec<NextStep>,
    pub headline: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub goal_reach: Vec<GoalReach>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub nav_coverage: Option<NavCoverage>,
}

/// How much of the shipped graph the match actually used. Nodes with
/// no ARGLOG sample within 96u carried no traffic this tape - the
/// same nodes dark across several tapes are edict-budget dead weight.
/// typed_links pairs each typed-link family in the graph against its
/// runtime event count, the dormant-system detector (RJ pads with no
/// walk-ins rode unnoticed until v3.21; sprint links sit behind their
/// skill gate today).
#[derive(Debug, Clone, Serialize)]
pub struct NavCoverage {
    pub nodes: usize,
    pub visited: usize,
    pub pct: u32,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub never_visited_sample: Vec<u32>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub typed_links: BTreeMap<String, String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct GoalReach {
    pub classname: String,
    pub times: u32,
    pub reach: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_node: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub band: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NextStep {
    pub priority: u8,
    pub area: String,
    pub look_at: String,
    pub why: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Gate {
    pub name: String,
    pub pass: bool,
    pub a: f64,
    pub b: f64,
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CompareReport {
    pub verdict: Verdict,
    pub headline: String,
    pub gates: Vec<Gate>,
    pub findings: Vec<String>,
    pub next_steps: Vec<NextStep>,
    pub a: MatchBrief,
    pub b: MatchBrief,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub scaled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scale_note: Option<String>,
}

/// LLM-sized brief: no per-event maps, no every bot sample field.
#[derive(Debug, Clone, Serialize)]
pub struct BriefLite {
    pub headline: String,
    pub map: Option<String>,
    pub totals: Totals,
    pub flags: Vec<String>,
    pub next_steps: Vec<NextStep>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub hotspots: Vec<Hotspot>,
    pub bots: Vec<BotLite>,
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    pub goals: BTreeMap<String, u32>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub goal_reach: Vec<GoalReach>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nav_coverage: Option<NavCoverage>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BotLite {
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frags: Option<i32>,
    pub deaths: i32,
    pub stalls: i32,
    pub goals: i32,
}

/// LLM-sized A/B: verdict and gates, not two full briefs.
#[derive(Debug, Clone, Serialize)]
pub struct CompareLite {
    pub verdict: Verdict,
    pub headline: String,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub scaled: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scale_note: Option<String>,
    pub gates: Vec<Gate>,
    pub findings: Vec<String>,
    pub next_steps: Vec<NextStep>,
    pub baseline: Totals,
    pub candidate: Totals,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub candidate_flags: Vec<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub hotspots: Vec<Hotspot>,
}

pub fn brief_lite(b: &MatchBrief) -> BriefLite {
    BriefLite {
        headline: b.headline.clone(),
        map: b.map.clone(),
        totals: b.totals.clone(),
        flags: b.flags.clone(),
        next_steps: b.next_steps.clone(),
        hotspots: b.hotspots.iter().take(5).cloned().collect(),
        bots: b
            .bots
            .iter()
            .map(|bot| BotLite {
                name: bot.name.clone(),
                frags: bot.frags,
                deaths: bot.deaths,
                stalls: bot.stalls,
                goals: bot.goals,
            })
            .collect(),
        goals: b.goals.clone(),
        goal_reach: b.goal_reach.clone(),
        nav_coverage: b.nav_coverage.clone(),
    }
}

pub fn compare_lite(r: &CompareReport) -> CompareLite {
    CompareLite {
        verdict: r.verdict,
        headline: r.headline.clone(),
        scaled: r.scaled,
        scale_note: r.scale_note.clone(),
        gates: r.gates.clone(),
        findings: r.findings.clone(),
        next_steps: r.next_steps.clone(),
        baseline: r.a.totals.clone(),
        candidate: r.b.totals.clone(),
        candidate_flags: r.b.flags.clone(),
        hotspots: r.b.hotspots.iter().take(5).cloned().collect(),
    }
}

pub fn want_full(detail: Option<&str>) -> bool {
    detail
        .map(|d| d.eq_ignore_ascii_case("full"))
        .unwrap_or(false)
}

struct KnownSpot {
    map: &'static str,
    name: &'static str,
    x: f64,
    y: f64,
    z: f64,
    radius: f64,
    note: &'static str,
}

const KNOWN: &[KnownSpot] = &[
    KnownSpot {
        map: "dm4",
        name: "walkway_200_-900",
        x: 200.0,
        y: -900.0,
        z: 24.0,
        radius: 160.0,
        note: "chronic dm4 walkway stall corner; suspected deflection dithering",
    },
    KnownSpot {
        map: "dm4",
        name: "walkway_700_-800",
        x: 700.0,
        y: -800.0,
        z: -200.0,
        radius: 160.0,
        note: "chronic dm4 walkway stall corner; suspected deflection dithering",
    },
];

const CELL: f64 = 128.0;

pub fn brief_tape(tape: &MatchTape, map_hint: Option<&str>) -> MatchBrief {
    brief_tape_lava(tape, map_hint, None)
}

fn brief_tape_lava(
    tape: &MatchTape,
    map_hint: Option<&str>,
    hull: Option<&crate::bsp::Hull0>,
) -> MatchBrief {
    let map = map_hint
        .map(|s| s.to_ascii_lowercase())
        .or_else(|| tape.map.clone());
    let summary = tape.summary();
    // bands, gates and flags are statements about the BOT build:
    // every bot-quality figure below excludes human tracks (v3.72's
    // human death line put Shane's lava swims into the dm4 band flag
    // and his idle spell into the freeze count). The human rows stay
    // in `bots` and the kill matrix; their totals go in `human`.
    let humans = tape.human_names();
    let bot_rows: Vec<_> = summary.bots.iter().filter(|b| !humans.contains(&b.name)).collect();
    let duration = summary.bots.iter().map(|b| b.dur).fold(0.0, f64::max);
    let stalls = bot_rows.iter().map(|b| b.stalls).sum();
    let goals = bot_rows.iter().map(|b| b.goals).sum();
    let frags = bot_rows.iter().filter_map(|b| b.frags).sum();
    let deaths = bot_rows.iter().map(|b| b.deaths).sum();
    let cover = bot_rows.iter().map(|b| b.cover).sum();
    let avg_speed = if bot_rows.is_empty() {
        0.0
    } else {
        bot_rows.iter().map(|b| b.avg).sum::<f64>() / bot_rows.len() as f64
    };
    let frag_vals: Vec<i32> = bot_rows.iter().filter_map(|b| b.frags).collect();
    let kd_spread = match (frag_vals.iter().max(), frag_vals.iter().min()) {
        (Some(hi), Some(lo)) => hi - lo,
        _ => 0,
    };
    let all_frags_positive = !frag_vals.is_empty() && frag_vals.iter().all(|f| *f > 0);

    let mut lava_deaths = 0;
    let mut world_deaths = 0;
    let mut player_kills = 0;
    let mut h_deaths = 0;
    let mut h_world = 0;
    let mut h_lava = 0;
    let mut h_kills = 0;
    for d in &tape.deaths {
        let lava = d.killer.eq_ignore_ascii_case("world")
            && crate::bsp::death_is_lava(hull, d.pos.x, d.pos.y, d.pos.z);
        if humans.contains(&d.victim) {
            h_deaths += 1;
            if d.killer.eq_ignore_ascii_case("world") {
                h_world += 1;
                if lava {
                    h_lava += 1;
                }
            }
            continue;
        }
        if d.killer.eq_ignore_ascii_case("world") {
            world_deaths += 1;
            if lava {
                lava_deaths += 1;
            }
        } else {
            player_kills += 1;
            if humans.contains(&d.killer) {
                h_kills += 1;
            }
        }
    }
    let human = if humans.is_empty() {
        None
    } else {
        let mut names: Vec<String> = humans.iter().cloned().collect();
        names.sort();
        Some(HumanTracks {
            names,
            deaths: h_deaths,
            world_deaths: h_world,
            lava_deaths: h_lava,
            kills: h_kills,
        })
    };
    let lava_rule = Some(if hull.is_some() {
        "contents".into()
    } else {
        "z_fallback".into()
    });

    let fz: Vec<_> = tape
        .freezes()
        .into_iter()
        .filter(|f| !humans.contains(&f.bot))
        .collect();
    let freeze_underfire = fz.iter().filter(|f| f.hp_drop >= 10.0).count() as u32;
    let freeze_max_sec = fz.first().map(|f| f.dur).unwrap_or(0.0);

    let ev = |k: &str| *tape.event_counts.get(k).unwrap_or(&0);
    let totals = Totals {
        duration_sec: duration,
        stalls,
        goals,
        frags,
        deaths,
        player_kills,
        world_deaths,
        lava_deaths,
        engages: ev("engage"),
        hazards: ev("hazard"),
        abandons: ev("abandon"),
        routefails: ev("routefail"),
        weapons: ev("weapon"),
        cover,
        avg_speed,
        kd_spread,
        all_frags_positive,
        lava_rule,
        freezes: fz.len() as u32,
        freeze_max_sec,
        freeze_underfire,
        mover_waits: ev("lift") + ev("train"),
        boards: ev("board"),
        human,
    };

    let hotspots = cluster_hotspots(tape, map.as_deref(), hull);
    let mode_share = mode_share(tape);
    let mut flags = flags(&totals, &hotspots, map.as_deref());
    if !tape.failed_spawns.is_empty() {
        // every historical mx_lqdm2 probe briefed as lqdm2 while the
        // engine, missing the BSP, ran the match on the start map
        // with no nav - and the lab judged gates on it. A refused
        // spawn makes the whole tape describe the wrong map: say so
        // first, louder than anything else.
        flags.insert(
            0,
            format!(
                "WRONG MAP: engine refused to spawn {} (missing BSP?) and fell back to '{}' - every figure in this brief describes the fallback map, judge NOTHING from it",
                tape.failed_spawns.join(", "),
                tape.map.as_deref().unwrap_or("unknown"),
            ),
        );
    }
    if let Some(worst) = fz.first() {
        flags.push(format!(
            "{} freeze(s) 6 s+, longest {:.1} s at '{:.0} {:.0} {:.0}' ({})",
            fz.len(),
            worst.dur,
            worst.x,
            worst.y,
            worst.z,
            worst.bot
        ));
    }
    if totals.freeze_underfire > 0 {
        flags.push(format!(
            "{} freeze(s) UNDER FIRE - a bot lost 10+ hp standing still",
            totals.freeze_underfire
        ));
    }
    if totals.mover_waits >= 3 && totals.boards == 0 {
        flags.push(format!(
            "{} lift/train waits with ZERO boards - a pad or board gate is broken, not slow",
            totals.mover_waits
        ));
    }
    let kills = killer_matrix(tape);
    let goals = count_event_rest(tape, "goal");
    let weapons = count_event_rest(tape, "weapon");
    let mut brief = MatchBrief {
        map,
        totals,
        mode_share,
        bots: summary.bots,
        events: summary.events,
        hotspots,
        flags,
        kills,
        goals,
        weapons,
        next_steps: Vec::new(),
        headline: String::new(),
        goal_reach: Vec::new(),
        nav_coverage: None,
    };
    brief.next_steps = suggest_next(&brief, None);
    brief.headline = headline_one(&brief.totals, &brief.flags, brief.map.as_deref());
    brief
}

pub fn brief_text(text: &str, map_hint: Option<&str>) -> MatchBrief {
    brief_tape(&parse_tape(text), map_hint)
}

/// Like brief_text, but classifies lava deaths by hull-0 contents when
/// the BSP is on hand - the same rule as analyze_match.py and
/// compare_runs. Without this, experiment's match section reported
/// lava under the z < -300 fallback while its own compare section used
/// contents, and the two disagreed on dm2 (killing lava at z -35) and
/// on dm4 (solid pit floors at -360).
pub fn brief_text_hull(cfg: &Config, text: &str, map_hint: Option<&str>) -> MatchBrief {
    let tape = parse_tape(text);
    let map = map_hint
        .map(|s| s.to_ascii_lowercase())
        .or_else(|| tape.map.clone());
    let hull = map.as_deref().and_then(|m| hull0_for_map(cfg, m));
    brief_tape_lava(&tape, map_hint, hull.as_ref())
}

pub fn brief_path(path: &Path, map_hint: Option<&str>) -> Result<MatchBrief, String> {
    let tape = parse_tape_path(path).map_err(|e| format!("{}: {e}", path.display()))?;
    Ok(brief_tape(&tape, map_hint))
}

fn hull0_for_map(cfg: &Config, map: &str) -> Option<crate::bsp::Hull0> {
    let (path, _) = crate::cartograph::ingest_bsp(cfg, map).ok()?;
    crate::bsp::read_bsp29(&path).ok()?.hull0
}

pub fn brief_run(cfg: &Config, log: &str, map_hint: Option<&str>) -> Result<MatchBrief, String> {
    let path = resolve_run_ref(cfg, log, map_hint)?;
    let tape = parse_tape_path(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let map = map_hint
        .map(|s| s.to_ascii_lowercase())
        .or_else(|| tape.map.clone());
    let hull = map.as_deref().and_then(|m| hull0_for_map(cfg, m));
    let mut brief = brief_tape_lava(&tape, map_hint, hull.as_ref());
    attach_nav(cfg, &mut brief);
    attach_coverage(cfg, &tape, &mut brief);
    attach_atlas(cfg, &mut brief, hull.as_ref());
    brief.next_steps = suggest_next(&brief, None);
    for step in &mut brief.next_steps {
        step.look_at = crate::qc_index::look_at(cfg, &step.look_at);
    }
    Ok(brief)
}

pub fn resolve_run_ref(
    cfg: &Config,
    spec: &str,
    map_hint: Option<&str>,
) -> Result<std::path::PathBuf, String> {
    let s = spec.trim();
    if s.eq_ignore_ascii_case("baseline") || s.eq_ignore_ascii_case("shipped") {
        return resolve_baseline(cfg, map_hint);
    }
    if s.eq_ignore_ascii_case("latest") {
        return resolve_latest(cfg);
    }
    resolve_log(cfg, s)
}

fn map_baseline_name(map: Option<&str>) -> Option<&'static str> {
    match map.unwrap_or("dm4") {
        "dm4" => Some("ab_dm4_water"),
        "dm2" => Some("ab_dm2_lava"),
        "dm3" => Some("ab_dm3_water"),
        "dm6" => Some("ab_dm6_first"),
        "lqdm2" => Some("match_v3"),
        _ => None,
    }
}

/// runs/baselines.json maps a map name to the run that experiment and
/// compare gate against, e.g. {"dm4": "ab_dm4_stair"}. The hardcoded
/// defaults above are era-frozen tapes (ab_dm4_water is v3.20, five
/// metric boundaries old) that made every modern run read "regressed";
/// refreshing a baseline is now editing one line in one file instead
/// of a Rust rebuild.
pub fn baseline_override_for(cfg: &Config, map: &str) -> Option<String> {
    let p = cfg.runs.join("baselines.json");
    let text = std::fs::read_to_string(&p).ok()?;
    let map_table: std::collections::BTreeMap<String, String> =
        serde_json::from_str(&text).ok()?;
    map_table.get(&map.to_ascii_lowercase()).cloned()
}

fn resolve_baseline(cfg: &Config, map_hint: Option<&str>) -> Result<std::path::PathBuf, String> {
    if let Some(m) = map_hint {
        if let Some(name) = baseline_override_for(cfg, m) {
            match resolve_log(cfg, &name) {
                Ok(p) => return Ok(p),
                Err(_) => {
                    return Err(format!(
                        "baselines.json names '{name}' for {m} but no such run exists in ARGUS_RUNS"
                    ))
                }
            }
        }
    }
    if let Some(name) = map_baseline_name(map_hint) {
        if let Ok(p) = resolve_log(cfg, name) {
            return Ok(p);
        }
    }
    let extras: &[&str] = match map_hint.map(|s| s.to_ascii_lowercase()).as_deref() {
        Some("dm2") => &["ab_dm2_first"],
        Some("dm3") => &["ab_dm3_first"],
        _ => &[],
    };
    for name in extras {
        if let Ok(p) = resolve_log(cfg, name) {
            return Ok(p);
        }
    }
    for candidate in ["ab_dm4_parity", "ab_dm4_B3", "ab_dm4_A"] {
        if let Ok(p) = resolve_log(cfg, candidate) {
            return Ok(p);
        }
    }
    Err("no shipped baseline log in ARGUS_RUNS (tried ab_dm4_parity)".into())
}

fn resolve_latest(cfg: &Config) -> Result<std::path::PathBuf, String> {
    let mut best: Option<(std::time::SystemTime, std::path::PathBuf)> = None;
    let rd = std::fs::read_dir(&cfg.runs).map_err(|e| format!("ARGUS_RUNS: {e}"))?;
    for ent in rd.flatten() {
        let path = ent.path();
        if path.extension().and_then(|s| s.to_str()) != Some("log") || !path.is_file() {
            continue;
        }
        let mtime = ent
            .metadata()
            .and_then(|m| m.modified())
            .unwrap_or(std::time::UNIX_EPOCH);
        if best.as_ref().map(|(t, _)| mtime > *t).unwrap_or(true) {
            best = Some((mtime, path));
        }
    }
    best.map(|(_, p)| p)
        .ok_or_else(|| "no logs in ARGUS_RUNS".into())
}

struct MapBars {
    lava_delta: i32,
    stall_ratio: f64,
    engage_ratio: f64,
}

fn bars_for(map: Option<&str>) -> MapBars {
    match map.map(|s| s.to_ascii_lowercase()).as_deref() {
        Some("dm2") => MapBars {
            lava_delta: 3,
            stall_ratio: 1.30,
            engage_ratio: 0.65,
        },
        Some("dm3") => MapBars {
            lava_delta: 3,
            stall_ratio: 1.35,
            engage_ratio: 0.50,
        },
        _ => MapBars {
            lava_delta: 3,
            stall_ratio: 1.25,
            engage_ratio: 0.70,
        },
    }
}

pub fn compare_briefs(a: MatchBrief, b: MatchBrief) -> CompareReport {
    let mut gates = Vec::new();
    let bars = bars_for(b.map.as_deref().or(a.map.as_deref()));

    let lava_delta = b.totals.lava_deaths as f64 - a.totals.lava_deaths as f64;
    gates.push(Gate {
        name: "lava_deaths".into(),
        pass: lava_delta <= bars.lava_delta as f64
            && b.totals.lava_deaths <= a.totals.lava_deaths.max(3) + bars.lava_delta,
        a: a.totals.lava_deaths as f64,
        b: b.totals.lava_deaths as f64,
        note: if lava_delta > bars.lava_delta as f64 {
            "lava/slime deaths jumped; hazard guard likely broken".into()
        } else if b.totals.lava_deaths < a.totals.lava_deaths {
            "fewer lava deaths".into()
        } else {
            format!(
                "lava deaths at parity ({})",
                b.totals.lava_rule.as_deref().unwrap_or("z_fallback")
            )
        },
    });

    let stall_a = a.totals.stalls.max(1) as f64;
    let stall_ratio = b.totals.stalls as f64 / stall_a;
    gates.push(Gate {
        name: "stall_parity".into(),
        pass: stall_ratio <= bars.stall_ratio,
        a: a.totals.stalls as f64,
        b: b.totals.stalls as f64,
        note: if stall_ratio > 1.25 {
            format!("stalls up {:.0}%", (stall_ratio - 1.0) * 100.0)
        } else if stall_ratio < 0.85 {
            format!("stalls down {:.0}%", (1.0 - stall_ratio) * 100.0)
        } else {
            "stalls at parity".into()
        },
    });

    let eng_a = a.totals.engages.max(1) as f64;
    let eng_ratio = b.totals.engages as f64 / eng_a;
    gates.push(Gate {
        name: "engagements".into(),
        pass: eng_ratio >= bars.engage_ratio,
        a: a.totals.engages as f64,
        b: b.totals.engages as f64,
        note: if eng_ratio < bars.engage_ratio {
            "engagements collapsed; combat or fire-button regression".into()
        } else if eng_ratio > 1.15 {
            "more engagements".into()
        } else {
            "engagements at parity".into()
        },
    });

    gates.push(Gate {
        name: "frags_positive".into(),
        pass: b.totals.all_frags_positive || b.totals.frags >= a.totals.frags,
        a: a.totals.frags as f64,
        b: b.totals.frags as f64,
        note: if !b.totals.all_frags_positive && b.totals.frags < 0 {
            "a bot finished with negative frags".into()
        } else {
            "frag board healthy".into()
        },
    });

    gates.push(Gate {
        name: "kd_spread".into(),
        pass: b.totals.kd_spread <= a.totals.kd_spread.max(6) + 2,
        a: a.totals.kd_spread as f64,
        b: b.totals.kd_spread as f64,
        note: if b.totals.kd_spread > a.totals.kd_spread.max(6) + 2 {
            "K/D spread widened; one bot is dominating or starving".into()
        } else {
            "K/D spread tight".into()
        },
    });

    // statues are the defect class humans notice first, and it rode
    // green verdicts for three tapes before the west-pad session:
    // the review battery saw the freezes but no gate could fail on
    // them. Fail on any under-fire freeze, on a 10 s+ statue the
    // baseline does not have, or on the count clearly growing.
    let fz_pass = b.totals.freeze_underfire == 0
        && (b.totals.freeze_max_sec < 10.0
            || b.totals.freeze_max_sec <= a.totals.freeze_max_sec + 2.0)
        && b.totals.freezes <= a.totals.freezes + 2;
    gates.push(Gate {
        name: "freezes".into(),
        pass: fz_pass,
        a: a.totals.freeze_max_sec,
        b: b.totals.freeze_max_sec,
        note: if b.totals.freeze_underfire > 0 {
            "a bot took damage while frozen - free frag for a human".into()
        } else if !fz_pass && b.totals.freeze_max_sec >= 10.0 {
            format!(
                "a {:.1} s statue the baseline does not have",
                b.totals.freeze_max_sec
            )
        } else if !fz_pass {
            format!(
                "freezes {} vs baseline {}",
                b.totals.freezes, a.totals.freezes
            )
        } else if b.totals.freezes == 0 {
            "no statues".into()
        } else {
            format!(
                "{} bounded freeze(s), longest {:.1} s",
                b.totals.freezes, b.totals.freeze_max_sec
            )
        },
    });

    let cover_a = a.totals.cover.max(1) as f64;
    let cover_ratio = b.totals.cover as f64 / cover_a;
    gates.push(Gate {
        name: "coverage".into(),
        pass: cover_ratio >= 0.80,
        a: a.totals.cover as f64,
        b: b.totals.cover as f64,
        note: if cover_ratio < 0.80 {
            "map coverage dropped".into()
        } else {
            "coverage at parity".into()
        },
    });

    let hard_fail = gates.iter().any(|g| {
        !g.pass
            && matches!(
                g.name.as_str(),
                "lava_deaths" | "stall_parity" | "engagements" | "freezes"
            )
    });
    let any_fail = gates.iter().any(|g| !g.pass);
    let improved = !hard_fail
        && ((b.totals.lava_deaths < a.totals.lava_deaths)
            || (b.totals.stalls as f64) < stall_a * 0.85
            || eng_ratio > 1.15
            || (b.totals.frags > a.totals.frags && b.totals.all_frags_positive));

    let verdict = if hard_fail {
        Verdict::Regressed
    } else if any_fail {
        Verdict::Mixed
    } else if improved {
        Verdict::Improved
    } else {
        Verdict::Parity
    };

    let mut findings = Vec::new();
    for g in &gates {
        if !g.pass {
            findings.push(format!("{}: {}", g.name, g.note));
        }
    }
    for h in &b.hotspots {
        if let Some(known) = &h.known {
            findings.push(format!(
                "hotspot {} x{count} at {x:.0} {y:.0} {z:.0}: {note}",
                known,
                count = h.count,
                x = h.x,
                y = h.y,
                z = h.z,
                note = h.note.as_deref().unwrap_or("")
            ));
        }
    }
    if findings.is_empty() {
        findings.push("no gate failures; movement and combat look like the baseline".into());
    }

    let next_steps = suggest_next(&b, Some(&gates));

    let headline = format!(
        "{:?}: lava {}→{}, stalls {}→{}, engages {}→{}, frags {}→{}",
        verdict,
        a.totals.lava_deaths,
        b.totals.lava_deaths,
        a.totals.stalls,
        b.totals.stalls,
        a.totals.engages,
        b.totals.engages,
        a.totals.frags,
        b.totals.frags
    );

    CompareReport {
        verdict,
        headline,
        gates,
        findings,
        next_steps,
        a,
        b,
        scaled: false,
        scale_note: None,
    }
}

fn scale_i32(v: i32, k: f64) -> i32 {
    (v as f64 * k).round() as i32
}

fn scale_u32(v: u32, k: f64) -> u32 {
    (v as f64 * k).round() as u32
}

/// Scale count totals to a target duration. Rates (speed, K/D spread) stay put.
pub fn scale_brief_to_duration(mut brief: MatchBrief, target_sec: f64) -> MatchBrief {
    let src = brief.totals.duration_sec.max(1.0);
    let k = target_sec / src;
    brief.totals.duration_sec = target_sec;
    brief.totals.stalls = scale_i32(brief.totals.stalls, k);
    brief.totals.goals = scale_i32(brief.totals.goals, k);
    brief.totals.frags = scale_i32(brief.totals.frags, k);
    brief.totals.deaths = scale_i32(brief.totals.deaths, k);
    brief.totals.player_kills = scale_i32(brief.totals.player_kills, k);
    brief.totals.world_deaths = scale_i32(brief.totals.world_deaths, k);
    brief.totals.lava_deaths = scale_i32(brief.totals.lava_deaths, k);
    brief.totals.engages = scale_u32(brief.totals.engages, k);
    brief.totals.hazards = scale_u32(brief.totals.hazards, k);
    brief.totals.abandons = scale_u32(brief.totals.abandons, k);
    brief.totals.routefails = scale_u32(brief.totals.routefails, k);
    brief.totals.weapons = scale_u32(brief.totals.weapons, k);
    brief.totals.cover = ((brief.totals.cover as f64) * k).round() as usize;
    brief.totals.freezes = scale_u32(brief.totals.freezes, k);
    brief.totals.mover_waits = scale_u32(brief.totals.mover_waits, k);
    brief.totals.boards = scale_u32(brief.totals.boards, k);
    // freeze_max_sec and freeze_underfire are severities, not rates:
    // a 15 s statue is a 15 s statue in any match length
    brief
}

/// Compare two briefs. When durations differ by more than 20%, scale A to B
/// so a 30 s experiment is not judged as an engagement collapse vs 185 s.
pub fn compare_briefs_scaled(a: MatchBrief, b: MatchBrief) -> CompareReport {
    let da = a.totals.duration_sec;
    let db = b.totals.duration_sec;
    if da > 1.0 && db > 1.0 && ((da / db) - 1.0).abs() > 0.20 {
        let a2 = scale_brief_to_duration(a, db);
        let mut report = compare_briefs(a2, b);
        report.scaled = true;
        report.scale_note = Some(format!(
            "baseline counts scaled from {da:.0}s to {db:.0}s so a short experiment is comparable"
        ));
        report
    } else {
        compare_briefs(a, b)
    }
}

pub fn compare_runs(
    cfg: &Config,
    log_a: &str,
    log_b: &str,
    map_hint: Option<&str>,
) -> Result<CompareReport, String> {
    compare_runs_inner(cfg, log_a, log_b, map_hint, false)
}

/// Same as compare_runs, but scale counts when the two tapes have different lengths.
pub fn compare_runs_scaled(
    cfg: &Config,
    log_a: &str,
    log_b: &str,
    map_hint: Option<&str>,
) -> Result<CompareReport, String> {
    compare_runs_inner(cfg, log_a, log_b, map_hint, true)
}

fn compare_runs_inner(
    cfg: &Config,
    log_a: &str,
    log_b: &str,
    map_hint: Option<&str>,
    scale: bool,
) -> Result<CompareReport, String> {
    let a = brief_run(cfg, log_a, map_hint)?;
    let b = brief_run(cfg, log_b, map_hint)?;
    let mut report = if scale {
        compare_briefs_scaled(a, b)
    } else {
        compare_briefs(a, b)
    };
    for step in &mut report.next_steps {
        step.look_at = crate::qc_index::look_at(cfg, &step.look_at);
    }
    Ok(report)
}

fn killer_matrix(tape: &MatchTape) -> BTreeMap<String, u32> {
    let mut out = BTreeMap::new();
    for d in &tape.deaths {
        *out.entry(format!("{}>{}", d.killer, d.victim)).or_insert(0) += 1;
    }
    out
}

fn count_event_rest(tape: &MatchTape, verb: &str) -> BTreeMap<String, u32> {
    let mut out = BTreeMap::new();
    for ev in &tape.events {
        if ev.verb != verb {
            continue;
        }
        let key = ev
            .rest
            .split_whitespace()
            .next()
            .unwrap_or("(none)")
            .to_string();
        if key.is_empty() {
            continue;
        }
        *out.entry(key).or_insert(0) += 1;
    }
    out
}

pub fn suggest_next(brief: &MatchBrief, gates: Option<&[Gate]>) -> Vec<NextStep> {
    let mut steps = Vec::new();
    let lava_fail = gates
        .map(|g| g.iter().any(|x| x.name == "lava_deaths" && !x.pass))
        .unwrap_or(false);
    if lava_fail || brief.totals.lava_deaths >= 4 {
        steps.push(NextStep {
            priority: 1,
            area: "hazard".into(),
            look_at: "src/argus.qc Argus_MoveHazard / brink deflection".into(),
            why: format!(
                "{} lava/slime deaths (world, {}); the 2026-08-14 guard should keep dm4 near 2-7 per 185s",
                brief.totals.lava_deaths,
                brief.totals.lava_rule.as_deref().unwrap_or("z_fallback")
            ),
        });
    }
    if brief.hotspots.iter().any(|h| h.known.is_some()) {
        steps.push(NextStep {
            priority: 2,
            area: "stalls".into(),
            look_at: "src/argus.qc hazard deflection dither at walkway corners".into(),
            why: "chronic dm4 cells around '200 -900 24' and '700 -800 -200' are still hot".into(),
        });
    }
    let engage_fail = gates
        .map(|g| g.iter().any(|x| x.name == "engagements" && !x.pass))
        .unwrap_or(false);
    if engage_fail || (brief.totals.engages == 0 && brief.totals.duration_sec >= 30.0) {
        steps.push(NextStep {
            priority: 1,
            area: "combat".into(),
            look_at: "src/argus.qc perception find() / button0 hold / W_FireLightning".into(),
            why: "engagements collapsed or never started; historically this was the fire-button bug".into(),
        });
    }
    if brief.totals.weapons == 0 && brief.totals.duration_sec >= 60.0 {
        steps.push(NextStep {
            priority: 2,
            area: "items".into(),
            look_at: "src/items.qc weapon_touch FL_CLIENT guard (must admit ar_isbot)".into(),
            why: "no ARGEVT weapon lines; bots may be stuck on spawn shotguns".into(),
        });
    }
    let quad = *brief.goals.get("item_artifact_super_damage").unwrap_or(&0);
    if quad >= 3 && brief.totals.routefails >= 3 {
        steps.push(NextStep {
            priority: 3,
            area: "nav".into(),
            look_at: "src/argus.qc Argus_BotCanRJ / ARGEVT rjump (dm4 rocket-jump pad 142->56)".into(),
            why: format!(
                "quad goalled {quad} times with {} routefails; pad exists — check rjump events and the RL/health toll",
                brief.totals.routefails
            ),
        });
    }
    if brief.mode_share.routed < 0.15
        && brief.mode_share.seeking > 0.50
        && brief.map.is_some()
        && brief.totals.duration_sec >= 30.0
    {
        steps.push(NextStep {
            priority: 2,
            area: "nav".into(),
            look_at: "src/argus_nav_dispatch.qc and the per-map argus_nav_<map>.qc".into(),
            why: format!(
                "only {:.0}% time in routed mode 2; dispatcher or graph may have missed this map",
                brief.mode_share.routed * 100.0
            ),
        });
    }
    if !brief.totals.all_frags_positive && brief.totals.lava_deaths == 0 && brief.totals.duration_sec >= 60.0
    {
        steps.push(NextStep {
            priority: 3,
            area: "parity".into(),
            look_at: "src/argus.qc max_health / T_Heal / Argus_CheckPowerups".into(),
            why: "a bot finished at or below zero frags without a lava spike; check healing and powerup expiry".into(),
        });
    }
    steps.sort_by_key(|s| s.priority);
    steps.truncate(5);
    steps
}

pub fn attach_nav(cfg: &Config, brief: &mut MatchBrief) {
    let Some(map) = brief.map.as_deref() else {
        return;
    };
    let path = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let Ok(text) = std::fs::read_to_string(&path) else {
        return;
    };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else {
        return;
    };
    let Some(nodes) = v.get("nodes").and_then(|n| n.as_array()) else {
        return;
    };
    let pts: Vec<(f64, f64, f64)> = nodes
        .iter()
        .filter_map(|n| {
            let a = n.as_array()?;
            Some((a.first()?.as_f64()?, a.get(1)?.as_f64()?, a.get(2)?.as_f64()?))
        })
        .collect();
    if pts.is_empty() {
        return;
    }
    for h in &mut brief.hotspots {
        let mut best = None;
        for (i, (x, y, z)) in pts.iter().enumerate() {
            let d = (h.x - x).hypot(h.y - y).hypot(h.z - z);
            if best.map(|(_, bd)| d < bd).unwrap_or(true) {
                best = Some((i as u32, d));
            }
        }
        if let Some((i, d)) = best {
            h.nearest_node = Some(i);
            h.nearest_dist = Some(d);
        }
    }
}

fn attach_atlas(cfg: &Config, brief: &mut MatchBrief, hull: Option<&crate::bsp::Hull0>) {
    let Some(map) = brief.map.clone() else {
        return;
    };
    let Ok(atlas) = crate::cartograph::cartograph(cfg, &map) else {
        return;
    };
    for h in &mut brief.hotspots {
        let mut best: Option<(String, f64)> = None;
        for item in atlas
            .items
            .iter()
            .filter(|i| matches!(i.kind.as_str(), "weapon" | "armor" | "health" | "powerup" | "ammo"))
        {
            let Some(o) = item.origin else { continue };
            let d = ((h.x - o[0] as f64).powi(2)
                + (h.y - o[1] as f64).powi(2)
                + (h.z - o[2] as f64).powi(2))
            .sqrt();
            if d < 192.0 && best.as_ref().map(|(_, bd)| d < *bd).unwrap_or(true) {
                best = Some((item.classname.clone(), d));
            }
        }
        if let Some((name, d)) = best {
            h.nearest_item = Some(name);
            h.nearest_item_dist = Some(d);
        }
        h.cause = hotspot_cause(&atlas.door_aabbs, &atlas.plat_aabbs, hull, h.x, h.y, h.z);
    }
    brief.goal_reach = brief
        .goals
        .iter()
        .filter_map(|(cls, n)| {
            let c = atlas.control.iter().find(|c| &c.classname == cls)?;
            Some(GoalReach {
                classname: cls.clone(),
                times: *n,
                reach: c.reach.clone(),
                nearest_node: c.nearest_node,
                band: c.band.clone(),
            })
        })
        .collect();
    // the tape is ground truth and the atlas is a theory: when the
    // two disagree, say so instead of letting the labels stand (the
    // item_eye bug briefed 11 of 12 dm4 control items off_graph on a
    // map whose tapes route 57% of the time, and nothing shouted)
    let evidence = reach_evidence_flags(&brief.goal_reach, &brief.events, &brief.mode_share);
    let contradicted = !evidence.is_empty() && evidence[0].contains("CONTRADICTED");
    brief.flags.extend(evidence);
    if !contradicted
        && brief.goal_reach.iter().any(|g| g.reach == "rocket_jump" || g.reach == "off_graph")
    {
        brief.flags.push(
            "bots goaled an item the nav graph cannot walk to; expect routefail, not a stall loop"
                .into(),
        );
    }
    if atlas.control.iter().any(|c| c.elevated && c.classname.contains("super_damage"))
        && *brief.goals.get("item_artifact_super_damage").unwrap_or(&0) >= 2
        && !brief.next_steps.iter().any(|s| s.look_at.contains("rocket-jump"))
    {
        brief.flags.push(
            "bots are goaling elevated quad; dm4 pad is 142->56 — look for ARGEVT rjump, not a stall loop".into(),
        );
    }
    for line in atlas.implications.iter().take(2) {
        if !brief.flags.iter().any(|f| f == line) {
            brief.flags.push(line.clone());
        }
    }
}

/// Classify a hotspot by its geometric neighbourhood: within a door
/// brush, inside a plat's swept column (the compiled AABB is the TOP
/// position, so the column extends well below it), or beside lava.
/// First match wins - a plat over lava is a plat problem first.
fn hotspot_cause(
    doors: &[([f32; 3], [f32; 3])],
    plats: &[([f32; 3], [f32; 3])],
    hull: Option<&crate::bsp::Hull0>,
    x: f64,
    y: f64,
    z: f64,
) -> Option<String> {
    let inside = |mins: [f32; 3], maxs: [f32; 3], pad_xy: f64, pad_dn: f64, pad_up: f64| {
        x >= mins[0] as f64 - pad_xy
            && x <= maxs[0] as f64 + pad_xy
            && y >= mins[1] as f64 - pad_xy
            && y <= maxs[1] as f64 + pad_xy
            && z >= mins[2] as f64 - pad_dn
            && z <= maxs[2] as f64 + pad_up
    };
    if doors.iter().any(|(mn, mx)| inside(*mn, *mx, 48.0, 32.0, 48.0)) {
        return Some("door".into());
    }
    if plats.iter().any(|(mn, mx)| inside(*mn, *mx, 64.0, 320.0, 72.0)) {
        return Some("plat_column".into());
    }
    if hull.is_some() {
        // ring probe one step out and below: the cell sits on a brink
        // when any neighbour reads lava a body-length down
        for (dx, dy) in [
            (64.0, 0.0),
            (-64.0, 0.0),
            (0.0, 64.0),
            (0.0, -64.0),
            (45.0, 45.0),
            (45.0, -45.0),
            (-45.0, 45.0),
            (-45.0, -45.0),
        ] {
            // two depths: a walkway lip sits just above the lava, a
            // pit-floor cell stands a body-length or more over it
            if crate::bsp::death_is_lava(hull, x + dx, y + dy, z - 40.0)
                || crate::bsp::death_is_lava(hull, x + dx, y + dy, z - 104.0)
            {
                return Some("lava_edge".into());
            }
        }
    }
    None
}

/// Tape-vs-atlas referee, pure so it is testable: the labels claim
/// reachability, the route/routefail events measure it.
fn reach_evidence_flags(
    goal_reach: &[GoalReach],
    events: &BTreeMap<String, u32>,
    mode_share: &ModeShare,
) -> Vec<String> {
    let off = goal_reach.iter().filter(|g| g.reach == "off_graph").count();
    let routes = *events.get("route").unwrap_or(&0);
    let fails = *events.get("routefail").unwrap_or(&0);
    let mut out = Vec::new();
    if off >= 3 && routes >= 30 && (fails as f64) < 0.15 * routes as f64 && mode_share.routed >= 0.35
    {
        out.push(format!(
            "atlas reach labels CONTRADICTED by tape evidence: {off} goaled control items read off_graph yet the match routed {:.0}% of the time ({fails} fails in {routes} routes) - suspect the reach classifier or a stale nav cache, not the map; tools/argus_reach.py is the referee",
            mode_share.routed * 100.0
        ));
    } else if off <= 1 && routes >= 20 && fails as f64 > 0.5 * routes as f64 {
        out.push(format!(
            "routing collapses ({fails} fails in {routes} routes) despite walkable atlas labels - the runtime graph disagrees with the atlas; run tools/argus_reach.py for the directed-reach numbers"
        ));
    }
    out
}

/// Graph utilisation from the tape: which nodes carried traffic, and
/// whether each typed-link family in the graph actually fired.
pub fn attach_coverage(cfg: &Config, tape: &MatchTape, brief: &mut MatchBrief) {
    let Some(map) = brief.map.as_deref() else {
        return;
    };
    let path = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let Ok(text) = std::fs::read_to_string(&path) else {
        return;
    };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else {
        return;
    };
    let Some(nodes) = v.get("nodes").and_then(|n| n.as_array()) else {
        return;
    };
    let pts: Vec<(f64, f64, f64)> = nodes
        .iter()
        .filter_map(|n| {
            let a = n.as_array()?;
            Some((a.first()?.as_f64()?, a.get(1)?.as_f64()?, a.get(2)?.as_f64()?))
        })
        .collect();
    if pts.is_empty() {
        return;
    }
    let mut visited = vec![false; pts.len()];
    for rec in tape.samples.values() {
        for s in rec {
            for (i, p) in pts.iter().enumerate() {
                if !visited[i] {
                    let dx = s.pos.x - p.0;
                    let dy = s.pos.y - p.1;
                    let dz = s.pos.z - p.2;
                    if dx * dx + dy * dy + dz * dz < 96.0 * 96.0 {
                        visited[i] = true;
                    }
                }
            }
        }
    }
    let visited_n = visited.iter().filter(|v| **v).count();
    let never: Vec<u32> = visited
        .iter()
        .enumerate()
        .filter(|(_, v)| !**v)
        .map(|(i, _)| i as u32)
        .take(12)
        .collect();
    let mut typed = BTreeMap::new();
    let mut dormant = Vec::new();
    for (key, verb) in [
        ("rjlinks", "rjump"),
        ("liftlinks", "board"),
        ("swimlinks", "swim"),
        ("trainlinks", "train"),
        ("sprintlinks", ""),
    ] {
        let n = v.get(key).and_then(|a| a.as_array()).map(|a| a.len()).unwrap_or(0);
        if n == 0 {
            continue;
        }
        let fired = if verb.is_empty() {
            None
        } else {
            Some(*brief.events.get(verb).unwrap_or(&0))
        };
        let line = match fired {
            Some(f) => format!("{n} link(s), {f} {verb} event(s)"),
            None => format!("{n} link(s), no runtime verb yet"),
        };
        if fired == Some(0) && brief.totals.duration_sec >= 120.0 {
            dormant.push(format!("{key} ({n})"));
        }
        typed.insert(key.trim_end_matches("links").to_string(), line);
    }
    if !dormant.is_empty() {
        brief.flags.push(format!(
            "typed links never fired this tape: {} - dormant system or unreachable pads",
            dormant.join(", ")
        ));
    }
    brief.nav_coverage = Some(NavCoverage {
        nodes: pts.len(),
        visited: visited_n,
        pct: (100 * visited_n / pts.len().max(1)) as u32,
        never_visited_sample: never,
        typed_links: typed,
    });
}

fn is_lava(d: &DeathEvent, hull: Option<&crate::bsp::Hull0>) -> bool {
    d.killer.eq_ignore_ascii_case("world")
        && crate::bsp::death_is_lava(hull, d.pos.x, d.pos.y, d.pos.z)
}

fn cluster_hotspots(
    tape: &MatchTape,
    map: Option<&str>,
    hull: Option<&crate::bsp::Hull0>,
) -> Vec<Hotspot> {
    let mut cells: BTreeMap<(i32, i32, i32, String), (u32, Pos)> = BTreeMap::new();
    let mut bump = |kind: &str, p: Pos| {
        let key = (
            (p.x / CELL).floor() as i32,
            (p.y / CELL).floor() as i32,
            (p.z / CELL).floor() as i32,
            kind.to_string(),
        );
        let e = cells.entry(key).or_insert((0, p));
        e.0 += 1;
    };

    for d in &tape.deaths {
        if is_lava(d, hull) {
            bump("lava", d.pos);
        } else if d.killer.eq_ignore_ascii_case("world") {
            bump("world_death", d.pos);
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
        if matches!(ev.verb.as_str(), "hazard" | "abandon" | "routefail") {
            if let Some(p) = ev.pos {
                bump(&ev.verb, p);
            }
        }
    }

    let mut out: Vec<Hotspot> = cells
        .into_iter()
        .filter(|(_, (n, _))| *n >= 2)
        .map(|((_, _, _, kind), (count, p))| {
            let known = map.and_then(|m| hit_known(m, p));
            Hotspot {
                kind,
                count,
                x: p.x,
                y: p.y,
                z: p.z,
                known: known.map(|k| k.name.to_string()),
                note: known.map(|k| k.note.to_string()),
                nearest_node: None,
                nearest_dist: None,
                nearest_item: None,
                nearest_item_dist: None,
                cause: None,
            }
        })
        .collect();
    out.sort_by(|a, b| b.count.cmp(&a.count));
    out.truncate(12);
    out
}

fn hit_known(map: &str, p: Pos) -> Option<&'static KnownSpot> {
    KNOWN.iter().find(|k| {
        k.map.eq_ignore_ascii_case(map) && {
            let dx = k.x - p.x;
            let dy = k.y - p.y;
            let dz = k.z - p.z;
            (dx * dx + dy * dy + dz * dz).sqrt() <= k.radius
        }
    })
}

fn mode_share(tape: &MatchTape) -> ModeShare {
    let mut seeking = 0.0;
    let mut combat = 0.0;
    let mut routed = 0.0;
    for rec in tape.samples.values() {
        for w in rec.windows(2) {
            let dt = (w[1].t - w[0].t).max(0.0);
            match w[0].mode {
                2 => routed += dt,
                1 => combat += dt,
                _ => seeking += dt,
            }
        }
    }
    let tot = (seeking + combat + routed).max(0.001);
    ModeShare {
        seeking: seeking / tot,
        combat: combat / tot,
        routed: routed / tot,
    }
}

fn flags(totals: &Totals, hotspots: &[Hotspot], map: Option<&str>) -> Vec<String> {
    let mut f = Vec::new();
    if totals.lava_deaths > 0 {
        let rule = totals.lava_rule.as_deref().unwrap_or("z_fallback");
        let how = if rule == "contents" {
            "hull-0 contents"
        } else {
            "z < -300 fallback"
        };
        f.push(format!(
            "{} lava/slime death(s) (world killer, {how})",
            totals.lava_deaths
        ));
    }
    if map == Some("dm4") && totals.lava_deaths >= 8 && totals.duration_sec >= 120.0 {
        f.push("dm4 lava deaths look pre-hazard-guard (was 32/185s before the 2026-08-14 fix)".into());
    }
    if !totals.all_frags_positive && totals.duration_sec >= 60.0 {
        f.push("not every bot finished with a positive frag count".into());
    }
    if totals.kd_spread >= 8 {
        f.push(format!("K/D spread is {}", totals.kd_spread));
    }
    if totals.engages == 0 && totals.duration_sec >= 30.0 {
        f.push("zero engagements; perception or fire path may be dead".into());
    }
    if totals.routefails as i32 > totals.goals && totals.goals > 0 {
        f.push("more routefails than goal completions".into());
    }
    for h in hotspots {
        if h.known.is_some() {
            f.push(format!(
                "known hotspot {} ({}, n={})",
                h.known.as_deref().unwrap_or(""),
                h.kind,
                h.count
            ));
        }
    }
    f
}

fn headline_one(totals: &Totals, flags: &[String], map: Option<&str>) -> String {
    let map = map.unwrap_or("unknown-map");
    let mut s = format!(
        "{map} {dur:.0}s: {frags} frags, {deaths} deaths ({lava} lava), {stalls} stalls, {goals} goals, {eng} engages, {haz} hazards, spread {spread}",
        dur = totals.duration_sec,
        frags = totals.frags,
        deaths = totals.deaths,
        lava = totals.lava_deaths,
        stalls = totals.stalls,
        goals = totals.goals,
        eng = totals.engages,
        haz = totals.hazards,
        spread = totals.kd_spread
    );
    if let Some(first) = flags.first() {
        s.push_str(". ");
        s.push_str(first);
    }
    s
}

#[derive(Debug, Clone, Serialize)]
pub struct SimReport {
    pub map: String,
    pub duration_sec: f64,
    pub kills: BTreeMap<String, i32>,
    pub deaths: BTreeMap<String, i32>,
    pub item_pickups: BTreeMap<String, u32>,
    pub nav_errors: Vec<String>,
    pub stalls: i32,
    pub routefails: u32,
    pub headline: String,
}

pub fn sim_report(brief: &MatchBrief) -> SimReport {
    let mut kills = BTreeMap::new();
    let mut deaths = BTreeMap::new();
    for b in &brief.bots {
        if let Some(f) = b.frags {
            kills.insert(b.name.clone(), f);
        }
        deaths.insert(b.name.clone(), b.deaths);
    }
    let mut nav_errors = Vec::new();
    if brief.totals.routefails > 0 {
        nav_errors.push(format!("{} routefail events", brief.totals.routefails));
    }
    if brief.totals.stalls > 0 {
        nav_errors.push(format!("{} stall counters (last ARGLOG)", brief.totals.stalls));
    }
    for h in brief.hotspots.iter().filter(|h| h.kind == "stall" || h.kind == "lava") {
        nav_errors.push(format!(
            "{} x{} at {:.0} {:.0} {:.0}",
            h.kind, h.count, h.x, h.y, h.z
        ));
    }
    SimReport {
        map: brief.map.clone().unwrap_or_default(),
        duration_sec: brief.totals.duration_sec,
        kills,
        deaths,
        item_pickups: brief.goals.clone(),
        nav_errors,
        stalls: brief.totals.stalls,
        routefails: brief.totals.routefails,
        headline: brief.headline.clone(),
    }
}

pub fn known_log_note(name: &str) -> Option<&'static str> {
    let base = name.rsplit(['/', '\\']).next().unwrap_or(name);
    match base {
        "ab_dm4_parity.log" => Some("v3.6 masquerade parity; first health-box heals"),
        "ab_dm4_B3.log" => Some("shipped hazard deflection (lava 32 -> 2)"),
        "ab_dm4_B.log" | "ab_dm4_B2.log" => Some("rejected dead-stop hazard variants"),
        "ab_dm4_button.log" => Some("fire-button fix; NG/SNG/LG actually fire"),
        "ab_dm4_weapons.log" | "ab_dm4_weapons2.log" => Some("weapon pickup and selection"),
        "ab_dm4_deathanim.log" => Some("PlayerDie death animations"),
        "ab_dm4_jumplinks.log" => Some("jump links; broken autofire still visible"),
        "ab_dm4_telefrag.log" => Some("spawn telefrag / spawn fog"),
        "ab_dm4_A.log" => Some("pre-hazard baseline"),
        "ab_dm4_water.log" => Some("v3.20 water+lift; current dm4 shipped baseline"),
        "ab_dm2_lava.log" => Some("dm2 slice 1 lava-graph; current dm2 baseline"),
        "ab_dm2_doortype.log" | "ab_dm2_doortype2.log" => {
            Some("dm2 typed door links + classname door fix (v3.35 probes)")
        }
        "ab_dm2_first.log" => Some("dm2 debut; pre-slice-1 (do not use as baseline)"),
        "ab_dm3_water.log" => Some("dm3 water+first lift rides; current dm3 baseline"),
        _ => None,
    }
}

pub const QUALITY_BARS: &str = "\
Argus A/B quality bars (from the project charter):

- lava/slime deaths are hull-0 contents at the death origin (and 24u below).
  z < -300 is the no-BSP fallback only; it misses dm2 lava at z about -35
  and miscounts some solid dm4 pit floors. Judge lava via this gate, not z.
- dm4: lava stay in band (~2-7 / 185s), stalls within 25%, engages >= 70% of A
- dm2: same lava delta, stalls within 30%, engages >= 65% (campaign map)
- dm3: stalls within 35%, engages >= 50% (still island-shattered)
- every bot should finish with a positive frag count
- K/D spread across equal bots should stay tight
- coverage and average speed should not crater
- routed mode 2 links are walk-verified; hazard deflections belong in mode 0/1

Key metrics: stalls, goals, K/D spread, coverage cells, avg speed, lava deaths, engagements.
";

#[cfg(test)]
mod tests {
    use super::*;

    fn log_a() -> String {
        "\
ARGUS init on dm4
ARGLOG Reap t 1.0 pos '0.0 0.0 24.0' spd 0 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGLOG Omi t 1.0 pos '100.0 0.0 24.0' spd 0 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t 10.0 pos '64.0 0.0 24.0' spd 200 yaw 0 mode 2 st 5 gl 8 hp 90 frg 4
ARGLOG Omi t 10.0 pos '100.0 64.0 24.0' spd 200 yaw 0 mode 2 st 5 gl 8 hp 80 frg 3
ARGEVT Reap engage Omi
ARGEVT Omi engage Reap
ARGEVT Reap death Omi pos '64.0 0.0 24.0'
".into()
    }

    fn log_lava() -> String {
        "\
ARGUS init on dm4
ARGLOG Reap t 1.0 pos '200.0 -900.0 24.0' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Omi t 1.0 pos '100.0 0.0 24.0' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t 2.0 pos '210.0 -910.0 24.0' spd 10 yaw 0 mode 0 st 8 gl 1 hp 50 frg -2
ARGLOG Omi t 2.0 pos '100.0 10.0 24.0' spd 10 yaw 0 mode 0 st 8 gl 1 hp 50 frg -1
ARGLOG Reap t 3.0 pos '205.0 -905.0 24.0' spd 5 yaw 0 mode 0 st 16 gl 1 hp 40 frg -2
ARGEVT Reap death world pos '12.0 260.0 -360.0'
ARGEVT Omi death world pos '8.0 250.0 -358.0'
ARGEVT Reap death world pos '10.0 255.0 -362.0'
ARGEVT Reap death world pos '11.0 256.0 -361.0'
ARGEVT Reap hazard
ARGEVT Reap hazard
".into()
    }

    #[test]
    fn brief_counts_lava_and_flags_dm4_pit() {
        let b = brief_text(&log_lava(), None);
        assert_eq!(b.map.as_deref(), Some("dm4"));
        assert_eq!(b.totals.lava_deaths, 4);
        assert_eq!(b.totals.world_deaths, 4);
        assert!(b.flags.iter().any(|f| f.contains("lava")));
        assert!(
            b.hotspots.iter().any(|h| h.known.as_deref() == Some("walkway_200_-900")),
            "hotspots: {:?}",
            b.hotspots
        );
        assert!(
            b.next_steps.iter().any(|s| s.area == "hazard"),
            "next_steps: {:?}",
            b.next_steps
        );
        assert!(b.kills.keys().any(|k| k.starts_with("world>")));
    }

    #[test]
    fn compare_flags_lava_and_stall_regression() {
        let a = brief_text(&log_a(), None);
        let b = brief_text(&log_lava(), None);
        let report = compare_briefs(a, b);
        assert_eq!(report.verdict, Verdict::Regressed);
        assert!(report.gates.iter().any(|g| g.name == "lava_deaths" && !g.pass));
        assert!(report.gates.iter().any(|g| g.name == "stall_parity" && !g.pass));
    }

    #[test]
    fn compare_same_log_is_parity() {
        let a = brief_text(&log_a(), None);
        let b = brief_text(&log_a(), None);
        let report = compare_briefs(a, b);
        assert_eq!(report.verdict, Verdict::Parity);
        assert!(report.gates.iter().all(|g| g.pass));
    }

    #[test]
    fn scaled_compare_does_not_flag_a_short_tape() {
        let mut a = brief_text(&log_a(), None);
        a.totals.duration_sec = 185.0;
        a.totals.engages = 52;
        a.totals.stalls = 51;
        a.totals.lava_deaths = 3;
        let mut b = brief_text(&log_a(), None);
        b.totals.duration_sec = 30.0;
        b.totals.engages = 8;
        b.totals.stalls = 8;
        b.totals.lava_deaths = 0;
        let raw = compare_briefs(a.clone(), b.clone());
        assert_eq!(
            raw.verdict,
            Verdict::Regressed,
            "unscaled 30s vs 185s should look like an engagement collapse"
        );
        let scaled = compare_briefs_scaled(a, b);
        assert!(scaled.scaled);
        let eng = scaled
            .gates
            .iter()
            .find(|g| g.name == "engagements")
            .unwrap();
        assert!(eng.pass, "scaled engagements should pass: {:?}", scaled.gates);
        assert_ne!(scaled.verdict, Verdict::Regressed);
        let lite = compare_lite(&scaled);
        assert_eq!(lite.verdict, scaled.verdict);
        assert!(lite.scale_note.is_some());
    }

    #[test]
    fn briefs_real_parity_log_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/ab_dm4_parity.log");
        if !path.exists() {
            return;
        }
        let brief = brief_path(&path, None).unwrap();
        assert_eq!(brief.map.as_deref(), Some("dm4"));
        assert!(brief.totals.duration_sec > 100.0);
        assert!(brief.totals.deaths > 0);
        assert!(brief.totals.engages > 0);
        assert!(brief.headline.contains("dm4"));

        let pre = path.with_file_name("ab_dm4_A.log");
        if pre.exists() {
            let a = brief_path(&pre, None).unwrap();
            let report = compare_briefs(a, brief);
            assert_eq!(
                report.verdict,
                Verdict::Improved,
                "hazard fix should beat pre-hazard baseline: {}",
                report.headline
            );
        }
    }

    #[test]
    fn real_v363_tape_catches_the_west_pad_statues_if_present() {
        // The escaped defect this gate exists for: Shane's 588 s
        // session had six 12.7-19.4 s statues at the west train pad,
        // one under fire, zero boards for its 13 train waits - and
        // every then-existing gate stayed green. This tape must trip
        // the freeze machinery forever.
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/shane_dm2_2026-08-20_v363.log");
        if !path.exists() {
            return;
        }
        let brief = brief_path(&path, None).unwrap();
        assert!(
            brief.totals.freezes >= 5,
            "expected the statue cluster, got {}",
            brief.totals.freezes
        );
        assert!(brief.totals.freeze_max_sec >= 14.0);
        assert!(
            brief.totals.freeze_underfire >= 1,
            "Carmack lost 48 hp standing still and must register"
        );
        assert!(brief
            .flags
            .iter()
            .any(|f| f.contains("freeze")), "brief must flag the statues");
    }

    #[test]
    fn cause_tagger_classifies_doors_plats_and_nothing() {
        let doors = vec![([100.0f32, 100.0, 0.0], [140.0f32, 200.0, 96.0])];
        let plats = vec![([500.0f32, 500.0, 200.0], [600.0f32, 600.0, 260.0])];
        // beside the door brush
        assert_eq!(
            hotspot_cause(&doors, &plats, None, 90.0, 150.0, 24.0),
            Some("door".into())
        );
        // deep below the plat's compiled (top) AABB: still the column
        assert_eq!(
            hotspot_cause(&doors, &plats, None, 550.0, 550.0, -60.0),
            Some("plat_column".into())
        );
        // open floor far from both, no hull: unclassified
        assert_eq!(hotspot_cause(&doors, &plats, None, 2000.0, 2000.0, 24.0), None);
    }

    #[test]
    fn reach_evidence_referee_judges_both_directions() {
        let gr = |reach: &str| GoalReach {
            classname: "x".into(),
            times: 5,
            reach: reach.into(),
            nearest_node: None,
            band: None,
        };
        let mut ev = BTreeMap::new();
        ev.insert("route".to_string(), 100u32);
        ev.insert("routefail".to_string(), 5u32);
        let ms = ModeShare { seeking: 0.3, combat: 0.1, routed: 0.6 };
        // labels say unreachable, tape routes fine: labels are wrong
        let flags = reach_evidence_flags(
            &[gr("off_graph"), gr("off_graph"), gr("off_graph"), gr("walk")],
            &ev,
            &ms,
        );
        assert!(flags.iter().any(|f| f.contains("CONTRADICTED")), "{flags:?}");
        // labels say walkable, routing collapses: graph is wrong
        let mut ev2 = BTreeMap::new();
        ev2.insert("route".to_string(), 40u32);
        ev2.insert("routefail".to_string(), 30u32);
        let flags2 = reach_evidence_flags(&[gr("walk")], &ev2, &ms);
        assert!(flags2.iter().any(|f| f.contains("routing collapses")), "{flags2:?}");
        // agreement: silence
        assert!(reach_evidence_flags(&[gr("walk")], &ev, &ms).is_empty());
    }

    #[test]
    fn coverage_marks_visited_nodes_and_flags_dormant_links() {
        use crate::config::load_for_reads_from;
        use std::collections::HashMap;
        use std::fs;
        let root = std::env::temp_dir().join(format!("argus-mcp-cov-{}", std::process::id()));
        let src = root.join("src");
        fs::create_dir_all(&src).unwrap();
        fs::write(
            src.join("argus_nav_dmcov.qc.json"),
            r#"{"nodes":[[0,0,24],[500,500,24],[5000,5000,24]],"links":[],"rjlinks":[[0,1]],"teles":[]}"#,
        )
        .unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let log = "\
ARGUS init on dmcov
ARGLOG Reap t 1.0 pos '10.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t 130.0 pos '20.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGEVT Reap spawned
";
        let tape = parse_tape(log);
        let mut brief = brief_text(log, Some("dmcov"));
        attach_coverage(&cfg, &tape, &mut brief);
        let cov = brief.nav_coverage.expect("coverage attached");
        assert_eq!(cov.nodes, 3);
        assert_eq!(cov.visited, 1, "only the node under the samples");
        assert_eq!(cov.never_visited_sample, vec![1, 2]);
        assert!(cov.typed_links.get("rj").unwrap().contains("1 link"));
        assert!(
            brief.flags.iter().any(|f| f.contains("never fired")),
            "rj link with zero rjump events over 120s+ must flag: {:?}",
            brief.flags
        );
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn real_v372_tape_splits_human_tracks_out_of_bot_bands_if_present() {
        // The escaped distortion this split exists for: the second
        // 2026-08-26 marvel-test tape briefed Shane's four lava swims
        // into the dm4 bot lava band (priority-1 flag) and his 12.7 s
        // idle spell as the match's one statue. Human tracks are
        // review data; bands and gates judge the build.
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/shane_dm4_2026-08-26_v372.log");
        if !path.exists() {
            return;
        }
        let brief = brief_path(&path, None).unwrap();
        let human = brief.totals.human.as_ref().expect("tape has a human track");
        assert_eq!(human.names, vec!["player".to_string()]);
        assert_eq!(human.deaths, 13, "all 13 player deaths in the human block");
        assert_eq!(human.kills, 14, "player killed bots 14 times");
        assert_eq!(brief.totals.deaths, 64, "bot deaths exclude the human's 13");
        assert_eq!(
            brief.totals.freezes, 0,
            "the only statue was the human idling; bots froze zero times"
        );
        if brief.totals.lava_rule.as_deref() == Some("contents") {
            assert_eq!(human.world_deaths, 4, "Shane's four lava swims are his");
            assert!(
                brief.totals.lava_deaths <= 5,
                "bot lava must sit in band without the human's swims, got {}",
                brief.totals.lava_deaths
            );
        }

        // end to end through brief_run with the real tree: coverage
        // and cause tags ride the same tape when the root is present
        use crate::config::load_for_reads_from;
        use std::collections::HashMap;
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        if !root.join("src/argus_nav_dm4.qc.json").exists() {
            return;
        }
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let full = brief_run(&cfg, "shane_dm4_2026-08-26_v372", None).unwrap();
        let cov = full.nav_coverage.as_ref().expect("dm4 nav coverage");
        assert_eq!(cov.nodes, 145);
        assert!(
            cov.pct >= 60,
            "a 335 s 4-track dm4 match paints most of the graph, got {}%",
            cov.pct
        );
        assert!(
            full.hotspots.iter().any(|h| h.cause.as_deref() == Some("lava_edge")),
            "dm4 pit hotspots must tag lava_edge: {:?}",
            full.hotspots.iter().map(|h| (h.x, h.y, h.z, h.cause.clone())).collect::<Vec<_>>()
        );
    }

    #[test]
    fn control_board_and_aliases() {
        let b = brief_text(&log_a(), None);
        assert_eq!(b.kills.get("Omi>Reap"), Some(&1));

        use crate::config::load_for_reads_from;
        use std::collections::HashMap;
        use std::fs;
        let root = std::env::temp_dir().join(format!("argus-mcp-alias-{}", std::process::id()));
        let runs = root.join("runs");
        fs::create_dir_all(&runs).unwrap();
        fs::write(runs.join("ab_dm4_parity.log"), log_a()).unwrap();
        std::thread::sleep(std::time::Duration::from_millis(20));
        fs::write(runs.join("mcp_new.log"), log_lava()).unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let base = resolve_run_ref(&cfg, "baseline", Some("dm4")).unwrap();
        assert!(base.ends_with("ab_dm4_parity.log"));
        let latest = resolve_run_ref(&cfg, "latest", None).unwrap();
        assert!(latest.ends_with("mcp_new.log"));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn baselines_json_overrides_the_era_frozen_default() {
        let root = std::env::temp_dir().join(format!("argus-base-{}", std::process::id()));
        let runs = root.join("runs");
        std::fs::create_dir_all(&runs).unwrap();
        std::fs::write(
            runs.join("ab_dm4_fresh.log"),
            "ARGUS init on dm4\nARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
        )
        .unwrap();
        std::fs::write(runs.join("baselines.json"), r#"{"dm4": "ab_dm4_fresh"}"#).unwrap();
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = crate::config::load_for_reads_from(&env, &root).unwrap();
        let p = resolve_baseline(&cfg, Some("dm4")).unwrap();
        assert!(p.display().to_string().ends_with("ab_dm4_fresh.log"));
        // a named-but-missing baseline is a loud error, not a silent
        // fall-through to the era-frozen default
        std::fs::write(runs.join("baselines.json"), r#"{"dm4": "ab_dm4_gone"}"#).unwrap();
        assert!(resolve_baseline(&cfg, Some("dm4")).is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn dm2_style_lava_needs_hull0() {
        let log = "\
ARGUS init on dm2
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGEVT Reap death world pos '1937.0 -1650.0 -35.0'
";
        let fallback = brief_text(log, Some("dm2"));
        assert_eq!(fallback.totals.lava_deaths, 0, "z < -300 must not fire at z -35");
        assert_eq!(fallback.totals.lava_rule.as_deref(), Some("z_fallback"));

        let raw = crate::bsp::write_halfspace_bsp();
        let bsp = crate::bsp::parse_bsp29(&raw).unwrap();
        let counted = brief_tape_lava(&parse_tape(log), Some("dm2"), bsp.hull0.as_ref());
        assert_eq!(counted.totals.lava_deaths, 1);
        assert_eq!(counted.totals.lava_rule.as_deref(), Some("contents"));
    }
}
