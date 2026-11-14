//! Live triggers for bot-eye capture.
//!
//! A recorded POV is only useful if it holds the moment worth looking at,
//! and a fixed window rarely does: a stall, a pin or a reversal storm
//! happens when it happens. This module tails the live match console and
//! names the first bot to do the thing asked for, so the camera can cut to
//! it while the moment is still going on.
//!
//! The console is the only place these events exist. ARGEVT and ARGUS
//! lines are developer dprints, which reach the server log and never a
//! client, so the camera's own connection cannot see them.
use regex::Regex;
use std::collections::{HashMap, HashSet, VecDeque};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

/// Default trigger set: a stall event, or a bot that has not left a 32u
/// circle for 2.5 s. Together they cover the pins the freeze gate counts,
/// but early enough that the camera arrives while the bot is still stuck.
pub const DEFAULT_SPEC: &str = "stall,still";

/// A bot inside this radius for the whole window has not gone anywhere.
/// The same circle the freeze detector uses.
const STILL_RADIUS: f32 = 32.0;
/// Default stationary window. The freeze gate waits 6 s; arriving at 2.5 s
/// leaves most of a real freeze still to film.
const STILL_DEFAULT_SECS: f64 = 2.5;
/// How far apart repeated markers may be and still count as one burst.
pub const WORD_WINDOW_SECS: f64 = 2.0;

/// One condition that fires a capture.
#[derive(Debug, Clone, PartialEq)]
pub enum Trigger {
    /// Every ARGLOG sample across `secs` sits inside STILL_RADIUS of the
    /// newest one, with the bot alive throughout.
    Still { secs: f64 },
    /// `count` ARGEVT verbs or ARGUS markers whose first word after the bot
    /// name is `word`, within WORD_WINDOW_SECS of game time.
    Word { word: String, count: u32 },
}

impl Trigger {
    fn label(&self) -> String {
        match self {
            Trigger::Still { secs } => format!("still {secs}s"),
            Trigger::Word { word, count: 1 } => word.clone(),
            Trigger::Word { word, count } => format!("{word} x{count}"),
        }
    }
}

/// Parse `stall,still:3,flip:3`. A bare word fires on its first
/// occurrence; `word:N` needs N inside the burst window; `still:S` sets the
/// stationary window in seconds.
pub fn parse_spec(spec: &str) -> Result<Vec<Trigger>, String> {
    let mut out = Vec::new();
    for raw in spec.split(',') {
        let item = raw.trim();
        if item.is_empty() {
            continue;
        }
        let (word, arg) = match item.split_once(':') {
            Some((w, a)) => (w.trim(), Some(a.trim())),
            None => (item, None),
        };
        if word.is_empty() || !word.chars().all(|c| c.is_ascii_lowercase() || c == '_') {
            return Err(format!(
                "trigger {item:?}: use a lowercase event or marker word, e.g. stall, still:3, flip:3"
            ));
        }
        if word == "still" {
            let secs = match arg {
                None => STILL_DEFAULT_SECS,
                Some(a) => a
                    .parse::<f64>()
                    .ok()
                    .filter(|s| s.is_finite() && (1.0..=30.0).contains(s))
                    .ok_or_else(|| format!("trigger {item:?}: still needs 1..30 seconds"))?,
            };
            out.push(Trigger::Still { secs });
        } else {
            let count = match arg {
                None => 1,
                Some(a) => a
                    .parse::<u32>()
                    .ok()
                    .filter(|n| (1..=20).contains(n))
                    .ok_or_else(|| format!("trigger {item:?}: a burst count is 1..20"))?,
            };
            out.push(Trigger::Word {
                word: word.to_string(),
                count,
            });
        }
    }
    if out.is_empty() {
        return Err("no trigger given; try stall,still".into());
    }
    if out.len() > 8 {
        return Err("at most 8 triggers".into());
    }
    Ok(out)
}

/// What fired, for whom, and the console line that did it.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct Fired {
    /// Bot name as its ARGLOG lines spell it; spaces allowed.
    pub bot: String,
    /// The trigger's label: `stall`, `flip x3` or `still 2.5s`.
    pub trigger: String,
    /// The tape's game clock: the newest ARGLOG time read so far. ARGEVT
    /// and ARGUS lines carry no time of their own, so this is accurate to
    /// the 0.5 s ARGLOG cadence.
    pub game_time: f64,
    /// The console line that fired, trimmed to 200 characters.
    pub line: String,
}

struct Sample {
    t: f64,
    pos: [f32; 3],
    hp: f32,
}

/// Feed it console lines in order; it returns the first trigger to fire.
pub struct Detector {
    triggers: Vec<Trigger>,
    focus: Option<String>,
    ignored: HashSet<String>,
    names: Vec<String>,
    clock: f64,
    samples: HashMap<String, VecDeque<Sample>>,
    hits: HashMap<(String, String), VecDeque<f64>>,
    keep_secs: f64,
    pub lines_read: u64,
}

fn arglog_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    // ftos pads, so a sample can read "t  21.1" with two spaces: a single
    // space here silently dropped every sample under 100 s once before.
    RE.get_or_init(|| {
        Regex::new(
            r"^ARGLOG (.+?) t +(-?[0-9.]+) pos '\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s*'.* hp +(-?[0-9.]+)",
        )
        .unwrap()
    })
}

impl Detector {
    /// `focus` limits firing to one bot; lab instruments never fire.
    pub fn new(triggers: Vec<Trigger>, focus: Option<String>) -> Self {
        let keep_secs = triggers
            .iter()
            .map(|t| match t {
                Trigger::Still { secs } => *secs,
                Trigger::Word { .. } => 0.0,
            })
            .fold(0.0, f64::max)
            + 1.0;
        Detector {
            triggers,
            focus,
            ignored: HashSet::new(),
            names: Vec::new(),
            clock: 0.0,
            samples: HashMap::new(),
            hits: HashMap::new(),
            keep_secs,
            lines_read: 0,
        }
    }

    /// Never fire for this name again (the camera cannot target it).
    pub fn ignore(&mut self, name: &str) {
        self.ignored.insert(name.to_string());
    }

    /// Bot names learnt from ARGLOG so far, in first-seen order.
    pub fn names(&self) -> &[String] {
        &self.names
    }

    fn eligible(&self, name: &str) -> bool {
        !name.starts_with("lab")
            && !self.ignored.contains(name)
            && self.focus.as_deref().is_none_or(|f| f == name)
    }

    /// Process one console line; Some when a trigger fires on it.
    pub fn feed(&mut self, line: &str) -> Option<Fired> {
        self.lines_read += 1;
        let line = line.trim_end();
        if let Some(c) = arglog_re().captures(line) {
            let name = c[1].to_string();
            let t: f64 = c[2].parse().ok()?;
            let pos = [c[3].parse().ok()?, c[4].parse().ok()?, c[5].parse().ok()?];
            let hp: f32 = c[6].parse().ok()?;
            if !self.names.contains(&name) {
                self.names.push(name.clone());
            }
            self.clock = self.clock.max(t);
            return self.sample(name, Sample { t, pos, hp }, line);
        }
        let rest = line
            .strip_prefix("ARGEVT ")
            .or_else(|| line.strip_prefix("ARGUS "))?;
        // Names may hold spaces ("Joe Rogan"), so a first token is not a
        // name. Only names an ARGLOG line has already vouched for count,
        // longest first, which also keeps "ARGUS routecache adopt" and
        // "ARGUS difficulty <name> ..." from inventing bots.
        let (name, after) = self
            .names
            .iter()
            .filter_map(|n| {
                rest.strip_prefix(n.as_str())
                    .and_then(|a| a.strip_prefix(' '))
                    .map(|a| (n.clone(), a))
            })
            .max_by_key(|(n, _)| n.len())?;
        let word = after.split_whitespace().next()?.to_string();
        if !self.eligible(&name) {
            return None;
        }
        let clock = self.clock;
        let mut fired = None;
        for trig in &self.triggers {
            let Trigger::Word { word: w, count } = trig else {
                continue;
            };
            if *w != word {
                continue;
            }
            let q = self.hits.entry((name.clone(), word.clone())).or_default();
            q.push_back(clock);
            while q.front().is_some_and(|&t| t < clock - WORD_WINDOW_SECS) {
                q.pop_front();
            }
            if q.len() as u32 >= *count {
                fired = Some(Fired {
                    bot: name.clone(),
                    trigger: trig.label(),
                    game_time: clock,
                    line: line.chars().take(200).collect(),
                });
                break;
            }
        }
        fired
    }

    fn sample(&mut self, name: String, s: Sample, line: &str) -> Option<Fired> {
        let newest_t = s.t;
        let q = self.samples.entry(name.clone()).or_default();
        // a respawn or a map restart can step time backwards for one bot
        if q.back().is_some_and(|b| b.t > newest_t) {
            q.clear();
        }
        q.push_back(s);
        while q.front().is_some_and(|f| f.t < newest_t - self.keep_secs) {
            q.pop_front();
        }
        if !self.eligible(&name) {
            return None;
        }
        let q = &self.samples[&name];
        let newest = q.back()?;
        for trig in &self.triggers {
            let Trigger::Still { secs } = trig else {
                continue;
            };
            // the window must actually be covered, or a bot that has only
            // just appeared would read as having stood still forever
            let Some(start) = q.iter().rposition(|x| x.t <= newest.t - secs + 0.01) else {
                continue;
            };
            let window = q.iter().skip(start);
            let mut held = true;
            for x in window {
                let d = ((x.pos[0] - newest.pos[0]).powi(2)
                    + (x.pos[1] - newest.pos[1]).powi(2)
                    + (x.pos[2] - newest.pos[2]).powi(2))
                .sqrt();
                if x.hp <= 0.0 || d > STILL_RADIUS {
                    held = false;
                    break;
                }
            }
            if held {
                return Some(Fired {
                    bot: name,
                    trigger: trig.label(),
                    game_time: newest.t,
                    line: line.chars().take(200).collect(),
                });
            }
        }
        None
    }
}

/// Reads only what a live log gained since the last call, line by line.
pub struct LogTail {
    path: PathBuf,
    offset: u64,
    partial: Vec<u8>,
}

impl LogTail {
    /// Start at the log's current end: earlier lines belong to moments the
    /// camera can no longer film.
    pub fn at_end(path: &Path) -> Result<Self, String> {
        let len = std::fs::metadata(path)
            .map_err(|e| format!("match log {}: {e}", path.display()))?
            .len();
        Ok(LogTail {
            path: path.to_path_buf(),
            offset: len,
            partial: Vec::new(),
        })
    }

    /// Start at the beginning, for replaying a finished log.
    pub fn from_start(path: &Path) -> Self {
        LogTail {
            path: path.to_path_buf(),
            offset: 0,
            partial: Vec::new(),
        }
    }

    /// Complete lines appended since the previous call.
    pub fn read_lines(&mut self) -> Result<Vec<String>, String> {
        let mut f = std::fs::File::open(&self.path)
            .map_err(|e| format!("match log {}: {e}", self.path.display()))?;
        let len = f.metadata().map_err(|e| e.to_string())?.len();
        if len < self.offset {
            // a new launch truncates qconsole.log
            self.offset = 0;
            self.partial.clear();
        }
        if len == self.offset {
            return Ok(Vec::new());
        }
        f.seek(SeekFrom::Start(self.offset))
            .map_err(|e| e.to_string())?;
        let mut buf = Vec::new();
        f.take((len - self.offset).min(8 * 1024 * 1024))
            .read_to_end(&mut buf)
            .map_err(|e| e.to_string())?;
        self.offset += buf.len() as u64;
        self.partial.extend_from_slice(&buf);
        let mut lines = Vec::new();
        while let Some(nl) = self.partial.iter().position(|&b| b == b'\n') {
            let raw: Vec<u8> = self.partial.drain(..=nl).collect();
            let text = String::from_utf8_lossy(&raw);
            lines.push(text.trim_end_matches(['\r', '\n']).to_string());
        }
        Ok(lines)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn arglog(name: &str, t: f64, x: f32, y: f32, hp: i32) -> String {
        format!(
            "ARGLOG {name} t {t:6.1} pos '{x:6.1} {y:6.1} -104.0' spd 0 yaw 90 mode 2 st 0 gl 0 hp {hp} frg 0"
        )
    }

    fn run(spec: &str, focus: Option<&str>, lines: &[String]) -> Option<Fired> {
        let mut d = Detector::new(parse_spec(spec).unwrap(), focus.map(String::from));
        lines.iter().find_map(|l| d.feed(l))
    }

    #[test]
    fn spec_parses_words_bursts_and_still_windows() {
        assert_eq!(
            parse_spec(" stall , still:3 ,flip:4").unwrap(),
            vec![
                Trigger::Word {
                    word: "stall".into(),
                    count: 1
                },
                Trigger::Still { secs: 3.0 },
                Trigger::Word {
                    word: "flip".into(),
                    count: 4
                },
            ]
        );
        assert_eq!(
            parse_spec("still").unwrap(),
            vec![Trigger::Still { secs: 2.5 }]
        );
        for bad in [
            "",
            ",",
            "Stall",
            "still:0.5",
            "still:x",
            "flip:0",
            "flip:99",
            "a b",
        ] {
            assert!(parse_spec(bad).is_err(), "{bad:?} should be refused");
        }
    }

    #[test]
    fn a_stall_event_fires_for_a_spaced_name_learnt_from_arglog() {
        let lines = vec![
            arglog("Joe Rogan", 4.3, 0.0, 0.0, 100),
            "ARGEVT Joe Rogan hazard".to_string(),
            "ARGEVT Joe Rogan stall".to_string(),
        ];
        let f = run("stall", None, &lines).unwrap();
        assert_eq!(f.bot, "Joe Rogan");
        assert_eq!(f.trigger, "stall");
        assert_eq!(f.game_time, 4.3);
    }

    #[test]
    fn events_for_unvouched_names_and_lab_seats_never_fire() {
        // "ARGUS difficulty Romero ..." must not invent a bot "difficulty",
        // and an event before any ARGLOG has nobody to belong to.
        let lines = vec![
            "ARGEVT Romero stall".to_string(),
            "ARGUS difficulty Romero t 33.2 base 1".to_string(),
            arglog("labcamera", 5.0, 0.0, 0.0, 100),
            "ARGEVT labcamera stall".to_string(),
        ];
        assert_eq!(run("stall,difficulty", None, &lines), None);
    }

    #[test]
    fn a_burst_needs_its_count_inside_the_window() {
        let spread = vec![
            arglog("Romero", 1.0, 0.0, 0.0, 100),
            "ARGUS Romero flip strafe ms 1000 from 10 to 190".to_string(),
            arglog("Romero", 4.0, 0.0, 0.0, 100),
            "ARGUS Romero flip strafe ms 4000 from 190 to 10".to_string(),
            arglog("Romero", 7.0, 0.0, 0.0, 100),
            "ARGUS Romero flip strafe ms 7000 from 10 to 190".to_string(),
        ];
        assert_eq!(run("flip:3", None, &spread), None);
        let storm = vec![
            arglog("Romero", 1.0, 0.0, 0.0, 100),
            "ARGUS Romero flip strafe".to_string(),
            arglog("Romero", 1.5, 0.0, 0.0, 100),
            "ARGUS Romero flip combat_hazard".to_string(),
            "ARGUS Romero flip strafe".to_string(),
        ];
        let f = run("flip:3", None, &storm).unwrap();
        assert_eq!((f.bot.as_str(), f.trigger.as_str()), ("Romero", "flip x3"));
    }

    #[test]
    fn still_fires_only_once_the_whole_window_is_covered_and_alive() {
        let mut lines = Vec::new();
        for i in 0..5 {
            lines.push(arglog(
                "Carmack",
                1.0 + i as f64 * 0.5,
                100.0 + i as f32 * 3.0,
                0.0,
                100,
            ));
        }
        // 2.0 s covered, 12u of drift: not yet 2.5 s
        assert_eq!(run("still", None, &lines), None);
        lines.push(arglog("Carmack", 3.5, 115.0, 0.0, 100));
        let f = run("still", None, &lines).unwrap();
        assert_eq!((f.bot.as_str(), f.game_time), ("Carmack", 3.5));

        // a bot walking 20u every half second is moving, not stuck
        let walk: Vec<_> = (0..10)
            .map(|i| arglog("Carmack", 1.0 + i as f64 * 0.5, i as f32 * 20.0, 0.0, 100))
            .collect();
        assert_eq!(run("still", None, &walk), None);

        // a corpse lies still too, and is not a pin
        let dead: Vec<_> = (0..10)
            .map(|i| {
                arglog(
                    "Carmack",
                    1.0 + i as f64 * 0.5,
                    0.0,
                    0.0,
                    if i < 3 { 100 } else { -20 },
                )
            })
            .collect();
        assert_eq!(run("still", None, &dead), None);
    }

    #[test]
    fn focus_and_ignore_limit_who_can_fire() {
        let lines = vec![
            arglog("Romero", 2.0, 0.0, 0.0, 100),
            arglog("Carmack", 2.0, 0.0, 0.0, 100),
            "ARGEVT Romero stall".to_string(),
            "ARGEVT Carmack stall".to_string(),
        ];
        assert_eq!(
            run("stall", Some("Carmack"), &lines).unwrap().bot,
            "Carmack"
        );
        let mut d = Detector::new(parse_spec("stall").unwrap(), None);
        d.ignore("Romero");
        assert_eq!(lines.iter().find_map(|l| d.feed(l)).unwrap().bot, "Carmack");
    }

    #[test]
    fn the_tail_returns_only_complete_new_lines_and_survives_truncation() {
        let dir = std::env::temp_dir().join(format!("pov_tail_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("qconsole.log");
        std::fs::write(&path, "old line\n").unwrap();
        let mut tail = LogTail::at_end(&path).unwrap();
        assert!(tail.read_lines().unwrap().is_empty());
        use std::io::Write;
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap();
        f.write_all(b"ARGEVT Romero stall\r\nhalf a li").unwrap();
        drop(f);
        assert_eq!(tail.read_lines().unwrap(), vec!["ARGEVT Romero stall"]);
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .open(&path)
            .unwrap();
        f.write_all(b"ne\n").unwrap();
        drop(f);
        assert_eq!(tail.read_lines().unwrap(), vec!["half a line"]);
        std::fs::write(&path, "new\n").unwrap();
        assert_eq!(tail.read_lines().unwrap(), vec!["new"]);
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The detector against a real committed tape: dm4 fires early on a
    /// stall or a pin, every time, for a bot the tape knows.
    #[test]
    fn a_committed_dm4_tape_fires_for_a_real_bot() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../runs");
        let tape = root.join("smoke_deploy_ed8926c1_dm4.log");
        if !tape.is_file() {
            return;
        }
        let mut tail = LogTail::from_start(&tape);
        let mut d = Detector::new(parse_spec(DEFAULT_SPEC).unwrap(), None);
        let lines = tail.read_lines().unwrap();
        let fired = lines
            .iter()
            .find_map(|l| d.feed(l))
            .expect("a 75 s dm4 tape has a stall or a pin");
        assert!(d.names().contains(&fired.bot), "{fired:?}");
        assert!(fired.game_time > 0.0 && fired.game_time < 80.0, "{fired:?}");
    }
}
