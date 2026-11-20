//! What a tape says about itself: the build that recorded it, the engine
//! clock it ran on, and the bookmarks a human pressed while playing.
//!
//! - `ARGUS build <id>`: the QC source identity (#823, see build_stamp.rs).
//! - `ARGUS clock frame_us <n> tick_us <n> seed <n>`: frame_us 0 is an
//!   ordinary server whose frames last as long as the wall clock says. A
//!   positive frame_us is the lab's fixed-frame clock (host_framerate),
//!   which runs faster than real time and repeats exactly for a given seed.
//! - `ARGUS mark <n> t <t> pos '<x y z>' yaw <deg> [seen <0|1> dist <u>]
//!   near <name|none>`: the session bookmark (Argus_Mark, impulse 200).
//!
//! Tapes recorded before these lines existed simply carry none of them.

use regex::Regex;
use serde::Serialize;
use std::sync::OnceLock;

#[derive(Debug, Clone, Default, Serialize, PartialEq)]
pub struct TapeIdentity {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub build: Option<String>,
    /// More than one distinct build in one segment means the file was
    /// stitched together and no single build owns it.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub other_builds: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub clock: Option<TapeClock>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub marks: Vec<SessionMark>,
}

impl TapeIdentity {
    pub fn is_empty(&self) -> bool {
        self.build.is_none()
            && self.other_builds.is_empty()
            && self.clock.is_none()
            && self.marks.is_empty()
    }

    /// True when the tape ran on the lab's fixed-frame clock.
    pub fn fixed_frame(&self) -> bool {
        self.clock.as_ref().is_some_and(|c| c.frame_us > 0)
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TapeClock {
    pub frame_us: u64,
    pub tick_us: u64,
    pub seed: u64,
    /// "fixed" for the lab clock (a pinned frame, faster than real time),
    /// "realtime" for an ordinary server.
    pub kind: &'static str,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SessionMark {
    pub n: u32,
    pub t: f64,
    pub pos: [f64; 3],
    pub yaw: f64,
    /// The bot that most plausibly drew the eye: nearest in sight, else
    /// nearest at all. None when no bot was alive.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub near: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub seen: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dist: Option<f64>,
}

fn build_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^ARGUS build ([0-9a-f]{6,32})\s*$").expect("build regex"))
}

fn clock_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^ARGUS clock frame_us\s+(\d+) tick_us\s+(\d+) seed\s+(\d+)\s*$")
            .expect("clock regex")
    })
}

fn mark_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(concat!(
            r"^ARGUS mark (\d+) t\s+(-?[\d.]+) pos '\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)'",
            r" yaw\s+(-?[\d.]+)(?: near none| seen ([01]) dist\s+(-?[\d.]+) near (.+?))\s*$"
        ))
        .expect("mark regex")
    })
}

/// Read the identity lines out of one level segment of a tape.
pub fn inspect(text: &str) -> TapeIdentity {
    let mut id = TapeIdentity::default();
    for raw in text.lines() {
        let line = raw.trim_end_matches('\r');
        if !line.starts_with("ARGUS ") {
            continue;
        }
        if let Some(c) = build_re().captures(line) {
            let build = c[1].to_string();
            match &id.build {
                None => id.build = Some(build),
                Some(first) if *first != build && !id.other_builds.contains(&build) => {
                    id.other_builds.push(build)
                }
                _ => {}
            }
        } else if let Some(c) = clock_re().captures(line) {
            let frame_us: u64 = c[1].parse().unwrap_or(0);
            id.clock = Some(TapeClock {
                frame_us,
                tick_us: c[2].parse().unwrap_or(0),
                seed: c[3].parse().unwrap_or(0),
                kind: if frame_us > 0 { "fixed" } else { "realtime" },
            });
        } else if let Some(c) = mark_re().captures(line) {
            let num = |i: usize| c[i].parse::<f64>().ok().filter(|n| n.is_finite());
            let (Ok(n), Some(t), Some(x), Some(y), Some(z), Some(yaw)) =
                (c[1].parse(), num(2), num(3), num(4), num(5), num(6))
            else {
                continue;
            };
            let dist = if c.get(8).is_some() {
                let Some(value) = num(8) else { continue };
                Some(value)
            } else {
                None
            };
            id.marks.push(SessionMark {
                n,
                t,
                pos: [x, y, z],
                yaw,
                seen: c.get(7).map(|m| m.as_str() == "1"),
                dist,
                near: c.get(9).map(|m| m.as_str().to_string()),
            });
        }
    }
    id
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_matches_the_shared_cases() {
        #[derive(serde::Deserialize)]
        struct Case {
            name: String,
            lines: Vec<String>,
            expected: serde_json::Value,
        }
        let cases: Vec<Case> =
            serde_json::from_str(include_str!("../testdata/tape_identity_cases.json")).unwrap();
        for case in cases {
            let actual = inspect(&case.lines.join("\r\n"));
            assert_eq!(
                serde_json::to_value(actual).unwrap(),
                case.expected,
                "{}",
                case.name
            );
        }
    }

    #[test]
    fn reads_build_clock_and_marks() {
        let text = "ARGUS init on dm4\nARGUS build 4a6980c09cea\n\
            ARGUS clock frame_us 13900 tick_us 1000 seed 7\n\
            ARGLOG Carmack t   1.2 pos '1 2 3' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n\
            ARGUS mark 1 t  12.4 pos ' 12.0 -34.5  24.0' yaw -90 seen 1 dist 240 near Joe Rogan\n\
            ARGUS mark 2 t 130.0 pos '0.0 0.0 0.0' yaw 0 near none\n";
        let id = inspect(text);
        assert_eq!(id.build.as_deref(), Some("4a6980c09cea"));
        let clock = id.clock.clone().unwrap();
        assert_eq!(
            (clock.frame_us, clock.tick_us, clock.seed),
            (13900, 1000, 7)
        );
        assert_eq!(clock.kind, "fixed");
        assert!(id.fixed_frame());
        assert_eq!(id.marks.len(), 2);
        assert_eq!(id.marks[0].near.as_deref(), Some("Joe Rogan"));
        assert_eq!(id.marks[0].seen, Some(true));
        assert_eq!(id.marks[0].dist, Some(240.0));
        assert_eq!(id.marks[0].pos, [12.0, -34.5, 24.0]);
        assert_eq!(id.marks[0].yaw, -90.0);
        assert_eq!(id.marks[1].near, None);
        assert_eq!(id.marks[1].t, 130.0);
    }

    #[test]
    fn a_realtime_server_and_an_old_tape() {
        let id = inspect("ARGUS clock frame_us 0 tick_us 50000 seed 0\n");
        assert_eq!(id.clock.as_ref().unwrap().kind, "realtime");
        assert!(!id.fixed_frame());
        assert!(inspect("ARGUS init on dm4\nARGLOG x t 1 pos '1 2 3'\n").is_empty());
    }

    #[test]
    fn a_marker_line_is_not_a_mark_and_two_builds_are_reported() {
        let id = inspect(
            "ARGUS Carmack hesitate junction\nARGUS mark of the beast\n\
             ARGUS build aaaaaa000000\nARGUS build bbbbbb111111\nARGUS build aaaaaa000000\n",
        );
        assert!(id.marks.is_empty());
        assert_eq!(id.build.as_deref(), Some("aaaaaa000000"));
        assert_eq!(id.other_builds, vec!["bbbbbb111111".to_string()]);
    }

    #[test]
    fn damaged_bookmarks_leave_other_identity_rows_readable() {
        let lines: Vec<String> =
            serde_json::from_str(include_str!("../testdata/tape_invalid_marks.json")).unwrap();
        let identity = inspect(&lines.join("\n"));
        assert_eq!(identity.build.as_deref(), Some("4a6980c09cea"));
        assert_eq!(identity.clock.unwrap().seed, 7);
        assert_eq!(identity.marks.len(), 1);
        assert_eq!(identity.marks[0].n, 9);
        assert_eq!(identity.marks[0].t, 6.25);
    }
}
