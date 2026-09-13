//! Live visibility and whitelist tune for a dedicated server.
//!
//! Vanilla NetQuake has no QW RCON. The live path is the child's stdin
//! console. Bot aim/physics constants are compiled; only existing cvars
//! can change without a rebuild. skill applies at the next bot respawn.

use crate::parse_arglog::{parse_tape, MatchTape};
use regex::Regex;
use serde::Serialize;
use std::sync::OnceLock;

#[derive(Debug, Clone, Serialize)]
pub struct Knob {
    pub name: String,
    pub kind: String,
    pub live: bool,
    pub when: String,
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BotLive {
    pub name: String,
    pub t: f64,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub spd: f64,
    pub mode: u8,
    pub mode_name: String,
    pub stalls: i32,
    pub goals: i32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hp: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub frags: Option<i32>,
    pub last_event: Option<String>,
}

pub fn knobs() -> Vec<Knob> {
    vec![
        Knob {
            name: "skill".into(),
            kind: "cvar".into(),
            live: true,
            when: "next bot respawn (Argus_SetSkill)".into(),
            note: "0..3. Tune via tune or +skill on match_start. Does not retune a live body until it dies.".into(),
        },
        Knob {
            name: "fraglimit".into(),
            kind: "cvar".into(),
            live: true,
            when: "immediate (bots check each frame)".into(),
            note: "Argus ends the match when a bot hits fraglimit.".into(),
        },
        Knob {
            name: "timelimit".into(),
            kind: "cvar".into(),
            live: true,
            when: "immediate".into(),
            note: "Stock match clock.".into(),
        },
        Knob {
            name: "map".into(),
            kind: "console".into(),
            live: true,
            when: "restarts the level".into(),
            note: "Whitelist map names only. Same dedicated child.".into(),
        },
        Knob {
            name: "developer".into(),
            kind: "cvar".into(),
            live: true,
            when: "immediate".into(),
            note: "Must stay 1 for ARGLOG/ARGEVT (dprint).".into(),
        },
        Knob {
            name: "edicts / edict <n> / edictcount".into(),
            kind: "console".into(),
            live: true,
            when: "immediate".into(),
            note: "Read-only dump of every edict with its non-default fields, ar_* included. The forensics instrument.".into(),
        },
        Knob {
            name: "profile / serverprofile".into(),
            kind: "console".into(),
            live: true,
            when: "immediate".into(),
            note: "Read-only QC execution counts. Nothing has ever measured where progs time goes.".into(),
        },
        Knob {
            name: "notarget".into(),
            kind: "console".into(),
            live: true,
            when: "immediate".into(),
            note: "Monsters ignore players: isolates bot behaviour from the bestiary in a co-op look.".into(),
        },
        Knob {
            name: "sv_freezenonclients".into(),
            kind: "cvar".into(),
            live: true,
            when: "immediate".into(),
            note: "Freezes everything but clients, so a stuck bot can be walked around and inspected.".into(),
        },
        Knob {
            name: "AR_JUMPVEL / AR_AIMRATE / AR_*".into(),
            kind: "qc constant".into(),
            live: false,
            when: "compile_qc then rematch".into(),
            note: "Vanilla QC cannot load files. Change the constant, compile, probe.".into(),
        },
        Knob {
            name: "personalities (Reap/Omi/Zeus offsets)".into(),
            kind: "qc".into(),
            live: false,
            when: "compile_qc then rematch".into(),
            note: "Argus_SetSkill in src/argus.qc. Use qc_read to see the numbers.".into(),
        },
    ]
}

pub fn validate_tune(line: &str) -> Result<String, String> {
    let line = line.trim();
    if line.is_empty() || line.contains('\n') || line.contains('\r') {
        return Err("tune must be one console line".into());
    }
    let re = tune_re();
    if !re.is_match(line) {
        return Err(
            "not on the live whitelist. Allowed: skill 0-3, fraglimit N, timelimit N, developer 0|1, deathmatch 1, map <name>, scratch1-4 N (scratch1 1 = ARGDBG decision tape), status, serverinfo, edicts, edict <n>, edictcount, profile, serverprofile, notarget, sv_freezenonclients 0|1. See knobs()."
                .into(),
        );
    }
    Ok(line.to_string())
}

pub fn snapshot(text: &str) -> Vec<BotLive> {
    let tape = parse_tape(text);
    snapshot_tape(&tape)
}

/// Incremental live view. `since_line` is 0-based line count already consumed.
pub fn snapshot_window(text: &str, since_line: Option<u32>) -> serde_json::Value {
    let all: Vec<&str> = text.lines().collect();
    let total = all.len() as u32;
    let start = since_line.unwrap_or(0) as usize;
    let start = start.min(all.len());
    let slice = &all[start..];
    let clip = slice.join("\n");
    serde_json::json!({
        "bots": snapshot(if since_line.unwrap_or(0) == 0 { text } else { &clip }),
        "next_line": total,
        "new_lines": slice.len(),
    })
}

pub fn snapshot_tape(tape: &MatchTape) -> Vec<BotLive> {
    let mut out = Vec::new();
    for (name, rec) in &tape.samples {
        let Some(last) = rec.last() else { continue };
        let last_event = tape
            .events
            .iter()
            .rev()
            .find(|e| e.bot == *name)
            .map(|e| {
                if e.rest.is_empty() {
                    e.verb.clone()
                } else {
                    format!("{} {}", e.verb, e.rest)
                }
            });
        out.push(BotLive {
            name: name.clone(),
            t: last.t,
            x: last.pos.x,
            y: last.pos.y,
            z: last.pos.z,
            spd: last.spd,
            mode: last.mode,
            mode_name: mode_name(last.mode).into(),
            stalls: last.stalls,
            goals: last.goals,
            hp: last.hp,
            frags: last.frags,
            last_event,
        });
    }
    out
}

pub fn mode_name(mode: u8) -> &'static str {
    match mode {
        2 => "routed",
        1 => "combat",
        _ => "seeking",
    }
}

fn tune_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        // scratch1-4 are the vanilla QC float pipe (registered for
        // QC use since 1996): scratch1 1 arms the ARGDBG decision
        // tape live, and future debug channels ride the other three
        //
        // edicts / edict / edictcount are read-only server dumps.
        // ED_PrintEdicts walks the progs field definitions, so the
        // dump carries our own ar_* fields, which is every value a
        // forensics session has had to add a dprint and recompile to
        // read. All three only print, so they are as safe to inject
        // as status.
        //
        // profile / serverprofile print QC execution counts, and are
        // read-only in the same way (#255). notarget and
        // sv_freezenonclients are the two server-side debug toggles
        // worth having on a lab child: notarget takes monsters out of
        // the picture so a co-op look measures the bot rather than
        // the bestiary, and sv_freezenonclients holds everything but
        // the clients still so a stuck bot can be walked around and
        // inspected. All four confirmed present in the lab engine.
        //
        // viewpos and setpos are deliberately NOT here. Both act on a
        // local player and every lab match is -dedicated, where there
        // is none, so injecting them through this channel would do
        // nothing. They are worth typing on a listen server, which is
        // a human's console rather than this one.
        Regex::new(
            r"(?i)^(skill\s+[0-3]|fraglimit\s+\d{1,3}|timelimit\s+\d{1,3}|developer\s+[01]|deathmatch\s+1|map\s+[A-Za-z0-9_]+|scratch[1-4]\s+-?\d{1,6}|status|serverinfo|edicts|edictcount|edict\s+\d{1,4}|profile|serverprofile|notarget|sv_freezenonclients\s+[01])$",
        )
        .expect("tune")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn whitelist_accepts_skill_rejects_give() {
        assert!(validate_tune("skill 3").is_ok());
        assert!(validate_tune("map dm4").is_ok());
        assert!(validate_tune("fraglimit 20").is_ok());
        assert!(validate_tune("edicts").is_ok());
        assert!(validate_tune("edict 42").is_ok());
        assert!(validate_tune("edictcount").is_ok());
        // the engine debug verbs adopted in #255: read-only
        // dumps and the two server-side toggles
        assert!(validate_tune("profile").is_ok());
        assert!(validate_tune("serverprofile").is_ok());
        assert!(validate_tune("notarget").is_ok());
        assert!(validate_tune("sv_freezenonclients 1").is_ok());
        assert!(validate_tune("sv_freezenonclients 0").is_ok());
        // and the two that need a local player, which a
        // dedicated child does not have, stay off it
        assert!(validate_tune("viewpos").is_err());
        assert!(validate_tune("setpos 0 0 0").is_err());
        assert!(validate_tune("sv_freezenonclients 2").is_err());

        assert!(validate_tune("edict all").is_err());
        assert!(validate_tune("give all").is_err());
        assert!(validate_tune("quit").is_err());
        assert!(validate_tune("skill 9").is_err());
    }

    #[test]
    fn snapshot_last_sample() {
        let text = "\
ARGLOG Reap t 1.0 pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Reap t 2.0 pos '10 0 24' spd 50 yaw 0 mode 2 st 1 gl 2 hp 80 frg 1
ARGEVT Reap engage Omi
";
        let snap = snapshot(text);
        assert_eq!(snap.len(), 1);
        assert_eq!(snap[0].name, "Reap");
        assert_eq!(snap[0].stalls, 1);
        assert_eq!(snap[0].mode, 2);
        assert_eq!(snap[0].mode_name, "routed");
        assert_eq!(snap[0].last_event.as_deref(), Some("engage Omi"));
        let win = snapshot_window(text, Some(1));
        assert_eq!(win["next_line"], 3);
        assert_eq!(win["new_lines"], 2);
    }
}
