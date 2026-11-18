//! Seeded fixed-clock ladders: many matches, several engines at once.
//!
//! The fixed lab clock (`EngineClock::Fixed`) runs a match at the played
//! frame rate but faster than real time, and repeats exactly for one seed.
//! A ladder of N seeds on L lanes therefore costs roughly
//! N * duration / (6.5 * L) seconds of wall time instead of N * duration,
//! and any one of its tapes can be replayed bit for bit by its seed - a
//! freeze or a death that happened once can be made to happen again.
//!
//! Tapes are named `<stem>_s<seed>` and land in runs/ like any other match.
//! Each lane owns its own UDP port, and every lane launch takes the run
//! directory's lease, so two ladders cannot share a tape.
//!
//! The MCP server reaches the same clock through `match_run seeds` (#853),
//! one engine at a time through its single live match slot, and only on maps
//! where tools/lab_instruments.json records the fixed clock as accepted
//! (`fixed_clock_standing`). This CLI stays open on every map, because a
//! validation has to record fixed tapes on a map before it can accept one.

use crate::config::Config;
use crate::engine::EngineClock;
use crate::match_ctrl::{MatchCtrl, MatchRunResult};
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

/// First lane port; lane k uses `LANE_PORT_BASE + k`.
pub const LANE_PORT_BASE: u16 = 26060;
pub const MAX_LANES: u32 = 8;
/// The QC burns `saved4` draws in one think; 2000 keeps it far inside the
/// original engine's runaway limit (Argus_Init says why).
pub const MAX_SEED: u32 = 2_000;
/// Most seeds one MCP `match_run` takes. The server runs them one after
/// another on one engine, so ten 185 s tapes cost about five minutes of wall
/// time; `argus-mcp seeds` runs a longer ladder on parallel lanes.
pub const MAX_MCP_SEEDS: usize = 10;

#[derive(Debug, Clone)]
pub struct SeedOptions {
    pub map: String,
    pub count: u32,
    pub stem: String,
    pub duration_sec: u32,
    pub skill: Option<u32>,
    pub lanes: u32,
    /// Index of the first seed in the sequence `seed_for` walks.
    pub first: u32,
    /// Explicit seeds, in place of the walked sequence.
    pub seeds: Vec<u32>,
    pub coop: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct SeedRun {
    pub run_name: String,
    pub seed: u32,
    pub lane: u32,
    pub ok: bool,
    pub wall_sec: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub headline: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub duration_sec: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub build: Option<String>,
    /// The seed the tape itself reports, which must equal `seed`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tape_seed: Option<u64>,
}

impl SeedRun {
    /// A lane's finished match, with what its tape says about itself.
    pub fn from_result(
        run_name: String,
        seed: u32,
        lane: u32,
        wall_sec: f64,
        result: &MatchRunResult,
    ) -> Self {
        let id = &result.brief.identity;
        SeedRun {
            run_name,
            seed,
            lane,
            ok: true,
            wall_sec: round1(wall_sec),
            error: None,
            headline: Some(result.brief.headline.clone()),
            duration_sec: Some(result.brief.totals.duration_sec),
            build: id.build.clone(),
            tape_seed: id.clock.as_ref().map(|c| c.seed),
        }
    }

    /// A lane's match that produced no usable tape.
    pub fn failed(run_name: String, seed: u32, lane: u32, wall_sec: f64, error: String) -> Self {
        SeedRun {
            run_name,
            seed,
            lane,
            ok: false,
            wall_sec: round1(wall_sec),
            error: Some(error),
            headline: None,
            duration_sec: None,
            build: None,
            tape_seed: None,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SeedReport {
    pub map: String,
    pub clock: &'static str,
    pub lanes: u32,
    pub runs: Vec<SeedRun>,
    pub ok: usize,
    pub failed: usize,
    pub wall_sec: f64,
    pub game_sec: f64,
    /// Game seconds recorded per wall second, across all lanes.
    pub throughput: f64,
}

impl SeedReport {
    /// Totals over `runs`, kept in the order given.
    pub fn from_runs(map: String, lanes: u32, runs: Vec<SeedRun>, wall_sec: f64) -> Self {
        let game: f64 = runs.iter().filter_map(|r| r.duration_sec).sum();
        let ok = runs.iter().filter(|r| r.ok).count();
        SeedReport {
            map,
            clock: "fixed",
            lanes,
            failed: runs.len() - ok,
            ok,
            runs,
            wall_sec: round1(wall_sec),
            game_sec: round1(game),
            throughput: if wall_sec > 0.0 {
                round1(game / wall_sec)
            } else {
                0.0
            },
        }
    }
}

/// What a seeded MCP `match_run` says about the clock it ran on (#853): the
/// clock, its frame and seeds, and every metric the map's registered
/// validation did not read equivalent. Those are the map's limits.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct FixedClockCard {
    pub clock: &'static str,
    pub frame_ms: f64,
    pub seeds: Vec<u32>,
    /// Metric to reading (inconclusive, different, not measured).
    pub limits: BTreeMap<String, String>,
    pub rule: &'static str,
}

pub const FIXED_CLOCK_RULE: &str = "A fixed tape cannot settle a limit metric on this map: \
    a claim about one needs wall-clock tapes, and a change that passes a fixed screen still \
    owes them (docs/fixed-clock.md).";

/// The fixed clock's frame for this launch, in milliseconds.
pub fn launch_frame_ms() -> f64 {
    crate::engine::fixed_frame()
        .parse::<f64>()
        .map(|sec| (sec * 1e6).round() / 1e3)
        .unwrap_or(0.0)
}

/// The map's fixed-clock standing from `instruments` (the parsed
/// tools/lab_instruments.json), or why a seeded match is refused there.
/// `frame_ms` is the frame the launch would run, which must be the frame
/// the map was validated at: acceptance at 14.25 ms says nothing of 13.9.
pub fn fixed_clock_card(
    instruments: &Value,
    map: &str,
    frame_ms: f64,
    seeds: &[u32],
) -> Result<FixedClockCard, String> {
    let maps = instruments
        .pointer("/fixed_clock/maps")
        .and_then(Value::as_object);
    let accepted = |entry: &Value| entry.get("accepted").and_then(Value::as_bool) == Some(true);
    let Some(entry) = maps.and_then(|m| m.get(map)).filter(|e| accepted(e)) else {
        let names: Vec<&str> = maps
            .map(|m| {
                m.iter()
                    .filter(|(_, e)| accepted(e))
                    .map(|(name, _)| name.as_str())
                    .collect()
            })
            .unwrap_or_default();
        let standing = if names.is_empty() {
            "on no map".to_string()
        } else {
            format!("on {} only", names.join(", "))
        };
        return Err(format!(
            "the fixed clock is not validated on {map}: tools/lab_instruments.json accepts it \
             {standing} (docs/fixed-clock.md). Run {map} without seeds, on the wall clock."
        ));
    };
    let validated = entry
        .get("frame_ms")
        .and_then(Value::as_f64)
        .or_else(|| {
            instruments
                .pointer("/fixed_clock/frame_ms")
                .and_then(Value::as_f64)
        })
        .ok_or_else(|| {
            format!("tools/lab_instruments.json records no validated frame for {map}")
        })?;
    if (validated - frame_ms).abs() > 1e-6 {
        return Err(format!(
            "the fixed clock is validated on {map} at {validated} ms and this launch would run \
             {frame_ms} ms (ARGUS_FIXED_FRAME). Unset it, or measure a frame with argus-mcp \
             match --seed."
        ));
    }
    let metrics = entry
        .get("metrics")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            format!("tools/lab_instruments.json records no metric readings for {map}")
        })?;
    let limits = metrics
        .iter()
        .filter_map(|(metric, reading)| {
            let reading = reading.as_str().unwrap_or("unrecorded");
            (reading != "equivalent").then(|| (metric.clone(), reading.to_string()))
        })
        .collect();
    Ok(FixedClockCard {
        clock: "fixed",
        frame_ms,
        seeds: seeds.to_vec(),
        limits,
        rule: FIXED_CLOCK_RULE,
    })
}

/// `fixed_clock_card` against the checkout's tools/lab_instruments.json and
/// the frame this launch would run.
pub fn fixed_clock_standing(
    cfg: &Config,
    map: &str,
    seeds: &[u32],
) -> Result<FixedClockCard, String> {
    let path = cfg.root.join("tools").join("lab_instruments.json");
    let unknown = |why: String| {
        format!(
            "{why}: the fixed clock's standing on {map} is unknown, so a seeded match is refused"
        )
    };
    let text = std::fs::read_to_string(&path)
        .map_err(|e| unknown(format!("cannot read {}: {e}", path.display())))?;
    let instruments: Value = serde_json::from_str(&text)
        .map_err(|e| unknown(format!("{} is not JSON: {e}", path.display())))?;
    fixed_clock_card(&instruments, map, launch_frame_ms(), seeds)
}

/// The seeds an MCP `match_run` may take: 1 to `MAX_MCP_SEEDS` of them,
/// each run in turn on the one engine the server drives.
pub fn validate_mcp_seeds(seeds: &[u32]) -> Result<(), String> {
    if seeds.is_empty() {
        return Err("seeds needs at least one seed; omit it to run on the wall clock".into());
    }
    if seeds.len() > MAX_MCP_SEEDS {
        return Err(format!(
            "at most {MAX_MCP_SEEDS} seeds per match_run, which runs them one after another on \
             one engine; argus-mcp seeds runs a longer ladder on parallel lanes"
        ));
    }
    check_seed_list(seeds)
}

/// Every seed in range, and none twice: one seed and build is one match.
fn check_seed_list(seeds: &[u32]) -> Result<(), String> {
    if let Some(bad) = seeds.iter().find(|s| **s == 0 || **s > MAX_SEED) {
        return Err(format!("seed {bad} is outside 1..={MAX_SEED}"));
    }
    let mut unique = seeds.to_vec();
    unique.sort_unstable();
    unique.dedup();
    if unique.len() != seeds.len() {
        return Err("a seed is listed twice: one seed and build is one match".into());
    }
    Ok(())
}

/// The `index`-th seed: a fixed walk through 1..=1999 (1999 is prime, so
/// the walk visits every seed once before repeating) that keeps neighbouring
/// indices far apart. Adjacent seeds shift the random stream by a single
/// draw, which on a seed burnt before the roster spawns can still pick the
/// same spawn pads; spacing them avoids that start.
pub fn seed_for(index: u32) -> u32 {
    1 + ((u64::from(index) * 1291) % 1999) as u32
}

pub fn validate(opts: &SeedOptions) -> Result<(), String> {
    if opts.count == 0 && opts.seeds.is_empty() {
        return Err("count must be at least 1".into());
    }
    if opts.count > 200 || opts.seeds.len() > 200 {
        return Err("at most 200 seeds per ladder".into());
    }
    if !(1..=MAX_LANES).contains(&opts.lanes) {
        return Err(format!("lanes must be 1..={MAX_LANES}"));
    }
    check_seed_list(&opts.seeds)?;
    if !crate::paths::valid_run_name(&format!("{}_s1", opts.stem)) {
        return Err(format!("stem {}", crate::paths::RUN_NAME_RULE));
    }
    crate::paths::map_name(&opts.map).map(|_| ())
}

pub fn seed_list(opts: &SeedOptions) -> Vec<u32> {
    if !opts.seeds.is_empty() {
        return opts.seeds.clone();
    }
    (opts.first..opts.first + opts.count)
        .map(seed_for)
        .collect()
}

pub async fn run(cfg: Arc<Config>, opts: SeedOptions) -> Result<SeedReport, String> {
    validate(&opts)?;
    let queue: Arc<Mutex<VecDeque<u32>>> =
        Arc::new(Mutex::new(seed_list(&opts).into_iter().collect()));
    let results: Arc<Mutex<Vec<SeedRun>>> = Arc::new(Mutex::new(Vec::new()));
    let started = Instant::now();
    let opts = Arc::new(opts);
    let mut workers = Vec::new();
    for lane in 0..opts.lanes {
        let port = LANE_PORT_BASE + lane as u16;
        let (cfg, opts, queue, results) =
            (cfg.clone(), opts.clone(), queue.clone(), results.clone());
        workers.push(tokio::spawn(async move {
            // Staggered starts: engines launched in the same instant have
            // been seen to lose one at network initialisation on Windows.
            tokio::time::sleep(Duration::from_millis(1500 * u64::from(lane))).await;
            let mut ctrl = MatchCtrl::on_port(port);
            loop {
                let Some(seed) = queue.lock().await.pop_front() else {
                    break;
                };
                let run_name = format!("{}_s{seed}", opts.stem);
                let mut outcome = None;
                for attempt in 0..2 {
                    ctrl.set_clock(EngineClock::fixed(seed));
                    let t0 = Instant::now();
                    let res = ctrl
                        .run(
                            &cfg,
                            &opts.map,
                            opts.duration_sec,
                            Some(&run_name),
                            None,
                            opts.skill,
                            Some(opts.coop),
                        )
                        .await;
                    let wall = t0.elapsed().as_secs_f64();
                    match res {
                        Ok(r) => {
                            outcome =
                                Some(SeedRun::from_result(run_name.clone(), seed, lane, wall, &r));
                            break;
                        }
                        Err(e) => {
                            // a startup loss is retried once; anything else
                            // is reported as it happened
                            let retry = attempt == 0 && e.contains("before ARGLOG");
                            outcome = Some(SeedRun::failed(run_name.clone(), seed, lane, wall, e));
                            if !retry {
                                break;
                            }
                            tokio::time::sleep(Duration::from_secs(2)).await;
                        }
                    }
                }
                if let Some(o) = outcome {
                    results.lock().await.push(o);
                }
            }
            ctrl.shutdown().await;
        }));
    }
    for w in workers {
        w.await.map_err(|e| format!("lane task failed: {e}"))?;
    }
    let mut runs = std::mem::take(&mut *results.lock().await);
    runs.sort_by_key(|r| r.seed);
    Ok(SeedReport::from_runs(
        opts.map.clone(),
        opts.lanes,
        runs,
        started.elapsed().as_secs_f64(),
    ))
}

fn round1(v: f64) -> f64 {
    (v * 10.0).round() / 10.0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opts() -> SeedOptions {
        SeedOptions {
            map: "dm4".into(),
            count: 4,
            stem: "fx_dm4".into(),
            duration_sec: 185,
            skill: Some(2),
            lanes: 4,
            first: 1,
            seeds: Vec::new(),
            coop: false,
        }
    }

    #[test]
    fn the_seed_walk_is_in_range_spread_and_distinct() {
        let seeds: Vec<u32> = (0..1999).map(seed_for).collect();
        assert!(seeds.iter().all(|s| (1..=MAX_SEED).contains(s)));
        let unique: std::collections::BTreeSet<_> = seeds.iter().collect();
        assert_eq!(unique.len(), seeds.len());
        assert!(seeds.windows(2).all(|w| w[0].abs_diff(w[1]) > 50));
    }

    #[test]
    fn options_are_validated_before_any_engine() {
        assert!(validate(&opts()).is_ok());
        assert!(validate(&SeedOptions { lanes: 0, ..opts() }).is_err());
        assert!(validate(&SeedOptions { lanes: 9, ..opts() }).is_err());
        assert!(validate(&SeedOptions { count: 0, ..opts() }).is_err());
        assert!(validate(&SeedOptions {
            stem: "../x".into(),
            ..opts()
        })
        .is_err());
        assert!(validate(&SeedOptions {
            map: "../dm4".into(),
            ..opts()
        })
        .is_err());
        assert!(validate(&SeedOptions {
            seeds: vec![0],
            ..opts()
        })
        .is_err());
        assert!(validate(&SeedOptions {
            seeds: vec![2_001],
            ..opts()
        })
        .is_err());
        assert!(validate(&SeedOptions {
            seeds: vec![5, 5],
            ..opts()
        })
        .is_err());
    }

    #[test]
    fn explicit_seeds_replace_the_walk() {
        assert_eq!(
            seed_list(&SeedOptions {
                seeds: vec![5, 9],
                ..opts()
            }),
            vec![5, 9]
        );
        assert_eq!(seed_list(&opts()), (1..5).map(seed_for).collect::<Vec<_>>());
    }

    fn instruments(frame_ms: f64) -> Value {
        serde_json::json!({
            "fixed_clock": {
                "frame_ms": frame_ms,
                "maps": {
                    "dm4": {
                        "accepted": true,
                        "frame_ms": frame_ms,
                        "metrics": {
                            "stalls": "inconclusive",
                            "engages": "equivalent",
                            "lava_deaths": "different",
                            "avg_speed": "not measured"
                        }
                    },
                    "dm2": {"accepted": true, "metrics": {"goals": "equivalent"}},
                    "dm3": {"accepted": false, "frame_ms": frame_ms, "metrics": {}},
                    "dm6": {"accepted": true, "frame_ms": frame_ms}
                }
            }
        })
    }

    #[test]
    fn the_card_names_the_clock_and_every_metric_not_read_equivalent() {
        let card = fixed_clock_card(&instruments(14.25), "dm4", 14.25, &[273, 1564]).unwrap();
        assert_eq!(card.clock, "fixed");
        assert_eq!(card.frame_ms, 14.25);
        assert_eq!(card.seeds, vec![273, 1564]);
        let limits: Vec<(&str, &str)> = card
            .limits
            .iter()
            .map(|(m, r)| (m.as_str(), r.as_str()))
            .collect();
        assert_eq!(
            limits,
            [
                ("avg_speed", "not measured"),
                ("lava_deaths", "different"),
                ("stalls", "inconclusive")
            ]
        );
        assert!(card.rule.contains("wall-clock tapes"));
        // a map with no frame of its own falls back to the instrument's
        let dm2 = fixed_clock_card(&instruments(14.25), "dm2", 14.25, &[5]).unwrap();
        assert!(dm2.limits.is_empty());
    }

    #[test]
    fn the_card_refuses_what_the_validation_did_not_accept() {
        let record = instruments(14.25);
        for map in ["dm3", "e1m1"] {
            let error = fixed_clock_card(&record, map, 14.25, &[5]).unwrap_err();
            assert!(
                error.contains(&format!("not validated on {map}"))
                    && error.contains("dm2, dm4, dm6 only")
                    && error.contains("without seeds"),
                "{error}"
            );
        }
        let error = fixed_clock_card(&record, "dm4", 13.9, &[5]).unwrap_err();
        assert!(error.contains("validated on dm4 at 14.25 ms"), "{error}");
        assert!(error.contains("13.9 ms"), "{error}");
        let error = fixed_clock_card(&record, "dm6", 14.25, &[5]).unwrap_err();
        assert!(error.contains("no metric readings"), "{error}");
        let error = fixed_clock_card(&serde_json::json!({}), "dm4", 14.25, &[5]).unwrap_err();
        assert!(error.contains("on no map"), "{error}");
    }

    /// The checkout's own record, read the way the MCP reads it. dm4's
    /// acceptance at the default frame is the settled result in
    /// docs/fixed-clock.md, and its lava reading is the limit that doc warns
    /// about most.
    #[test]
    fn the_checkout_record_accepts_dm4_at_the_default_frame() {
        let text = std::fs::read_to_string(
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../lab_instruments.json"),
        )
        .unwrap();
        let record: Value = serde_json::from_str(&text).unwrap();
        let frame = crate::engine::FIXED_FRAME.parse::<f64>().unwrap() * 1e3;
        let frame = (frame * 1e3).round() / 1e3;
        let card = fixed_clock_card(&record, "dm4", frame, &[273]).unwrap();
        assert_eq!(card.frame_ms, 14.25);
        assert!(card.limits.contains_key("lava_deaths"));
        assert!(!card.limits.contains_key("engages"));
        assert!(fixed_clock_card(&record, "nonesuch", frame, &[273]).is_err());
    }

    #[test]
    fn mcp_seed_lists_are_short_in_range_and_distinct() {
        assert!(validate_mcp_seeds(&[273]).is_ok());
        assert!(validate_mcp_seeds(&(1..=MAX_MCP_SEEDS as u32).collect::<Vec<_>>()).is_ok());
        for (seeds, why) in [
            (vec![], "at least one"),
            ((1..=MAX_MCP_SEEDS as u32 + 1).collect(), "at most"),
            (vec![0], "outside"),
            (vec![MAX_SEED + 1], "outside"),
            (vec![5, 9, 5], "twice"),
        ] {
            let error = validate_mcp_seeds(&seeds).unwrap_err();
            assert!(error.contains(why), "{seeds:?}: {error}");
        }
    }
}
