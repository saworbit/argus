//! Deeper look at one bot's ARGLOG/ARGEVT tape.

use crate::cartograph::{band_label, cartograph};
use crate::config::Config;
use crate::live::{snapshot_tape, BotLive};
use crate::nav_graph::{load_nav, nearest_node as nav_nearest};
use crate::parse_arglog::{parse_tape, MatchTape};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct BotDeep {
    pub live: BotLive,
    pub events: Vec<String>,
    pub deaths: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_node: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_dist: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_item: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub band: Option<String>,
    pub modes: crate::intel::ModeShare,
}

#[derive(Debug, Clone, Serialize)]
pub struct Timeline {
    pub bot: String,
    pub map: Option<String>,
    pub events: Vec<String>,
}

pub fn bot_deep(cfg: &Config, text: &str, name: &str) -> Result<BotDeep, String> {
    let tape = parse_tape(text);
    let snap = snapshot_tape(&tape);
    let live = snap
        .into_iter()
        .find(|b| b.name.eq_ignore_ascii_case(name))
        .ok_or_else(|| format!("no ARGLOG for {name}"))?;
    let events: Vec<String> = tape
        .events
        .iter()
        .filter(|e| e.bot.eq_ignore_ascii_case(name))
        .rev()
        .take(12)
        .map(|e| {
            if e.rest.is_empty() {
                e.verb.clone()
            } else {
                format!("{} {}", e.verb, e.rest)
            }
        })
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    let deaths: Vec<String> = tape
        .deaths
        .iter()
        .filter(|d| d.victim.eq_ignore_ascii_case(name))
        .map(|d| format!("{} @ {:.0} {:.0} {:.0}", d.killer, d.pos.x, d.pos.y, d.pos.z))
        .collect();
    let mut nearest_node = None;
    let mut nearest_dist = None;
    let mut nearest_item = None;
    let mut band = None;
    if let Some(map) = tape.map.as_deref() {
        if let Ok(g) = load_nav(cfg, map) {
            let (id, d) = nav_nearest(&g, live.x as f32, live.y as f32, live.z as f32);
            nearest_node = Some(id);
            nearest_dist = Some(d);
            band = Some(band_label(map, live.z as f32));
        }
        if let Ok(atlas) = cartograph(cfg, map) {
            let mut best: Option<(String, f64)> = None;
            for c in &atlas.control {
                let Some(o) = c.origin else { continue };
                let d = ((live.x - o[0] as f64).powi(2)
                    + (live.y - o[1] as f64).powi(2)
                    + (live.z - o[2] as f64).powi(2))
                .sqrt();
                if best.as_ref().map(|(_, bd)| d < *bd).unwrap_or(true) {
                    best = Some((format!("{} ({})", c.classname, c.reach), d));
                }
            }
            if let Some((name, _)) = best {
                nearest_item = Some(name);
            }
        }
    }
    let modes = mode_share_bot(&tape, name);
    Ok(BotDeep {
        live,
        events,
        deaths,
        nearest_node,
        nearest_dist,
        nearest_item,
        band,
        modes,
    })
}

#[derive(Debug, Clone, Serialize)]
pub struct PlanStep {
    pub bot: String,
    pub finish: String,
    pub via: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub t: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PlanView {
    pub map: Option<String>,
    pub plans: Vec<PlanStep>,
    pub headline: String,
}

pub fn plan_view(text: &str) -> PlanView {
    let tape = parse_tape(text);
    let mut plans = Vec::new();
    for e in &tape.events {
        if e.verb != "plan" {
            continue;
        }
        let (finish, via) = parse_plan_rest(&e.rest);
        plans.push(PlanStep {
            bot: e.bot.clone(),
            finish,
            via,
            t: e.t,
        });
    }
    let headline = if plans.is_empty() {
        "no GOAP plan events in this tape".into()
    } else {
        format!("{} plan event(s)", plans.len())
    };
    PlanView {
        map: tape.map,
        plans,
        headline,
    }
}

fn parse_plan_rest(rest: &str) -> (String, String) {
    let r = rest.trim();
    if let Some((a, b)) = r.split_once(" via ") {
        (a.trim().to_string(), b.trim().to_string())
    } else {
        (r.to_string(), String::new())
    }
}

pub fn timeline(text: &str, bot: &str, limit: usize) -> Timeline {
    let tape = parse_tape(text);
    let events: Vec<String> = tape
        .events
        .iter()
        .filter(|e| e.bot.eq_ignore_ascii_case(bot))
        .take(limit)
        .map(|e| {
            let t = e.t.map(|t| format!("t={t:.1} ")).unwrap_or_default();
            if e.rest.is_empty() {
                format!("{t}{}", e.verb)
            } else {
                format!("{t}{} {}", e.verb, e.rest)
            }
        })
        .collect();
    Timeline {
        bot: bot.to_string(),
        map: tape.map,
        events,
    }
}

/// `Reap` (live/last log) or `latest:Reap` / `ab_dm4_parity:Reap`
pub fn split_tape_bot<'a>(name: &'a str) -> (&'a str, Option<&'a str>) {
    if let Some((log, bot)) = name.split_once(':') {
        if !bot.is_empty() && !log.chars().all(|c| c.is_ascii_digit()) {
            return (bot, Some(log));
        }
    }
    (name, None)
}

fn mode_share_bot(tape: &MatchTape, name: &str) -> crate::intel::ModeShare {
    let mut seeking = 0.0;
    let mut combat = 0.0;
    let mut routed = 0.0;
    if let Some(rec) = tape.samples.get(name).or_else(|| {
        tape.samples
            .iter()
            .find(|(n, _)| n.eq_ignore_ascii_case(name))
            .map(|(_, r)| r)
    }) {
        for w in rec.windows(2) {
            let dt = (w[1].t - w[0].t).max(0.0);
            match w[0].mode {
                2 => routed += dt,
                1 => combat += dt,
                _ => seeking += dt,
            }
        }
    }
    let tot = (seeking + combat + routed).max(0.001);
    crate::intel::ModeShare {
        seeking: seeking / tot,
        combat: combat / tot,
        routed: routed / tot,
    }
}

pub fn load_named_tape(cfg: &Config, log: &str) -> Result<String, String> {
    let path = crate::intel::resolve_run_ref(cfg, log, None)?;
    std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_log_and_bot() {
        assert_eq!(split_tape_bot("Reap"), ("Reap", None));
        assert_eq!(split_tape_bot("latest:Omi"), ("Omi", Some("latest")));
        assert_eq!(split_tape_bot("ab_dm4_parity:Zeus"), ("Zeus", Some("ab_dm4_parity")));
    }

    #[test]
    fn parses_plan_events() {
        let text = "ARGEVT Reap plan item_artifact_super_damage via weapon\n";
        let v = plan_view(text);
        assert_eq!(v.plans.len(), 1);
        assert_eq!(v.plans[0].finish, "item_artifact_super_damage");
        assert_eq!(v.plans[0].via, "weapon");
    }
}
