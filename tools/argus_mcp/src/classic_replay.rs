//! Side-by-side observations from ordinary protocol 15 demos.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::demo::{parse_demo_with_players, VisiblePlayer};

const MAX_GAP: f64 = 0.25;
const MAX_SPEED: f64 = 1000.0;
const PAUSE_SPEED: f64 = 10.0;
const MIN_PAUSE: f64 = 0.5;
const NEAR_DISTANCE: f64 = 256.0;

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Setup {
    map: String,
    engine: String,
    rules: String,
    perspective: String,
    recordings: Vec<Recording>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Recording {
    demo: PathBuf,
    bot: String,
    version: String,
    skill: String,
    subject_entity: u16,
    opponent_entity: u16,
}

#[derive(Debug, Default, Serialize)]
struct Observation {
    demo_md5: String,
    duration_sec: f64,
    observed_sec: f64,
    travelled_u: f64,
    paused_sec: f64,
    pair_observed_sec: f64,
    pair_near_sec: f64,
}

#[derive(Serialize)]
pub struct Report {
    setup: Setup,
    observations: Vec<Observation>,
    protocol: u8,
    notes: Vec<String>,
}

pub fn compare(path: &Path) -> Result<Report, String> {
    let bytes = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut setup: Setup =
        serde_json::from_slice(&bytes).map_err(|e| format!("{}: {e}", path.display()))?;
    setup.map = crate::paths::map_name(&setup.map)?;
    if setup.recordings.len() < 2
        || [&setup.engine, &setup.rules, &setup.perspective]
            .iter()
            .any(|s| s.trim().is_empty())
    {
        return Err("declare the engine, rules, perspective and at least two recordings".into());
    }

    let mut sources = BTreeSet::new();
    let mut observations = Vec::with_capacity(setup.recordings.len());
    for recording in &setup.recordings {
        let name = recording.demo.display();
        if [&recording.bot, &recording.version, &recording.skill]
            .iter()
            .any(|s| s.trim().is_empty())
            || recording.subject_entity == 0
            || recording.opponent_entity == 0
            || recording.subject_entity == recording.opponent_entity
        {
            return Err(format!(
                "{name}: declare bot, version, skill and two distinct player entities"
            ));
        }
        let file = path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join(&recording.demo);
        let bytes = std::fs::read(&file).map_err(|e| format!("{}: {e}", file.display()))?;
        let digest = format!("{:x}", md5::compute(&bytes));
        if !sources.insert(digest.clone()) {
            return Err(format!("{name}: the suite repeats the same demo bytes"));
        }
        let demo = parse_demo_with_players(&name.to_string(), &bytes)
            .map_err(|error| format!("{name}: {error}"))?;
        if demo.brief.protocol != 15
            || demo.brief.truncated
            || !demo.brief.duration_sec.is_finite()
            || demo.brief.duration_sec <= 0.0
        {
            return Err(format!("{name}: expected a complete protocol 15 demo"));
        }
        if demo.map_starts.len() != 1 || demo.map_starts[0].as_deref() != Some(setup.map.as_str()) {
            return Err(format!(
                "{name}: expected exactly one start on {}",
                setup.map
            ));
        }
        let samples = |entity| {
            demo.visible_players
                .get(&entity)
                .ok_or_else(|| format!("{name}: player entity {entity} has no recorded samples"))
        };
        let mut row = measure(
            samples(recording.subject_entity)?,
            samples(recording.opponent_entity)?,
        );
        if row.observed_sec == 0.0 {
            return Err(format!(
                "{name}: subject has no continuous observed intervals"
            ));
        }
        row.demo_md5 = digest;
        row.duration_sec = demo.brief.duration_sec;
        observations.push(row);
    }

    Ok(Report {
        setup,
        observations,
        protocol: 15,
        notes: vec![
            "The manifest declares the engine, rules, perspective and bot builds. Each demo confirms the map and protocol.".into(),
            format!("Recorder visibility limits the samples. Movement uses consecutive demo blocks with gaps up to {MAX_GAP} seconds and speed up to {MAX_SPEED} units per second."),
            format!("A pause is at least {MIN_PAUSE} seconds at or below {PAUSE_SPEED} units per second. Nearby exposure requires both entities within {NEAR_DISTANCE} units at both ends of an observed interval."),
            "Nearby exposure measures proximity in the recorded stream. Lines of sight, attacks and events outside the recorder's view require other evidence. Skill settings are specific to each bot.".into(),
        ],
    })
}

fn distance(a: [f32; 3], b: [f32; 3]) -> f64 {
    a.into_iter()
        .zip(b)
        .map(|(a, b)| (f64::from(a) - f64::from(b)).powi(2))
        .sum::<f64>()
        .sqrt()
}

fn interval(a: &VisiblePlayer, b: &VisiblePlayer) -> Option<(f64, f64)> {
    let dt = b.time - a.time;
    let travelled = distance(a.pos, b.pos);
    (b.block == a.block + 1 && dt > 0.0 && dt <= MAX_GAP && travelled <= MAX_SPEED * dt)
        .then_some((dt, travelled))
}

fn measure(subject: &[VisiblePlayer], opponent: &[VisiblePlayer]) -> Observation {
    let mut row = Observation::default();
    let mut pause = 0.0;
    let opponent: BTreeMap<_, _> = opponent
        .iter()
        .map(|sample| (sample.block, sample))
        .collect();
    for pair in subject.windows(2) {
        let (a, b) = (&pair[0], &pair[1]);
        let step = interval(a, b);
        if let Some((dt, _)) = step.filter(|&(dt, travelled)| travelled <= PAUSE_SPEED * dt) {
            pause += dt;
        } else {
            if pause >= MIN_PAUSE {
                row.paused_sec += pause;
            }
            pause = 0.0;
        }
        let Some((dt, travelled)) = step else {
            continue;
        };
        row.observed_sec += dt;
        row.travelled_u += travelled;
        if let Some((other_a, other_b)) = opponent.get(&a.block).zip(opponent.get(&b.block)) {
            if interval(other_a, other_b).is_some() {
                row.pair_observed_sec += dt;
                if distance(a.pos, other_a.pos) <= NEAR_DISTANCE
                    && distance(b.pos, other_b.pos) <= NEAR_DISTANCE
                {
                    row.pair_near_sec += dt;
                }
            }
        }
    }
    if pause >= MIN_PAUSE {
        row.paused_sec += pause;
    }
    row
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn block(demo: &mut Vec<u8>, messages: &[u8]) {
        demo.extend((messages.len() as u32).to_le_bytes());
        demo.extend([0; 12]);
        demo.extend(messages);
    }

    fn frame(demo: &mut Vec<u8>, t: f32, players: &[(u8, u8, i16)]) {
        let mut messages = vec![7]; // svc_time
        messages.extend(t.to_le_bytes());
        for &(entity, model, x) in players {
            // Fast update with U_MOREBITS, U_ORIGIN1 and U_MODEL.
            messages.extend([0x83, 0x04, entity, model]);
            messages.extend((8 * x).to_le_bytes());
        }
        block(demo, &messages);
    }

    fn demo(map: &str, rival_x: i16) -> Vec<u8> {
        let mut demo = b"-1\n".to_vec();
        let mut server = vec![11]; // svc_serverinfo
        server.extend(15_i32.to_le_bytes());
        server.extend([1, 1]); // maxclients, gametype
        server.extend(format!("Fixture map\0maps/{map}.bsp\0progs/player.mdl\0\0\0").bytes());
        block(&mut demo, &server);
        for i in 0..=5 {
            let mut visible = vec![(12, 2, 0)];
            if i != 3 {
                visible.push((19, 2, rival_x));
            }
            frame(&mut demo, i as f32 / 8.0, &visible);
        }
        frame(&mut demo, 0.75, &[(12, 2, 16), (19, 2, rival_x + 16)]);
        frame(&mut demo, 0.875, &[(19, 2, rival_x)]);
        frame(&mut demo, 1.0, &[(12, 2, 2048)]);
        frame(&mut demo, 1.125, &[(12, 1, 2048)]);
        frame(&mut demo, 1.25, &[(12, 2, 2048)]);
        block(&mut demo, &[2]); // svc_disconnect
        demo
    }

    #[test]
    fn classic_replays_use_visible_player_updates_and_refuse_the_wrong_map() {
        let dir = crate::test_support::TestDir::new("classic-replay").unwrap();
        let path = dir.path().join("suite.json");
        let recording = |demo, bot, skill| {
            json!({
                "demo": demo, "bot": bot, "skill": skill, "version": "test",
                "subject_entity": 12, "opponent_entity": 19
            })
        };
        let suite = json!({
            "map": "dm4", "engine": "QuakeSpasm test", "rules": "deathmatch 1",
            "perspective": "fixed observer", "recordings": [
                recording("one.dem", "Argus", "skill 1"),
                recording("two.dem", "Reference", "skill 3")
            ]
        });
        std::fs::write(&path, suite.to_string()).unwrap();
        std::fs::write(dir.path().join("one.dem"), demo("dm4", 32)).unwrap();
        let second = dir.path().join("two.dem");
        std::fs::write(&second, demo("dm2", 512)).unwrap();
        assert!(compare(&path)
            .err()
            .unwrap()
            .contains("expected exactly one start on dm4"));
        std::fs::write(&second, demo("dm4", 512)).unwrap();
        let report = compare(&path).unwrap();
        let first = &report.observations[0];
        assert_eq!(first.observed_sec, 0.75);
        assert_eq!(first.travelled_u, 16.0);
        assert_eq!(first.paused_sec, 0.625);
        assert_eq!(first.pair_observed_sec, 0.5);
        assert_eq!(first.pair_near_sec, 0.5);
        assert_eq!(report.observations[1].pair_near_sec, 0.0);
        assert_eq!(report.setup.recordings[1].skill, "skill 3");
    }
}
