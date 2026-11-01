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

/// Resolve existing ancestors, including links, without creating the leaf.
/// Refuse parent traversal and dangling links rather than guessing their target.
pub(crate) fn canonical_target(path: &Path) -> Result<PathBuf, String> {
    use std::path::Component;
    if !path.is_absolute() || path.components().any(|c| c == Component::ParentDir) {
        return Err(format!(
            "expected absolute path without parent traversal: {}",
            path.display()
        ));
    }
    let mut ancestor = path;
    let mut missing = Vec::new();
    loop {
        match std::fs::canonicalize(ancestor) {
            Ok(mut resolved) => {
                for part in missing.iter().rev() {
                    resolved.push(part);
                }
                return Ok(native_path(resolved));
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                if std::fs::symlink_metadata(ancestor).is_ok() {
                    return Err(format!("unresolved link: {}", ancestor.display()));
                }
                missing.push(
                    ancestor
                        .file_name()
                        .ok_or_else(|| error.to_string())?
                        .to_os_string(),
                );
                ancestor = ancestor.parent().ok_or_else(|| error.to_string())?;
            }
            Err(error) => return Err(format!("resolve {}: {error}", ancestor.display())),
        }
    }
}

fn native_path(path: PathBuf) -> PathBuf {
    // canonicalize uses Win32 extended paths, which external tools need not
    // understand. Keep UNC paths as UNC and drive paths in their usual form.
    #[cfg(windows)]
    {
        let raw = path.as_os_str().to_string_lossy();
        if let Some(rest) = raw.strip_prefix(r"\\?\UNC\") {
            return PathBuf::from(format!(r"\\{rest}"));
        }
        if let Some(rest) = raw.strip_prefix(r"\\?\") {
            return PathBuf::from(rest);
        }
    }
    path
}

/// PNGs belong under ARGUS_RUNS; generated QC belongs under ARGUS_SRC.
/// Only the map's own generated files may replace tracked source.
pub fn resolve_output(
    cfg: &Config,
    given: &str,
    allowed: &Path,
    extension: &str,
    replace: Option<&Path>,
) -> Result<PathBuf, String> {
    let p = PathBuf::from(given);
    let p = if p.is_absolute() { p } else { cfg.root.join(p) };
    if p.extension().and_then(|v| v.to_str()) != Some(extension) {
        return Err(format!("output must have .{extension} extension"));
    }
    for leaf in [&p, &PathBuf::from(format!("{}.json", p.display()))] {
        match std::fs::symlink_metadata(leaf) {
            Ok(meta) if meta.file_type().is_symlink() => {
                return Err(format!("output cannot be a symlink: {}", leaf.display()))
            }
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(format!("inspect output {}: {e}", leaf.display())),
        }
    }
    let target = canonical_target(&p)?;
    let allowed = canonical_target(allowed)?;
    if target == allowed || !target.starts_with(&allowed) {
        return Err(format!("output must be under {}", allowed.display()));
    }
    let replace = replace.map(canonical_target).transpose()?;
    let root = canonical_target(&cfg.root)?;
    for candidate in [
        target.clone(),
        PathBuf::from(format!("{}.json", target.display())),
    ] {
        let resolved = canonical_target(&candidate)?;
        if !resolved.starts_with(&allowed) {
            return Err(format!("output sidecar escapes {}", allowed.display()));
        }
        let own = replace
            .as_ref()
            .is_some_and(|p| resolved == *p || resolved == format!("{}.json", p.display()));
        if own {
            continue;
        }
        if extension == "qc" && candidate.exists() {
            return Err(format!(
                "refusing to replace source {}",
                candidate.display()
            ));
        }
        if cfg.root.join(".git").exists() {
            if let Ok(rel) = resolved.strip_prefix(&root) {
                let mut command = std::process::Command::new("git");
                command
                    .arg("-C")
                    .arg(&cfg.root)
                    .args(["ls-files", "--error-unmatch", "--"])
                    .arg(rel);
                let output = crate::child_process::output_with_windows_loader_retry(&mut command)
                    .map_err(|e| format!("check tracked output: {e}"))?;
                match output.status.code() {
                    Some(0) => {
                        return Err(format!(
                            "refusing to replace tracked output {}",
                            candidate.display()
                        ))
                    }
                    Some(1) => {}
                    _ => {
                        return Err(format!(
                            "check tracked output: {}",
                            String::from_utf8_lossy(&output.stderr)
                        ))
                    }
                }
            }
        }
    }
    Ok(target)
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
    fn output_boundary_rejects_links_traversal_and_tracked_files() {
        let _gate = crate::test_support::git_test_lock();
        let dir = crate::test_support::TestDir::new("output-boundary").unwrap();
        let root = dir.path().join("repo");
        let outside = dir.path().join("outside");
        for p in [root.join("src"), root.join("runs"), outside.clone()] {
            std::fs::create_dir_all(p).unwrap();
        }
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            &root,
        )
        .unwrap();
        let own = cfg.src.join("argus_nav_dm4.qc");
        std::fs::write(&own, "nav").unwrap();
        std::fs::write(cfg.src.join("argus.qc"), "source").unwrap();
        std::fs::write(cfg.runs.join("kept.png"), "tracked").unwrap();
        crate::test_support::run_git(&root, &["init"]).unwrap();
        crate::test_support::run_git(&root, &["add", "src", "runs"]).unwrap();
        assert!(
            resolve_output(&cfg, "runs/kept.png", &cfg.runs, "png", None)
                .unwrap_err()
                .contains("tracked")
        );
        assert!(resolve_output(&cfg, "src/argus.qc", &cfg.src, "qc", Some(&own)).is_err());
        assert_eq!(
            resolve_output(&cfg, "src/argus_nav_dm4.qc", &cfg.src, "qc", Some(&own)).unwrap(),
            own
        );
        assert!(resolve_output(&cfg, "runs/../escape.png", &cfg.runs, "png", None).is_err());
        assert!(resolve_output(
            &cfg,
            outside.join("escape.png").to_str().unwrap(),
            &cfg.runs,
            "png",
            None
        )
        .is_err());
        let link = cfg.runs.join("escape");
        crate::test_support::directory_link(&outside, &link);
        assert!(resolve_output(&cfg, "runs/escape/new/image.png", &cfg.runs, "png", None).is_err());
        assert!(!outside.join("new").exists());
        std::fs::write(cfg.runs.join("receipt.png.json"), "tracked receipt").unwrap();
        crate::test_support::run_git(&root, &["add", "runs/receipt.png.json"]).unwrap();
        assert!(resolve_output(&cfg, "runs/receipt.png", &cfg.runs, "png", None).is_err());
        let normal = resolve_output(&cfg, "./runs//fresh.png", &cfg.runs, "png", None).unwrap();
        assert_eq!(normal, cfg.runs.join("fresh.png"));
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
