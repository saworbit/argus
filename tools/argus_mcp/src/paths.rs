use crate::config::Config;
use std::path::{Path, PathBuf};

/// One spelling that is also safe in Argus_Nav_Spawn_<map>.
pub fn map_name(raw: &str) -> Result<String, String> {
    let name = raw.trim().to_ascii_lowercase();
    if name.is_empty()
        || name.len() > 32
        || name == "dispatch"
        || !name
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_')
    {
        return Err("map must match [a-z0-9_]{1,32}; dispatch is reserved".into());
    }
    Ok(name)
}

pub fn valid_run_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 80
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-')
}

pub fn default_run_name() -> String {
    chrono::Utc::now().format("mcp_%Y%m%d_%H%M%S").to_string()
}

/// Resolve a user-supplied path. Existing absolute/relative wins, then
/// `$ARGUS_ROOT/<p>`, `$ARGUS_MAPS/<p>`, `$ARGUS_MAPS/<p>.bsp`.
pub fn resolve_input(cfg: &Config, given: &str) -> Result<PathBuf, String> {
    let as_given = PathBuf::from(given);
    if as_given.exists() {
        return Ok(as_given);
    }
    let under_root = cfg.root.join(given);
    if under_root.exists() {
        return Ok(under_root);
    }
    let map = map_name(given).unwrap_or_else(|_| given.to_string());
    let under_maps = cfg.maps.join(&map);
    if under_maps.exists() {
        return Ok(under_maps);
    }
    let with_bsp = cfg.maps.join(format!("{map}.bsp"));
    if with_bsp.exists() {
        return Ok(with_bsp);
    }
    Err(format!("path not found: {given}"))
}

/// Resolve a harvested match log: existing path, then under ARGUS_ROOT,
/// then `$ARGUS_RUNS/<name>` and `$ARGUS_RUNS/<name>.log`.
pub fn resolve_log(cfg: &Config, given: &str) -> Result<PathBuf, String> {
    if let Ok(p) = resolve_input(cfg, given) {
        return Ok(p);
    }
    let stem = given.trim_end_matches(".log");
    let candidates = [
        cfg.runs.join(given),
        cfg.runs.join(format!("{given}.log")),
        cfg.runs.join(format!("{stem}.log")),
    ];
    for p in candidates {
        if p.is_file() {
            return Ok(p);
        }
    }
    Err(format!(
        "log not found: {given} (tried ARGUS_RUNS/{given} and {given}.log)"
    ))
}

pub fn resolve_output(cfg: &Config, given: &str) -> PathBuf {
    let p = PathBuf::from(given);
    if p.is_absolute() {
        p
    } else {
        cfg.root.join(p)
    }
}

pub fn tail_lines(text: &str, n: usize) -> Vec<String> {
    let mut lines: Vec<String> = text.lines().map(|s| s.to_string()).collect();
    let skip = lines.len().saturating_sub(n);
    lines.drain(..skip);
    lines
}

pub fn read_tail(path: &Path, n: usize) -> Vec<String> {
    match read_engine_text(path) {
        Ok(text) => tail_lines(&text, n),
        Err(_) => Vec::new(),
    }
}

/// Quake console bytes may use bit 7 for bronze text. Keep the ASCII telemetry
/// readable while preserving real filesystem errors for the caller.
pub fn read_engine_text(path: impl AsRef<Path>) -> std::io::Result<String> {
    std::fs::read(path).map(|bytes| String::from_utf8_lossy(&bytes).into_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shipped_map_names_are_already_canonical() {
        let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../src");
        for entry in std::fs::read_dir(src).unwrap() {
            let entry = entry.unwrap();
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if let Some(map) = name
                .strip_prefix("argus_nav_")
                .and_then(|n| n.strip_suffix(".qc"))
            {
                if map != "dispatch" {
                    assert_eq!(map_name(map).unwrap(), map);
                }
            }
        }
    }

    #[test]
    fn run_name_rejects_path_escape() {
        assert!(valid_run_name("ab_dm4_parity"));
        assert!(valid_run_name("mcp_20260817_140131"));
        assert!(!valid_run_name("../etc"));
        assert!(!valid_run_name("a/b"));
        assert!(!valid_run_name(""));
        assert!(!valid_run_name("has space"));
    }

    #[test]
    fn resolve_log_accepts_run_name() {
        use crate::config::load_for_reads_from;
        use std::collections::HashMap;
        use std::fs;
        let root = std::env::temp_dir().join(format!("argus-mcp-log-{}", std::process::id()));
        let runs = root.join("runs");
        fs::create_dir_all(&runs).unwrap();
        fs::write(runs.join("ab_dm4_parity.log"), b"x").unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let p = resolve_log(&cfg, "ab_dm4_parity").unwrap();
        assert!(p.ends_with("ab_dm4_parity.log"));
        let _ = fs::remove_dir_all(&root);
    }
}
