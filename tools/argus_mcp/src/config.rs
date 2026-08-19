//! Env-and-TOML config. No baked-in machine paths.

use serde::Serialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use thiserror::Error;

const REQUIRED: &[&str] = &[
    "ARGUS_ROOT",
    "ARGUS_FTEQCC",
    "ARGUS_ENGINE",
    "ARGUS_BASEDIR",
    "ARGUS_PYTHON",
];

#[derive(Debug, Clone)]
pub struct Config {
    pub root: PathBuf,
    pub fteqcc: PathBuf,
    pub engine: PathBuf,
    pub basedir: PathBuf,
    pub python: PathBuf,
    pub game: String,
    pub src: PathBuf,
    pub runs: PathBuf,
    pub progs: PathBuf,
    pub maps: PathBuf,
}

#[derive(Debug, Clone, Serialize)]
pub struct ConfigEntry {
    pub key: String,
    pub value: Option<String>,
    pub exists: bool,
    pub required: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ConfigReport {
    pub entries: Vec<ConfigEntry>,
    pub complete: bool,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("missing required config key {0}")]
    MissingKey(&'static str),
    #[error("config path for {key} does not exist: {path}")]
    MissingPath { key: &'static str, path: String },
}

impl Config {
    pub fn load() -> Result<Self, ConfigError> {
        let env: HashMap<String, String> = std::env::vars().collect();
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        load_from(&env, &cwd)
    }

    pub fn report() -> ConfigReport {
        let env: HashMap<String, String> = std::env::vars().collect();
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        report_from(&env, &cwd)
    }

    pub fn install_paths(&self) -> Vec<PathBuf> {
        let mut out = vec![
            self.root.join("game").join(&self.game).join("progs.dat"),
            self.basedir.join(&self.game).join("progs.dat"),
        ];
        if let Some(p) = rerelease_progs(&self.game) {
            out.push(p);
        }
        out.sort();
        out.dedup();
        out
    }

    pub fn navgen_script(&self) -> PathBuf {
        self.root.join("tools").join("argus_navgen.py")
    }

    pub fn analyze_script(&self) -> PathBuf {
        self.root.join("tools").join("analyze_match.py")
    }

    pub fn require_ready(&self) -> Result<(), ConfigError> {
        check_exists("ARGUS_ROOT", &self.root)?;
        check_exists("ARGUS_FTEQCC", &self.fteqcc)?;
        check_exists("ARGUS_ENGINE", &self.engine)?;
        check_exists("ARGUS_BASEDIR", &self.basedir)?;
        check_exists("ARGUS_PYTHON", &self.python)?;
        check_exists("ARGUS_SRC", &self.src)?;
        Ok(())
    }

    /// Logs and briefs only need the repo root. Engine paths may be unset.
    pub fn load_for_reads() -> Result<Self, ConfigError> {
        let env: HashMap<String, String> = std::env::vars().collect();
        let cwd = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        load_for_reads_from(&env, &cwd)
    }
}

pub fn load_for_reads_from(
    env: &HashMap<String, String>,
    cwd: &Path,
) -> Result<Config, ConfigError> {
    let merged = merge(env, cwd);
    let root = required_path(&merged, "ARGUS_ROOT")?;
    let game = merged
        .get("ARGUS_GAME")
        .cloned()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "argus".into());
    let src = optional_path(&merged, "ARGUS_SRC").unwrap_or_else(|| root.join("src"));
    let runs = optional_path(&merged, "ARGUS_RUNS").unwrap_or_else(|| root.join("runs"));
    let progs = optional_path(&merged, "ARGUS_PROGS").unwrap_or_else(|| root.join("lq1").join("progs.dat"));
    let maps = optional_path(&merged, "ARGUS_MAPS").unwrap_or_else(|| root.join("maps_local"));
    Ok(Config {
        root: root.clone(),
        fteqcc: optional_path(&merged, "ARGUS_FTEQCC").unwrap_or_default(),
        engine: optional_path(&merged, "ARGUS_ENGINE").unwrap_or_default(),
        basedir: optional_path(&merged, "ARGUS_BASEDIR").unwrap_or_default(),
        python: optional_path(&merged, "ARGUS_PYTHON").unwrap_or_default(),
        game,
        src,
        runs,
        progs,
        maps,
    })
}

pub fn load_from(env: &HashMap<String, String>, cwd: &Path) -> Result<Config, ConfigError> {
    let merged = merge(env, cwd);
    let root = required_path(&merged, "ARGUS_ROOT")?;
    let fteqcc = required_path(&merged, "ARGUS_FTEQCC")?;
    let engine = required_path(&merged, "ARGUS_ENGINE")?;
    let basedir = required_path(&merged, "ARGUS_BASEDIR")?;
    let python = required_path(&merged, "ARGUS_PYTHON")?;

    let game = merged
        .get("ARGUS_GAME")
        .cloned()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "argus".into());
    let src = optional_path(&merged, "ARGUS_SRC").unwrap_or_else(|| root.join("src"));
    let runs = optional_path(&merged, "ARGUS_RUNS").unwrap_or_else(|| root.join("runs"));
    let progs = optional_path(&merged, "ARGUS_PROGS").unwrap_or_else(|| root.join("lq1").join("progs.dat"));
    let maps = optional_path(&merged, "ARGUS_MAPS").unwrap_or_else(|| root.join("maps_local"));

    Ok(Config {
        root,
        fteqcc,
        engine,
        basedir,
        python,
        game,
        src,
        runs,
        progs,
        maps,
    })
}

pub fn report_from(env: &HashMap<String, String>, cwd: &Path) -> ConfigReport {
    let merged = merge(env, cwd);
    let mut keys: Vec<&str> = REQUIRED.to_vec();
    keys.extend([
        "ARGUS_GAME",
        "ARGUS_SRC",
        "ARGUS_RUNS",
        "ARGUS_PROGS",
        "ARGUS_MAPS",
    ]);

    let mut entries = Vec::new();
    let mut complete = true;
    for key in keys {
        let required = REQUIRED.contains(&key);
        let raw = merged.get(key).cloned().filter(|s| !s.is_empty());
        let value = if raw.is_none() {
            default_display(&merged, key)
        } else {
            raw.clone()
        };
        let exists = value
            .as_deref()
            .map(|p| Path::new(p).exists())
            .unwrap_or(false);
        if required && (raw.is_none() || !exists) {
            complete = false;
        }
        entries.push(ConfigEntry {
            key: key.to_string(),
            value,
            exists,
            required,
        });
    }
    ConfigReport { entries, complete }
}

fn merge(env: &HashMap<String, String>, cwd: &Path) -> HashMap<String, String> {
    let mut out = HashMap::new();
    if let Some(path) = toml_path(env, cwd) {
        if let Ok(text) = std::fs::read_to_string(&path) {
            if let Ok(table) = text.parse::<toml::Table>() {
                flatten_toml(&table, &mut out);
            }
        }
    }
    for (k, v) in env {
        if k.starts_with("ARGUS_") && k != "ARGUS_MCP_CONFIG" {
            out.insert(k.clone(), v.clone());
        }
    }
    apply_discovery(cwd, &mut out);
    out
}

/// If keys are unset, infer ARGUS_ROOT from a parent that has
/// game/argus/autoexec.cfg, then fteqcc / engine / basedir / python
/// from the usual lab layout.
fn apply_discovery(cwd: &Path, out: &mut HashMap<String, String>) {
    if !out.contains_key("ARGUS_ROOT") {
        if let Some(root) = find_root(cwd) {
            out.insert("ARGUS_ROOT".into(), root.display().to_string());
        }
    }
    let Some(root) = out.get("ARGUS_ROOT").map(PathBuf::from) else {
        return;
    };
    if !out.contains_key("ARGUS_FTEQCC") {
        if let Some(p) = find_fteqcc(&root) {
            out.insert("ARGUS_FTEQCC".into(), p.display().to_string());
        }
    }
    if !out.contains_key("ARGUS_ENGINE") {
        let p = root.join("engine").join("quakespasm.exe");
        if p.is_file() {
            out.insert("ARGUS_ENGINE".into(), p.display().to_string());
        } else {
            let p = root.join("engine").join("quakespasm");
            if p.is_file() {
                out.insert("ARGUS_ENGINE".into(), p.display().to_string());
            }
        }
    }
    if !out.contains_key("ARGUS_BASEDIR") {
        let p = root.join("engine");
        if p.join("id1").is_dir() || p.join("id1").is_file() {
            out.insert("ARGUS_BASEDIR".into(), p.display().to_string());
        }
    }
    if !out.contains_key("ARGUS_PYTHON") {
        if let Some(p) = find_python() {
            out.insert("ARGUS_PYTHON".into(), p);
        }
    }
}

/// 2021 rerelease mods live under Saved Games, not the Steam tree.
fn rerelease_progs(game: &str) -> Option<PathBuf> {
    let home = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME"))?;
    let dir = PathBuf::from(home)
        .join("Saved Games")
        .join("Nightdive Studios")
        .join("Quake")
        .join(game);
    if dir.is_dir() {
        Some(dir.join("progs.dat"))
    } else {
        None
    }
}

fn find_root(start: &Path) -> Option<PathBuf> {
    let mut cur = if start.is_absolute() {
        start.to_path_buf()
    } else {
        std::env::current_dir().ok()?.join(start)
    };
    for _ in 0..8 {
        if cur.join("game").join("argus").join("autoexec.cfg").is_file() {
            return Some(cur);
        }
        if !cur.pop() {
            break;
        }
    }
    None
}

fn find_fteqcc(root: &Path) -> Option<PathBuf> {
    let win = root.join("tools").join("win");
    if !win.is_dir() {
        return None;
    }
    fn walk(dir: &Path, depth: u8) -> Option<PathBuf> {
        if depth == 0 {
            return None;
        }
        let rd = std::fs::read_dir(dir).ok()?;
        for ent in rd.flatten() {
            let p = ent.path();
            if p.is_dir() {
                if let Some(hit) = walk(&p, depth - 1) {
                    return Some(hit);
                }
            } else if p.file_name().and_then(|s| s.to_str()) == Some("fteqcc64.exe") {
                return Some(p);
            }
        }
        None
    }
    walk(&win, 5)
}

fn find_python() -> Option<String> {
    let cands = if cfg!(windows) {
        vec![
            "C:\\Windows\\py.exe".into(),
            "C:\\Windows\\System32\\py.exe".into(),
        ]
    } else {
        vec!["/usr/bin/python3".into(), "/usr/bin/python".into()]
    };
    cands.into_iter().find(|p| Path::new(p).is_file())
}

fn toml_path(env: &HashMap<String, String>, cwd: &Path) -> Option<PathBuf> {
    if let Some(p) = env.get("ARGUS_MCP_CONFIG") {
        return Some(PathBuf::from(p));
    }
    if let Some(root) = env.get("ARGUS_ROOT") {
        return Some(PathBuf::from(root).join("tools").join("argus_mcp.toml"));
    }
    Some(cwd.join("tools").join("argus_mcp.toml"))
}

fn flatten_toml(table: &toml::Table, out: &mut HashMap<String, String>) {
    for (k, v) in table {
        match v {
            toml::Value::String(s) => {
                out.insert(k.clone(), s.clone());
            }
            toml::Value::Integer(i) => {
                out.insert(k.clone(), i.to_string());
            }
            toml::Value::Table(inner) => flatten_toml(inner, out),
            other => {
                out.insert(k.clone(), other.to_string());
            }
        }
    }
}

fn required_path(merged: &HashMap<String, String>, key: &'static str) -> Result<PathBuf, ConfigError> {
    let raw = merged
        .get(key)
        .cloned()
        .filter(|s| !s.is_empty())
        .ok_or(ConfigError::MissingKey(key))?;
    Ok(PathBuf::from(raw))
}

fn optional_path(merged: &HashMap<String, String>, key: &str) -> Option<PathBuf> {
    merged
        .get(key)
        .cloned()
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
}

fn default_display(merged: &HashMap<String, String>, key: &str) -> Option<String> {
    let root = merged.get("ARGUS_ROOT")?;
    let root = Path::new(root);
    match key {
        "ARGUS_GAME" => Some("argus".into()),
        "ARGUS_SRC" => Some(root.join("src").display().to_string()),
        "ARGUS_RUNS" => Some(root.join("runs").display().to_string()),
        "ARGUS_PROGS" => Some(root.join("lq1").join("progs.dat").display().to_string()),
        "ARGUS_MAPS" => Some(root.join("maps_local").display().to_string()),
        _ => None,
    }
}

fn check_exists(key: &'static str, path: &Path) -> Result<(), ConfigError> {
    if path.exists() {
        Ok(())
    } else {
        Err(ConfigError::MissingPath {
            key,
            path: path.display().to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Write;

    fn tmpdir() -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "argus-mcp-cfg-{}-{}",
            std::process::id(),
            chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0)
        ));
        fs::create_dir_all(&p).unwrap();
        p
    }

    fn write_exe(dir: &Path, name: &str) -> PathBuf {
        let p = dir.join(name);
        fs::write(&p, b"x").unwrap();
        p
    }

    #[test]
    fn missing_required_keys_error_by_name() {
        let env = HashMap::new();
        let empty = tmpdir();
        let err = load_from(&env, &empty).unwrap_err();
        match err {
            ConfigError::MissingKey(k) => assert_eq!(k, "ARGUS_ROOT"),
            other => panic!("unexpected {other}"),
        }
        let _ = fs::remove_dir_all(&empty);
    }

    #[test]
    fn discovers_root_from_autoexec() {
        let root = tmpdir();
        fs::create_dir_all(root.join("game").join("argus")).unwrap();
        fs::write(root.join("game").join("argus").join("autoexec.cfg"), b"//").unwrap();
        let env = HashMap::new();
        let err = load_from(&env, &root);
        // root is found; toolchain keys may still be missing
        match err {
            Ok(cfg) => assert_eq!(cfg.root, root),
            Err(ConfigError::MissingKey(k)) => assert_ne!(k, "ARGUS_ROOT"),
            other => panic!("unexpected {other:?}"),
        }
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn defaults_fill_optional_keys() {
        let root = tmpdir();
        let fteqcc = write_exe(&root, "fteqcc");
        let engine = write_exe(&root, "engine");
        let python = write_exe(&root, "python");
        fs::create_dir_all(root.join("id1")).unwrap();

        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        env.insert("ARGUS_FTEQCC".into(), fteqcc.display().to_string());
        env.insert("ARGUS_ENGINE".into(), engine.display().to_string());
        env.insert("ARGUS_BASEDIR".into(), root.display().to_string());
        env.insert("ARGUS_PYTHON".into(), python.display().to_string());

        let cfg = load_from(&env, &root).unwrap();
        assert_eq!(cfg.game, "argus");
        assert_eq!(cfg.src, root.join("src"));
        assert_eq!(cfg.runs, root.join("runs"));
        assert_eq!(cfg.progs, root.join("lq1").join("progs.dat"));
        assert_eq!(cfg.maps, root.join("maps_local"));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn env_overrides_toml() {
        let root = tmpdir();
        let fteqcc = write_exe(&root, "fteqcc");
        let engine = write_exe(&root, "engine");
        let python = write_exe(&root, "python");
        let toml_path = root.join("cfg.toml");
        let mut f = fs::File::create(&toml_path).unwrap();
        writeln!(
            f,
            "ARGUS_ROOT = \"{}\"\nARGUS_GAME = \"fromfile\"\nARGUS_FTEQCC = \"{}\"\nARGUS_ENGINE = \"{}\"\nARGUS_BASEDIR = \"{}\"\nARGUS_PYTHON = \"{}\"",
            root.display().to_string().replace('\\', "/"),
            fteqcc.display().to_string().replace('\\', "/"),
            engine.display().to_string().replace('\\', "/"),
            root.display().to_string().replace('\\', "/"),
            python.display().to_string().replace('\\', "/"),
        )
        .unwrap();

        let mut env = HashMap::new();
        env.insert("ARGUS_MCP_CONFIG".into(), toml_path.display().to_string());
        env.insert("ARGUS_GAME".into(), "fromenv".into());

        let cfg = load_from(&env, &root).unwrap();
        assert_eq!(cfg.game, "fromenv");
        assert_eq!(cfg.root, root);
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn report_never_errors_when_empty() {
        let empty = tmpdir();
        let report = report_from(&HashMap::new(), &empty);
        assert!(!report.complete);
        assert!(report.entries.iter().any(|e| e.key == "ARGUS_ROOT" && e.value.is_none()));
        let _ = fs::remove_dir_all(&empty);
    }

    #[test]
    fn reads_config_needs_only_root() {
        let root = tmpdir();
        fs::create_dir_all(root.join("runs")).unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        assert_eq!(cfg.runs, root.join("runs"));
        let _ = fs::remove_dir_all(&root);
    }
}
