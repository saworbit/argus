//! Counterbalanced control and candidate arms inside the same match (#374).
//!
//! Both arms share the map, item economy, spawn stream and frame timing. The
//! second tape swaps the per-slot assignment so personality is not confounded
//! with the arm. This instrument is valid only for code paths gated per bot;
//! graph and other world-level changes still require separate matches.

use std::collections::BTreeMap;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::Serialize;

use crate::config::Config;
use crate::match_ctrl::MatchCtrl;
use crate::netclient::NetClient;
use crate::parse_arglog::{parse_tape_path, BotStats, MatchTape};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Arm {
    Control,
    Candidate,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ArmScore {
    pub bots: usize,
    pub stalls_mean: f64,
    pub goals_mean: f64,
    pub frags_mean: f64,
    pub deaths_mean: f64,
    pub engagements_mean: f64,
    pub avg_speed_mean: f64,
    pub cross_arm_kills: u32,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct ArmDelta {
    pub stalls: f64,
    pub goals: f64,
    pub frags: f64,
    pub deaths: f64,
    pub engagements: f64,
    pub avg_speed: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct StrengthEstimate {
    pub candidate_cross_arm_kills: u32,
    pub control_cross_arm_kills: u32,
    /// Two-arm Bradley-Terry log strength, candidate minus control.
    pub log_strength: f64,
    pub ci95_low: f64,
    pub ci95_high: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ArmTrial {
    pub run_name: String,
    pub log_path: String,
    pub candidate_mask: u32,
    pub control: ArmScore,
    pub candidate: ArmScore,
    pub candidate_minus_control: ArmDelta,
    pub strength: StrengthEstimate,
}

#[derive(Debug, Clone, Serialize)]
pub struct WithinAbReport {
    pub map: String,
    pub duration_sec: u32,
    pub skill: u32,
    pub note: String,
    pub trials: Vec<ArmTrial>,
    pub paired_mean_candidate_minus_control: ArmDelta,
    pub combined_strength: StrengthEstimate,
}

fn assignments(tape: &MatchTape) -> Result<BTreeMap<String, Arm>, String> {
    let mut out = BTreeMap::new();
    for event in tape.events.iter().filter(|event| event.verb == "arm") {
        let arm = match event.rest.split_whitespace().next() {
            Some("control") => Arm::Control,
            Some("candidate") => Arm::Candidate,
            _ => return Err(format!("{}: malformed arm event", event.bot)),
        };
        out.insert(event.bot.clone(), arm);
    }
    let controls = out.values().filter(|arm| **arm == Arm::Control).count();
    let candidates = out.values().filter(|arm| **arm == Arm::Candidate).count();
    if controls != 2 || candidates != 2 {
        return Err(format!(
            "within-match A/B needs two control and two candidate bots; tape has {controls} and {candidates}"
        ));
    }
    Ok(out)
}

fn arm_score(
    tape: &MatchTape,
    rows: &[BotStats],
    arms: &BTreeMap<String, Arm>,
    arm: Arm,
) -> Result<ArmScore, String> {
    let selected: Vec<&BotStats> = rows
        .iter()
        .filter(|row| arms.get(&row.name) == Some(&arm))
        .collect();
    if selected.len() != 2 {
        return Err(format!(
            "arm assignment names did not resolve to two ARGLOG bot rows (found {})",
            selected.len()
        ));
    }
    let n = selected.len() as f64;
    let mean = |values: Vec<f64>| values.into_iter().sum::<f64>() / n;
    let engagements = |name: &str| {
        tape.events
            .iter()
            .filter(|event| event.bot == name && event.verb == "engage")
            .count() as f64
    };
    let cross_arm_kills = tape
        .deaths
        .iter()
        .filter(|death| {
            arms.get(&death.killer) == Some(&arm)
                && arms
                    .get(&death.victim)
                    .is_some_and(|victim_arm| *victim_arm != arm)
        })
        .count() as u32;
    Ok(ArmScore {
        bots: selected.len(),
        stalls_mean: mean(selected.iter().map(|row| row.stalls as f64).collect()),
        goals_mean: mean(selected.iter().map(|row| row.goals as f64).collect()),
        frags_mean: mean(
            selected
                .iter()
                .map(|row| row.frags.unwrap_or_default() as f64)
                .collect(),
        ),
        deaths_mean: mean(selected.iter().map(|row| row.deaths as f64).collect()),
        engagements_mean: mean(selected.iter().map(|row| engagements(&row.name)).collect()),
        avg_speed_mean: mean(selected.iter().map(|row| row.avg).collect()),
        cross_arm_kills,
    })
}

fn delta(control: &ArmScore, candidate: &ArmScore) -> ArmDelta {
    ArmDelta {
        stalls: candidate.stalls_mean - control.stalls_mean,
        goals: candidate.goals_mean - control.goals_mean,
        frags: candidate.frags_mean - control.frags_mean,
        deaths: candidate.deaths_mean - control.deaths_mean,
        engagements: candidate.engagements_mean - control.engagements_mean,
        avg_speed: candidate.avg_speed_mean - control.avg_speed_mean,
    }
}

fn strength(candidate: u32, control: u32) -> StrengthEstimate {
    // Haldane-Anscombe correction keeps an all-zero null finite. With two
    // arms, the Bradley-Terry MLE is the log ratio of their cross-arm wins.
    let c = candidate as f64 + 0.5;
    let k = control as f64 + 0.5;
    let estimate = (c / k).ln();
    let radius = 1.96 * (1.0 / c + 1.0 / k).sqrt();
    StrengthEstimate {
        candidate_cross_arm_kills: candidate,
        control_cross_arm_kills: control,
        log_strength: estimate,
        ci95_low: estimate - radius,
        ci95_high: estimate + radius,
    }
}

fn analyze_tape(run_name: &str, log_path: &str, mask: u32) -> Result<ArmTrial, String> {
    let tape =
        parse_tape_path(std::path::Path::new(log_path)).map_err(|error| error.to_string())?;
    let arms = assignments(&tape)?;
    let rows = tape.summary().bots;
    let control = arm_score(&tape, &rows, &arms, Arm::Control)?;
    let candidate = arm_score(&tape, &rows, &arms, Arm::Candidate)?;
    Ok(ArmTrial {
        run_name: run_name.into(),
        log_path: log_path.into(),
        candidate_mask: mask,
        candidate_minus_control: delta(&control, &candidate),
        strength: strength(candidate.cross_arm_kills, control.cross_arm_kills),
        control,
        candidate,
    })
}

fn mean_delta(trials: &[ArmTrial]) -> ArmDelta {
    let n = trials.len() as f64;
    let mean = |get: fn(&ArmDelta) -> f64| {
        trials
            .iter()
            .map(|trial| get(&trial.candidate_minus_control))
            .sum::<f64>()
            / n
    };
    ArmDelta {
        stalls: mean(|d| d.stalls),
        goals: mean(|d| d.goals),
        frags: mean(|d| d.frags),
        deaths: mean(|d| d.deaths),
        engagements: mean(|d| d.engagements),
        avg_speed: mean(|d| d.avg_speed),
    }
}

async fn run_trial(
    cfg: &Config,
    map: &str,
    duration_sec: u32,
    skill: u32,
    run_name: &str,
    mask: u32,
) -> Result<ArmTrial, String> {
    let mut ctrl = MatchCtrl::default();
    ctrl.begin(
        cfg,
        map,
        duration_sec.saturating_add(15),
        Some(run_name),
        Some(5),
        Some(skill),
        Some(false),
    )
    .await?;

    let setup = async {
        let mut client = NetClient::connect("127.0.0.1", 26000, "labprobe")?;
        client.pump(Duration::from_secs(3));
        if client.world.signon < 3 {
            return Err(format!("signon stalled at {}", client.world.signon));
        }
        ctrl.command("scratch1 147").await?;
        tokio::time::sleep(Duration::from_millis(200)).await;
        client.set_impulse(101); // fourth bot: two bodies per arm
        client.pump(Duration::from_millis(800));
        ctrl.command(&format!("scratch4 {mask}")).await?;
        tokio::time::sleep(Duration::from_millis(200)).await;
        client.set_impulse(215); // snapshot and emit the assignment
        client.pump(Duration::from_millis(500));
        client.disconnect();
        Ok::<(), String>(())
    }
    .await;
    if let Err(error) = setup {
        let _ = ctrl.stop(Duration::from_secs(3)).await;
        return Err(error);
    }

    tokio::time::sleep(Duration::from_secs(duration_sec as u64)).await;
    let result = ctrl.finish(cfg, map).await?;
    analyze_tape(&result.run_name, &result.log_path, mask)
}

pub async fn run_pair(
    cfg: &Config,
    map: &str,
    duration_sec: u32,
    skill: u32,
    prefix: Option<&str>,
) -> Result<WithinAbReport, String> {
    crate::engine::validate_map(map)?;
    if !(10..=300).contains(&duration_sec) {
        return Err("within-match A/B duration must be 10..=300 seconds".into());
    }
    if skill > 3 {
        return Err("skill must be 0..3".into());
    }
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let base = prefix
        .map(str::to_string)
        .unwrap_or_else(|| format!("within_{map}_{stamp}"));
    if !crate::paths::valid_run_name(&base) {
        return Err("run prefix must match [A-Za-z0-9._-]+".into());
    }
    let first = run_trial(cfg, map, duration_sec, skill, &format!("{base}_a"), 5).await?;
    let second = run_trial(cfg, map, duration_sec, skill, &format!("{base}_b"), 10).await?;
    let trials = vec![first, second];
    let candidate_kills = trials
        .iter()
        .map(|trial| trial.candidate.cross_arm_kills)
        .sum();
    let control_kills = trials
        .iter()
        .map(|trial| trial.control.cross_arm_kills)
        .sum();
    Ok(WithinAbReport {
        map: map.into(),
        duration_sec,
        skill,
        note: "Per-bot code paths only. Slot masks 5 and 10 are swapped across the two tapes; nav/world changes are invalid on this instrument.".into(),
        paired_mean_candidate_minus_control: mean_delta(&trials),
        combined_strength: strength(candidate_kills, control_kills),
        trials,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse_arglog::parse_tape;

    fn tape(mask: u32) -> String {
        let arms = if mask == 5 {
            [
                ("Carmack", "candidate"),
                ("Romero", "control"),
                ("Joe Rogan", "candidate"),
                ("Mr Elusive", "control"),
            ]
        } else {
            [
                ("Carmack", "control"),
                ("Romero", "candidate"),
                ("Joe Rogan", "control"),
                ("Mr Elusive", "candidate"),
            ]
        };
        let mut text = String::from("ARGUS init on dm4\n");
        for (index, (name, arm)) in arms.iter().enumerate() {
            text.push_str(&format!("ARGEVT {name} spawned\nARGEVT {name} arm {arm}\nARGLOG {name} t 10.0 pos '{} 0 24' spd {} yaw 0 mode 2 st {} gl {} hp 100 frg {}\n", index * 64, 100 + index, index, index + 1, index));
        }
        text.push_str("ARGEVT Carmack engage Romero\nARGEVT Carmack death Romero pos '0 0 24'\nARGEVT Romero death Carmack pos '0 0 24'\n");
        text
    }

    #[test]
    fn arm_events_require_two_bots_on_each_side() {
        let good = parse_tape(&tape(5));
        assert_eq!(assignments(&good).unwrap().len(), 4);
        let bad = parse_tape("ARGEVT Carmack arm candidate\n");
        assert!(assignments(&bad).unwrap_err().contains("two control"));
    }

    #[test]
    fn swapped_slots_are_scored_by_arm_not_name() {
        for mask in [5, 10] {
            let parsed = parse_tape(&tape(mask));
            let arms = assignments(&parsed).unwrap();
            let rows = parsed.summary().bots;
            let control = arm_score(&parsed, &rows, &arms, Arm::Control).unwrap();
            let candidate = arm_score(&parsed, &rows, &arms, Arm::Candidate).unwrap();
            assert_eq!(control.bots, 2);
            assert_eq!(candidate.bots, 2);
            assert_eq!(control.cross_arm_kills + candidate.cross_arm_kills, 2);
        }
    }

    #[test]
    fn bradley_terry_null_is_centered_and_finite() {
        let estimate = strength(0, 0);
        assert_eq!(estimate.log_strength, 0.0);
        assert!(estimate.ci95_low.is_finite());
        assert!(estimate.ci95_high.is_finite());
    }
}
