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

use crate::config::Config;
use crate::engine::EngineClock;
use crate::match_ctrl::MatchCtrl;
use serde::Serialize;
use std::collections::VecDeque;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

/// First lane port; lane k uses `LANE_PORT_BASE + k`.
pub const LANE_PORT_BASE: u16 = 26060;
pub const MAX_LANES: u32 = 8;
/// The QC burns `saved4` draws in one think; 2000 keeps it far inside the
/// original engine's runaway limit (Argus_Init says why).
pub const MAX_SEED: u32 = 2_000;

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
    if let Some(bad) = opts.seeds.iter().find(|s| **s == 0 || **s > MAX_SEED) {
        return Err(format!("seed {bad} is outside 1..={MAX_SEED}"));
    }
    let mut unique = opts.seeds.clone();
    unique.sort_unstable();
    unique.dedup();
    if unique.len() != opts.seeds.len() {
        return Err("a seed is listed twice: one seed and build is one match".into());
    }
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
                            let id = &r.brief.identity;
                            outcome = Some(SeedRun {
                                run_name: run_name.clone(),
                                seed,
                                lane,
                                ok: true,
                                wall_sec: round1(wall),
                                error: None,
                                headline: Some(r.brief.headline.clone()),
                                duration_sec: Some(r.brief.totals.duration_sec),
                                build: id.build.clone(),
                                tape_seed: id.clock.as_ref().map(|c| c.seed),
                            });
                            break;
                        }
                        Err(e) => {
                            // a startup loss is retried once; anything else
                            // is reported as it happened
                            let retry = attempt == 0 && e.contains("before ARGLOG");
                            outcome = Some(SeedRun {
                                run_name: run_name.clone(),
                                seed,
                                lane,
                                ok: false,
                                wall_sec: round1(wall),
                                error: Some(e),
                                headline: None,
                                duration_sec: None,
                                build: None,
                                tape_seed: None,
                            });
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
    let wall = started.elapsed().as_secs_f64();
    let game: f64 = runs.iter().filter_map(|r| r.duration_sec).sum();
    let ok = runs.iter().filter(|r| r.ok).count();
    Ok(SeedReport {
        map: opts.map.clone(),
        clock: "fixed",
        lanes: opts.lanes,
        failed: runs.len() - ok,
        ok,
        runs,
        wall_sec: round1(wall),
        game_sec: round1(game),
        throughput: if wall > 0.0 { round1(game / wall) } else { 0.0 },
    })
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
}
