use crate::config::Config;
use crate::paths::{resolve_input, tail_lines};
use serde::Serialize;
use std::process::Command;

#[derive(Debug, Clone, Serialize)]
pub struct NavgenResult {
    pub ok: bool,
    pub out_qc: String,
    pub out_png: String,
    pub stdout_tail: Vec<String>,
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
        return Err(format!("ARGUS_ROOT tools/argus_navgen.py missing: {}", script.display()));
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
        stdout_tail: tail_lines(&text, 40),
    })
}
