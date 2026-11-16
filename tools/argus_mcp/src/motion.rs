//! Opt-in full-rate movement observations, separate from ARGLOG counters.
use crate::demo::{movement_stats, MovementStats};
use crate::parse_arglog::{is_instrument, GameEvent};
use regex::Regex;
use serde::Serialize;
use std::collections::{BTreeMap, HashSet};
use std::sync::OnceLock;

#[derive(Debug, Clone, Serialize)]
pub struct MotionReport {
    pub layout: String,
    pub eligible_for_reversal_claims: bool,
    pub errors: Vec<String>,
    /// Brink deflection episodes for every bot, keyed by the steering
    /// cause that preceded each one (see `BotMotion::deflection_causes`).
    pub deflection_causes: BTreeMap<String, usize>,
    /// Brink encounters for every bot, keyed by what started each one (see
    /// `BotMotion::brink_encounters`). Judge brink changes on these.
    pub brink_encounters: BTreeMap<String, usize>,
    pub bots: Vec<BotMotion>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BotMotion {
    pub name: String,
    pub samples: usize,
    pub epochs: usize,
    pub measured_hz: f64,
    pub movement: MovementStats,
    pub marker_attributed: usize,
    pub unattributed: usize,
    pub reversal_causes: BTreeMap<String, usize>,
    /// Context is useful evidence, but is not relabelled as a proven cause.
    pub unattributed_context: BTreeMap<String, usize>,
    /// A run of `hazard_*` samples is one deflection episode, credited to
    /// the last non-hazard cause before it. The ARGEVT hazard count is
    /// throttled to one a second per bot and cannot say whether route
    /// steering or a combat strafe met the brink; this can (
    /// docs/specs/2026-11-16-route-elbow-protocol.md). It also counts
    /// flicker: route steering re-asserts its heading for a frame or two
    /// between guard deflections, so one encounter reads as many episodes.
    pub deflection_causes: BTreeMap<String, usize>,
    /// Episodes less than `ENCOUNTER_GAP_SEC` apart merged into one brink
    /// encounter, keyed by what started it: the steering cause before it,
    /// or for route steering `route_turn` (the wish rotating at least 3.5
    /// degrees a frame for three frames, the same way), `route_steady`
    /// (routed and not turning) or `route_seek` (unrouted). On
    /// lab_voidcorner three in four mid-turn route episodes began straight
    /// after a previous deflection, and the encounter rate was far steadier
    /// between ladders than the episode rate (docs/lab-scenarios.md).
    pub brink_encounters: BTreeMap<String, usize>,
    pub reversal_events: Vec<ReversalObservation>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReversalObservation {
    pub t: f64,
    pub pos: [f32; 3],
    pub marker_cause: Option<String>,
    pub active_branch: String,
}

#[derive(Default)]
struct Epoch {
    t: Vec<f64>,
    pos: Vec<[f32; 3]>,
    wish: Vec<f64>,
    mode: Vec<i64>,
    context: Vec<String>,
    turns: Vec<(f64, String)>,
}

/// Deflections closer together than this belong to one brink encounter.
pub const ENCOUNTER_GAP_SEC: f64 = 0.25;

fn sample_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(
        r"^ARGMOT (.+?) ms\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' wish\s+(-?[\d.]+) cause ([a-z_]+) ctx '\s*(-?[\d.]+)[^']*' hp\s+(-?[\d.]+) ground(?: .*|)$"
    ).expect("motion sample grammar"))
}

fn turn_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^ARGUS (.+?) flip ([a-z_]+) ms\s+([\d.]+) from\s+(-?[\d.]+) to\s+(-?[\d.]+)$")
            .expect("motion turn grammar")
    })
}

/// Called on the selected map segment. Only identities with bot birth events
/// qualify; humans and instruments never enter the bot movement report.
pub fn inspect(text: &str, events: &[GameEvent]) -> Option<MotionReport> {
    let bots: HashSet<&str> = events
        .iter()
        .filter(|e| matches!(e.verb.as_str(), "spawned" | "respawn") && !is_instrument(&e.bot))
        .map(|e| e.bot.as_str())
        .collect();
    let mut epochs: BTreeMap<String, BTreeMap<usize, Epoch>> = BTreeMap::new();
    let mut epoch = 0;
    let mut active = false;
    let mut errors = Vec::new();
    let mut seen = false;
    for (line_no, line) in text.lines().enumerate() {
        let line = line.trim_end_matches('\r');
        if line.starts_with("ARGMOT begin") {
            seen = true;
            epoch += 1;
            active = line == "ARGMOT begin layout 2";
            if !active {
                errors.push(format!("unsupported motion layout at line {}", line_no + 1));
            }
            continue;
        }
        if let Some(c) = sample_re().captures(line) {
            seen = true;
            if !active {
                errors.push(format!(
                    "motion sample without layout at line {}",
                    line_no + 1
                ));
                continue;
            }
            if !bots.contains(&c[1]) {
                continue;
            }
            let numbers: Option<Vec<f64>> = [2, 3, 4, 5, 6, 9, 8]
                .iter()
                .map(|i| c[*i].parse::<f64>().ok().filter(|v| v.is_finite()))
                .collect();
            let Some(n) = numbers else {
                errors.push(format!("invalid motion number at line {}", line_no + 1));
                continue;
            };
            let stream = epochs
                .entry(c[1].into())
                .or_default()
                .entry(epoch)
                .or_default();
            if stream.t.last().is_some_and(|last| n[0] / 1000.0 <= *last)
                || n[1..4]
                    .iter()
                    .any(|value| value.abs() > f64::from(f32::MAX))
            {
                errors.push(format!(
                    "invalid motion order or position at line {}",
                    line_no + 1
                ));
                continue;
            }
            stream.t.push(n[0] / 1000.0);
            stream.pos.push([n[1] as f32, n[2] as f32, n[3] as f32]);
            stream.wish.push(n[4]);
            stream.mode.push(n[6] as i64);
            stream.context.push(c[7].into());
        } else if let Some(c) = turn_re().captures(line) {
            seen = true;
            if !active {
                errors.push(format!(
                    "motion turn without layout at line {}",
                    line_no + 1
                ));
                continue;
            }
            if !bots.contains(&c[1]) {
                continue;
            }
            let numbers: Option<Vec<f64>> = [3, 4, 5]
                .iter()
                .map(|i| c[*i].parse::<f64>().ok().filter(|v| v.is_finite()))
                .collect();
            if let Some(n) = numbers.filter(|n| {
                let delta = (n[2] - n[1] + 180.0).rem_euclid(360.0) - 180.0;
                delta.is_finite() && delta.abs() >= 89.9
            }) {
                epochs
                    .entry(c[1].into())
                    .or_default()
                    .entry(epoch)
                    .or_default()
                    .turns
                    .push((n[0] / 1000.0, c[2].into()));
            } else {
                errors.push(format!("invalid turn at line {}", line_no + 1));
            }
        } else if line.starts_with("ARGMOT ") {
            seen = true;
            errors.push(format!("malformed motion sample at line {}", line_no + 1));
        }
    }
    if !seen {
        return None;
    }
    let mut rows = Vec::new();
    for (name, streams) in epochs {
        let mut total: Option<MovementStats> = None;
        let mut samples = 0;
        let mut measured_intervals = 0;
        let mut measured_sec = 0.0;
        let mut attributed = 0;
        let mut unattributed = 0;
        let mut causes = BTreeMap::new();
        let mut context = BTreeMap::new();
        let mut deflections = BTreeMap::new();
        let mut encounters = BTreeMap::new();
        let mut reversal_events = Vec::new();
        let epoch_count = streams.len();
        for stream in streams.values() {
            count_deflections(&stream.context, &mut deflections);
            count_encounters(stream, &mut encounters);
            let Some(stats) = movement_stats(&stream.t, &stream.pos) else {
                continue;
            };
            samples += stream.t.len();
            measured_intervals += stream
                .t
                .windows(2)
                .filter(|w| w[1] > w[0] && w[1] - w[0] <= 0.25)
                .count();
            measured_sec += stream
                .t
                .windows(2)
                .filter(|w| w[1] > w[0] && w[1] - w[0] <= 0.25)
                .map(|w| w[1] - w[0])
                .sum::<f64>();
            for reversal in &stats.reversal_times {
                let index = stream
                    .t
                    .partition_point(|t| *t <= *reversal)
                    .saturating_sub(1);
                let branch = stream.context.get(index).cloned().unwrap_or_default();
                let marker = stream
                    .turns
                    .iter()
                    .rev()
                    .find(|(t, _)| *t <= *reversal && reversal - t <= 0.25);
                if let Some((_, cause)) = marker {
                    attributed += 1;
                    *causes.entry(cause.clone()).or_insert(0) += 1;
                } else {
                    unattributed += 1;
                    *context.entry(branch.clone()).or_insert(0) += 1;
                }
                reversal_events.push(ReversalObservation {
                    t: *reversal,
                    pos: stream.pos[index],
                    marker_cause: marker.map(|(_, cause)| cause.clone()),
                    active_branch: branch,
                });
            }
            if let Some(sum) = &mut total {
                sum.observed_sec += stats.observed_sec;
                sum.moving_sec += stats.moving_sec;
                sum.reversals += stats.reversals;
                sum.discontinuities += stats.discontinuities;
                sum.reversal_times
                    .extend(stats.reversal_times.iter().copied());
            } else {
                total = Some(stats);
            }
        }
        if let Some(mut stats) = total {
            stats.reversals_per_moving_minute =
                (stats.moving_sec > 0.0).then(|| stats.reversals as f64 * 60.0 / stats.moving_sec);
            rows.push(BotMotion {
                name,
                samples,
                epochs: epoch_count,
                measured_hz: if measured_sec > 0.0 {
                    measured_intervals as f64 / measured_sec
                } else {
                    0.0
                },
                movement: stats,
                marker_attributed: attributed,
                unattributed,
                reversal_causes: causes,
                unattributed_context: context,
                deflection_causes: deflections,
                brink_encounters: encounters,
                reversal_events,
            });
        }
    }
    let mut deflection_causes = BTreeMap::new();
    let mut brink_encounters = BTreeMap::new();
    for bot in &rows {
        for (cause, n) in &bot.deflection_causes {
            *deflection_causes.entry(cause.clone()).or_insert(0) += n;
        }
        for (start, n) in &bot.brink_encounters {
            *brink_encounters.entry(start.clone()).or_insert(0) += n;
        }
    }
    Some(MotionReport {
        layout: "argus-motion-v2".into(),
        eligible_for_reversal_claims: errors.is_empty() && !rows.is_empty(),
        errors,
        deflection_causes,
        brink_encounters,
        bots: rows,
    })
}

/// Fold one epoch into brink encounters by what started each one.
fn count_encounters(stream: &Epoch, out: &mut BTreeMap<String, usize>) {
    let causes = &stream.context;
    let rotation =
        |k: usize| (stream.wish[k] - stream.wish[k - 1] + 180.0).rem_euclid(360.0) - 180.0;
    let mut last_hazard: Option<f64> = None;
    let mut inside = false;
    for i in 0..causes.len() {
        let hazard = causes[i].starts_with("hazard_");
        if hazard && !inside {
            let fresh = last_hazard.is_none_or(|t| stream.t[i] - t > ENCOUNTER_GAP_SEC);
            if fresh {
                let start = match (0..i).rev().find(|&j| !causes[j].starts_with("hazard_")) {
                    None => "unknown".to_string(),
                    Some(j) if causes[j] != "route_steer" => causes[j].clone(),
                    Some(j) if stream.mode[j] != 2 => "route_seek".to_string(),
                    Some(j) => {
                        let turning = j >= 3 && {
                            let r = [rotation(j), rotation(j - 1), rotation(j - 2)];
                            r.iter().all(|v| v.abs() >= 3.5)
                                && (r.iter().all(|v| *v > 0.0) || r.iter().all(|v| *v < 0.0))
                        };
                        if turning {
                            "route_turn"
                        } else {
                            "route_steady"
                        }
                        .to_string()
                    }
                };
                *out.entry(start).or_insert(0) += 1;
            }
        }
        if hazard {
            last_hazard = Some(stream.t[i]);
        }
        inside = hazard;
    }
}

/// Fold one epoch's per-sample causes into deflection episodes by the
/// steering cause that led into each. An epoch that opens mid-deflection
/// credits it to "unknown" rather than guessing.
fn count_deflections(causes: &[String], out: &mut BTreeMap<String, usize>) {
    let mut before: Option<&str> = None;
    let mut inside = false;
    for cause in causes {
        if cause.starts_with("hazard_") {
            if !inside {
                *out.entry(before.unwrap_or("unknown").to_string())
                    .or_insert(0) += 1;
            }
            inside = true;
        } else {
            inside = false;
            before = Some(cause);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn born(name: &str) -> GameEvent {
        GameEvent {
            bot: name.into(),
            verb: "spawned".into(),
            rest: String::new(),
            t: Some(0.0),
            pos: None,
        }
    }
    fn sample(name: &str, ms: u32, x: i32) -> String {
        format!("ARGMOT {name} ms {ms} pos '{x} 0 24' wish 0 cause combat_strafe ctx '2 0 1' hp 100 ground worldspawn\n")
    }
    fn reversal(name: &str, marker: bool) -> String {
        format!(
            "ARGMOT begin layout 2\n{}{}{}{}",
            sample(name, 0, 0),
            sample(name, 100, 20),
            if marker {
                format!("ARGUS {name} flip strafe_reroll ms 100 from 0 to 180\n")
            } else {
                String::new()
            },
            sample(name, 200, 0)
        )
    }

    #[test]
    fn actual_motion_and_intent_marker_are_distinct_evidence() {
        let report = inspect(&reversal("Joe Rogan", true), &[born("Joe Rogan")]).unwrap();
        assert!(report.eligible_for_reversal_claims);
        let bot = &report.bots[0];
        assert_eq!(bot.movement.reversals, 1);
        assert_eq!(bot.marker_attributed, 1);
        assert_eq!(bot.unattributed, 0);
        assert_eq!(bot.reversal_causes.get("strafe_reroll"), Some(&1));
    }

    #[test]
    fn deflection_episodes_are_credited_to_the_cause_before_them() {
        let row = |ms: u32, x: i32, cause: &str| {
            format!("ARGMOT Romero ms {ms} pos '{x} 0 24' wish 0 cause {cause} ctx '2 0 1' hp 100 ground worldspawn
")
        };
        let mut text = String::from(
            "ARGMOT begin layout 2
",
        );
        for (i, cause) in [
            "hazard_fan",
            "route_steer",
            "hazard_fan",
            "hazard_hold",
            "route_steer",
            "combat_hazard",
            "hazard_hold",
            "combat_hazard",
        ]
        .iter()
        .enumerate()
        {
            text.push_str(&row(100 * i as u32, 4 * i as i32, cause));
        }
        let report = inspect(&text, &[born("Romero")]).unwrap();
        let bot = &report.bots[0];
        assert_eq!(bot.deflection_causes.get("route_steer"), Some(&1));
        assert_eq!(bot.deflection_causes.get("combat_hazard"), Some(&1));
        assert_eq!(bot.deflection_causes.get("unknown"), Some(&1));
        assert_eq!(report.deflection_causes, bot.deflection_causes);
    }

    #[test]
    fn flicker_inside_a_quarter_second_is_one_brink_encounter() {
        let row = |ms: u32, wish: i32, cause: &str| {
            format!("ARGMOT Carmack ms {ms} pos '{ms} 0 24' wish {wish} cause {cause} ctx '2 0 1' hp 100 ground worldspawn\n")
        };
        let mut text = String::from("ARGMOT begin layout 2\n");
        // a straight routed run meets the brink, then route steering and the
        // guard alternate frame by frame: one encounter, three episodes
        let frames: [(i32, &str); 12] = [
            (90, "route_steer"),
            (90, "route_steer"),
            (90, "route_steer"),
            (90, "route_steer"),
            (60, "hazard_hold"),
            (65, "route_steer"),
            (60, "hazard_hold"),
            (65, "route_steer"),
            (60, "hazard_hold"),
            (65, "route_steer"),
            (65, "route_steer"),
            (65, "route_steer"),
        ];
        for (i, (wish, cause)) in frames.iter().enumerate() {
            text.push_str(&row(14 * i as u32, *wish, cause));
        }
        // half a second later a turning routed run starts a second encounter
        for (k, wish) in [10, 15, 20, 25].iter().enumerate() {
            text.push_str(&row(700 + 14 * k as u32, *wish, "route_steer"));
        }
        text.push_str(&row(760, 25, "hazard_fan"));
        let report = inspect(&text, &[born("Carmack")]).unwrap();
        let bot = &report.bots[0];
        assert_eq!(bot.deflection_causes.get("route_steer"), Some(&4));
        assert_eq!(bot.brink_encounters.get("route_steady"), Some(&1));
        assert_eq!(bot.brink_encounters.get("route_turn"), Some(&1));
        assert_eq!(bot.brink_encounters.values().sum::<usize>(), 2);
        assert_eq!(report.brink_encounters, bot.brink_encounters);
    }

    #[test]
    fn context_is_not_promoted_to_a_proven_cause() {
        let report = inspect(&reversal("Joe Rogan", false), &[born("Joe Rogan")]).unwrap();
        let bot = &report.bots[0];
        assert_eq!(bot.marker_attributed, 0);
        assert_eq!(bot.unattributed, 1);
        assert_eq!(bot.unattributed_context.get("combat_strafe"), Some(&1));
    }

    #[test]
    fn human_and_instrument_tracks_never_enter_bot_bands() {
        for name in ["player", "labprobe"] {
            let births = if name == "labprobe" {
                vec![born(name)]
            } else {
                Vec::new()
            };
            assert!(inspect(&reversal(name, true), &births)
                .unwrap()
                .bots
                .is_empty());
        }
    }

    #[test]
    fn invalid_layout_missing_header_and_duplicate_times_refuse_claims() {
        let good = reversal("Joe Rogan", true);
        for text in [
            good.replace("layout 2", "layout 1"),
            good.replace("ARGMOT begin layout 2\n", ""),
            good.replace("ms 200 pos", "ms 100 pos"),
            good.replace("from 0 to 180", "from 0 to 0"),
        ] {
            assert!(
                !inspect(&text, &[born("Joe Rogan")])
                    .unwrap()
                    .eligible_for_reversal_claims
            );
        }
    }

    #[test]
    fn new_epoch_never_bridges_an_unobserved_interval() {
        let text = format!(
            "ARGMOT begin layout 2\n{}{}ARGMOT begin layout 2\n{}{}",
            sample("Joe Rogan", 0, 0),
            sample("Joe Rogan", 100, 20),
            sample("Joe Rogan", 150, 20),
            sample("Joe Rogan", 250, 0)
        );
        let report = inspect(&text, &[born("Joe Rogan")]).unwrap();
        assert_eq!(report.bots[0].movement.reversals, 0);
        assert_eq!(report.bots[0].epochs, 2);
    }

    #[test]
    fn tape_and_match_brief_keep_existing_counters_separate() {
        let text=format!("ARGUS init on dm4\nARGEVT Joe Rogan spawned\nARGLOG Joe Rogan t 0 pos '0 0 24' spd 0 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n{}",reversal("Joe Rogan",true));
        let tape = crate::parse_arglog::parse_tape(&text);
        assert_eq!(tape.samples["Joe Rogan"].len(), 1);
        assert_eq!(
            tape.movement.as_ref().unwrap().bots[0].movement.reversals,
            1
        );
        let brief = crate::intel::brief_tape(&tape, Some("dm4"));
        assert_eq!(brief.movement.unwrap().bots[0].marker_attributed, 1);
    }
}
