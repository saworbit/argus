//! Register generated argus_nav_<map>.qc in the dispatcher and progs.src.

use crate::config::Config;
use serde::Serialize;
use std::fs;

fn require_playable_first_registration(cfg: &Config, map: &str) -> Result<(), String> {
    let bsp = cfg.maps.join(format!("{map}.bsp"));
    let graph = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    if !bsp.is_file() || !graph.is_file() {
        return Err(format!(
            "{map} is experimental: need {} and {} before registration",
            bsp.display(),
            graph.display()
        ));
    }
    let script = cfg.root.join("tools").join("argus_mapgate.py");
    if !script.is_file() || !cfg.python.is_file() {
        return Err(format!(
            "{map} is experimental: the playability gate needs ARGUS_PYTHON"
        ));
    }
    let output = std::process::Command::new(&cfg.python)
        .arg(script)
        .arg(&bsp)
        .arg(&graph)
        .output()
        .map_err(|e| format!("{map} playability gate: {e}"))?;
    if output.status.success() {
        return Ok(());
    }
    let stdout = String::from_utf8_lossy(&output.stdout);
    let reason = stdout
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>()
        .join("; ");
    Err(format!("{map} is experimental: {reason}"))
}

#[derive(Debug, Clone, Serialize)]
pub struct NavSyncReport {
    pub ok: bool,
    pub maps: Vec<String>,
    pub added_dispatch: Vec<String>,
    pub added_progs: Vec<String>,
    pub already: Vec<String>,
    pub headline: String,
}

pub fn nav_sync_dispatch(cfg: &Config) -> Result<NavSyncReport, String> {
    let mut maps = Vec::new();
    let rd = fs::read_dir(&cfg.src).map_err(|e| format!("ARGUS_SRC: {e}"))?;
    for ent in rd.flatten() {
        let name = ent.file_name().to_string_lossy().into_owned();
        if let Some(map) = name
            .strip_prefix("argus_nav_")
            .and_then(|s| s.strip_suffix(".qc"))
        {
            if map == "dispatch" || map.contains('.') {
                continue;
            }
            if map.chars().all(|c| c.is_ascii_alphanumeric() || c == '_') {
                maps.push(map.to_string());
            }
        }
    }
    maps.sort();
    if maps.is_empty() {
        return Err("no argus_nav_<map>.qc files under ARGUS_SRC".into());
    }

    let mut added_dispatch = Vec::new();
    let mut added_progs = Vec::new();
    let mut already = Vec::new();

    let disp_path = cfg.src.join("argus_nav_dispatch.qc");
    let mut disp =
        fs::read_to_string(&disp_path).map_err(|e| format!("{}: {e}", disp_path.display()))?;
    let progs_path = cfg.src.join("progs.src");
    let mut progs =
        fs::read_to_string(&progs_path).map_err(|e| format!("{}: {e}", progs_path.display()))?;

    for map in &maps {
        let branch = format!("mapname == \"{map}\"");
        let spawn = format!("Argus_Nav_Spawn_{map}");
        let has_branch = disp.contains(&branch);
        let qc_line = format!("argus_nav_{map}.qc");
        let has_qc = progs.contains(&qc_line);
        if !(has_branch && has_qc) {
            require_playable_first_registration(cfg, map)?;
        }
        if has_branch {
            already.push(map.clone());
        } else {
            disp = insert_dispatch_branch(&disp, map, &spawn)?;
            added_dispatch.push(map.clone());
        }
        if !has_qc {
            progs = insert_progs_line(&progs, &qc_line)?;
            added_progs.push(map.clone());
        }
    }

    if !added_dispatch.is_empty() {
        fs::write(&disp_path, disp).map_err(|e| format!("write dispatch: {e}"))?;
    }
    if !added_progs.is_empty() {
        fs::write(&progs_path, progs).map_err(|e| format!("write progs.src: {e}"))?;
    }

    let headline = if added_dispatch.is_empty() && added_progs.is_empty() {
        format!("dispatcher already covers {}", maps.join(", "))
    } else {
        format!(
            "registered {} dispatch branch(es), {} progs.src line(s)",
            added_dispatch.len(),
            added_progs.len()
        )
    };
    Ok(NavSyncReport {
        ok: true,
        maps,
        added_dispatch,
        added_progs,
        already,
        headline,
    })
}

fn insert_dispatch_branch(src: &str, map: &str, spawn: &str) -> Result<String, String> {
    // Insert before the closing `};` of Argus_Nav_Spawn.
    let needle = "};";
    let Some(idx) = src.rfind(needle) else {
        return Err("argus_nav_dispatch.qc: no closing };".into());
    };
    let indent = "    ";
    let branch = format!("{indent}else if (mapname == \"{map}\")\n{indent}    {spawn} ();\n");
    let mut out = String::new();
    out.push_str(&src[..idx]);
    out.push_str(&branch);
    out.push_str(&src[idx..]);
    Ok(out)
}

fn insert_progs_line(src: &str, qc_line: &str) -> Result<String, String> {
    if let Some(idx) = src.find("argus_nav_dispatch.qc") {
        let mut out = String::new();
        out.push_str(&src[..idx]);
        out.push_str(qc_line);
        out.push('\n');
        out.push_str(&src[idx..]);
        return Ok(out);
    }
    Err("progs.src has no argus_nav_dispatch.qc line to insert before".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inserts_branch_before_close() {
        let src = "void() Argus_Nav_Spawn =\n{\n    if (mapname == \"dm4\")\n        Argus_Nav_Spawn_dm4 ();\n};\n";
        let out = insert_dispatch_branch(src, "e1m1", "Argus_Nav_Spawn_e1m1").unwrap();
        assert!(out.contains("mapname == \"e1m1\""));
        assert!(out.contains("Argus_Nav_Spawn_e1m1"));
        assert!(out.find("e1m1").unwrap() < out.rfind("};").unwrap());
    }

    #[test]
    fn inserts_progs_before_dispatch() {
        let src = "argus_nav_dm4.qc\nargus_nav_dispatch.qc\nargus.qc\n";
        let out = insert_progs_line(src, "argus_nav_e1m1.qc").unwrap();
        assert!(out.contains("argus_nav_e1m1.qc\nargus_nav_dispatch.qc"));
    }

    #[test]
    fn sync_does_not_bypass_the_first_registration_gate() {
        let temp = std::env::temp_dir().join(format!("argus-nav-sync-gate-{}", std::process::id()));
        let _ = fs::remove_dir_all(&temp);
        let src = temp.join("src");
        let maps = temp.join("maps");
        fs::create_dir_all(&src).unwrap();
        fs::create_dir_all(&maps).unwrap();
        fs::write(src.join("argus_nav_newmap.qc"), "fixture").unwrap();
        fs::write(
            src.join("argus_nav_newmap.qc.json"),
            r#"{"nodes": [], "links": []}"#,
        )
        .unwrap();
        fs::write(
            src.join("argus_nav_dispatch.qc"),
            "void() Argus_Nav_Spawn =\n{\n};\n",
        )
        .unwrap();
        fs::write(src.join("progs.src"), "argus_nav_dispatch.qc\n").unwrap();
        let mut cfg = Config::load_for_reads().expect("repo config");
        cfg.src = src.clone();
        cfg.maps = maps;

        let err = nav_sync_dispatch(&cfg).unwrap_err();

        assert!(err.contains("newmap is experimental"), "{err}");
        assert!(!fs::read_to_string(src.join("progs.src"))
            .unwrap()
            .contains("argus_nav_newmap.qc"));
        let _ = fs::remove_dir_all(&temp);
    }
}
