use crate::config::Config;
use crate::paths::{resolve_input, tail_lines};
use serde::Serialize;
use std::path::Path;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct NavgenResult {
    pub ok: bool,
    pub out_qc: String,
    pub out_png: String,
    pub preview_generated: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edict_budget: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub playability_gate: Option<String>,
    pub stdout_tail: Vec<String>,
}

fn edict_budget_line(output: &str) -> Option<String> {
    output
        .lines()
        .find(|line| line.starts_with("edict budget: status "))
        .map(str::to_owned)
}

fn playability_gate_line(output: &str) -> Option<String> {
    output
        .lines()
        .find(|line| line.starts_with("playability gate: status "))
        .map(str::to_owned)
}

/// A preview is current only when its receipt matches all three output files.
pub(crate) fn preview_generated(qc: &Path, png: &Path) -> bool {
    let verify = || -> Option<bool> {
        let receipt: serde_json::Value =
            serde_json::from_slice(&std::fs::read(format!("{}.json", png.display())).ok()?).ok()?;
        if receipt["schema"] != "nav-preview-v1" || receipt["generated"] != true {
            return Some(false);
        }
        for (key, path) in [
            ("qc_md5", qc.to_path_buf()),
            ("graph_md5", format!("{}.json", qc.display()).into()),
            ("png_md5", png.to_path_buf()),
        ] {
            let bytes = std::fs::read(path).ok()?;
            if bytes.is_empty() || receipt[key] != format!("{:x}", md5::compute(bytes)) {
                return Some(false);
            }
        }
        Some(true)
    };
    verify().unwrap_or(false)
}

pub fn nav_generate(
    cfg: &Config,
    bsp: &str,
    map: &str,
    out_qc: Option<&str>,
    out_png: Option<&str>,
    register: bool,
) -> Result<NavgenResult, String> {
    let bsp_path = resolve_input(cfg, bsp)?;
    let out_qc = match out_qc {
        Some(p) => crate::paths::resolve_output(cfg, p),
        None => cfg.src.join(format!("argus_nav_{map}.qc")),
    };
    let out_png = match out_png {
        Some(p) => crate::paths::resolve_output(cfg, p),
        None => cfg.runs.join(format!("nav_{map}.png")),
    };
    if let Some(parent) = out_qc.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Some(parent) = out_png.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    let script = cfg.navgen_script();
    if !script.exists() {
        return Err(format!(
            "ARGUS_ROOT tools/argus_navgen.py missing: {}",
            script.display()
        ));
    }

    let mut cmd = Command::new(&cfg.python);
    cmd.arg(&script)
        .arg(&bsp_path)
        .arg(map)
        .arg(&out_qc)
        .arg(&out_png)
        .arg("--no-dispatcher");
    if register {
        // Python-side --register wires progs.src and the dispatcher
        // idempotently (and itself implies --no-dispatcher)
        cmd.arg("--register");
    }
    let output = cmd
        .output()
        .map_err(|e| format!("failed to spawn ARGUS_PYTHON: {e}"))?;

    let mut text = String::from_utf8_lossy(&output.stdout).into_owned();
    if !output.stderr.is_empty() {
        text.push('\n');
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }
    Ok(NavgenResult {
        ok: output.status.success(),
        out_qc: out_qc.display().to_string(),
        out_png: out_png.display().to_string(),
        preview_generated: text
            .lines()
            .any(|line| line == format!("wrote {}", out_png.display()))
            && preview_generated(&out_qc, &out_png),
        edict_budget: edict_budget_line(&text),
        playability_gate: playability_gate_line(&text),
        stdout_tail: tail_lines(&text, 40),
    })
}

#[cfg(test)]
mod tests {
    use super::{edict_budget_line, playability_gate_line, preview_generated};

    #[test]
    fn previews_require_a_successful_receipt_and_matching_graph_and_image() {
        let dir = crate::test_support::TestDir::new("nav-preview").unwrap();
        let qc = dir.path().join("nav.qc");
        let graph = dir.path().join("nav.qc.json");
        let png = dir.path().join("nav.png");
        let receipt = dir.path().join("nav.png.json");
        for path in [&qc, &graph, &png] {
            std::fs::write(path, "fresh").unwrap();
        }
        // An existing image and unknown or unavailable receipts are insufficient.
        assert!(!preview_generated(&qc, &png));
        for value in [
            "broken",
            "{}",
            r#"{"schema":"nav-preview-v1","generated":false}"#,
        ] {
            std::fs::write(&receipt, value).unwrap();
            assert!(!preview_generated(&qc, &png));
        }
        let hash = format!("{:x}", md5::compute("fresh"));
        let state = serde_json::json!({"schema":"nav-preview-v1", "generated":true,
            "qc_md5":hash, "graph_md5":hash, "png_md5":hash});
        std::fs::write(&receipt, state.to_string()).unwrap();
        assert!(preview_generated(&qc, &png));
        for path in [&qc, &graph, &png] {
            std::fs::write(path, "changed").unwrap();
            assert!(!preview_generated(&qc, &png));
            std::fs::write(path, "fresh").unwrap();
        }
        std::fs::remove_file(&png).unwrap();
        assert!(!preview_generated(&qc, &png));
    }

    #[test]
    fn extracts_the_generator_edict_verdict_for_the_gui() {
        let output = "wrote map.qc\nedict budget: status tight; waypoints 260; live bsp entities 252 of 300; world and client slots 9; runtime reserve 60 for four bots and dynamic entities; total 581 of 600; slack 19\nregister: done\n";
        assert_eq!(
            edict_budget_line(output).as_deref(),
            Some("edict budget: status tight; waypoints 260; live bsp entities 252 of 300; world and client slots 9; runtime reserve 60 for four bots and dynamic entities; total 581 of 600; slack 19")
        );
    }

    #[test]
    fn extracts_the_registration_playability_verdict_for_the_gui() {
        let output = "wrote map.qc\nplayability gate: status experimental; spawns 4; deathmatch pickups 18; graph md5 abc123\nregister: skipped because reach and mill evidence are incomplete\n";
        assert_eq!(
            playability_gate_line(output).as_deref(),
            Some("playability gate: status experimental; spawns 4; deathmatch pickups 18; graph md5 abc123")
        );
    }
}
