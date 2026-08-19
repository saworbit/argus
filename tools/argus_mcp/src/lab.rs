//! One-shot lab dashboard.

use crate::cartograph::{atlas_brief, list_maps, AtlasBrief};
use crate::config::{Config, ConfigReport};
use crate::match_ctrl::{list_runs, MatchStatus};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct LabStatus {
    pub ready: bool,
    pub config: ConfigReport,
    pub maps: Vec<LabMap>,
    pub recent_runs: Vec<crate::match_ctrl::RunEntry>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub live: Option<MatchStatus>,
    pub recommend: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LabMap {
    pub name: String,
    pub source: String,
    pub has_bsp: bool,
    pub has_nav: bool,
    pub dispatcher: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub headline: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recipe: Option<String>,
}

pub fn lab_status(cfg: &Config, live: Option<MatchStatus>) -> LabStatus {
    let config = Config::report();
    let ready = cfg.require_ready().is_ok();
    let maps: Vec<LabMap> = list_maps(cfg)
        .unwrap_or_default()
        .into_iter()
        .map(|m| {
            let dispatcher = dispatcher_knows(cfg, &m.name);
            let has_bsp = m.path.is_some();
            LabMap {
                recipe: has_bsp.then(|| {
                    format!(
                        "experiment map={} duration_sec=30 ; or match_run map={} duration_sec=185",
                        m.name, m.name
                    )
                }),
                headline: None,
                name: m.name,
                source: m.source,
                has_bsp,
                has_nav: m.has_nav,
                dispatcher,
            }
        })
        .collect();
    let recent_runs: Vec<crate::match_ctrl::RunEntry> =
        list_runs(cfg).unwrap_or_default().into_iter().take(8).collect();
    let recommend = recommend(ready, &maps, &recent_runs, live.as_ref());
    LabStatus {
        ready,
        config,
        maps,
        recent_runs,
        live,
        recommend,
    }
}

fn dispatcher_knows(cfg: &Config, map: &str) -> bool {
    let path = cfg.src.join("argus_nav_dispatch.qc");
    std::fs::read_to_string(path)
        .map(|t| t.contains(&format!("mapname == \"{map}\"")))
        .unwrap_or(false)
}

fn recommend(
    ready: bool,
    maps: &[LabMap],
    runs: &[crate::match_ctrl::RunEntry],
    live: Option<&MatchStatus>,
) -> String {
    if live.map(|s| s.running).unwrap_or(false) {
        return "a match is live; see what=live or see what=status, or tune command=\"skill 3\"".into();
    }
    if !ready {
        return "config is incomplete; run config_check and set the missing ARGUS_* keys".into();
    }
    if let Some(m) = maps.iter().find(|m| m.has_bsp && !m.has_nav) {
        return format!(
            "{} has a BSP but no nav JSON; cartograph bsp={} generate_nav=true",
            m.name, m.name
        );
    }
    if runs.is_empty() {
        if let Some(m) = maps.iter().find(|m| m.recipe.is_some()) {
            return m.recipe.clone().unwrap();
        }
        return "no harvested logs; match_run map=dm4 duration_sec=185".into();
    }
    format!(
        "see what=project, or experiment after a QC edit, or compare_runs log_b=latest"
    )
}

pub fn cartograph_all(cfg: &Config) -> Result<Vec<AtlasBrief>, String> {
    let mut out = Vec::new();
    for m in list_maps(cfg)? {
        if m.path.is_none() {
            continue;
        }
        if let Ok(atlas) = crate::cartograph::cartograph(cfg, &m.name) {
            out.push(atlas_brief(&atlas));
        }
    }
    if out.is_empty() {
        return Err("no on-disk BSPs to cartograph (extract with cartograph bsp=<name> first)".into());
    }
    Ok(out)
}
