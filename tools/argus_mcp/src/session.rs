//! Last-seen memory so an LLM can ask "what did I just look at".
//! Persisted to runs/.lab_session.json since 2026-08-27: restarts
//! are the NORM in this lab (every staged binary needs one), and an
//! in-process-only memory amnesia'd on exactly the events it was
//! most needed after.

use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SessionSeen {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_what: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_map: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_fn: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_run: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_experiment: Option<ExperimentRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExperimentRecord {
    pub map: String,
    pub run_name: String,
    pub duration_sec: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub compile_ok: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub verdict: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub headline: Option<String>,
}

impl SessionSeen {
    pub fn note_see(&mut self, what: &str, name: Option<&str>) {
        self.last_what = Some(what.to_string());
        self.last_name = name.map(|s| s.to_string());
        match what {
            "map" | "recipe" | "node" => {
                if let Some(n) = name {
                    let map = n.split(':').next().unwrap_or(n);
                    if !map.is_empty() {
                        self.last_map = Some(map.to_string());
                    }
                }
            }
            "fn" => {
                if let Some(n) = name {
                    self.last_fn = Some(n.to_string());
                }
            }
            "run" => {
                if let Some(n) = name {
                    self.last_run = Some(n.to_string());
                }
            }
            _ => {}
        }
    }

    pub fn note_experiment(&mut self, rec: ExperimentRecord) {
        self.last_map = Some(rec.map.clone());
        self.last_run = Some(rec.run_name.clone());
        self.last_experiment = Some(rec);
        self.last_what = Some("experiment".into());
    }

    pub fn load(path: &Path) -> Self {
        std::fs::read_to_string(path)
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_default()
    }

    pub fn save(&self, path: &Path) {
        if let Ok(text) = serde_json::to_string_pretty(self) {
            let _ = std::fs::write(path, text);
        }
    }
}

/// Where the memory lives when a lab root is resolvable.
pub fn session_path() -> Option<std::path::PathBuf> {
    crate::config::Config::load_for_reads().ok().map(|c| c.runs.join(".lab_session.json"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn records_map_from_node_ref() {
        let mut s = SessionSeen::default();
        s.note_see("node", Some("dm4:56"));
        assert_eq!(s.last_map.as_deref(), Some("dm4"));
        assert_eq!(s.last_name.as_deref(), Some("dm4:56"));
    }

    #[test]
    fn records_experiment() {
        let mut s = SessionSeen::default();
        s.note_experiment(ExperimentRecord {
            map: "dm4".into(),
            run_name: "exp_dm4".into(),
            duration_sec: 30,
            compile_ok: Some(true),
            verdict: Some("parity".into()),
            headline: Some("Parity: lava 0→0".into()),
        });
        assert_eq!(s.last_run.as_deref(), Some("exp_dm4"));
        assert_eq!(s.last_what.as_deref(), Some("experiment"));
    }
}
