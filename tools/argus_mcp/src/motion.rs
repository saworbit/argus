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
    context: Vec<String>,
    turns: Vec<(f64, String)>,
}

fn sample_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(
        r"^ARGMOT (.+?) ms\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' wish\s+(-?[\d.]+) cause ([a-z_]+) ctx '[^']+' hp\s+(-?[\d.]+) ground(?: .*|)$"
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
            let numbers: Option<Vec<f64>> = [2, 3, 4, 5, 6, 8]
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
        let mut reversal_events = Vec::new();
        let epoch_count = streams.len();
        for stream in streams.values() {
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
                reversal_events,
            });
        }
    }
    Some(MotionReport {
        layout: "argus-motion-v2".into(),
        eligible_for_reversal_claims: errors.is_empty() && !rows.is_empty(),
        errors,
        bots: rows,
    })
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
