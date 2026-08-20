//! ARGLOG / ARGEVT tape, aligned with tools/analyze_match.py.

use regex::Regex;
use serde::Serialize;
use std::collections::{BTreeMap, HashSet};
use std::sync::OnceLock;

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Pos {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct BotStats {
    pub name: String,
    pub dur: f64,
    pub dist: f64,
    pub avg: f64,
    pub cover: usize,
    pub goals: i32,
    pub stalls: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frags: Option<i32>,
    pub deaths: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hp: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MatchSummary {
    pub bots: Vec<BotStats>,
    pub events: BTreeMap<String, u32>,
}

#[derive(Debug, Clone)]
pub struct Sample {
    pub t: f64,
    pub pos: Pos,
    pub spd: f64,
    pub mode: u8,
    pub stalls: i32,
    pub goals: i32,
    pub hp: Option<f64>,
    pub frags: Option<i32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DeathEvent {
    pub victim: String,
    pub killer: String,
    pub pos: Pos,
}

#[derive(Debug, Clone)]
pub struct GameEvent {
    pub bot: String,
    pub verb: String,
    pub rest: String,
    pub t: Option<f64>,
    pub pos: Option<Pos>,
}

#[derive(Debug, Clone)]
pub struct MatchTape {
    pub map: Option<String>,
    pub samples: BTreeMap<String, Vec<Sample>>,
    pub deaths: Vec<DeathEvent>,
    pub events: Vec<GameEvent>,
    pub event_counts: BTreeMap<String, u32>,
}

impl MatchTape {
    pub fn summary(&self) -> MatchSummary {
        let mut bots: Vec<BotStats> = self
            .samples
            .iter()
            .map(|(name, rec)| {
                let first = rec.first().unwrap();
                let last = rec.last().unwrap();
                let dur = last.t - first.t;
                let dist = rec
                    .windows(2)
                    .map(|w| {
                        let dx = w[1].pos.x - w[0].pos.x;
                        let dy = w[1].pos.y - w[0].pos.y;
                        (dx * dx + dy * dy).sqrt()
                    })
                    .sum::<f64>();
                let cover = rec
                    .iter()
                    .map(|p| {
                        (
                            (p.pos.x / 64.0).floor() as i32,
                            (p.pos.y / 64.0).floor() as i32,
                        )
                    })
                    .collect::<HashSet<_>>()
                    .len();
                let deaths = self
                    .deaths
                    .iter()
                    .filter(|d| d.victim == *name)
                    .count() as i32;
                BotStats {
                    name: name.clone(),
                    dur,
                    dist,
                    avg: if dur > 0.0 { dist / dur } else { 0.0 },
                    cover,
                    goals: last.goals,
                    stalls: last.stalls,
                    frags: last.frags,
                    hp: last.hp,
                    deaths,
                }
            })
            .collect();
        bots.sort_by(|a, b| a.name.cmp(&b.name));
        MatchSummary {
            bots,
            events: self.event_counts.clone(),
        }
    }

    pub fn last_pos(&self, bot: &str) -> Option<Pos> {
        self.samples.get(bot).and_then(|s| s.last()).map(|s| s.pos)
    }

    pub fn pos_at_or_before(&self, bot: &str, t: f64) -> Option<Pos> {
        self.samples.get(bot).and_then(|s| {
            s.iter()
                .rev()
                .find(|sm| sm.t <= t + 0.05)
                .or(s.last())
                .map(|sm| sm.pos)
        })
    }
}

pub fn parse_arglog(text: &str) -> MatchSummary {
    parse_tape(text).summary()
}

pub fn parse_arglog_path(path: &std::path::Path) -> std::io::Result<MatchSummary> {
    let text = std::fs::read_to_string(path)?;
    Ok(parse_arglog(&text))
}

pub fn parse_tape_path(path: &std::path::Path) -> std::io::Result<MatchTape> {
    let text = std::fs::read_to_string(path)?;
    Ok(parse_tape(&text))
}

pub fn parse_tape(text: &str) -> MatchTape {
    let v1 = v1_re();
    let death = death_re();
    let evt = evt_re();
    let map_re = map_re();

    let mut samples: BTreeMap<String, Vec<Sample>> = BTreeMap::new();
    let mut deaths = Vec::new();
    let mut events = Vec::new();
    let mut event_counts: BTreeMap<String, u32> = BTreeMap::new();
    let mut map = None;
    let mut last_t: BTreeMap<String, f64> = BTreeMap::new();

    for line in text.lines() {
        if map.is_none() {
            if let Some(caps) = map_re.captures(line) {
                map = Some(caps[1].to_ascii_lowercase());
            }
        }
        if let Some(caps) = v1.captures(line) {
            let name = caps[1].to_string();
            let t = caps[2].parse().unwrap_or(0.0);
            samples.entry(name.clone()).or_default().push(Sample {
                t,
                pos: Pos {
                    x: caps[3].parse().unwrap_or(0.0),
                    y: caps[4].parse().unwrap_or(0.0),
                    z: caps[5].parse().unwrap_or(0.0),
                },
                spd: caps[6].parse().unwrap_or(0.0),
                mode: caps[8].parse().unwrap_or(0),
                stalls: caps[9].parse().unwrap_or(0),
                goals: caps[10].parse().unwrap_or(0),
                hp: caps.get(11).and_then(|m| m.as_str().parse().ok()),
                frags: caps.get(12).and_then(|m| m.as_str().parse().ok()),
            });
            last_t.insert(name, t);
            continue;
        }
        if let Some(caps) = death.captures(line) {
            deaths.push(DeathEvent {
                victim: caps[1].to_string(),
                killer: caps
                    .get(2)
                    .map(|m| m.as_str().to_string())
                    .unwrap_or_else(|| "world".to_string()),
                pos: Pos {
                    x: caps[3].parse().unwrap_or(0.0),
                    y: caps[4].parse().unwrap_or(0.0),
                    z: caps[5].parse().unwrap_or(0.0),
                },
            });
        }
        if let Some(caps) = evt.captures(line) {
            let bot = caps[1].to_string();
            let verb = caps[2].to_string();
            let rest = caps.get(3).map(|m| m.as_str().trim().to_string()).unwrap_or_default();
            // Argus_Die logs a bare "death" then "death <killer> pos ...".
            // Count only the detailed line.
            if verb == "death" && rest.is_empty() {
                continue;
            }
            *event_counts.entry(verb.clone()).or_insert(0) += 1;
            let t = last_t.get(&bot).copied();
            let pos = t.and_then(|tt| {
                samples.get(&bot).and_then(|s| {
                    s.iter()
                        .rev()
                        .find(|sm| sm.t <= tt + 0.05)
                        .map(|sm| sm.pos)
                })
            });
            events.push(GameEvent {
                bot,
                verb,
                rest,
                t,
                pos,
            });
        }
    }

    MatchTape {
        map,
        samples,
        deaths,
        events,
        event_counts,
    }
}

// Netnames may contain spaces (the v3.37 homage roster: "Joe Rogan").
// Anchor on the grammar keywords, never on whitespace-splitting - a
// \S+ name silently dropped every spaced bot from briefs and A/B
// verdicts (the analyzer's parsers learnt this on 2026-08-19; this
// parser caught up the same day).
fn v1_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(
            r"(?:BOTLOG|ARGLOG) (.+?) t\s+([\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)' spd\s+(-?[\d.]+) yaw\s+(-?[\d.]+) mode\s+(\d) st\s+(\d+) gl\s+(\d+)(?: hp\s+(-?[\d.]+) frg\s+(-?\d+))?",
        )
        .expect("v1 regex")
    })
}

fn death_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        // the killer may be spaced too, and historical rows can carry
        // an empty killer (nameless crushers pre-v3.21)
        Regex::new(
            r"ARGEVT (.+?) death\s+(?:(.+?)\s+)?pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'",
        )
        .expect("death regex")
    })
}

fn evt_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        // the verb comes from the closed telemetry vocabulary: a lazy
        // name followed by \S+ would split "Joe Rogan" into name
        // "Joe" and verb "Rogan"
        Regex::new(
            r"ARGEVT (.+?) (spawned|respawn|goal|route|routefail|trapped|abandon|stall|stallnode|jump|rjump|lift|swim|door|train|hazard|engage|pursue|retreat|grab|weapon|plan|death)(?:\s+(.*))?$",
        )
        .expect("evt regex")
    })
}

fn map_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)(?:SpawnServer:\s+|ARGUS init on\s+)([A-Za-z0-9_]+)")
            .expect("map regex")
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    #[test]
    fn fixture_yields_known_metrics() {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/snippet.log");
        let text = fs::read_to_string(path).unwrap();
        let summary = parse_arglog(&text);

        let reap = summary.bots.iter().find(|b| b.name == "Reap").unwrap();
        assert_eq!(reap.stalls, 1);
        assert_eq!(reap.goals, 2);
        assert_eq!(reap.frags, Some(1));
        assert_eq!(reap.deaths, 1);
        assert_eq!(reap.cover, 2);
        assert!((reap.avg - 64.0).abs() < 1e-6, "avg={}", reap.avg);

        let omi = summary.bots.iter().find(|b| b.name == "Omi").unwrap();
        assert_eq!(omi.stalls, 3);
        assert_eq!(omi.goals, 4);
        assert_eq!(omi.frags, Some(2));
        assert_eq!(omi.deaths, 0);
        assert_eq!(omi.cover, 2);

        assert_eq!(summary.events.get("spawned"), Some(&2));
        assert_eq!(summary.events.get("death"), Some(&1));
        assert_eq!(summary.events.get("hazard"), Some(&1));
        assert_eq!(summary.events.get("engage"), Some(&1));
        assert_eq!(summary.events.get("weapon"), Some(&1));
    }

    #[test]
    fn tape_reads_map_and_world_death_z() {
        let text = "\
ARGUS init on dm4
ARGLOG Reap t 1.0 pos '0.0 0.0 24.0' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGEVT Reap death world pos '10.5 260.2 -360.0'
";
        let tape = parse_tape(text);
        assert_eq!(tape.map.as_deref(), Some("dm4"));
        assert_eq!(tape.deaths.len(), 1);
        assert_eq!(tape.deaths[0].killer, "world");
        assert!((tape.deaths[0].pos.z + 360.0).abs() < 0.01);
    }

    #[test]
    fn spaced_netnames_parse_whole() {
        let text = "\
ARGLOG Joe Rogan t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 3 hp 100 frg 2
ARGLOG Joe Rogan t 2.0 pos '64 0 24' spd 128 yaw 0 mode 2 st 1 gl 4 hp 100 frg 2
ARGEVT Joe Rogan engage Trent Reznor
ARGEVT Joe Rogan death Trent Reznor pos '64 0 24'
";
        let tape = parse_tape(text);
        let summary = tape.summary();
        let jr = summary.bots.iter().find(|b| b.name == "Joe Rogan");
        assert!(jr.is_some(), "spaced netname must not be dropped");
        let jr = jr.unwrap();
        assert_eq!(jr.goals, 4);
        assert_eq!(jr.deaths, 1);
        assert_eq!(tape.deaths[0].victim, "Joe Rogan");
        assert_eq!(tape.deaths[0].killer, "Trent Reznor");
        assert_eq!(tape.event_counts.get("engage"), Some(&1));
        let e = tape.events.iter().find(|e| e.verb == "engage").unwrap();
        assert_eq!(e.bot, "Joe Rogan");
        assert_eq!(e.rest, "Trent Reznor");
    }

    #[test]
    fn bare_death_event_is_not_double_counted() {
        let text = "\
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 10 frg 0
ARGEVT Reap death
ARGEVT Reap death world pos '10 20 -360'
";
        let tape = parse_tape(text);
        assert_eq!(tape.deaths.len(), 1);
        assert_eq!(tape.event_counts.get("death"), Some(&1));
        assert_eq!(tape.events.iter().filter(|e| e.verb == "death").count(), 1);
    }
}
