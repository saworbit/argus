//! Campaign lab mode harness, co-op fail taxonomy, and dual-seat evaluation (#176).

use crate::parse_arglog::parse_tape;
use serde::{Deserialize, Serialize};

pub const CAMPAIGN_CORE_MAPS: &[&str] = &[
    "start", "e1m1", "e1m2", "e1m3", "e1m4", "e1m5", "e1m6", "e1m7",
];

pub const CAMPAIGN_STRETCH_MAPS: &[&str] = &["e2m3", "e3m4", "e4m2"];

pub fn is_campaign_map(map: &str) -> bool {
    let m = map.to_ascii_lowercase();
    CAMPAIGN_CORE_MAPS.contains(&m.as_str()) || CAMPAIGN_STRETCH_MAPS.contains(&m.as_str())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CampaignFailReason {
    StuckTimeout,
    EdictOverflow,
    LavaDeathLoop,
    KeyUnclaimed,
    NoRipple,
}

impl std::fmt::Display for CampaignFailReason {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::StuckTimeout => write!(f, "STUCK_TIMEOUT"),
            Self::EdictOverflow => write!(f, "EDICT_OVERFLOW"),
            Self::LavaDeathLoop => write!(f, "LAVA_DEATH_LOOP"),
            Self::KeyUnclaimed => write!(f, "KEY_UNCLAIMED"),
            Self::NoRipple => write!(f, "NO_RIPPLE"),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CampaignReport {
    pub map: String,
    pub seat: String, // "solo" or "companion"
    pub ok: bool,
    pub verdict: String, // "PASS" or "FAIL"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fail_reason: Option<CampaignFailReason>,
    pub checkpoints: Vec<String>,
    pub escort_break_s: f64,
    pub steal_events: u32,
    pub block_events: u32,
    pub elapsed_sec: u64,
    pub log_path: String,
    pub summary_line: String,
}

/// Evaluates a campaign tape against win conditions, checkpoints, fail taxonomy, and co-op metrics.
pub fn evaluate_campaign_log(
    text: &str,
    map: &str,
    seat: &str,
    log_path: &str,
    elapsed_sec: u64,
    bsp: Option<&crate::bsp::Bsp29>,
    skill: Option<u32>,
) -> CampaignReport {
    let tape = parse_tape(text);
    let mut checkpoints = Vec::new();
    let mut has_win = false;

    // 1. Scan for win and checkpoint events
    for line in text.lines() {
        if line.contains("win exit")
            || line.contains("exited the level")
            || line.contains("LOC_CLIENT_EXIT_LEVEL")
        {
            has_win = true;
            if !checkpoints.contains(&"exit".to_string()) {
                checkpoints.push("exit".into());
            }
        }
        if line.contains("Chthon defeat") || line.contains("boss defeat") {
            has_win = true;
            if !checkpoints.contains(&"chthon_defeated".to_string()) {
                checkpoints.push("chthon_defeated".into());
            }
        }
        if line.contains("checkpoint gold_key") && !checkpoints.contains(&"gold_key".to_string()) {
            checkpoints.push("gold_key".into());
        }
        if line.contains("checkpoint silver_key")
            && !checkpoints.contains(&"silver_key".to_string())
        {
            checkpoints.push("silver_key".into());
        }
        if line.contains("checkpoint silver_door")
            && !checkpoints.contains(&"silver_door".to_string())
        {
            checkpoints.push("silver_door".into());
        }
        if line.contains("checkpoint gold_door") && !checkpoints.contains(&"gold_door".to_string())
        {
            checkpoints.push("gold_door".into());
        }
    }

    // 2. Extract co-op telemetry counters
    let mut escort_break_s = 0.0f64;
    let mut steal_events = 0u32;
    let mut block_events = 0u32;

    for line in text.lines() {
        if line.contains("coop_stats break ") {
            // ARGEVT <bot> coop_stats break <float> steal <float> block <float>
            if let Some(pos) = line.find("coop_stats break ") {
                let rest = &line[pos + 17..];
                let parts: Vec<&str> = rest.split_whitespace().collect();
                if parts.len() >= 5 {
                    if let Ok(b) = parts[0].parse::<f64>() {
                        if b > escort_break_s {
                            escort_break_s = b;
                        }
                    }
                    if parts[1] == "steal" {
                        if let Ok(s) = parts[2].parse::<u32>() {
                            if s > steal_events {
                                steal_events = s;
                            }
                        }
                    }
                    if parts[3] == "block" {
                        if let Ok(bl) = parts[4].parse::<u32>() {
                            if bl > block_events {
                                block_events = bl;
                            }
                        }
                    }
                }
            }
        }
    }

    // "steal" is not a verb in the ARGEVT grammar - the QC only ever
    // prints it as a field of coop_stats, which the loop above reads.
    // The old per-event count here could never match anything.

    // 3. Evaluate fail taxonomy if not won
    let fail_reason = if has_win {
        None
    } else {
        Some(determine_fail_reason(text, &tape, &checkpoints, bsp, skill))
    };

    let ok = has_win;
    let verdict = if ok { "PASS" } else { "FAIL" }.to_string();

    let cp_str = if checkpoints.is_empty() {
        "none".to_string()
    } else {
        checkpoints.join(", ")
    };

    let summary_line = if ok {
        format!(
            "[{}][{}] PASS: exit reached in {}s (checkpoints: {}; break={:.1}s, steal={}, block={})",
            map.to_ascii_uppercase(),
            seat.to_ascii_uppercase(),
            elapsed_sec,
            cp_str,
            escort_break_s,
            steal_events,
            block_events
        )
    } else {
        let fr = fail_reason.as_ref().unwrap();
        format!(
            "[{}][{}] FAIL: {} (checkpoints: {}; break={:.1}s, steal={}, block={})",
            map.to_ascii_uppercase(),
            seat.to_ascii_uppercase(),
            fr,
            cp_str,
            escort_break_s,
            steal_events,
            block_events
        )
    };

    CampaignReport {
        map: map.to_string(),
        seat: seat.to_string(),
        ok,
        verdict,
        fail_reason,
        checkpoints,
        escort_break_s,
        steal_events,
        block_events,
        elapsed_sec,
        log_path: log_path.to_string(),
        summary_line,
    }
}

fn determine_fail_reason(
    text: &str,
    tape: &crate::parse_arglog::MatchTape,
    checkpoints: &[String],
    bsp: Option<&crate::bsp::Bsp29>,
    skill: Option<u32>,
) -> CampaignFailReason {
    let lower = text.to_ascii_lowercase();

    // 1. EDICT_OVERFLOW
    if lower.contains("ed_alloc: no free edicts")
        || lower.contains("ed_alloc")
        || lower.contains("host_error: ed_alloc")
        || lower.contains("edict limit reached")
    {
        return CampaignFailReason::EdictOverflow;
    }

    // 2. LAVA_DEATH_LOOP
    // Argus_Die and ClientObituary print "world" for every nameless
    // killer, so no killer string ever says lava. Classify by hull 0
    // contents at the death position exactly as intel does, with the
    // z rule surviving only as the no-BSP fallback inside
    // death_is_lava. The old z < -300 literal was dm4's pit depth and
    // sits below every campaign map's lava.
    let hull = bsp.and_then(|bsp| bsp.hull0.as_ref());
    let mut hazard_deaths = 0usize;
    for d in &tape.deaths {
        if d.killer.eq_ignore_ascii_case("world")
            && crate::bsp::death_is_lava(hull, d.pos.x, d.pos.y, d.pos.z)
        {
            hazard_deaths += 1;
        }
    }
    if hazard_deaths >= 2 {
        return CampaignFailReason::LavaDeathLoop;
    }

    // 3. NO_RIPPLE / KEY_UNCLAIMED
    if lower.contains("no_ripple") || lower.contains("ripple fail") {
        return CampaignFailReason::NoRipple;
    }
    if lower.contains("key_unclaimed") || lower.contains("coop key fail") {
        return CampaignFailReason::KeyUnclaimed;
    }

    if bsp.is_some_and(|bsp| has_unclaimed_key(&bsp.entities, skill, checkpoints)) {
        return CampaignFailReason::KeyUnclaimed;
    }

    // Default fallback is STUCK_TIMEOUT (duration expired without progress)
    CampaignFailReason::StuckTimeout
}

fn has_unclaimed_key(entities: &str, skill: Option<u32>, checkpoints: &[String]) -> bool {
    // Campaign always launches with coop 1 and deathmatch 0. Quake applies
    // skill flags in this mode. If skill is inherited, require an unrestricted key.
    const NOT_EASY: i32 = 256;
    const NOT_MEDIUM: i32 = 512;
    const NOT_HARD: i32 = 1024;
    let excluded = match skill {
        Some(0) => NOT_EASY,
        Some(1) => NOT_MEDIUM,
        Some(_) => NOT_HARD,
        None => NOT_EASY | NOT_MEDIUM | NOT_HARD,
    };
    crate::cartograph::parse_entities(entities)
        .iter()
        .any(|entity| {
            let checkpoint = match entity.get("classname").map(String::as_str) {
                Some("item_key1") => "silver_key",
                Some("item_key2") => "gold_key",
                _ => return false,
            };
            let flags = entity
                .get("spawnflags")
                .and_then(|value| value.parse::<f32>().ok())
                .unwrap_or_default() as i32;
            flags & excluded == 0 && !checkpoints.iter().any(|taken| taken == checkpoint)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn campaign_core_maps_are_identified() {
        assert!(is_campaign_map("start"));
        assert!(is_campaign_map("e1m1"));
        assert!(is_campaign_map("E1M2"));
        assert!(is_campaign_map("e1m7"));
        assert!(is_campaign_map("e2m3"));
        assert!(is_campaign_map("e3m4"));
        assert!(is_campaign_map("e4m2"));
        assert!(!is_campaign_map("dm4"));
        assert!(!is_campaign_map("lqdm2"));
    }

    #[test]
    fn classifies_clean_win() {
        let text = r#"
ARGEVT Ranger spawned
ARGEVT Ranger checkpoint gold_key
ARGEVT Ranger checkpoint silver_door
ARGEVT Ranger win exit
ARGEVT Ranger coop_stats break 4.5 steal 0 block 1
"#;
        let report = evaluate_campaign_log(text, "e1m1", "solo", "runs/test.log", 34, None, None);
        assert!(report.ok);
        assert_eq!(report.verdict, "PASS");
        assert_eq!(report.fail_reason, None);
        assert_eq!(report.checkpoints, vec!["gold_key", "silver_door", "exit"]);
        assert_eq!(report.escort_break_s, 4.5);
        assert_eq!(report.steal_events, 0);
        assert_eq!(report.block_events, 1);
        assert!(report
            .summary_line
            .contains("[E1M1][SOLO] PASS: exit reached in 34s"));
    }

    #[test]
    fn classifies_edict_overflow() {
        let text = r#"
ARGEVT Ranger spawned
Host_Error: ED_Alloc: no free edicts
"#;
        let report = evaluate_campaign_log(text, "e1m2", "solo", "runs/test.log", 12, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::EdictOverflow));
        assert!(report.summary_line.contains("FAIL: EDICT_OVERFLOW"));
    }

    #[test]
    fn classifies_lava_death_loop() {
        let text = r#"
ARGEVT Ranger spawned
ARGEVT Ranger death world pos '100 200 -350'
ARGEVT Ranger respawn
ARGEVT Ranger death world pos '100 200 -350'
"#;
        let report = evaluate_campaign_log(text, "e1m3", "solo", "runs/test.log", 20, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::LavaDeathLoop));
        assert!(report.summary_line.contains("FAIL: LAVA_DEATH_LOOP"));
    }

    // #217: the QC prints "world" for every nameless killer, so no
    // death line ever says lava. With no BSP death_is_lava falls back
    // to the z rule, which is what this exercises; on a real campaign
    // map the hull 0 contents decide.
    #[test]
    fn lava_loop_is_classified_from_a_world_killer() {
        let text = "ARGEVT Ranger spawned
ARGEVT Ranger death world pos '100 200 -350'
ARGEVT Ranger respawn
ARGEVT Ranger death world pos '100 200 -350'
";
        let report = evaluate_campaign_log(text, "e1m1", "solo", "runs/test.log", 20, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::LavaDeathLoop));
    }

    #[test]
    fn classifies_key_unclaimed() {
        let text = r#"
ARGEVT Ranger spawned
ARGUS coop key fail: KEY_UNCLAIMED
"#;
        let report = evaluate_campaign_log(text, "e1m1", "solo", "runs/test.log", 30, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::KeyUnclaimed));
    }

    #[test]
    fn classifies_no_ripple() {
        let text = r#"
ARGEVT Ranger spawned
ARGUS no_ripple for door *12
"#;
        let report =
            evaluate_campaign_log(text, "e1m5", "companion", "runs/test.log", 45, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::NoRipple));
        assert!(report.summary_line.contains("FAIL: NO_RIPPLE"));
    }

    #[test]
    fn keyless_e1m1_is_a_timeout() {
        let bsp = test_bsp(r#"{ "classname" "worldspawn" }"#);
        for bsp in [Some(&bsp), None] {
            let report = evaluate_campaign_log("", "e1m1", "solo", "runs/test.log", 30, bsp, None);
            assert_eq!(report.fail_reason, Some(CampaignFailReason::StuckTimeout));
        }
    }

    #[test]
    fn campaign_key_expectations_use_the_coop_skill_and_matching_checkpoint() {
        // The silver key is hidden in deathmatch and on easy.
        let bsp = test_bsp(r#"{ "classname" "item_key1" "spawnflags" "2304" }"#);
        for (skill, log, expected) in [
            (Some(0), "", CampaignFailReason::StuckTimeout),
            (None, "", CampaignFailReason::StuckTimeout),
            (Some(2), "", CampaignFailReason::KeyUnclaimed),
            (
                Some(3),
                "checkpoint gold_key",
                CampaignFailReason::KeyUnclaimed,
            ),
            (
                Some(2),
                "checkpoint silver_key",
                CampaignFailReason::StuckTimeout,
            ),
        ] {
            let report =
                evaluate_campaign_log(log, "e1m2", "solo", "runs/test.log", 30, Some(&bsp), skill);
            assert_eq!(report.fail_reason, Some(expected));
        }
    }

    fn test_bsp(entities: &str) -> crate::bsp::Bsp29 {
        crate::bsp::Bsp29 {
            version: 29,
            entities: entities.into(),
            mins: [0.0; 3],
            maxs: [0.0; 3],
            models: Vec::new(),
            clip: None,
            hull0: None,
        }
    }

    #[test]
    fn classifies_stuck_timeout() {
        let text = r#"
ARGEVT Ranger spawned
ARGLOG Ranger t 0.0 pos '10 10 24' spd 0.0 yaw 0.0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Ranger t 3.0 pos '10 10 24' spd 0.0 yaw 0.0 mode 0 st 0 gl 0 hp 100 frg 0
ARGLOG Ranger t 8.0 pos '10 10 24' spd 0.0 yaw 0.0 mode 0 st 0 gl 0 hp 100 frg 0
"#;
        let report = evaluate_campaign_log(text, "start", "solo", "runs/test.log", 60, None, None);
        assert!(!report.ok);
        assert_eq!(report.fail_reason, Some(CampaignFailReason::StuckTimeout));
        assert!(report.summary_line.contains("FAIL: STUCK_TIMEOUT"));
    }
}
