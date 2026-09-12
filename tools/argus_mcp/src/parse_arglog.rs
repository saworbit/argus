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
pub struct Confinement {
    pub bot: String,
    pub t_start: f64,
    pub dur: f64,
    pub x: f64,
    pub y: f64,
    pub avg_spd: f64,
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
    /// Maps the engine REFUSED to spawn ("Couldn't spawn server").
    /// Non-empty means the tape's match ran somewhere other than what
    /// was asked for and every metric describes the wrong map.
    pub failed_spawns: Vec<String>,
    /// How many levels this file spans (#266). More than one and only
    /// the busiest segment was parsed: `time` and every counter field
    /// restart at a level change, so nothing may be aggregated across
    /// them.
    pub segments: u32,
    pub segment_note: Option<String>,
}

/// A statue: 6 s or longer at under 20 u/s inside a 32u circle,
/// aligned with tools/argus_review.py's freeze detector. `hp_drop`
/// above zero means the bot took damage while frozen - the class
/// Shane farmed at the west train pad (v363 tape) while the ship
/// gates stayed green because nothing measured it.
#[derive(Debug, Clone, Serialize)]
pub struct Freeze {
    pub bot: String,
    pub t_start: f64,
    pub dur: f64,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub hp_drop: f64,
}

impl MatchTape {
    /// Tracks that are real clients, not bots: every bot emits ARGEVT
    /// spawned at creation and respawn after each death; a human track
    /// (ARGLOG rows since v3.66, death lines since v3.72) emits
    /// neither. Quality bands and gates are statements about the BOT
    /// build - a human's lava swims and idle spells are review data,
    /// not defects (the 2026-08-26 v372 tape fired the dm4 lava band
    /// flag on Shane's own four swims, and its only "statue" was
    /// Shane standing still for 12.7 s).
    pub fn human_names(&self) -> HashSet<String> {
        let bots: HashSet<&str> = self
            .events
            .iter()
            .filter(|e| e.verb == "spawned" || e.verb == "respawn")
            .map(|e| e.bot.as_str())
            .collect();
        // A tape with no spawned/respawn at all (legacy vintage, a
        // tail slice, a synthetic fixture) cannot support the
        // discrimination - treat every track as a bot rather than
        // demote the whole roster to review data.
        if bots.is_empty() {
            return HashSet::new();
        }
        self.samples
            .keys()
            .filter(|n| !bots.contains(n.as_str()))
            .cloned()
            .collect()
    }

    /// Statue scan over the ARGLOG samples, longest first. A death
    /// respawns the bot elsewhere, which breaks the position run, so
    /// a freeze never spans a respawn.
    pub fn freezes(&self) -> Vec<Freeze> {
        let mut out = Vec::new();
        for (name, rec) in &self.samples {
            let mut i = 0;
            while i < rec.len() {
                if rec[i].spd >= 20.0 {
                    i += 1;
                    continue;
                }
                let (x0, y0) = (rec[i].pos.x, rec[i].pos.y);
                let hp_first = rec[i].hp.unwrap_or(0.0);
                let mut hp_min = hp_first;
                let mut j = i;
                while j + 1 < rec.len() {
                    let s = &rec[j + 1];
                    let dx = s.pos.x - x0;
                    let dy = s.pos.y - y0;
                    if s.spd < 20.0 && (dx * dx + dy * dy).sqrt() < 32.0 {
                        if let Some(h) = s.hp {
                            if h < hp_min {
                                hp_min = h;
                            }
                        }
                        j += 1;
                    } else {
                        break;
                    }
                }
                let dur = rec[j].t - rec[i].t;
                if dur >= 6.0 {
                    out.push(Freeze {
                        bot: name.clone(),
                        t_start: rec[i].t,
                        dur,
                        x: x0,
                        y: y0,
                        z: rec[i].pos.z,
                        hp_drop: (hp_first - hp_min).max(0.0),
                    });
                }
                i = j + 1;
            }
        }
        out.sort_by(|a, b| b.dur.partial_cmp(&a.dur).unwrap());
        out
    }

    /// Confinement scan (#272). The freeze detector needs low speed
    /// and the stall detector needs low speed, so a bot can oscillate
    /// inside a small box at full run speed and leave no trace in any
    /// gate. One dm2 tape has a bot spending 13 seconds of 185 inside
    /// a 220 unit box averaging 355 u/s, in mode 2, not fighting: the
    /// route succeeded and the walking failed, and the only residue
    /// was nine hazard deflections, which the lab deliberately reads
    /// as the guard WORKING. Seven per cent of that bot's match
    /// disappeared with every gate green.
    ///
    /// So this one ignores speed entirely and asks the honest
    /// question instead: how long did the bot fail to get anywhere.
    /// A freeze at 0 u/s and an oscillation at 355 u/s are the same
    /// family and this reports both. Legitimate fights and item
    /// orbits also sit still in a box, so it is informational and not
    /// a gate.
    pub fn confinements(&self, box_u: f64, min_sec: f64) -> Vec<Confinement> {
        let mut out = Vec::new();
        for (name, rec) in &self.samples {
            let mut i = 0;
            while i < rec.len() {
                // grow the longest run whose whole span fits the box
                let (mut lo_x, mut hi_x) = (rec[i].pos.x, rec[i].pos.x);
                let (mut lo_y, mut hi_y) = (rec[i].pos.y, rec[i].pos.y);
                let mut j = i;
                let mut spd_sum = rec[i].spd;
                while j + 1 < rec.len() {
                    let s = &rec[j + 1];
                    let nlo_x = lo_x.min(s.pos.x);
                    let nhi_x = hi_x.max(s.pos.x);
                    let nlo_y = lo_y.min(s.pos.y);
                    let nhi_y = hi_y.max(s.pos.y);
                    if nhi_x - nlo_x > box_u || nhi_y - nlo_y > box_u {
                        break;
                    }
                    lo_x = nlo_x;
                    hi_x = nhi_x;
                    lo_y = nlo_y;
                    hi_y = nhi_y;
                    spd_sum += s.spd;
                    j += 1;
                }
                let dur = rec[j].t - rec[i].t;
                if dur >= min_sec && j > i {
                    out.push(Confinement {
                        bot: name.clone(),
                        t_start: rec[i].t,
                        dur,
                        x: (lo_x + hi_x) * 0.5,
                        y: (lo_y + hi_y) * 0.5,
                        avg_spd: spd_sum / ((j - i + 1) as f64),
                    });
                }
                i = j + 1;
            }
        }
        out.sort_by(|a, b| b.dur.partial_cmp(&a.dur).unwrap());
        out
    }

    /// Closest that any two bots ever came to each other (#279). Zero
    /// engagements gets diagnosed as a dead fire path, and on one
    /// e1m1 tape the bots never came within 939 units of each other
    /// all match: perception range and the fire button were
    /// irrelevant, because there was nothing to perceive. The brief
    /// already holds every track, so this is a few lines over data in
    /// hand, and it is worth reporting unconditionally - "closest
    /// approach 939 u" on a map where bots are meant to fight is a
    /// finding on its own.
    ///
    /// Samples are compared at matching timestamps, rounded to the
    /// tape's 1 Hz grid, so two bots that pass the same spot a minute
    /// apart are not counted as having met.
    pub fn closest_approach(&self) -> Option<f64> {
        let humans = self.human_names();
        let tracks: Vec<&Vec<Sample>> = self
            .samples
            .iter()
            .filter(|(n, _)| !humans.contains(n.as_str()))
            .map(|(_, r)| r)
            .collect();
        if tracks.len() < 2 {
            return None;
        }
        let mut best: Option<f64> = None;
        for a in 0..tracks.len() {
            for b in (a + 1)..tracks.len() {
                let mut i = 0;
                let mut j = 0;
                while i < tracks[a].len() && j < tracks[b].len() {
                    let sa = &tracks[a][i];
                    let sb = &tracks[b][j];
                    let dt = sa.t - sb.t;
                    if dt.abs() <= 0.6 {
                        let dx = sa.pos.x - sb.pos.x;
                        let dy = sa.pos.y - sb.pos.y;
                        let dz = sa.pos.z - sb.pos.z;
                        let d = (dx * dx + dy * dy + dz * dz).sqrt();
                        if best.map(|v| d < v).unwrap_or(true) {
                            best = Some(d);
                        }
                    }
                    if dt < 0.0 {
                        i += 1;
                    } else {
                        j += 1;
                    }
                }
            }
        }
        best
    }

    pub fn summary(&self) -> MatchSummary {
        let mut bots: Vec<BotStats> = self
            .samples
            .iter()
            .map(|(name, rec)| {
                let first = rec.first().unwrap();
                let last = rec.last().unwrap();
                let dur = last.t - first.t;
                // A death and respawn puts two consecutive 1 Hz samples
                // at opposite ends of the map, and summing that step
                // credited the bot with thousands of units it never
                // walked - inflating both distance and avg speed by
                // roughly one map width per death. Nothing in Quake
                // moves a player 700 u/s under its own power (run 320,
                // a rocket-jump launch well under 700), so a segment
                // implying more than that is a teleport, not travel.
                let dist = rec
                    .windows(2)
                    .map(|w| {
                        let dx = w[1].pos.x - w[0].pos.x;
                        let dy = w[1].pos.y - w[0].pos.y;
                        let dz = w[1].pos.z - w[0].pos.z;
                        let d = (dx * dx + dy * dy).sqrt();
                        let dt = (w[1].t - w[0].t).abs();
                        if dt > 0.0 && (d.max(dz.abs()) / dt) > 700.0 {
                            0.0
                        } else {
                            d
                        }
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

/// Split a log on level changes and return the busiest segment.
///
/// The engine restarts `time` at a level change, and a tape that spans
/// one is not one match (#266). A co-op session on e1m2 that exits to
/// e1m3 briefed as a 1.5 second match at 12,326 u/s: duration came
/// from the short trailing segment while distance was summed over the
/// whole file, counter fields like `st` and `gl` reset and the brief
/// read the last value, so totals.stalls said 0 while events.stall
/// counted 40 and a hotspot showed 37 hits at one cell. The tape
/// contradicted itself inside one JSON object, and every
/// geometry-joined field was computed against the wrong level's graph.
///
/// The existing wrong-map guard could not catch it, because that one
/// only fires on "Couldn't spawn server" and both spawns here
/// succeeded. It was a deathmatch-only assumption, and reaching an
/// exit is the normal end of a co-op session.
///
/// Briefing the busiest segment and saying so is the honest reading:
/// on that tape it is 133 seconds of e1m2 against 3 seconds of e1m3.
fn split_segments(text: &str) -> Vec<&str> {
    let map_re = map_re();
    let mut cuts: Vec<usize> = Vec::new();
    let mut seen_samples = false;
    let mut pos = 0usize;
    for line in text.lines() {
        let start = pos;
        pos += line.len() + 1;
        if line.starts_with("ARGLOG ") {
            seen_samples = true;
            continue;
        }
        // Only a SpawnServer that follows actual play is a level
        // change. The first one is just the match starting, and a
        // refused spawn is handled by the failed_spawns guard.
        if seen_samples && map_re.is_match(line) && line.contains("SpawnServer") {
            cuts.push(start);
            seen_samples = false;
        }
    }
    if cuts.is_empty() {
        return vec![text];
    }
    let mut out = Vec::new();
    let mut prev = 0usize;
    for c in cuts {
        out.push(&text[prev..c]);
        prev = c;
    }
    out.push(&text[prev..]);
    out
}

fn arglog_lines(seg: &str) -> usize {
    seg.lines().filter(|l| l.starts_with("ARGLOG ")).count()
}

pub fn parse_tape(text: &str) -> MatchTape {
    let segs = split_segments(text);
    if segs.len() > 1 {
        let total = segs.len();
        let (idx, best) = segs
            .iter()
            .enumerate()
            .max_by_key(|(_, s)| arglog_lines(s))
            .map(|(i, s)| (i, *s))
            .unwrap();
        let mut tape = parse_one(best);
        tape.segments = total as u32;
        tape.segment_note = Some(format!(
            "tape spans {total} levels; briefed segment {} of {total} ({} sample rows, map {}). Counters and time restart at a level change, so figures are NOT aggregated across them",
            idx + 1,
            arglog_lines(best),
            tape.map.as_deref().unwrap_or("?")
        ));
        return tape;
    }
    parse_one(text)
}

fn parse_one(text: &str) -> MatchTape {
    let v1 = v1_re();
    let death = death_re();
    let evt = evt_re();
    let map_re = map_re();

    let mut samples: BTreeMap<String, Vec<Sample>> = BTreeMap::new();
    let mut deaths = Vec::new();
    let mut events = Vec::new();
    let mut event_counts: BTreeMap<String, u32> = BTreeMap::new();
    let mut map = None;
    let mut pending_map: Option<String> = None;
    let mut failed_spawns: Vec<String> = Vec::new();
    let mut last_t: BTreeMap<String, f64> = BTreeMap::new();

    for line in text.lines() {
        // A SpawnServer line is a REQUEST, not a fact: when the BSP is
        // missing the engine prints "Couldn't spawn server maps/x.bsp"
        // and falls back to the start map, and taking the first
        // SpawnServer as the tape's map briefed every historical
        // mx_lqdm2 probe as lqdm2 while the bots actually fought on
        // start with no nav (found 2026-08-26). A spawn is confirmed
        // by not being refused before the next request.
        if let Some(caps) = map_re.captures(line) {
            if map.is_none() {
                if let Some(prev) = pending_map.take() {
                    map = Some(prev);
                }
                if map.is_none() {
                    pending_map = Some(caps[1].to_ascii_lowercase());
                }
            }
        } else if let Some(rest) = line.strip_prefix("Couldn't spawn server maps/") {
            let name = rest.trim_end_matches(".bsp").to_ascii_lowercase();
            if pending_map.as_deref() == Some(name.as_str()) {
                pending_map = None;
            }
            failed_spawns.push(name);
        } else if line.starts_with("ARGUS ") {
            // plain ARGUS console lines sit OUTSIDE the closed ARGEVT
            // vocabulary by design (shove since v3.73, routecache
            // adopt since v3.63) - count them as pseudo-events so the
            // behaviour is visible in briefs without a grammar change
            if line.ends_with(" shove") {
                *event_counts.entry("shove".to_string()).or_insert(0) += 1;
            } else if line.ends_with("routecache adopt") {
                *event_counts.entry("routecache_adopt".to_string()).or_insert(0) += 1;
            } else if line.contains(" hunch ") {
                *event_counts.entry("hunch".to_string()).or_insert(0) += 1;
            } else if line.contains(" watch ") {
                *event_counts.entry("watch".to_string()).or_insert(0) += 1;
            } else if line.ends_with(" sprintjump") {
                *event_counts.entry("sprintjump".to_string()).or_insert(0) += 1;
            } else if line.ends_with(" prefire") {
                *event_counts.entry("prefire".to_string()).or_insert(0) += 1;
            } else if line.ends_with(" coop catchup warp") {
                // a rescue teleport across the level to the team mate,
                // and the single most consequential thing a co-op bot
                // does to itself. It used to be emitted with an ARGEVT
                // prefix and a verb the vocabulary never had, so it
                // matched nothing and was dropped (#278)
                *event_counts.entry("coop_warp".to_string()).or_insert(0) += 1;
            } else if line.contains(" unstick ") {
                // the other rescue teleport, plain since #262
                *event_counts.entry("unstick".to_string()).or_insert(0) += 1;
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

    if map.is_none() {
        map = pending_map; // last request stood unrefused
    }
    MatchTape {
        map,
        samples,
        deaths,
        events,
        event_counts,
        failed_spawns,
        segments: 1,
        segment_note: None,
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
            r"ARGEVT (.+?) (spawned|respawn|goal_push|goal_pop|goal|route|routefail|trapped|abandon|stall|stallnode|jump|rjump|lift|swim|door|train|board|hazard|engage|pursue|retreat|grab|weapon|plan|death|checkpoint|win|coop_stats)(?:\s+(.*))?$",
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

    // #229: goal_push and goal_pop must not be eaten by the goal arm.
    #[test]
    fn goal_stack_verbs_parse() {
        let tape = parse_tape(
            "ARGEVT Carmack goal_push 1
ARGEVT Carmack goal_pop 1
ARGEVT Carmack goal item_shells
",
        );
        let verbs: Vec<&str> = tape.events.iter().map(|e| e.verb.as_str()).collect();
        assert_eq!(verbs, vec!["goal_push", "goal_pop", "goal"]);
    }
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
    fn refused_spawn_reports_the_fallback_map() {
        // the engine, missing lqdm2.bsp, falls back to start - the
        // tape's map is where the match RAN, and the refusal is kept
        let text = "\
SpawnServer: lqdm2
FindFile: can't find maps/lqdm2.bsp
Couldn't spawn server maps/lqdm2.bsp
SpawnServer: start
ARGLOG Reap t 1.0 pos '0.0 0.0 24.0' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
";
        let tape = parse_tape(text);
        assert_eq!(tape.map.as_deref(), Some("start"));
        assert_eq!(tape.failed_spawns, vec!["lqdm2".to_string()]);
        // a clean spawn keeps its map and reports no refusals
        let clean = parse_tape("SpawnServer: dm4\nARGUS init on dm4\n");
        assert_eq!(clean.map.as_deref(), Some("dm4"));
        assert!(clean.failed_spawns.is_empty());
    }

    #[test]
    fn plain_argus_lines_count_as_pseudo_events() {
        let text = "\
ARGUS Carmack shove\n\
ARGUS Joe Rogan shove\n\
ARGUS routecache adopt\n\
ARGUS Carmack watch spawn\n\
ARGUS Joe Rogan sprintjump\n\
ARGUS Carmack coop catchup warp\n\
ARGUS Joe Rogan unstick pinned '2526.7 -40.9 -66.0'\n\
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n";
        let tape = parse_tape(text);
        assert_eq!(tape.event_counts.get("shove"), Some(&2));
        assert_eq!(tape.event_counts.get("routecache_adopt"), Some(&1));
        assert_eq!(tape.event_counts.get("watch"), Some(&1));
        assert_eq!(tape.event_counts.get("sprintjump"), Some(&1));
        // both rescue teleports are countable (#278)
        assert_eq!(tape.event_counts.get("coop_warp"), Some(&1));
        assert_eq!(tape.event_counts.get("unstick"), Some(&1));
    }

    // Every ARGEVT verb the QC actually emits has to be in the
    // parser's closed alternation. #278 was a verb, "coop", that was
    // never registered: the regex found no match at any split point
    // and the line was dropped silently, so a rescue teleport across
    // the level appeared in no brief, no total and no gate. Nothing
    // checked the two lists against each other. This does.
    //
    // Two emission forms exist. Argus_Event ("verb") takes the verb as
    // its argument, and the direct form prints "ARGEVT ", the netname,
    // then a literal that starts with a space and carries the verb.

    // #272: a bot oscillating at speed leaves no trace in the stall
    // or freeze detectors, because both need low speed. Confinement
    // ignores speed and asks whether the bot got anywhere.
    #[test]
    fn confinement_sees_a_fast_bot_going_nowhere() {
        let mut text = String::new();
        // 12 seconds shuttling inside a ~200u box at ~350 u/s
        let mut t = 1.0;
        while t < 13.0 {
            let x = if (t * 2.0) as i32 % 2 == 0 { 1500.0 } else { 1680.0 };
            text.push_str(&format!(
                "ARGLOG Carmack t {t:.1} pos '{x:.1} -1300.0 32.0' spd 355 yaw 0 mode 2 st 4 gl 0 hp 100 frg 0\n"
            ));
            t += 0.5;
        }
        let tape = parse_tape(&text);
        // the stall and freeze detectors see nothing here
        assert!(tape.freezes().is_empty(), "freeze detector should not fire at 355 u/s");
        let cf = tape.confinements(220.0, 5.0);
        assert!(!cf.is_empty(), "confinement should catch it");
        assert!(cf[0].dur >= 10.0, "expected a long window, got {}", cf[0].dur);
        assert!(cf[0].avg_spd > 300.0, "and it should report the real speed");

        // a bot actually crossing the map is not confined
        let mut t = 1.0;
        let mut moving = String::new();
        let mut x = 0.0;
        while t < 13.0 {
            moving.push_str(&format!(
                "ARGLOG Romero t {t:.1} pos '{x:.1} 0.0 24.0' spd 320 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            x += 160.0;
            t += 0.5;
        }
        let tape2 = parse_tape(&moving);
        assert!(
            tape2.confinements(220.0, 5.0).is_empty(),
            "a bot travelling should never read as confined"
        );
    }

    // #279: zero engagements was diagnosed as a dead fire path on a
    // tape where no two bots came within 939 units of each other.
    #[test]
    fn closest_approach_separates_no_targets_from_no_shooting() {
        // two bots in their own corners of the map
        let mut apart = String::new();
        let mut t = 1.0;
        while t < 8.0 {
            apart.push_str(&format!(
                "ARGEVT Carmack spawned\nARGLOG Carmack t {t:.1} pos '0.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            apart.push_str(&format!(
                "ARGEVT Romero spawned\nARGLOG Romero t {t:.1} pos '2000.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            t += 1.0;
        }
        let tape = parse_tape(&apart);
        let d = tape.closest_approach().expect("two tracks give an answer");
        assert!((d - 2000.0).abs() < 1.0, "expected 2000, got {d}");

        // and two that meet
        let mut near = String::new();
        let mut t = 1.0;
        let mut x = 2000.0;
        while t < 8.0 {
            near.push_str(&format!(
                "ARGEVT Carmack spawned\nARGLOG Carmack t {t:.1} pos '0.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            near.push_str(&format!(
                "ARGEVT Romero spawned\nARGLOG Romero t {t:.1} pos '{x:.1} 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n"
            ));
            x -= 300.0;
            t += 1.0;
        }
        let tape2 = parse_tape(&near);
        let d2 = tape2.closest_approach().expect("two tracks give an answer");
        assert!(d2 < 400.0, "bots that converge should read close, got {d2}");

        // passing the same spot a minute apart is not a meeting
        let ships = "ARGEVT Carmack spawned\nARGLOG Carmack t 1.0 pos '0.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n\
ARGEVT Romero spawned\nARGLOG Romero t 60.0 pos '0.0 0.0 24.0' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n";
        assert_eq!(
            parse_tape(ships).closest_approach(),
            None,
            "tracks that never share a timestamp have no approach"
        );
    }

    #[test]
    fn every_argevt_verb_the_qc_emits_is_known_to_the_parser() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("src");
        let dir = match std::fs::read_dir(&root) {
            Ok(d) => d,
            // the QC tree is not beside the crate in every checkout
            Err(_) => return,
        };

        let ev_open = "Argus_Event (\"";
        let ev_direct = "dprint (\"ARGEVT \");";
        let lit_open = "dprint (\" ";

        let mut verbs: Vec<(String, String)> = Vec::new();
        for entry in dir.flatten() {
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("qc") {
                continue;
            }
            let src = match std::fs::read_to_string(&path) {
                Ok(s) => s,
                Err(_) => continue,
            };
            let file = path
                .file_name()
                .and_then(|f| f.to_str())
                .unwrap_or("?")
                .to_string();

            // form 1: Argus_Event ("verb")
            for (i, _) in src.match_indices(ev_open) {
                let rest = &src[i + ev_open.len()..];
                if let Some(end) = rest.find('"') {
                    if let Some(v) = rest[..end].split_whitespace().next() {
                        verbs.push((v.to_string(), file.clone()));
                    }
                }
            }

            // form 2: dprint ("ARGEVT "); then the first literal that
            // begins with a space. Argus_Event's own " " separator is
            // skipped, because its verb arrives via form 1.
            for (i, _) in src.match_indices(ev_direct) {
                let stop = std::cmp::min(i + 400, src.len());
                let window = &src[i..stop];
                for (j, _) in window.match_indices(lit_open) {
                    let rest = &window[j + lit_open.len()..];
                    if let Some(end) = rest.find('"') {
                        // the verb literal may carry the line
                        // ending with it, as in " goal_pop\\n"
                        let lit = &rest[..end];
                        if let Some(v) = lit
                            .split(|c: char| c.is_whitespace() || c == '\\')
                            .find(|t| !t.is_empty())
                        {
                            verbs.push((v.to_string(), file.clone()));
                            break;
                        }
                    }
                }
            }
        }

        assert!(
            !verbs.is_empty(),
            "found no ARGEVT emissions at all - the scan is broken, not the QC"
        );

        let re = evt_re();
        let unknown: Vec<String> = verbs
            .iter()
            .filter(|(v, _)| {
                let line = format!("ARGEVT Joe Rogan {} rest", v);
                match re.captures(&line) {
                    Some(c) => &c[2] != v.as_str(),
                    None => true,
                }
            })
            .map(|(v, f)| format!("{} (in {})", v, f))
            .collect();

        assert!(
            unknown.is_empty(),
            "QC emits ARGEVT verbs the parser cannot read: {:?}. Either add the verb to evt_re's alternation, minding the goal_push|goal_pop|goal ordering so a longer verb is not shadowed, or emit a plain ARGUS line and count it as a pseudo-event.",
            unknown
        );
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
    fn freeze_detector_finds_statues_and_under_fire() {
        // Carmack stands at one spot for 8 s losing 48 hp (the
        // west-pad class Shane farmed); Romero pauses only 4 s and
        // must NOT count; a board event parses as its own verb.
        let mut text = String::new();
        let mut t = 0.0;
        while t <= 8.0 {
            text.push_str(&format!(
                "ARGLOG Carmack t {:.1} pos '1363 -1038 344' spd 3 yaw 0 mode 2 st 0 gl 0 hp {} frg 0\n",
                t,
                (81.0 - t * 6.0) as i32
            ));
            t += 0.5;
        }
        let mut t = 0.0;
        while t <= 4.0 {
            text.push_str(&format!(
                "ARGLOG Romero t {:.1} pos '2016 -980 344' spd 5 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n",
                t
            ));
            t += 0.5;
        }
        text.push_str("ARGLOG Romero t 4.5 pos '2100 -980 344' spd 300 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n");
        text.push_str("ARGEVT Romero board\n");
        let tape = parse_tape(&text);
        let fz = tape.freezes();
        assert_eq!(fz.len(), 1, "only the 8 s statue counts");
        assert_eq!(fz[0].bot, "Carmack");
        assert!(fz[0].dur >= 7.9);
        assert!(fz[0].hp_drop >= 40.0, "under-fire drop must register");
        assert_eq!(tape.event_counts.get("board"), Some(&1));
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

    #[test]
    fn a_respawn_does_not_count_as_travel() {
        // #101: consecutive 1 Hz samples either side of a death sit at
        // opposite ends of the map; summing that step credited the bot
        // with a map width of phantom distance per death.
        let tape = "ARGLOG Reap t   1.0 pos '0 0 0' spd 320 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t   2.0 pos '100 0 0' spd 320 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
ARGEVT Reap death world pos '100 0 0'
ARGLOG Reap t   3.0 pos '2100 0 0' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t   4.0 pos '2200 0 0' spd 320 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0
";
        let s = parse_arglog(tape);
        let bot = s.bots.iter().find(|b| b.name == "Reap").expect("Reap");
        // 100 + (skipped 2000) + 100
        assert!(
            bot.dist < 400.0,
            "respawn jump leaked into travel distance: {}",
            bot.dist
        );
        assert!(bot.dist >= 200.0, "real travel was dropped: {}", bot.dist);
    }
}
