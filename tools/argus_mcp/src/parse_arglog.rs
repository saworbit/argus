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
    /// Maps the engine REFUSED to spawn ("Couldn't spawn server").
    /// Non-empty means the tape's match ran somewhere other than what
    /// was asked for and every metric describes the wrong map.
    pub failed_spawns: Vec<String>,
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
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n";
        let tape = parse_tape(text);
        assert_eq!(tape.event_counts.get("shove"), Some(&2));
        assert_eq!(tape.event_counts.get("routecache_adopt"), Some(&1));
        assert_eq!(tape.event_counts.get("watch"), Some(&1));
        assert_eq!(tape.event_counts.get("sprintjump"), Some(&1));
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
