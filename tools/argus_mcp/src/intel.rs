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
    /// Bot deaths landed by someone other than the player the victim was
    /// visibly fighting at the time (#383).
    pub third_party_deaths: i32,
    pub player_kills: i32,
    pub world_deaths: i32,
    pub lava_deaths: i32,
    pub engages: u32,
    pub hazards: u32,
    pub abandons: u32,
    pub routefails: u32,
    pub weapons: u32,
    /// battle-grabs (ARGEVT grab). Together with weapons this is
    /// acquisitions: the figure that shows contested-map consumption
    /// when gl (current-goal touches) looks starved.
    pub grabs: u32,
    /// weapon switches plus battle-grabs. gl counts only the goal
    /// the bot currently holds; a passer-by eating the prize
    /// invalidates the goalers and gl stays low while everyone is
    /// still armed. This is the honest "did they take stuff" count.
    pub acquisitions: u32,
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
    /// Total seconds lost to statues (#257). A count alone reads a
    /// tape where one bot did nothing for 76 per cent of the match as
    /// "1 freeze", beside a tape with five short ones. Duration is
    /// the thing that matters and the count was hiding it.
    #[serde(default, skip_serializing_if = "crate::intel::is_zero_f64")]
    pub freeze_total_sec: f64,
    /// freezes during which the bot lost 10+ hp: a bot being shot
    /// while standing still, the worst class a human can witness
    pub freeze_underfire: u32,
    /// typed-hop success accounting: lift/train waits vs actual
    /// boardings (ARGEVT board). A wait storm with zero boards means
    /// a pad or gate is geometrically broken, not merely slow.
    pub mover_waits: u32,
    pub boards: u32,
    /// Longest stretch a bot spent getting nowhere, at any speed
    /// (#272). Stalls and freezes both need low speed, so a bot
    /// oscillating inside a 220 unit box at 355 u/s scores zero on
    /// both while losing seven per cent of its match. Informational,
    /// not a gate: a fight or an item orbit looks the same.
    #[serde(default, skip_serializing_if = "crate::intel::is_zero_f64")]
    pub confine_max_sec: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub confine_note: Option<String>,
    /// Closest any two bots came to each other all tape (#279). Zero
    /// engagements on a map where nobody got within 900 units is a
    /// navigation result, not a dead fire path.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub closest_approach: Option<f64>,
    /// Present only when the tape carries human tracks (names with
    /// ARGLOG rows but no spawned/respawn). Every figure above is
    /// then BOT-only - bands, gates and flags are statements about
    /// the build, and a human's lava swims or idle spells are review
    /// data, not defects. The human's numbers live here instead.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub human: Option<HumanTracks>,
    /// Mean gap between a bot's telemetry rows. The server's frame
    /// period falls out of it (parse_arglog::tick_gap_mean), and with
    /// it the only question that decides whether two tapes describe
    /// the same game.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tick_gap_mean: Option<f64>,
    /// "listen" (about 71 Hz, what Shane plays), "dedicated_fast"
    /// (about 19 Hz) or "dedicated_slow" (about 14 to 15 Hz). Every
    /// per-frame constant in bot physics and the whole aim spring
    /// integrate differently in each.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tick_class: Option<String>,
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
    /// For routefail/stall clusters: directed reach (percent of the
    /// graph) from the cluster's nearest node. A routefail cluster
    /// with low reach is a DIRECTED SINK - the graph's fault, not
    /// the walking (the v3.69 dm2 storm signature, joined
    /// automatically instead of by a forensics session).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reach_pct: Option<u32>,
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
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub item_control: Vec<ItemControl>,
    /// The film, cut in: when runs/demos carries a .dem under the
    /// same stem as the tape, its brief (aim statistics, highlight
    /// reel, full-rate track summary) rides the match brief - the
    /// whole "played, review" ritual in one call.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub paired_demo: Option<crate::demo::DemoBrief>,
    /// Present only on a tape with human tracks: the row the player
    /// would recognise. Lab gates measure the build against other
    /// builds; this measures the game against the last time it was
    /// played, which is the only question Shane ever asks.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub human_scorecard: Option<HumanScorecard>,
}

/// One session, scored on what the player sees. Rates are per minute
/// of tape so sessions of different lengths compare directly.
#[derive(Debug, Clone, Serialize)]
pub struct HumanScorecard {
    pub minutes: f64,
    /// how often the bots killed the player, per minute
    pub bot_kills_human_pm: f64,
    /// how often the player killed a bot, per minute
    pub human_kills_pm: f64,
    /// the ratio the skill tiers are calibrated on: at skill 1 the
    /// bots should sit at 0.6 to 0.8 of the player's rate (he wins,
    /// narrowly), at skill 2 about parity
    pub threat_ratio: f64,
    pub stall_pm: f64,
    pub routefail_pm: f64,
    pub freezes: u32,
    pub freeze_max_sec: f64,
    /// unstick teleports. A bot vanishing and reappearing is a visible
    /// failure the scorecard must show, never a fix. The target is 0.
    pub unstick_warps: u32,
}

/// The item-clock scoreboard: how tightly the roster runs each major
/// item against its respawn clock. Visit entries (any track entering
/// 96u of the spawn point) spaced at about the respawn period mean
/// someone arrives as it pops - the "be early, not on time" economy
/// (v3.48 clocks + v3.66 pre-positioning) finally has a measure.
#[derive(Debug, Clone, Serialize)]
pub struct ItemControl {
    pub classname: String,
    pub visits: usize,
    pub median_gap_sec: f64,
    pub period_sec: f64,
    /// median_gap / period: about 1 is a tight clock, well under 1
    /// means early arrivals lapping the spawn, well over means the
    /// item sits unclaimed - a control gap on a prize is a flag
    pub tightness: f64,
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
    pub gate_card: String,
    pub gates: Vec<Gate>,
    pub findings: Vec<String>,
    pub next_steps: Vec<NextStep>,
    pub a: MatchBrief,
    pub b: MatchBrief,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub scaled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scale_note: Option<String>,
    /// The banded gates the verdict actually rests on: per metric, the
    /// control median, the candidate median and the band between them.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub band: Vec<BandGate>,
    /// Which run "baseline" actually resolved to (#273). Every gate
    /// in this report is a statement about that tape, and a baseline
    /// many builds old quietly turns ordinary drift into a verdict.
    /// Naming it is the difference between reading a regression and
    /// chasing one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub baseline_run: Option<String>,
    /// IQM, a bootstrap interval, a probability of improvement and a
    /// sequential-test call per gate. The band says whether to
    /// convict; this says how big the effect is and whether enough
    /// tapes have been run to say so at all.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub stats: Vec<MetricStat>,
    /// the metric this change was pre-registered to move. When set,
    /// only that gate can convict and the rest flag (#377).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub primary: Option<String>,
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
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub item_control: Vec<ItemControl>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub paired_demo: Option<crate::demo::DemoBrief>,
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
    pub gate_card: String,
    /// the run every gate here is measured against (#273)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub baseline_run: Option<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub scaled: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scale_note: Option<String>,
    pub gates: Vec<Gate>,
    pub findings: Vec<String>,
    pub next_steps: Vec<NextStep>,
    /// IQM, interval, probability of improvement and the
    /// sequential-test call per gate. The lite view carries these
    /// because they are the numbers worth quoting.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub stats: Vec<MetricStat>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub primary: Option<String>,
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
        item_control: b.item_control.clone(),
        paired_demo: b.paired_demo.clone(),
    }
}

pub fn compare_lite(r: &CompareReport) -> CompareLite {
    CompareLite {
        verdict: r.verdict,
        headline: r.headline.clone(),
        gate_card: r.gate_card.clone(),
        baseline_run: r.baseline_run.clone(),
        scaled: r.scaled,
        scale_note: r.scale_note.clone(),
        gates: r.gates.clone(),
        findings: r.findings.clone(),
        next_steps: r.next_steps.clone(),
        stats: r.stats.clone(),
        primary: r.primary.clone(),
        baseline: r.a.totals.clone(),
        candidate: r.b.totals.clone(),
        candidate_flags: r.b.flags.clone(),
        hotspots: r.b.hotspots.iter().take(5).cloned().collect(),
    }
}

/// Does the caller want CSV instead of JSON?
pub fn want_csv(format: Option<&str>) -> bool {
    format.map(|f| f.eq_ignore_ascii_case("csv")).unwrap_or(false)
}

/// A brief as text: scalars as `key,value`, then one CSV table per
/// tabular section.
///
/// Every large part of a brief is a table - the per-bot rows, the
/// hotspots, the kill matrix, the goal and weapon counts - and a
/// table as JSON repeats every field name on every row. CSV names
/// them once. Measured on a real dm4 tape it is about half the
/// bytes, which is the Datadog finding and the reason this exists.
///
/// JSON stays the default. An agent that wants to index into one
/// field should not have to parse a table, and the lite brief is
/// already small; this is for the full one and for the sections
/// that are genuinely rows.
pub fn brief_csv(b: &MatchBrief) -> String {
    let mut s = String::new();
    s.push_str(&format!("# {}\n", b.headline));
    if let Some(m) = &b.map {
        s.push_str(&format!("map,{m}\n"));
    }
    let t = &b.totals;
    s.push_str("key,value\n");
    for (k, v) in [
        ("duration_sec", format!("{:.1}", t.duration_sec)),
        ("stalls", t.stalls.to_string()),
        ("engages", t.engages.to_string()),
        ("lava_deaths", t.lava_deaths.to_string()),
        ("world_deaths", t.world_deaths.to_string()),
        ("freezes", t.freezes.to_string()),
        ("freeze_underfire", t.freeze_underfire.to_string()),
        ("cover", t.cover.to_string()),
        ("goals", t.goals.to_string()),
        ("frags", t.frags.to_string()),
        ("deaths", t.deaths.to_string()),
        ("third_party_deaths", t.third_party_deaths.to_string()),
        ("routefails", t.routefails.to_string()),
        ("hazards", t.hazards.to_string()),
        ("kd_spread", t.kd_spread.to_string()),
        ("avg_speed", format!("{:.1}", t.avg_speed)),
        ("tick_class", t.tick_class.clone().unwrap_or_default()),
    ] {
        s.push_str(&format!("{k},{v}\n"));
    }
    if !b.bots.is_empty() {
        s.push_str("\nbot,frags,deaths,goals,stalls,cover,avg_speed\n");
        for r in &b.bots {
            s.push_str(&format!(
                "{},{},{},{},{},{},{:.1}\n",
                r.name,
                r.frags.map(|f| f.to_string()).unwrap_or_default(),
                r.deaths,
                r.goals,
                r.stalls,
                r.cover,
                r.avg
            ));
        }
    }
    if !b.hotspots.is_empty() {
        s.push_str("\nkind,x,y,z,count,cause\n");
        for h in &b.hotspots {
            s.push_str(&format!(
                "{},{:.0},{:.0},{:.0},{},{}\n",
                h.kind,
                h.x,
                h.y,
                h.z,
                h.count,
                h.cause.clone().unwrap_or_default()
            ));
        }
    }
    if !b.kills.is_empty() {
        s.push_str("\nkiller_victim,n\n");
        for (k, v) in &b.kills {
            s.push_str(&format!("{k},{v}\n"));
        }
    }
    if !b.goals.is_empty() {
        s.push_str("\ngoal_class,n\n");
        for (k, v) in &b.goals {
            s.push_str(&format!("{k},{v}\n"));
        }
    }
    if !b.events.is_empty() {
        s.push_str("\nevent,n\n");
        for (k, v) in &b.events {
            s.push_str(&format!("{k},{v}\n"));
        }
    }
    for f in &b.flags {
        s.push_str(&format!("# flag: {f}\n"));
    }
    for n in &b.next_steps {
        s.push_str(&format!("# next[{}] {}: {}\n", n.priority, n.area, n.why));
    }
    s
}

/// A compare as text: the verdict and the findings, then the two
/// totals side by side and the banded gates as rows.
pub fn compare_csv(r: &CompareReport) -> String {
    let mut s = String::new();
    s.push_str(&format!("# {}\n", r.headline));
    if let Some(b) = &r.baseline_run {
        s.push_str(&format!("# baseline_run: {b}\n"));
    }
    for f in &r.findings {
        s.push_str(&format!("# {f}\n"));
    }
    if !r.band.is_empty() {
        s.push_str("\ngate,control_median,candidate_median,lo,hi,call\n");
        for g in &r.band {
            s.push_str(&format!(
                "{},{},{},{:.1},{:.1},{}\n",
                g.name, g.control_median, g.candidate_median, g.lo, g.hi, g.call
            ));
        }
    }
    if !r.stats.is_empty() {
        s.push_str("\nmetric,control_iqm,candidate_iqm,ci_lo,ci_hi,p_improve,sprt,bound\n");
        for m in &r.stats {
            let (lo, hi) = match m.ci {
                Some(c) => (format!("{:.2}", c.lo), format!("{:.2}", c.hi)),
                None => (String::new(), String::new()),
            };
            s.push_str(&format!(
                "{},{:.2},{:.2},{},{},{:.2},{:?},{:.1}\n",
                m.name,
                m.control_iqm,
                m.candidate_iqm,
                lo,
                hi,
                m.prob_improvement,
                m.sprt,
                m.sprt_bound
            ));
        }
    }
    s.push_str("\nmetric,baseline,candidate\n");
    let a = &r.a.totals;
    let b = &r.b.totals;
    for (k, x, y) in [
        ("stalls", a.stalls.to_string(), b.stalls.to_string()),
        ("engages", a.engages.to_string(), b.engages.to_string()),
        (
            "third_party_deaths",
            a.third_party_deaths.to_string(),
            b.third_party_deaths.to_string(),
        ),
        ("lava_deaths", a.lava_deaths.to_string(), b.lava_deaths.to_string()),
        ("freezes", a.freezes.to_string(), b.freezes.to_string()),
        ("cover", a.cover.to_string(), b.cover.to_string()),
        ("goals", a.goals.to_string(), b.goals.to_string()),
        ("frags", a.frags.to_string(), b.frags.to_string()),
        ("kd_spread", a.kd_spread.to_string(), b.kd_spread.to_string()),
    ] {
        s.push_str(&format!("{k},{x},{y}\n"));
    }
    s
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
    // An instrument is NEITHER a bot nor a human, and has to come
    // out of both sides at every site that splits them. Excluding
    // it from one only moves it to the other: the first cut of
    // this took the puppet out of the human tracks and put its
    // deaths into the bot world-death count and its standing still
    // into the bot freeze count, on eight tapes.
    let instruments = tape.instrument_names();
    let is_bot = |n: &str| !humans.contains(n) && !instruments.contains(n);
    let bot_rows: Vec<_> = summary.bots.iter().filter(|b| is_bot(&b.name)).collect();
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
    let mut third_party_deaths = 0;
    let mut h_deaths = 0;
    let mut h_world = 0;
    let mut h_lava = 0;
    let mut h_kills = 0;
    for d in &tape.deaths {
        let lava = d.killer.eq_ignore_ascii_case("world")
            && crate::bsp::death_is_lava(hull, d.pos.x, d.pos.y, d.pos.z);
        if instruments.contains(&d.victim) {
            continue;
        }
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
        if d.third_party {
            third_party_deaths += 1;
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
        .filter(|f| is_bot(&f.bot))
        .collect();
    let freeze_underfire = fz.iter().filter(|f| f.hp_drop >= 10.0).count() as u32;
    let freeze_max_sec = fz.first().map(|f| f.dur).unwrap_or(0.0);
    // 220 units and 5 seconds: wide enough that a corridor fight or a
    // pre-position orbit is not reported every tape, tight enough to
    // catch the dm2 oscillation that started this (#272).
    let cf: Vec<_> = tape
        .confinements(220.0, 5.0)
        .into_iter()
        .filter(|c| is_bot(&c.bot))
        .collect();

    let ev = |k: &str| *tape.event_counts.get(k).unwrap_or(&0);
    let tick_gap_mean = tape.tick_gap_mean();
    let tick_class = tick_gap_mean.map(|g| crate::parse_arglog::tick_class(g).to_string());
    let totals = Totals {
        duration_sec: duration,
        tick_gap_mean,
        tick_class,
        stalls,
        goals,
        frags,
        deaths,
        third_party_deaths,
        player_kills,
        world_deaths,
        lava_deaths,
        engages: ev("engage"),
        hazards: ev("hazard"),
        abandons: ev("abandon"),
        routefails: ev("routefail"),
        weapons: ev("weapon"),
        grabs: ev("grab"),
        acquisitions: ev("weapon") + ev("grab"),
        cover,
        avg_speed,
        kd_spread,
        all_frags_positive,
        lava_rule,
        freezes: fz.len() as u32,
        freeze_max_sec,
        freeze_total_sec: fz.iter().map(|f| f.dur).sum(),
        freeze_underfire,
        mover_waits: ev("lift") + ev("train"),
        boards: ev("board"),
        confine_max_sec: cf.first().map(|c| c.dur).unwrap_or(0.0),
        confine_note: cf.first().map(|c| {
            format!(
                "{} spent {:.1}s inside a 220u box at {:.0} u/s around ({:.0}, {:.0})",
                c.bot, c.dur, c.avg_spd, c.x, c.y
            )
        }),
        closest_approach: tape.closest_approach(),
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
    if let Some(note) = &tape.segment_note {
        // A tape that spans a level change is not one match, and the
        // wrong-map guard above cannot see it because both spawns
        // succeeded (#266). Say which segment was read, first.
        flags.insert(0, format!("LEVEL CHANGE: {note}"));
    }
    // A Quake player caps near 320 u/s. Anything far past that is a
    // parsing defect rather than a fast bot, and the level-change tape
    // printed 12,326 before anyone noticed. Cheap, independent of the
    // cause, and worth keeping whatever else changes.
    if totals.avg_speed > 400.0 {
        flags.insert(
            0,
            format!(
                "IMPOSSIBLE SPEED: average {:.0} u/s, and a Quake player caps near 320.                  This is a parsing defect, not a fast bot - judge NOTHING from this brief",
                totals.avg_speed
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
        item_control: Vec::new(),
        paired_demo: None,
        human_scorecard: None,
    };
    brief.human_scorecard = human_scorecard(tape, &brief.totals);
    brief.next_steps = suggest_next(&brief, None);
    brief.headline = headline_one(&brief.totals, &brief.flags, brief.map.as_deref());
    brief
}

/// Score a session the way the player experienced it.
///
/// Returns None on a botmatch tape: every figure here is about a human
/// being in the game, and a lab tape has none. Rates are per minute so
/// a 131 s session and a 465 s one compare directly.
fn human_scorecard(tape: &MatchTape, totals: &Totals) -> Option<HumanScorecard> {
    let h = totals.human.as_ref()?;
    let minutes = (totals.duration_sec / 60.0).max(1.0 / 60.0);
    let bot_kills_human = h.deaths - h.world_deaths;
    let per_min = |n: f64| (n / minutes * 10.0).round() / 10.0;
    let ratio = if h.kills > 0 {
        (bot_kills_human as f64 / h.kills as f64 * 100.0).round() / 100.0
    } else {
        0.0
    };
    Some(HumanScorecard {
        minutes: (minutes * 10.0).round() / 10.0,
        bot_kills_human_pm: per_min(bot_kills_human.max(0) as f64),
        human_kills_pm: per_min(h.kills.max(0) as f64),
        threat_ratio: ratio,
        stall_pm: per_min(totals.stalls as f64),
        routefail_pm: per_min(totals.routefails as f64),
        freezes: totals.freezes,
        freeze_max_sec: totals.freeze_max_sec,
        unstick_warps: *tape.event_counts.get("unstick").unwrap_or(&0),
    })
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

pub fn hull0_for_map(cfg: &Config, map: &str) -> Option<crate::bsp::Hull0> {
    // the third parse of the same file in one brief_run (#228); the
    // shared mtime cache turns it into a pointer clone
    let (path, _) = crate::cartograph::ingest_bsp(cfg, map).ok()?;
    crate::cartograph::read_bsp29_cached(&path).ok()?.hull0.clone()
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
    attach_item_control(cfg, &tape, &mut brief);
    attach_paired_demo(cfg, &path, &mut brief);
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
/// Every tape a map's baseline names. A value in `baselines.json` may
/// be one run name (the old form) or a list of them, which is the
/// band a candidate is judged against: three tapes narrow every gate
/// by 42 per cent against one (see `compare_band`).
pub fn baseline_band_for(cfg: &Config, map: &str) -> Vec<String> {
    let p = cfg.runs.join("baselines.json");
    let Ok(text) = std::fs::read_to_string(&p) else {
        return Vec::new();
    };
    let Ok(table) = serde_json::from_str::<std::collections::BTreeMap<String, serde_json::Value>>(&text)
    else {
        return Vec::new();
    };
    match table.get(&map.to_ascii_lowercase()) {
        Some(serde_json::Value::String(one)) => vec![one.clone()],
        Some(serde_json::Value::Array(many)) => many
            .iter()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect(),
        _ => Vec::new(),
    }
}

/// Every band in `baselines.json`, as (map, tapes).
///
/// A band is a set of tapes from ONE build on ONE map, which makes it
/// a same-build arm and therefore a measurement of the instrument's
/// own noise. `measure` reads them for exactly that, and reading the
/// file keeps the detection-limit table current as maps are
/// re-baselined instead of freezing a list in the source.
pub fn all_baseline_bands(cfg: &Config) -> Vec<(String, Vec<String>)> {
    all_baseline_bands_in(&cfg.runs)
}

/// The same, from a runs directory alone, so the corpus analysis
/// and its tests run without a configured lab.
pub fn all_baseline_bands_in(runs: &Path) -> Vec<(String, Vec<String>)> {
    let p = runs.join("baselines.json");
    let Ok(text) = std::fs::read_to_string(&p) else {
        return Vec::new();
    };
    let Ok(table) =
        serde_json::from_str::<std::collections::BTreeMap<String, serde_json::Value>>(&text)
    else {
        return Vec::new();
    };
    table
        .into_iter()
        .map(|(map, v)| {
            let runs = match v {
                serde_json::Value::String(one) => vec![one],
                serde_json::Value::Array(many) => {
                    many.iter().filter_map(|x| x.as_str().map(str::to_string)).collect()
                }
                _ => Vec::new(),
            };
            (map, runs)
        })
        .collect()
}

pub fn baseline_override_for(cfg: &Config, map: &str) -> Option<String> {
    baseline_band_for(cfg, map).into_iter().next()
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
    // Only dm4 may fall through to the historical parity tapes. Every
    // other map used to land here too, so a dm2 or e1m1 candidate was
    // judged against a dm4 tape with no warning.
    match map_hint {
        None => {
            return Err(
                "compare against 'baseline' needs a map: pass map=, or a candidate log whose                  header names one, so baselines.json can be consulted"
                    .into(),
            )
        }
        Some(m) if m.eq_ignore_ascii_case("dm4") => {
            for candidate in ["ab_dm4_parity", "ab_dm4_B3", "ab_dm4_A"] {
                if let Ok(p) = resolve_log(cfg, candidate) {
                    return Ok(p);
                }
            }
        }
        Some(_) => {}
    }
    Err(format!(
        "no baseline for {} - add it to runs/baselines.json",
        map_hint.unwrap_or("?")
    ))
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

pub fn is_zero_f64(v: &f64) -> bool {
    *v == 0.0
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

pub fn format_gate_card(
    map: Option<&str>,
    verdict: Verdict,
    gates: &[Gate],
    a_totals: &Totals,
    b_totals: &Totals,
    scaled: bool,
) -> String {
    let map_name = map.unwrap_or("unknown");
    let scale_tag = if scaled { " (scaled)" } else { "" };
    let title = format!("ARGUS A/B QUALITY GATES: {map_name} (baseline vs candidate){scale_tag}");

    let mut out = String::new();
    out.push_str("┌─────────────────────────────────────────────────────────────┐\n");
    out.push_str(&format!("│ {:<59} │\n", title));
    out.push_str("├──────────────────────────┬────────┬──────────────┬──────────┤\n");
    out.push_str("│ Metric                   │ Status │ Delta        │ Verdict  │\n");
    out.push_str("├──────────────────────────┼────────┼──────────────┼──────────┤\n");

    let mut add_row = |name: &str, status: &str, delta: &str, verd: &str| {
        out.push_str(&format!(
            "│ {:<24} │   {}   │ {:<12} │ {:<8} │\n",
            name, status, delta, verd
        ));
    };

    // 1. Lava deaths
    if let Some(g) = gates.iter().find(|x| x.name == "lava_deaths") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = format!("{:.0} vs {:.0}", g.a, g.b);
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Lava/Slime Deaths", status, &delta, verd);
    }

    // 2. Nav Stalls
    if let Some(g) = gates.iter().find(|x| x.name == "stall_parity") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = if g.a > 0.0 {
            format!("{:+.1}%", ((g.b - g.a) / g.a) * 100.0)
        } else {
            format!("{:.0} vs {:.0}", g.a, g.b)
        };
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Nav Stalls", status, &delta, verd);
    }

    // 3. Weapon Engages
    if let Some(g) = gates.iter().find(|x| x.name == "engagements") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = if g.a > 0.0 {
            format!("{:+.1}%", ((g.b - g.a) / g.a) * 100.0)
        } else {
            format!("{:.0} vs {:.0}", g.a, g.b)
        };
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Weapon Engages", status, &delta, verd);
    }

    // 4. Goal Pickups (gl)
    {
        let ga = a_totals.goals as f64;
        let gb = b_totals.goals as f64;
        let delta = if ga > 0.0 {
            format!("{:+.1}%", ((gb - ga) / ga) * 100.0)
        } else {
            format!("{:.0} vs {:.0}", ga, gb)
        };
        let (status, verd) = if gb >= ga {
            ("🟢", "PASS")
        } else if gb >= ga * 0.75 {
            ("🟡", "WARN")
        } else {
            ("🔴", "FAIL")
        };
        add_row("Goal Pickups (gl)", status, &delta, verd);
    }

    // 5. Frag Spread Balance
    if let Some(g) = gates.iter().find(|x| x.name == "frags_positive") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = format!("{:.0} vs {:.0}", g.a, g.b);
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Frag Spread Balance", status, &delta, verd);
    }

    // 6. K/D Spread Tightness
    if let Some(g) = gates.iter().find(|x| x.name == "kd_spread") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = format!("{:.0} vs {:.0}", g.a, g.b);
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("K/D Spread Tightness", status, &delta, verd);
    }

    // 7. Freezes
    if let Some(g) = gates.iter().find(|x| x.name == "freezes") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = format!("{:.1}s vs {:.1}s", g.a, g.b);
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Freeze Stalls/Statues", status, &delta, verd);
    }

    // 8. Coverage
    if let Some(g) = gates.iter().find(|x| x.name == "coverage") {
        let status = if g.pass { "🟢" } else { "🔴" };
        let delta = if g.a > 0.0 {
            format!("{:.0} vs {:.0}", g.a, g.b)
        } else {
            "n/a".into()
        };
        let verd = if g.pass { "PASS" } else { "FAIL" };
        add_row("Navigation Coverage", status, &delta, verd);
    }

    // The tick rate is not a gate, it is the precondition for every
    // gate above: a 19 Hz tape and a 71 Hz tape are two different
    // games. Say it on the card so nobody reads a verdict without it.
    {
        let cls = |t: &Totals| t.tick_class.clone().unwrap_or_else(|| "unknown".into());
        let (ca, cb) = (cls(a_totals), cls(b_totals));
        let status = if ca == cb { "\u{1F7E2}" } else { "\u{1F534}" };
        let delta = if ca == cb {
            format!("both {ca}")
        } else {
            format!("{ca} vs {cb}")
        };
        let verd = if ca == cb { "SAME" } else { "VOID" };
        add_row("Server tick rate", status, &delta, verd);
    }

    out.push_str("├──────────────────────────┴────────┴──────────────┴──────────┤\n");
    let (icon, tag) = match verdict {
        Verdict::Improved =>  ("🟢", "APPROVED FOR RELEASE (IMPROVED)"),
        Verdict::Parity =>    ("🟢", "APPROVED FOR RELEASE (PARITY)"),
        Verdict::Mixed =>     ("🟡", "CAUTION (MIXED QUALITY GATES)"),
        Verdict::Regressed => ("🔴", "REJECTED (QUALITY GATES FAILED)"),
    };
    let overall = format!("OVERALL VERDICT:  {icon} {tag}");
    out.push_str(&format!("│ {:<58} │\n", overall));
    out.push_str("└─────────────────────────────────────────────────────────────┘\n");

    out
}

/// Coverage saturates, so it only tells you anything between tapes long
/// enough to have saturated.
const COVER_GATE_MIN_SEC: f64 = 120.0;

/// A metric's band: what a run of the SAME build produces on this map.
///
/// The half-widths are fitted, not guessed. The sixteen pairs of
/// byte-identical builds in `runs/` (the recovery plan's table 1.4)
/// give, one tape against one tape, a stall ratio from 0.18 to 11.0,
/// engagements 0.45 to 2.82, world deaths 0 to 4x and freezes 0 to 3.
/// Coverage (0.70 to 1.19) and goal pickups (0.82 to 1.27) are the
/// only metrics with enough signal to judge on a single pair, which is
/// worth knowing and is why they are reported rather than gated.
///
/// `k` is the multiplicative half-width at one tape a side and `abs`
/// the absolute floor that keeps small counts honest: one stall
/// becoming eleven is an 1100 per cent "regression" and happened on
/// identical code. These settings read 13 of the 16 null pairs as
/// parity, where the old OR rule read 0 as parity and 9 as
/// improvements.
///
/// See docs/plans/2026-09-14-regression-analysis-and-recovery.md.
struct BandSpec {
    name: &'static str,
    /// true when a bigger number is worse (stalls, lava, freezes)
    lower_is_better: bool,
    k: f64,
    abs: f64,
}

const BAND_SPECS: [BandSpec; 4] = [
    BandSpec { name: "stall_parity", lower_is_better: true, k: 1.00, abs: 4.0 },
    BandSpec { name: "engagements", lower_is_better: false, k: 0.55, abs: 4.0 },
    BandSpec { name: "lava_deaths", lower_is_better: true, k: 1.50, abs: 3.0 },
    BandSpec { name: "freezes", lower_is_better: true, k: 1.00, abs: 2.0 },
];

fn metric_of(t: &Totals, name: &str) -> f64 {
    match name {
        "stall_parity" => t.stalls as f64,
        "engagements" => t.engages as f64,
        "lava_deaths" => t.lava_deaths as f64,
        "freezes" => t.freezes as f64,
        _ => 0.0,
    }
}

/// A median of an even count lands on a half. Printing it to zero
/// decimals turned "0.5 freezes against 0" into "0 vs 0", which read
/// as a tie while it was quietly blocking an improvement verdict.
fn trim(v: f64) -> String {
    if (v - v.round()).abs() < 1e-9 {
        format!("{v:.0}")
    } else {
        format!("{v:.1}")
    }
}

fn median(vals: &[f64]) -> f64 {
    if vals.is_empty() {
        return 0.0;
    }
    let mut v = vals.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = v.len();
    if n % 2 == 1 {
        v[n / 2]
    } else {
        (v[n / 2 - 1] + v[n / 2]) / 2.0
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct BandGate {
    pub name: String,
    pub control_median: f64,
    pub candidate_median: f64,
    pub lo: f64,
    pub hi: f64,
    /// "improved", "in band" or "regressed"
    pub call: String,
}

/// The interval estimate beside the band call.
///
/// The band answers "is this outside what the same build does", which
/// is a yes or no. These answer "how much, and how sure", which is
/// what anyone quoting a result actually needs. IQM over the median
/// because three or four tapes are too few to throw most of away; an
/// interval because a min-max range does not narrow as evidence
/// accumulates; a probability because it has a direction where a
/// three-way label does not.
///
/// Sign convention throughout: POSITIVE MEANS THE CANDIDATE IS
/// BETTER, whichever way the metric runs.
#[derive(Debug, Clone, Serialize)]
pub struct MetricStat {
    pub name: String,
    pub control_iqm: f64,
    pub candidate_iqm: f64,
    /// 95 per cent stratified bootstrap interval on the improvement.
    /// Absent below two tapes a side, where resampling one observation
    /// returns that observation and the "interval" would be a point.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ci: Option<crate::stats::Interval>,
    /// chance a candidate tape beats a control tape; 0.5 is a coin flip
    pub prob_improvement: f64,
    pub sprt: crate::stats::SprtCall,
    /// the effect the sequential test is powered for, in the metric's units
    pub sprt_bound: f64,
    pub sprt_llr: f64,
    pub note: String,
}

/// Judge candidate tapes against control tapes as bands, never one
/// tape against one tape.
///
/// The rule, from the recovery plan:
///   - regressed if the candidate median falls outside the band on any
///     hard gate;
///   - improved only if it beats the whole band on at least one gate
///     AND is no worse than the control median on every hard gate;
///   - parity otherwise, which is what a null change must read.
///
/// The band is the controls' own min and max, widened by the fitted
/// null spread above. The widening shrinks as tapes accumulate on
/// either side, `k * sqrt((1/n_cand + 1/n_ctl) / 2)`, which is 1.0 at
/// one tape a side (where it was calibrated) and 0.58 at three a side.
/// That is the whole argument for running repeats: three tapes each
/// way narrows every band by 42 per cent.
pub fn compare_band(candidates: &[MatchBrief], controls: &[MatchBrief]) -> CompareReport {
    compare_band_primary(candidates, controls, None)
}

/// The same judgement with a PRE-REGISTERED primary metric.
///
/// Four gates each with their own chance to convict is not one test.
/// Measured over the sixteen null pairs, one tape a side, each gate
/// convicts a change that does not exist 0 to 12 per cent of the time
/// and the verdict as a whole convicts 19 per cent of the time - the
/// any-gate row is always the largest in the table, and it is the one
/// that decided sixty builds. See
/// docs/specs/2026-09-16-lab-measurement-limits.md.
///
/// The fix is not a correction factor, it is saying in advance which
/// gate the change is expected to move. With `primary` set, only that
/// metric can convict; the others are computed, reported and flagged,
/// and cannot turn a null into a finding. It also stops the habit the
/// corpus shows repeatedly, of deciding which gate to believe after
/// the tapes are in: a change predicted to affect lava has no
/// business being convicted by an engagement count.
///
/// The hard gates are unaffected. A freeze under fire or an engine
/// error is not a statistical question and never was.
pub fn compare_band_primary(
    candidates: &[MatchBrief],
    controls: &[MatchBrief],
    primary: Option<&str>,
) -> CompareReport {
    // never panic in a server path: an empty side is a caller bug, but
    // a wedged tool call is worse than a useless report
    if candidates.is_empty() || controls.is_empty() {
        let mut empty = MatchBrief::empty();
        empty.headline = "compare_band needs at least one tape on each side".into();
        let mut rep = compare_gates(empty.clone(), empty);
        rep.verdict = Verdict::Mixed;
        rep.findings = vec!["compare_band was given no tapes on one side".into()];
        return rep;
    }
    // representative tapes carry the existing diagnostics: the gate
    // card, the hotspots and the next steps still describe a real
    // match rather than an average that never happened.
    let rep_ctl = representative(controls);
    let rep_cand = representative(candidates);
    let mut report = compare_gates(rep_ctl, rep_cand);

    let n_c = candidates.len() as f64;
    let n_k = controls.len() as f64;
    let shrink = ((1.0 / n_c + 1.0 / n_k) / 2.0).sqrt();

    let mut band_gates = Vec::new();
    let mut metric_stats: Vec<MetricStat> = Vec::new();
    let mut regressed: Vec<&str> = Vec::new();
    let mut beat_the_band: Vec<&str> = Vec::new();
    let mut worse_than_median = false;

    // the map is the bootstrap's stratum and the key to the
    // measured sigma; every tape in a compare is one map today, and
    // stratifying now is what makes a cross-map compare correct
    // when one arrives
    let map = controls
        .first()
        .and_then(|b| b.map.clone())
        .or_else(|| candidates.first().and_then(|b| b.map.clone()));
    // a primary nobody registered is not a primary; a misspelt one
    // must not silently disable every gate
    let primary = primary.filter(|p| BAND_SPECS.iter().any(|s| s.name == *p));

    for spec in BAND_SPECS.iter() {
        let cv: Vec<f64> = controls.iter().map(|b| metric_of(&b.totals, spec.name)).collect();
        let dv: Vec<f64> = candidates.iter().map(|b| metric_of(&b.totals, spec.name)).collect();
        let cmed = median(&cv);
        let dmed = median(&dv);
        let cmin = cv.iter().cloned().fold(f64::INFINITY, f64::min);
        let cmax = cv.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let kk = spec.k * shrink;
        let abs = spec.abs * shrink;
        let lo = (cmin.min(cmed * (1.0 - kk)) - abs).max(0.0);
        let hi = cmax.max(cmed * (1.0 + kk)) + abs;

        let (is_reg, is_imp) = if spec.lower_is_better {
            (dmed > hi, dmed < lo)
        } else {
            (dmed < lo, dmed > hi)
        };
        // "not worse than the control median" is the anti-trade rule:
        // a change that halves stalls by doubling lava has not
        // improved.
        //
        // TRIED AND REVERTED (2026-09-15): relaxing this to "worse by
        // more than the metric's absolute floor", so that half a
        // freeze could not block a real improvement. It took the null
        // pairs from 15 parities to 12, and the two that flipped to
        // "improved" were ab_dm4_fightpin1 vs 2 (stalls 20 to 6) and
        // ab_dm2_apexgate1 vs 2 (97 to 17), both byte-identical
        // builds. The strict rule is what stops a lucky tape reading
        // as a result. The honest fix for the half-freeze was the
        // report, not the rule: print medians that are not whole
        // numbers as they are, and say which gate blocked.
        let worse = if spec.lower_is_better { dmed > cmed } else { dmed < cmed };
        // With a pre-registered primary, only that metric decides.
        // The rest are still computed and still printed; they
        // simply stop being four extra chances to convict a null.
        let convicts = primary.map(|p| p == spec.name).unwrap_or(true);
        if worse && convicts {
            worse_than_median = true;
        }
        if is_reg && convicts {
            regressed.push(spec.name);
        }
        if is_imp && convicts {
            beat_the_band.push(spec.name);
        }

        // the interval estimate beside the call
        let smap = map.clone().unwrap_or_else(|| "map".to_string());
        let cs: Vec<crate::stats::Sample> =
            cv.iter().map(|v| crate::stats::Sample::new(&smap, *v)).collect();
        let ds: Vec<crate::stats::Sample> =
            dv.iter().map(|v| crate::stats::Sample::new(&smap, *v)).collect();
        let ci = crate::stats::bootstrap_diff_ci(&ds, &cs, spec.lower_is_better, 0.05);
        let pimp = crate::stats::prob_improvement(&dv, &cv, spec.lower_is_better);
        // the corpus sigma beats the arms' own: three tapes
        // estimate a standard deviation terribly, and the whole
        // point of the sequential test is not to be fooled by a
        // small sample
        let (sigma, src) = match crate::measure::sigma_for(map.as_deref(), spec.name) {
            Some(s) => (s, "corpus"),
            None => (crate::stats::pooled_sd(&[cv.clone(), dv.clone()]), "these arms"),
        };
        let bound = crate::measure::ship_bound(sigma);
        let sp = crate::stats::sprt(
            spec.name,
            &dv,
            &cv,
            spec.lower_is_better,
            bound,
            sigma,
            src,
        );
        metric_stats.push(MetricStat {
            name: spec.name.into(),
            control_iqm: crate::stats::iqm(&cv),
            candidate_iqm: crate::stats::iqm(&dv),
            ci,
            prob_improvement: pimp,
            sprt: sp.call,
            sprt_bound: sp.bound,
            sprt_llr: sp.llr,
            note: sp.note.clone(),
        });
        band_gates.push(BandGate {
            name: spec.name.into(),
            control_median: cmed,
            candidate_median: dmed,
            lo,
            hi,
            call: if is_reg {
                "regressed".into()
            } else if is_imp {
                "improved".into()
            } else {
                "in band".into()
            },
        });
    }

    // Two tapes at different server frame rates are two different
    // games (see the note in compare_gates): one mixed class voids it.
    let classes: std::collections::BTreeSet<String> = candidates
        .iter()
        .chain(controls.iter())
        .filter_map(|b| b.totals.tick_class.clone())
        .collect();
    let cross_rate = classes.len() > 1;

    let verdict = if cross_rate {
        Verdict::Mixed
    } else if !regressed.is_empty() {
        Verdict::Regressed
    } else if !beat_the_band.is_empty() && !worse_than_median {
        Verdict::Improved
    } else {
        Verdict::Parity
    };

    let mut findings = Vec::new();
    if cross_rate {
        let list: Vec<&str> = classes.iter().map(|s| s.as_str()).collect();
        findings.push(format!(
            "the tapes ran at different tick rates ({}); the verdict is not valid. \
             Re-baseline at the played rate (task 0.5 of the recovery plan).",
            list.join(" and ")
        ));
    }
    for g in &band_gates {
        findings.push(format!(
            "{}: candidate median {} against a control band of {:.0} to {:.0} (control median {}), {}",
            g.name, trim(g.candidate_median), g.lo, g.hi, trim(g.control_median), g.call
        ));
        // At one tape a side the fitted null spread is wide enough to
        // push the lower edge to zero, so no result can beat the band
        // and "improved" is unreachable on that metric. That is the
        // honest answer, not a bug: a metric whose same-build ratio
        // runs 0.18 to 11.0 cannot be shown to have improved by one
        // match. Run repeats; the band narrows as the square root.
        if g.lo <= 0.0 && g.call != "regressed" {
            findings.push(format!(
                "{}: no improvement can be demonstrated at {} control tape(s) - the band's floor is zero. Run repeats.",
                g.name,
                controls.len()
            ));
        }
        // the interval and the stopping rule, which is the half the
        // band cannot express: an improvement is an interval that
        // clears zero, and "run another tape" is an answer
        if let Some(st) = metric_stats.iter().find(|m| m.name == g.name) {
            let interval = match st.ci {
                Some(ci) => format!(
                    "improvement 95% CI {:+.1} to {:+.1} ({})",
                    ci.lo,
                    ci.hi,
                    if ci.lo > 0.0 {
                        "clears zero"
                    } else if ci.hi < 0.0 {
                        "entirely worse"
                    } else {
                        "covers zero"
                    }
                ),
                None => "no interval below two tapes a side".to_string(),
            };
            findings.push(format!(
                "{}: IQM {} to {}, {}, P(improve) {:.2}; sprt {:?} at a bound of {:.1} - {}",
                st.name,
                trim(st.control_iqm),
                trim(st.candidate_iqm),
                interval,
                st.prob_improvement,
                st.sprt,
                st.sprt_bound,
                st.note,
            ));
        }
    }
    if let Some(p) = primary {
        findings.insert(
            0,
            format!(
                "primary metric pre-registered as {p}: only it can convict, the other gates flag. \
                 Four gates convict a null 19 per cent of the time against 0 to 12 per cent each \
                 (docs/specs/2026-09-16-lab-measurement-limits.md)."
            ),
        );
    } else {
        findings.push(
            "no primary metric was pre-registered, so all four gates could convict: that is a \
             19 per cent false positive rate on the null corpus. Pass primary=<metric> next time."
                .into(),
        );
    }
    if !beat_the_band.is_empty() && worse_than_median {
        let blocked: Vec<&str> = band_gates
            .iter()
            .zip(BAND_SPECS.iter())
            .filter(|(g, sp)| {
                if sp.lower_is_better {
                    g.candidate_median > g.control_median
                } else {
                    g.candidate_median < g.control_median
                }
            })
            .map(|(g, _)| g.name.as_str())
            .collect();
        findings.push(format!(
            "beat the band on {} but reads parity, not improved: worse than the control median on {}",
            beat_the_band.join(", "),
            blocked.join(", ")
        ));
    }
    findings.push(format!(
        "{} candidate tape(s) against {} control tape(s); the band carries {:.2} of the one-tape null spread",
        candidates.len(),
        controls.len(),
        shrink
    ));
    // the diagnostics compare_gates found are still worth reading,
    // they are simply no longer the verdict
    findings.extend(
        report
            .findings
            .iter()
            .filter(|f| f.starts_with("hotspot "))
            .cloned(),
    );

    let headline = format!(
        "{:?}: stalls {:.0} to {:.0}, engages {:.0} to {:.0}, lava {:.0} to {:.0}, freezes {:.0} to {:.0} (medians, {} control vs {} candidate tapes)",
        verdict,
        band_gates[0].control_median,
        band_gates[0].candidate_median,
        band_gates[1].control_median,
        band_gates[1].candidate_median,
        band_gates[2].control_median,
        band_gates[2].candidate_median,
        band_gates[3].control_median,
        band_gates[3].candidate_median,
        controls.len(),
        candidates.len(),
    );

    report.verdict = verdict;
    report.findings = findings;
    report.headline = headline;
    report.band = band_gates;
    report.stats = metric_stats;
    report.primary = primary.map(|p| p.to_string());
    report.gate_card = format_gate_card(
        report.b.map.as_deref().or(report.a.map.as_deref()),
        verdict,
        &report.gates,
        &report.a.totals,
        &report.b.totals,
        report.scaled,
    );
    report
}

impl MatchBrief {
    /// An empty brief, for the one path that must answer without data.
    pub fn empty() -> MatchBrief {
        brief_text("", None)
    }
}

/// The tape whose stall count is the median: a real match to show,
/// rather than an average of matches that never happened.
fn representative(briefs: &[MatchBrief]) -> MatchBrief {
    let mut idx: Vec<usize> = (0..briefs.len()).collect();
    idx.sort_by_key(|&i| briefs[i].totals.stalls);
    briefs[idx[idx.len() / 2]].clone()
}

/// One tape against one tape. Kept for every existing caller, and it
/// is now exactly `compare_band` with a single tape a side, so the
/// band widens to the full measured null spread and a null change
/// reads parity instead of a coin flip.
pub fn compare_briefs(a: MatchBrief, b: MatchBrief) -> CompareReport {
    compare_band(&[b], &[a])
}

/// One tape against one tape, with every diagnostic gate the lab has
/// ever grown. This builds the gates and the card; it does NOT decide
/// the verdict any more - `band_verdict` does, because a single pair
/// of tapes cannot tell a change from nothing (see `compare_band`).
fn compare_gates(a: MatchBrief, b: MatchBrief) -> CompareReport {
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

    // an absolute floor like lava and freezes have. Scaling a 185 s
    // baseline down to a 30 s experiment leaves 1 or 2 stalls, where
    // one stall of ordinary noise is a 100% "regression".
    let stall_floor = a.totals.stalls.max(3) + 2;
    let stall_a = a.totals.stalls.max(1) as f64;
    let stall_ratio = b.totals.stalls as f64 / stall_a;
    gates.push(Gate {
        name: "stall_parity".into(),
        pass: stall_ratio <= bars.stall_ratio || b.totals.stalls <= stall_floor,
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
        // same max(1) trap as the stall gate: with a zero-engage
        // baseline the ratio is fabricated and every candidate reads
        // as a collapse. There is nothing to collapse from.
        pass: eng_ratio >= bars.engage_ratio || a.totals.engages == 0,
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
    // Duration counts as well as the count and the worst case (#257).
    // A tape where one bot stood still for 144 of 190 seconds scored
    // "1 freeze" and sailed past a gate that a tape with five short
    // ones would have failed. Total frozen time is the figure that
    // actually describes what a watcher sees, so a candidate that
    // loses 30 s more than its baseline fails whatever the count did.
    let fz_pass = b.totals.freeze_underfire == 0
        && (b.totals.freeze_max_sec < 10.0
            || b.totals.freeze_max_sec <= a.totals.freeze_max_sec + 2.0)
        && b.totals.freezes <= a.totals.freezes + 2
        && (b.totals.freeze_total_sec < 30.0
            || b.totals.freeze_total_sec <= a.totals.freeze_total_sec + 30.0);
    gates.push(Gate {
        name: "freezes".into(),
        pass: fz_pass,
        a: a.totals.freeze_max_sec,
        b: b.totals.freeze_max_sec,
        note: if b.totals.freeze_underfire > 0 {
            "a bot took damage while frozen - free frag for a human".into()
        } else if !fz_pass
            && b.totals.freeze_total_sec > a.totals.freeze_total_sec + 30.0
            && b.totals.freeze_max_sec < 10.0
        {
            format!(
                "{:.0} s lost to statues against the baseline's {:.0} s, across {} freeze(s)",
                b.totals.freeze_total_sec, a.totals.freeze_total_sec, b.totals.freezes
            )
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
    // coverage is a saturating total, so it only compares between tapes
    // long enough to have saturated. A 30 s experiment legitimately sees
    // a third of what a 185 s tape sees; gating that is noise.
    let cover_gated = b.totals.duration_sec >= COVER_GATE_MIN_SEC
        && a.totals.duration_sec >= COVER_GATE_MIN_SEC;
    gates.push(Gate {
        name: "coverage".into(),
        pass: !cover_gated || cover_ratio >= 0.80,
        a: a.totals.cover as f64,
        b: b.totals.cover as f64,
        note: if !cover_gated {
            format!("not gated below {COVER_GATE_MIN_SEC:.0} s of tape")
        } else if cover_ratio < 0.80 {
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
            || (a.totals.stalls > 0 && (b.totals.stalls as f64) < stall_a * 0.85)
            || eng_ratio > 1.15
            || (b.totals.frags > a.totals.frags && b.totals.all_frags_positive));

    // Two tapes at different server frame rates are two different
    // games: bot physics, the swim drag, the tremor clock and the
    // whole aim spring integrate differently in each, so no gate
    // between them means anything. 438 of the archive's tapes are
    // 19 Hz, 124 are 14.5 Hz and every human session is 71 Hz, and
    // nothing before 2026-09-15 ever said which.
    let cross_rate = match (
        a.totals.tick_class.as_deref(),
        b.totals.tick_class.as_deref(),
    ) {
        (Some(x), Some(y)) if x != y => Some((x.to_string(), y.to_string())),
        _ => None,
    };

    let verdict = if cross_rate.is_some() {
        Verdict::Mixed
    } else if hard_fail {
        Verdict::Regressed
    } else if any_fail {
        Verdict::Mixed
    } else if improved {
        Verdict::Improved
    } else {
        Verdict::Parity
    };

    let mut findings = Vec::new();
    if let Some((x, y)) = &cross_rate {
        findings.push(format!(
            "the two tapes ran at different tick rates ({x} vs {y});              the verdict is not valid. Re-run the baseline at the              played rate (see task 0.5 of the recovery plan)."
        ));
    }
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

    let gate_card = format_gate_card(
        b.map.as_deref().or(a.map.as_deref()),
        verdict,
        &gates,
        &a.totals,
        &b.totals,
        false,
    );

    CompareReport {
        verdict,
        headline,
        gate_card,
        gates,
        findings,
        next_steps,
        a,
        b,
        scaled: false,
        scale_note: None,
        baseline_run: None,
        band: Vec::new(),
        stats: Vec::new(),
        primary: None,
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
    brief.totals.third_party_deaths = scale_i32(brief.totals.third_party_deaths, k);
    brief.totals.player_kills = scale_i32(brief.totals.player_kills, k);
    brief.totals.world_deaths = scale_i32(brief.totals.world_deaths, k);
    brief.totals.lava_deaths = scale_i32(brief.totals.lava_deaths, k);
    brief.totals.engages = scale_u32(brief.totals.engages, k);
    brief.totals.hazards = scale_u32(brief.totals.hazards, k);
    brief.totals.abandons = scale_u32(brief.totals.abandons, k);
    brief.totals.routefails = scale_u32(brief.totals.routefails, k);
    brief.totals.weapons = scale_u32(brief.totals.weapons, k);
    brief.totals.grabs = scale_u32(brief.totals.grabs, k);
    brief.totals.acquisitions = scale_u32(brief.totals.acquisitions, k);
    // cover is NOT scaled: it saturates. A bot has seen most of the map
    // inside the first minute or two, so scaling a 185 s figure of 446
    // cells down to 72 made the coverage gate impossible to fail.
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
        report.gate_card = format_gate_card(
            report.b.map.as_deref().or(report.a.map.as_deref()),
            report.verdict,
            &report.gates,
            &report.a.totals,
            &report.b.totals,
            true,
        );
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
/// Compare one or more candidate tapes against the map's whole
/// baseline band. Falls back to the single resolved baseline when
/// `baselines.json` still names one tape.
/// `primary` is the metric the change was PRE-REGISTERED to move.
/// Naming it before the tapes are in is what stops four gates each
/// taking a free shot at a null (#377); leave it None and every gate
/// can still convict, which the report now says out loud.
pub fn compare_runs_band(
    cfg: &Config,
    candidate_logs: &[String],
    map_hint: Option<&str>,
    primary: Option<&str>,
) -> Result<CompareReport, String> {
    if candidate_logs.is_empty() {
        return Err("compare_runs_band needs at least one candidate tape".into());
    }
    let mut cands = Vec::new();
    for l in candidate_logs {
        cands.push(brief_run(cfg, l, map_hint)?);
    }
    let map = map_hint
        .map(str::to_string)
        .or_else(|| cands[0].map.clone());
    let names = map
        .as_deref()
        .map(|m| baseline_band_for(cfg, m))
        .unwrap_or_default();
    let mut ctrls = Vec::new();
    for n in &names {
        if let Ok(b) = brief_run(cfg, n, map.as_deref()) {
            ctrls.push(b);
        }
    }
    if ctrls.is_empty() {
        ctrls.push(brief_run(cfg, "baseline", map.as_deref())?);
    }
    let mut rep = compare_band_primary(&cands, &ctrls, primary);
    rep.baseline_run = names.first().cloned();
    Ok(rep)
}

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
    // brief the candidate FIRST when no map was named: its header
    // carries the map, and without it "baseline" resolved to dm4 and
    // the gates ran on dm4 bars whatever the candidate actually was.
    let b = brief_run(cfg, log_b, map_hint)?;
    let hint_owned = map_hint.map(str::to_string).or_else(|| b.map.clone());
    let base_name = resolve_run_ref(cfg, log_a, hint_owned.as_deref())
        .ok()
        .and_then(|p| {
            p.file_stem()
                .and_then(|s| s.to_str())
                .map(|s| s.to_string())
        });
    let a = brief_run(cfg, log_a, hint_owned.as_deref())?;
    let mut report = if scale {
        compare_briefs_scaled(a, b)
    } else {
        compare_briefs(a, b)
    };
    // human tapes are review-only: gates judge the BOT build against
    // a botmatch baseline, and a compared human session distorts both
    // sides of that (totals are bot-only since the split, but pace,
    // engagement mix and item traffic are all human-shaped)
    if report.a.totals.human.is_some() || report.b.totals.human.is_some() {
        report.findings.insert(
            0,
            "a compared tape carries HUMAN tracks - human sessions are review material, not gate material; treat this verdict as indicative only".into(),
        );
    }
    report.baseline_run = base_name;
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
        // Ask whether there was anything to shoot at before blaming
        // the fire path (#279). One e1m1 tape returned this step at
        // priority 1, naming three combat call sites, on a match
        // where no two bots came within 939 units of each other all
        // game. Perception range and the fire button were irrelevant;
        // the bots were each stuck in their own pocket and zero
        // engagements was a navigation result. "Historically this was
        // the fire-button bug" is a prior, not a finding about the
        // tape in hand, and the engagement gate is one of seven, so
        // this advice attaches to most movement regressions.
        let never_met = brief
            .totals
            .closest_approach
            .map(|d| d > 600.0)
            .unwrap_or(false);
        if never_met {
            let d = brief.totals.closest_approach.unwrap_or(0.0);
            steps.push(NextStep {
                priority: 1,
                area: "nav".into(),
                look_at: "nav coverage, stall hotspots and the graph for this map".into(),
                why: format!(
                    "no two bots came within {d:.0} u all tape, so there was nothing to                      perceive and nothing to shoot: this is a navigation result, not a                      combat one. Check coverage and the stall hotspots before the fire path"
                ),
            });
        } else {
            steps.push(NextStep {
                priority: 1,
                area: "combat".into(),
                look_at: "src/argus.qc perception find() / button0 hold / W_FireLightning".into(),
                why: match brief.totals.closest_approach {
                    Some(d) => format!(
                        "engagements collapsed or never started and bots did get within                          {d:.0} u of each other, so they had targets; historically this                          was the fire-button bug"
                    ),
                    None => "engagements collapsed or never started; historically this was                              the fire-button bug"
                        .into(),
                },
            });
        }
    }
    if brief.totals.acquisitions == 0 && brief.totals.duration_sec >= 60.0 {
        steps.push(NextStep {
            priority: 2,
            area: "items".into(),
            look_at: "src/items.qc weapon_touch FL_CLIENT guard (must admit ar_isbot)".into(),
            why: "no weapon switches and no battle-grabs; bots may be stuck on spawn shotguns".into(),
        });
    }
    let quad = *brief.goals.get("item_artifact_super_damage").unwrap_or(&0);
    if quad >= 3 && brief.totals.routefails >= 3 {
        steps.push(NextStep {
            priority: 3,
            area: "nav".into(),
            look_at: "src/argus.qc Argus_BotCanRJ / ARGEVT rjump".into(),
            why: format!(
                "quad goalled {quad} times with {} routefails; pad exists - check rjump events and the RL/health toll",
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
            // no node numbers here (#276): they belong to one graph,
            // they shift on every regen, and this string was printing
            // dm4's on dm2 and e1m5 briefs. The actionable half is
            // the last clause, which loses nothing by being general.
            "bots are goaling elevated quad; look for ARGEVT rjump, not a stall loop".into(),
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

    // the trapped/routefail <-> reach join: a routefail cluster whose
    // nearest node reaches little of the graph is a DIRECTED SINK -
    // the v3.69 dm2 storm signature, stamped on the hotspot instead
    // of costing a forensics session. Forward edges are walk links
    // plus every typed hop, navgen 7h semantics.
    let mut fwd: Vec<Vec<usize>> = vec![Vec::new(); pts.len()];
    for key in ["links", "teles", "rjlinks", "liftlinks", "swimlinks", "trainlinks", "sprintlinks"]
    {
        if let Some(arr) = v.get(key).and_then(|a| a.as_array()) {
            for e in arr {
                let Some(p) = e.as_array() else { continue };
                let (Some(a), Some(b)) =
                    (p.first().and_then(|x| x.as_u64()), p.get(1).and_then(|x| x.as_u64()))
                else {
                    continue;
                };
                let (a, b) = (a as usize, b as usize);
                if a < fwd.len() && b < fwd.len() {
                    fwd[a].push(b);
                }
            }
        }
    }
    let reach_of = |start: usize| -> usize {
        let mut seen = vec![false; fwd.len()];
        seen[start] = true;
        let mut q = vec![start];
        let mut n = 0usize;
        while let Some(u) = q.pop() {
            n += 1;
            for &w in &fwd[u] {
                if !seen[w] {
                    seen[w] = true;
                    q.push(w);
                }
            }
        }
        n
    };
    let mut sink_notes: Vec<String> = Vec::new();
    for h in &mut brief.hotspots {
        if h.kind != "routefail" && h.kind != "stall" {
            continue;
        }
        let Some(n) = h.nearest_node else { continue };
        if h.nearest_dist.unwrap_or(f64::MAX) > 160.0 || (n as usize) >= fwd.len() {
            continue;
        }
        let pct = (100 * reach_of(n as usize) / pts.len().max(1)) as u32;
        h.reach_pct = Some(pct);
        if h.kind == "routefail" && pct < 60 && h.count >= 5 {
            sink_notes.push(format!("n{} at {:.0} {:.0} {:.0} reach {}%", n, h.x, h.y, h.z, pct));
        }
    }
    if !sink_notes.is_empty() {
        brief.flags.push(format!(
            "routefail cluster(s) sit in DIRECTED SINKS - the graph's fault, not the walking: {}; tools/argus_reach.py maps the pocket",
            sink_notes.join("; ")
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

/// Stock deathmatch respawn clocks for the classes v3.48 gave item
/// clocks. Mega is approximate: 20 s after the rot ends, so its
/// effective cycle depends on the taker's health.
fn respawn_period(classname: &str) -> Option<f64> {
    if classname.starts_with("weapon_") {
        return Some(30.0);
    }
    if classname.starts_with("item_armor") {
        return Some(20.0);
    }
    if classname.starts_with("item_artifact_") {
        return Some(60.0);
    }
    if classname == "item_health" {
        return Some(125.0); // control-list item_health is the mega
    }
    None
}

/// Pure item-clock scorer: visit entries are any track crossing into
/// 96u of the spawn point; gaps between consecutive entries measured
/// against the respawn period. Per spawn point, so a map's two RLs
/// each get a row.
pub fn item_control_rows(items: &[(String, [f32; 3])], tape: &MatchTape) -> Vec<ItemControl> {
    let mut out = Vec::new();
    for (cls, o) in items {
        let Some(period) = respawn_period(cls) else { continue };
        let mut entries: Vec<f64> = Vec::new();
        for rec in tape.samples.values() {
            let mut inside = false;
            for s in rec {
                let dx = s.pos.x - o[0] as f64;
                let dy = s.pos.y - o[1] as f64;
                let dz = (s.pos.z - o[2] as f64).abs();
                let now_in = dx * dx + dy * dy < 96.0 * 96.0 && dz < 80.0;
                if now_in && !inside {
                    entries.push(s.t);
                }
                inside = now_in;
            }
        }
        if entries.len() < 3 {
            continue;
        }
        entries.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let mut gaps: Vec<f64> = entries.windows(2).map(|w| w[1] - w[0]).collect();
        gaps.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let median = gaps[gaps.len() / 2];
        out.push(ItemControl {
            classname: cls.clone(),
            visits: entries.len(),
            median_gap_sec: median,
            period_sec: period,
            tightness: median / period,
        });
    }
    out.sort_by(|a, b| a.tightness.partial_cmp(&b.tightness).unwrap_or(std::cmp::Ordering::Equal));
    out
}

/// Attach the item-clock scoreboard for the atlas's control items,
/// and flag a top prize that sits unclaimed for multiples of its
/// clock - a control gap the circuits should be closing.
pub fn attach_item_control(cfg: &Config, tape: &MatchTape, brief: &mut MatchBrief) {
    let Some(map) = brief.map.clone() else { return };
    let Ok(atlas) = crate::cartograph::cartograph(cfg, &map) else {
        return;
    };
    let items: Vec<(String, [f32; 3])> = atlas
        .control
        .iter()
        .filter_map(|c| Some((c.classname.clone(), c.origin?)))
        .collect();
    brief.item_control = item_control_rows(&items, tape);
    if brief.totals.duration_sec < 120.0 {
        return; // short probes make every clock look loose
    }
    for row in &brief.item_control {
        let value = atlas
            .control
            .iter()
            .find(|c| c.classname == row.classname)
            .map(|c| c.value)
            .unwrap_or(0);
        if value >= 85 && row.tightness > 2.5 {
            brief.flags.push(format!(
                "prize sits unclaimed: {} median revisit {:.0} s vs its {:.0} s clock - a control gap the circuits should close",
                row.classname, row.median_gap_sec, row.period_sec
            ));
        }
    }
}

/// Join the tape's paired demo when the harvester left one under
/// the same stem: aim statistics, the highlight reel and full-rate
/// track summaries arrive with the brief instead of needing a
/// second call.
fn attach_paired_demo(cfg: &Config, log_path: &Path, brief: &mut MatchBrief) {
    let Some(stem) = log_path.file_stem().map(|s| s.to_string_lossy().into_owned()) else {
        return;
    };
    let dem = cfg.runs.join("demos").join(format!("{stem}.dem"));
    if !dem.exists() {
        return;
    }
    match crate::demo::read_demo(&dem) {
        Ok(d) => {
            brief.flags.push(format!(
                "paired demo joined: {} highlight(s), {} track(s) - playdemo {stem} and jump to a highlight's t",
                d.brief.highlights.len(),
                d.brief.tracks.len()
            ));
            brief.paired_demo = Some(d.brief);
        }
        Err(e) => brief.flags.push(format!("paired demo present but unreadable: {e}")),
    }
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
                reach_pct: None,
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
        "{map} {dur:.0}s: {frags} frags, {deaths} deaths ({lava} lava, {third} third-party), {stalls} stalls, {goals} goals, {eng} engages, {haz} hazards, spread {spread}",
        dur = totals.duration_sec,
        frags = totals.frags,
        deaths = totals.deaths,
        lava = totals.lava_deaths,
        third = totals.third_party_deaths,
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
    fn brief_surfaces_third_party_deaths() {
        let log = log_a().replace(
            "ARGEVT Reap death Omi pos '64.0 0.0 24.0'",
            "ARGEVT Reap death Omi pos '64.0 0.0 24.0' thirdparty",
        );
        let b = brief_text(&log, None);
        assert_eq!(b.totals.third_party_deaths, 1);
        assert!(b.headline.contains("1 third-party"));
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

    // The tape that motivated #279: e1m1, zero engagements, and the
    // brief's priority 1 step named three combat call sites. No two
    // bots came within 939 units of each other all match, so the
    // right answer was navigation.
    #[test]
    fn real_e1m1_inert_tape_blames_nav_not_the_fire_path_if_present() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");

        // The tape from the issue: zero engagements, and the bots
        // never came near each other. Closest approach is 1396 u.
        let apart = root.join("vibe_e1m1_long.log");
        if apart.exists() {
            if let Ok(brief) = brief_path(&apart, Some("e1m1")) {
                assert_eq!(brief.totals.engages, 0, "this tape is the inert one");
                let d = brief
                    .totals
                    .closest_approach
                    .expect("two bot tracks give an approach");
                assert!(d > 600.0, "bots were far apart all tape, got {d}");
                assert!(
                    !brief
                        .next_steps
                        .iter()
                        .any(|s| s.area == "combat" && s.look_at.contains("W_FireLightning")),
                    "must not send the reader to the fire path when nobody had a target"
                );
                assert!(
                    brief
                        .next_steps
                        .iter()
                        .any(|s| s.area == "nav" && s.why.contains("nothing to shoot")),
                    "expected the navigation step instead: {:?}",
                    brief.next_steps
                );
            }
        }

        // And the other direction, so the check cannot simply always
        // blame nav. A longer e1m1 tape has the bots passing within
        // 79 u and still never engaging, which IS a combat question,
        // and the step has to stay pointed at the fire path there.
        let met = root.join("ab_e1m1_unstick1.log");
        if met.exists() {
            if let Ok(brief) = brief_path(&met, Some("e1m1")) {
                assert_eq!(brief.totals.engages, 0);
                let d = brief.totals.closest_approach.expect("three tracks");
                assert!(d < 600.0, "these bots did meet, got {d}");
                assert!(
                    brief
                        .next_steps
                        .iter()
                        .any(|s| s.area == "combat" && s.look_at.contains("W_FireLightning")),
                    "bots that met and did not fight is a combat finding: {:?}",
                    brief.next_steps
                );
            }
        }
    }

    // #266: a co-op session that plays 133 s of e1m2, exits, and
    // records 3 s on e1m3 briefed as a 1.5 second match at 12,326
    // u/s, with totals.stalls 0 while events.stall counted 40.
    #[test]
    fn real_level_change_tape_is_not_briefed_as_one_match_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/shane_e1m3_2026-09-05_v409.log");
        if !path.exists() {
            return;
        }
        let brief = brief_path(&path, None).unwrap();

        // the long segment is the one worth reading, and it is e1m2
        assert_eq!(brief.map.as_deref(), Some("e1m2"));
        assert!(
            brief.totals.duration_sec > 100.0,
            "must read the 133 s segment, not the 1.5 s one: got {}",
            brief.totals.duration_sec
        );
        assert!(
            brief.totals.avg_speed < 400.0,
            "12,326 u/s was the symptom: got {}",
            brief.totals.avg_speed
        );
        // the tape used to contradict itself: totals 0, events 40
        let ev_stalls = *brief.events.get("stall").unwrap_or(&0) as i32;
        if ev_stalls > 0 {
            assert!(
                brief.totals.stalls > 0,
                "totals.stalls {} cannot be zero while {ev_stalls} stall events exist",
                brief.totals.stalls
            );
        }
        assert!(
            brief.flags.iter().any(|f| f.starts_with("LEVEL CHANGE:")),
            "the reader has to be told: {:?}",
            brief.flags
        );
    }

    // and a single-level tape must not be labelled
    #[test]
    fn an_ordinary_tape_raises_no_level_change_flag_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/ab_dm4_parity.log");
        if !path.exists() {
            return;
        }
        let brief = brief_path(&path, None).unwrap();
        assert!(
            !brief.flags.iter().any(|f| f.starts_with("LEVEL CHANGE:")),
            "single-level tape must not be flagged: {:?}",
            brief.flags
        );
        assert!(brief.totals.avg_speed < 400.0);
    }

    // #257: a tape where one bot stood still for most of the match
    // scored "1 freeze" and passed, because the gate weighed count
    // and worst case but never total time lost.
    #[test]
    fn freeze_gate_fails_on_total_time_even_when_the_count_is_low() {
        let mut a = brief_text(&log_a(), None);
        let mut b = brief_text(&log_a(), None);
        // baseline: nothing frozen
        a.totals.freezes = 0;
        a.totals.freeze_max_sec = 0.0;
        a.totals.freeze_total_sec = 0.0;
        // candidate: ONE freeze, but it ate most of the match. Under
        // the old rule this passed: count within +2, and the worst
        // case only fails at 10 s... which this exceeds, so use a
        // shape the old rule provably let through instead - several
        // sub-10 s freezes that add up.
        b.totals.freezes = 1;
        b.totals.freeze_max_sec = 9.0;
        b.totals.freeze_total_sec = 9.0;
        let r = compare_briefs(a.clone(), b.clone());
        let g = r.gates.iter().find(|g| g.name == "freezes").unwrap();
        assert!(g.pass, "9 s in one freeze is not a gate failure");

        // now the same count and worst case, but 80 s lost in total
        b.totals.freezes = 1;
        b.totals.freeze_max_sec = 9.0;
        b.totals.freeze_total_sec = 80.0;
        let r2 = compare_briefs(a.clone(), b.clone());
        let g2 = r2.gates.iter().find(|g| g.name == "freezes").unwrap();
        assert!(
            !g2.pass,
            "80 s lost to statues must fail even at one freeze under 10 s"
        );
        assert!(
            g2.note.contains("lost to statues"),
            "the note should say what failed: {}",
            g2.note
        );
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
        // a routefail cluster pinned to the disconnected node 2: the
        // sink join must stamp its reach and shout
        brief.hotspots.push(Hotspot {
            kind: "routefail".into(),
            count: 6,
            x: 5000.0,
            y: 5000.0,
            z: 24.0,
            known: None,
            note: None,
            nearest_node: Some(2),
            nearest_dist: Some(10.0),
            nearest_item: None,
            nearest_item_dist: None,
            cause: None,
            reach_pct: None,
        });
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
        let rf = brief.hotspots.iter().find(|h| h.kind == "routefail").unwrap();
        assert_eq!(rf.reach_pct, Some(33), "node 2 reaches only itself in a 3-node graph");
        assert!(
            brief.flags.iter().any(|f| f.contains("DIRECTED SINK")),
            "a big routefail cluster with 33% reach is a sink: {:?}",
            brief.flags
        );
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn item_clock_rows_measure_the_circuit() {
        // one RL spawn, one track lapping it every 30 s: median gap
        // equals the weapon clock, tightness 1.0
        let mut log = String::from("ARGUS init on dm4\nARGEVT Reap spawned\n");
        for k in 0..4 {
            let t_in = 5.0 + 30.0 * k as f64;
            log.push_str(&format!(
                "ARGLOG Reap t {t_in} pos '0.0 0.0 24.0' spd 200 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            log.push_str(&format!(
                "ARGLOG Reap t {} pos '500.0 0.0 24.0' spd 200 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n",
                t_in + 15.0
            ));
        }
        let tape = parse_tape(&log);
        let items = vec![
            ("weapon_rocketlauncher".to_string(), [0.0f32, 0.0, 24.0]),
            // two visits only: below the 3-visit floor, no row
            ("item_armor2".to_string(), [500.0f32, 0.0, 24.0]),
        ];
        let rows = item_control_rows(&items[..1], &tape);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].visits, 4);
        assert!((rows[0].median_gap_sec - 30.0).abs() < 0.01);
        assert!((rows[0].tightness - 1.0).abs() < 0.01, "tightness {}", rows[0].tightness);
        // an unknown class has no clock and never rows
        let none = item_control_rows(
            &[("misc_fireball".to_string(), [0.0f32, 0.0, 24.0])],
            &tape,
        );
        assert!(none.is_empty());
    }

    /// The sixteen pairs of byte-identical builds the recovery plan
    /// found. The old OR rule read nine of them as "improved", five as
    /// "regressed" and none as parity: a coin flip, and the instrument
    /// that shipped sixty builds. A null change must read parity.
    /// The row the player would recognise, from the last human dm4
    /// tape on record: Shane went 18 and 11 and the bots killed him
    /// ten times in 302 seconds.
    #[test]
    fn a_human_tape_carries_a_scorecard_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/shane_dm4_2026-08-29_v405.log");
        if !path.exists() {
            return;
        }
        let b = brief_path(&path, None).unwrap();
        let sc = b.human_scorecard.expect("human tape carries a scorecard");
        assert!((sc.minutes - 5.0).abs() < 0.3, "minutes {}", sc.minutes);
        assert!(
            (sc.bot_kills_human_pm - 2.0).abs() < 0.2,
            "bots killed him 10 times in 5 minutes, got {}",
            sc.bot_kills_human_pm
        );
        // 17, not the 18 the engine obituaries carry: the telefrag at
        // t 153 wrote its death line as "death world", because the
        // attacker is a nameless teledeath trigger (#337). The QC now
        // resolves that through the trigger's owner, so a tape recorded
        // after the fix reads 18 here; this one predates it.
        assert!(
            (sc.human_kills_pm - 3.4).abs() < 0.2,
            "he killed 17 by telemetry in 5 minutes, got {}",
            sc.human_kills_pm
        );
        assert!(sc.threat_ratio > 0.5 && sc.threat_ratio < 0.6, "{}", sc.threat_ratio);
        assert_eq!(sc.unstick_warps, 0, "no warps on that tape");

        // a botmatch has no player, so no scorecard
        let lab = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/ab_dm2_corridor1.log");
        if lab.exists() {
            assert!(brief_path(&lab, None).unwrap().human_scorecard.is_none());
        }
    }

    /// And the brief must not count it on either side. A tape the
    /// puppet connected to is a botmatch, its bot totals are the
    /// bots only, and nothing about it is review-only.
    /// `band_dm4_2` and `band_dm2_3` are committed baselines that
    /// briefed as human sessions until this.
    #[test]
    fn a_puppet_tape_is_a_botmatch_if_present() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let p = dir.join("band_dm4_2.log");
        if !p.exists() {
            return;
        }
        let b = brief_path(&p, None).unwrap();
        assert!(b.totals.human.is_none(), "the puppet briefed as a human");
        // three bots, and the puppet is not a fourth
        assert!(b.totals.cover > 300, "cover {}", b.totals.cover);
        assert!(b.totals.engages > 40, "engages {}", b.totals.engages);
    }

    /// THE CLAIM IS A MEASUREMENT, NOT A SLOGAN. "CSV is about half
    /// the tokens" is the reason `format=csv` exists, so it is
    /// measured on a real tape rather than asserted. Bytes stand in
    /// for tokens: both formats are ASCII over the same values, and
    /// the difference is entirely repeated field names.
    #[test]
    fn csv_is_materially_smaller_than_json_on_a_real_tape() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let p = dir.join("ab_dm4_deadlink1.log");
        if !p.exists() {
            return;
        }
        let b = brief_path(&p, None).unwrap();
        // COMPACT json is the conservative comparison. The server
        // actually sends to_string_pretty, which is larger again, so
        // the saving in practice is bigger than this asserts.
        let json = serde_json::to_string(&b).unwrap();
        let pretty = serde_json::to_string_pretty(&b).unwrap();
        let csv = brief_csv(&b);
        // Measured 2026-09-16 on this tape: 1765 against 3464 compact,
        // which is 51 per cent. "About half" is the honest phrase and
        // it is what the docs say; a bar at 55 leaves room for a tape
        // with more hotspots without leaving room for a regression.
        assert!(
            csv.len() * 100 < json.len() * 55,
            "csv {} bytes against compact json {} ({} pretty)",
            csv.len(),
            json.len(),
            pretty.len()
        );
        // and it still carries what a reader came for
        assert!(csv.contains("stalls,"), "{csv}");
        assert!(csv.contains("bot,frags,deaths"), "no per-bot table");
        assert!(csv.contains("kind,x,y,z,count,cause"), "no hotspot table");
    }

    /// And the compare view keeps the numbers a verdict rests on.
    #[test]
    fn compare_csv_carries_the_band_and_the_stats() {
        let base = brief_text(&log_a(), None);
        let mk = |stalls: i32| {
            let mut b = base.clone();
            b.totals.stalls = stalls;
            b.totals.engages = 60;
            b.totals.duration_sec = 185.0;
            b
        };
        let r = compare_band(&[mk(10), mk(11), mk(9)], &[mk(40), mk(42), mk(38)]);
        let csv = compare_csv(&r);
        assert!(csv.contains("gate,control_median,candidate_median"), "{csv}");
        assert!(csv.contains("metric,control_iqm,candidate_iqm"), "{csv}");
        assert!(csv.contains("stall_parity,"), "{csv}");
        // the verdict itself is the first line, as a comment
        assert!(csv.starts_with("# "), "{csv}");
    }

    #[test]
    fn same_build_pairs_read_parity_if_present() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        // one list, in measure.rs, so the validation set and the
        // corpus analysis cannot drift apart
        let pairs = crate::measure::NULL_PAIRS;
        let mut seen = 0;
        let mut parity = 0;
        let mut verdicts = Vec::new();
        for (a, b) in pairs {
            let (pa, pb) = (dir.join(format!("{a}.log")), dir.join(format!("{b}.log")));
            if !pa.exists() || !pb.exists() {
                continue;
            }
            seen += 1;
            let r = compare_band(
                &[brief_path(&pb, None).unwrap()],
                &[brief_path(&pa, None).unwrap()],
            );
            if r.verdict == Verdict::Parity {
                parity += 1;
            } else {
                verdicts.push(format!("{a} vs {b}: {:?}", r.verdict));
            }
        }
        if seen == 0 {
            return;
        }
        // 13, measured. The three that still get through are
        // ab_dm4_airlead1 vs 2 and ab_dm4_lgwade1 vs 2 (regressed,
        // stalls 1 to 11 on identical code) and ab_dm2_apexgate1 vs 2
        // (improved, stalls 97 to 17). The instrument has known
        // residual error; it is not an oracle. The old OR rule read
        // ZERO of the sixteen as parity and nine as improvements.
        assert!(
            parity >= 13,
            "only {parity} of {seen} null pairs read parity: {verdicts:?}"
        );
    }

    /// THE NEW ESTIMATORS FACE THE SAME BAR AS THE BAND. An
    /// estimator that finds an effect in code that has none is
    /// disqualified whatever else it improves, and this is the corpus
    /// that disqualifies it: sixteen pairs of byte-identical builds,
    /// one tape a side.
    ///
    /// The sequential test must never say "accept" on any of them.
    /// The arithmetic says it cannot: at one tape a side the standard
    /// error of the difference is sigma * sqrt(2), the bound is
    /// 1.77 * sigma, and crossing +2.944 needs the observed effect to
    /// reach about 4.2 sigma. That is the point of deriving the bound
    /// from the detection limit rather than picking one.
    #[test]
    fn the_sequential_test_never_accepts_a_null_pair() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let mut seen = 0;
        let mut accepted = Vec::new();
        for (a, b) in crate::measure::NULL_PAIRS {
            let (pa, pb) = (dir.join(format!("{a}.log")), dir.join(format!("{b}.log")));
            if !pa.exists() || !pb.exists() {
                continue;
            }
            seen += 1;
            let r = compare_band(
                &[brief_path(&pb, None).unwrap()],
                &[brief_path(&pa, None).unwrap()],
            );
            for st in &r.stats {
                if st.sprt == crate::stats::SprtCall::Accept {
                    accepted.push(format!("{a} vs {b}: {} llr {:.2}", st.name, st.sprt_llr));
                }
                // and it must not pretend to an interval it cannot have
                assert!(st.ci.is_none(), "{a} vs {b}: {} got an interval at one tape a side", st.name);
            }
        }
        if seen == 0 {
            return;
        }
        assert!(accepted.is_empty(), "sprt accepted a null: {accepted:?}");
    }

    /// And it must say "continue" rather than "reject" on them, which
    /// is the honest answer and the one the lab has never been able to
    /// give. One tape a side cannot rule an effect out either.
    #[test]
    fn the_sequential_test_asks_for_more_tapes_on_a_null_pair() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let (a, b) = crate::measure::NULL_PAIRS[0];
        let (pa, pb) = (dir.join(format!("{a}.log")), dir.join(format!("{b}.log")));
        if !pa.exists() || !pb.exists() {
            return;
        }
        let r = compare_band(
            &[brief_path(&pb, None).unwrap()],
            &[brief_path(&pa, None).unwrap()],
        );
        assert!(!r.stats.is_empty(), "no stats block");
        assert!(
            r.stats.iter().all(|s| s.sprt == crate::stats::SprtCall::Continue),
            "{:?}",
            r.stats.iter().map(|s| (s.name.clone(), s.sprt)).collect::<Vec<_>>()
        );
        // and the report says so in words, not only in a struct
        assert!(
            r.findings.iter().any(|f| f.contains("P(improve)")),
            "the interval and the probability never reached the findings"
        );
    }

    /// A pre-registered primary stops the other three gates from
    /// convicting. Four gates convict a null 19 per cent of the time
    /// against 0 to 12 per cent each, measured; this is the fix.
    #[test]
    fn a_pre_registered_primary_keeps_the_other_gates_from_convicting() {
        let base = brief_text(&log_a(), None);
        let mk = |stalls: i32, lava: i32| {
            let mut b = base.clone();
            b.totals.stalls = stalls;
            b.totals.engages = 60;
            b.totals.lava_deaths = lava;
            b.totals.freezes = 0;
            b.totals.duration_sec = 185.0;
            b
        };
        // lava is what moved, badly, and stalls did not budge
        let ctl: Vec<MatchBrief> = [10, 11, 9, 10].iter().map(|s| mk(*s, 1)).collect();
        let cand: Vec<MatchBrief> = [10, 11, 9, 10].iter().map(|s| mk(*s, 40)).collect();

        // with everything able to convict, it is a regression
        let open = compare_band(&cand, &ctl);
        assert_eq!(open.verdict, Verdict::Regressed, "{}", open.headline);

        // pre-register stalls and lava can only flag, because this
        // change was never predicted to touch it
        let pinned = compare_band_primary(&cand, &ctl, Some("stall_parity"));
        assert_eq!(pinned.verdict, Verdict::Parity, "{}", pinned.headline);
        assert_eq!(pinned.primary.as_deref(), Some("stall_parity"));
        // the flag is still printed: demoted, not hidden
        assert!(
            pinned.band.iter().any(|g| g.name == "lava_deaths" && g.call == "regressed"),
            "the demoted gate stopped being reported"
        );
        // pre-register the gate that did move and it convicts again
        let right = compare_band_primary(&cand, &ctl, Some("lava_deaths"));
        assert_eq!(right.verdict, Verdict::Regressed, "{}", right.headline);

        // a misspelt primary must not silently disarm every gate
        let typo = compare_band_primary(&cand, &ctl, Some("lava"));
        assert_eq!(typo.verdict, Verdict::Regressed, "{}", typo.headline);
        assert!(typo.primary.is_none());
    }

    /// The band must still be able to say yes. Three tapes a side
    /// narrow it by 42 per cent, which is the entire reason `repeats`
    /// exists: a real halving of stalls then reads as an improvement
    /// where one tape against one tape can only ever read parity.
    #[test]
    fn repeats_make_an_improvement_expressible() {
        let base = brief_text(&log_a(), None);
        let mk = |stalls: i32| {
            let mut b = base.clone();
            b.totals.stalls = stalls;
            b.totals.engages = 60;
            b.totals.lava_deaths = 2;
            b.totals.freezes = 0;
            b
        };
        let controls = [mk(40), mk(45), mk(50)];
        let candidates = [mk(10), mk(12), mk(11)];
        let r = compare_band(&candidates, &controls);
        assert_eq!(r.verdict, Verdict::Improved, "{}", r.headline);

        // the same halving, one tape a side, cannot be called
        let one = compare_band(&[mk(11)], &[mk(45)]);
        assert_eq!(one.verdict, Verdict::Parity, "{}", one.headline);
        assert!(
            one.findings.iter().any(|f| f.contains("Run repeats")),
            "a band that cannot express an improvement must say so: {:?}",
            one.findings
        );
    }

    /// The band must still convict. A dm2 arm at the September tail
    /// (100 stalls) against a late-August control (33) is a real
    /// regression and must read as one.
    #[test]
    fn the_band_still_convicts_a_real_stall_regression_if_present() {
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let (ctl, bad) = (
            dir.join("ab_dm2_seatregen1.log"),
            dir.join("ab_dm2_holds2.log"),
        );
        if !ctl.exists() || !bad.exists() {
            return;
        }
        let r = compare_band(
            &[brief_path(&bad, None).unwrap()],
            &[brief_path(&ctl, None).unwrap()],
        );
        assert_eq!(r.verdict, Verdict::Regressed, "{}", r.headline);
    }

    #[test]
    fn tick_class_separates_a_human_tape_from_a_lab_tape_if_present() {
        // The lab and the game were never the same game: every human
        // session is a listen server at about 71 Hz and every lab tape
        // before 2026-09-15 was dedicated at 19 or 14.5 Hz. A brief
        // that does not say which is a brief that cannot be compared.
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let cases = [
            ("shane_dm4_2026-08-29_v405.log", "listen", 0.5071),
            ("ab_dm2_corridor1.log", "dedicated_fast", 0.5150),
            ("ab_dm2_doors.log", "dedicated_slow", 0.5464),
        ];
        for (name, class, gap) in cases {
            let path = dir.join(name);
            if !path.exists() {
                continue;
            }
            let b = brief_path(&path, None).unwrap();
            assert_eq!(
                b.totals.tick_class.as_deref(),
                Some(class),
                "{name} should read {class}"
            );
            let got = b.totals.tick_gap_mean.expect("gap");
            assert!((got - gap).abs() < 0.0015, "{name} gap {got} wanted {gap}");
        }
    }

    #[test]
    fn compare_refuses_a_verdict_across_tick_rates_if_present() {
        // A 19 Hz tape and a 70 Hz tape are two different games. The
        // old rule would happily call one an improvement on the other.
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let (a, b) = (dir.join("ab_dm2_corridor1.log"), dir.join("ab_dm2_doors.log"));
        if !a.exists() || !b.exists() {
            return;
        }
        let rep = compare_briefs(
            brief_path(&a, None).unwrap(),
            brief_path(&b, None).unwrap(),
        );
        assert_eq!(rep.verdict, Verdict::Mixed, "cross-rate verdicts are void");
        assert!(
            rep.findings.iter().any(|f| f.contains("tick rate")),
            "findings must name the cause: {:?}",
            rep.findings
        );
        assert!(
            rep.gate_card.contains("Server tick rate") && rep.gate_card.contains("VOID"),
            "the card must show the void row:
{}",
            rep.gate_card
        );
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
        // the graph regenerates as navgen evolves (145 nodes at the
        // v3.72 tape, 155 since the v3.76 ledge-sink regen): assert
        // the scale, not the exact count, or this goes stale on every
        // regen and only fails on machines that carry the tree
        assert!(
            (120..=220).contains(&cov.nodes),
            "dm4 graph node count out of scale: {}",
            cov.nodes
        );
        assert!(
            cov.pct >= 60,
            "a 335 s 4-track dm4 match paints most of the graph, got {}%",
            cov.pct
        );
        // everything below needs the atlas, and the atlas needs the
        // BSP - machine-local (licensed id data, never in the repo),
        // so CI stops here while the committed nav json assertions
        // above still run everywhere
        if !root.join("maps_local/dm4.bsp").exists() {
            return;
        }
        assert!(
            full.hotspots.iter().any(|h| h.cause.as_deref() == Some("lava_edge")),
            "dm4 pit hotspots must tag lava_edge: {:?}",
            full.hotspots.iter().map(|h| (h.x, h.y, h.z, h.cause.clone())).collect::<Vec<_>>()
        );
        // item clocks: a 335 s 4-track dm4 match laps the RL spawns
        let rl = full
            .item_control
            .iter()
            .find(|r| r.classname == "weapon_rocketlauncher")
            .expect("RL control row");
        assert!(rl.visits >= 5, "RL visits {}", rl.visits);
        assert!(
            !full.flags.iter().any(|f| f.contains("DIRECTED SINK")),
            "dm4 reaches 98% - no sink flag belongs here: {:?}",
            full.flags
        );
    }

    #[test]
    fn paired_demo_joins_the_brief_if_present() {
        // machine-local: needs the harvested v374 session (tape
        // committed, demo in the gitignored runs/demos)
        use crate::config::load_for_reads_from;
        use std::collections::HashMap;
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        if !root.join("runs/demos/shane_dm4_2026-08-27_v374.dem").exists() {
            return;
        }
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let brief = brief_run(&cfg, "shane_dm4_2026-08-27_v374", None).unwrap();
        let demo = brief.paired_demo.as_ref().expect("demo joined");
        assert!(demo.highlights.iter().any(|h| h.kind == "multikill"), "{:?}", demo.highlights);
        assert!(demo.tracks.iter().any(|t| t.name.as_deref() == Some("player")));
        assert!(brief.flags.iter().any(|f| f.contains("paired demo joined")));
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

    // #211: with no map= the baseline used to resolve to a dm4 tape
    // whatever the candidate was, and an unknown map fell through to
    // ab_dm4_parity in silence.
    #[test]
    fn baseline_without_a_map_is_an_error_not_a_dm4_tape() {
        let root = std::env::temp_dir().join(format!("argus-nohint-{}", std::process::id()));
        let runs = root.join("runs");
        std::fs::create_dir_all(&runs).unwrap();
        std::fs::write(runs.join("ab_dm4_parity.log"), log_a()).unwrap();
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = crate::config::load_for_reads_from(&env, &root).unwrap();
        assert!(resolve_baseline(&cfg, None).is_err());
        assert!(resolve_baseline(&cfg, Some("e1m1")).is_err());
        assert!(resolve_baseline(&cfg, Some("dm4")).is_ok());
        let _ = std::fs::remove_dir_all(&root);
    }

    // #211: the candidate's own header supplies the map when none is passed.
    #[test]
    fn compare_with_no_map_takes_the_hint_from_the_candidate() {
        let root = std::env::temp_dir().join(format!("argus-hint-{}", std::process::id()));
        let runs = root.join("runs");
        std::fs::create_dir_all(&runs).unwrap();
        let dm2 = log_a().replace("init on dm4", "init on dm2");
        std::fs::write(runs.join("cand_dm2.log"), &dm2).unwrap();
        std::fs::write(runs.join("base_dm2.log"), &dm2).unwrap();
        std::fs::write(runs.join("ab_dm4_parity.log"), log_a()).unwrap();
        std::fs::write(runs.join("baselines.json"), r#"{"dm2": "base_dm2"}"#).unwrap();
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = crate::config::load_for_reads_from(&env, &root).unwrap();
        let rep = compare_runs(&cfg, "baseline", "cand_dm2", None).unwrap();
        assert_eq!(rep.a.map.as_deref(), Some("dm2"));
        assert_eq!(rep.b.map.as_deref(), Some("dm2"));
        let _ = std::fs::remove_dir_all(&root);
    }

    // #216: identical clean tapes are parity, and a couple of stalls on a
    // short tape is noise, not a hard fail.
    #[test]
    fn short_tape_stall_gate_has_a_floor() {
        let clean = "ARGUS init on dm4
ARGLOG Reap t 1.0 pos '0.0 0.0 24.0' spd 0 yaw 0 mode 2 st 0 gl 0 hp 100 frg 1
ARGLOG Reap t 30.0 pos '64.0 0.0 24.0' spd 200 yaw 0 mode 2 st 0 gl 8 hp 90 frg 4
";
        let a = brief_text(clean, Some("dm4"));
        let b = brief_text(clean, Some("dm4"));
        let rep = compare_briefs(a, b);
        assert_eq!(rep.verdict, Verdict::Parity, "two zero-stall tapes are parity");

        let two = clean.replace("st 0 gl 8", "st 2 gl 8");
        let a = brief_text(clean, Some("dm4"));
        let b = brief_text(&two, Some("dm4"));
        let rep = compare_briefs(a, b);
        let g = rep.gates.iter().find(|g| g.name == "stall_parity").unwrap();
        assert!(g.pass, "2 stalls against a 0-stall baseline is inside the floor");
    }

    // #216: coverage saturates. Scaling it made the gate unfailable.
    #[test]
    fn coverage_is_not_scaled_and_not_gated_on_short_tapes() {
        let a = brief_text(&log_a(), Some("dm4"));
        let cover = a.totals.cover;
        let scaled = scale_brief_to_duration(a, 30.0);
        assert_eq!(scaled.totals.cover, cover, "cover must survive scaling");
        let b = brief_text(&log_a(), Some("dm4"));
        let rep = compare_briefs(scaled, b);
        let g = rep.gates.iter().find(|g| g.name == "coverage").unwrap();
        assert!(g.note.contains("not gated"));
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

    #[test]
    fn gate_card_formatting_renders_card() {
        let a = brief_text(&log_a(), None);
        let b = brief_text(&log_lava(), None);
        let report = compare_briefs(a.clone(), b.clone());
        assert!(report.gate_card.contains("ARGUS A/B QUALITY GATES"));
        assert!(report.gate_card.contains("Lava/Slime Deaths"));
        assert!(report.gate_card.contains("Nav Stalls"));
        assert!(report.gate_card.contains("🔴"));
        assert!(report.gate_card.contains("REJECTED"));

        let parity = compare_briefs(a.clone(), a);
        assert!(parity.gate_card.contains("🟢"));
        assert!(parity.gate_card.contains("APPROVED FOR RELEASE"));
    }
}
