use crate::config::Config;
use crate::paths::{resolve_input, tail_lines};
use crate::python_helper::{self, Outputs, NAV_DEADLINE};
use serde::Serialize;
use std::path::Path;

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

pub async fn nav_generate(
    cfg: &Config,
    bsp: &str,
    map: &str,
    out_qc: Option<&str>,
    out_png: Option<&str>,
    register: bool,
) -> Result<NavgenResult, String> {
    let map = crate::paths::map_name(map)?;
    let map = map.as_str();
    let bsp_path = resolve_input(cfg, bsp)?;
    let own_qc = cfg.src.join(format!("argus_nav_{map}.qc"));
    let default_png = cfg.runs.join(format!("nav_{map}.png"));
    let out_qc = crate::paths::resolve_output(
        cfg,
        out_qc.unwrap_or(&own_qc.to_string_lossy()),
        &cfg.src,
        "qc",
        Some(&own_qc),
    )?;
    let out_png = crate::paths::resolve_output(
        cfg,
        out_png.unwrap_or(&default_png.to_string_lossy()),
        &cfg.runs,
        "png",
        None,
    )?;
    if register && out_qc != crate::paths::canonical_target(&own_qc)? {
        return Err("registration requires the map's default ARGUS_SRC output".into());
    }
    let script = cfg.navgen_script();
    if !script.exists() {
        return Err(format!(
            "ARGUS_ROOT tools/argus_navgen.py missing: {}",
            script.display()
        ));
    }
    // A failed child must not reuse an earlier successful receipt.
    let receipt = format!("{}.json", out_png.display());
    match std::fs::remove_file(&receipt) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(format!("invalidate preview receipt: {error}")),
    }
    if let Some(parent) = out_qc.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("create QC output directory: {e}"))?;
    }
    if let Some(parent) = out_png.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("create PNG output directory: {e}"))?;
    }

    let mut files = Outputs::new()?;
    let staged_qc = files.add(&out_qc, true)?;
    files.add(
        &std::path::PathBuf::from(format!("{}.json", out_qc.display())),
        true,
    )?;
    let staged_png = files.add(&out_png, false)?;
    files.add(&std::path::PathBuf::from(&receipt), false)?;
    for kind in ["costs", "probe", "proven", "mined"] {
        let input = out_qc
            .parent()
            .unwrap()
            .join(format!("argus_nav_{map}.{kind}.json"));
        if kind == "mined" {
            files.add(&input, false)?;
        }
        files.input(&input)?;
    }
    if register {
        for name in ["progs.src", "argus_nav_dispatch.qc"] {
            let input = cfg.src.join(name);
            files.add(&input, input.exists())?;
            files.input(&input)?;
        }
    }
    let mut args = vec![
        bsp_path.as_path(),
        Path::new(map),
        staged_qc.as_path(),
        staged_png.as_path(),
        Path::new("--no-dispatcher"),
    ];
    if register {
        args.push(Path::new("--register"));
    }
    let output = python_helper::run(cfg, &script, &args, NAV_DEADLINE).await?;
    if output.status.success() {
        files.publish()?;
    }

    let mut text = String::from_utf8_lossy(&output.stdout).into_owned();
    if !output.stderr.is_empty() {
        text.push('\n');
        text.push_str(&String::from_utf8_lossy(&output.stderr));
    }
    Ok(NavgenResult {
        ok: output.status.success(),
        out_qc: out_qc.display().to_string(),
        out_png: out_png.display().to_string(),
        preview_generated: output.status.success() && preview_generated(&out_qc, &out_png),
        edict_budget: edict_budget_line(&text),
        playability_gate: playability_gate_line(&text),
        stdout_tail: tail_lines(&text, 40),
    })
}

#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn cancelled_generation_cannot_publish_source_or_registration() {
        let dir = crate::test_support::TestDir::new("nav-cancel").unwrap();
        let root = dir.path();
        for name in ["src", "tools", "runs"] {
            std::fs::create_dir(root.join(name)).unwrap();
        }
        std::fs::write(root.join("map.bsp"), "bsp").unwrap();
        let mut saved = Vec::new();
        for name in [
            "argus_nav_dm4.qc",
            "argus_nav_dm4.qc.json",
            "argus_nav_dm4.mined.json",
            "progs.src",
            "argus_nav_dispatch.qc",
        ] {
            let path = root.join("src").join(name);
            std::fs::write(&path, "original").unwrap();
            saved.push(path);
        }
        std::fs::write(root.join("tools/argus_navgen.py"), r#"import sys,pathlib,time
qc,png=map(pathlib.Path,sys.argv[3:5])
for name in (qc.name,qc.name+'.json','argus_nav_dm4.mined.json','progs.src','argus_nav_dispatch.qc'):
    (qc.parent/name).write_text('partial')
(pathlib.Path(__file__).parent/'started').write_text(str(qc.parent))
time.sleep(2)
qc.write_text('orphan')
"#).unwrap();
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            root,
        )
        .unwrap();
        assert!(
            cfg.python.is_file(),
            "Python required for cancellation regression"
        );
        let work = tokio::spawn(async move {
            super::nav_generate(&cfg, "map.bsp", "dm4", None, None, true).await
        });
        let marker = root.join("tools/started");
        tokio::time::timeout(std::time::Duration::from_secs(5), async {
            while !marker.exists() {
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        let staged = std::path::PathBuf::from(std::fs::read_to_string(marker).unwrap());
        assert!(!staged.starts_with(root));
        work.abort();
        assert!(work.await.unwrap_err().is_cancelled());
        for path in saved {
            assert_eq!(std::fs::read_to_string(path).unwrap(), "original");
        }
        tokio::time::sleep(std::time::Duration::from_millis(2200)).await;
        assert!(!staged.exists(), "private workspace survived cancellation");
    }

    #[tokio::test]
    async fn preview_receipt_is_authoritative_and_must_be_from_this_invocation() {
        let dir = crate::test_support::TestDir::new("nav-receipt-paths").unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join("tools")).unwrap();
        std::fs::write(root.join("map.bsp"), "bsp").unwrap();
        let script = root.join("tools/argus_navgen.py");
        std::fs::write(&script, r#"import sys, pathlib, hashlib, json
qc, png = map(pathlib.Path, sys.argv[3:5])
graph = pathlib.Path(str(qc) + '.json')
for p in (qc, graph, png): p.write_bytes(b'fresh')
h = hashlib.md5(b'fresh').hexdigest()
pathlib.Path(str(png) + '.json').write_text(json.dumps(dict(schema='nav-preview-v1', generated=True, qc_md5=h, graph_md5=h, png_md5=h)))
print('preview ready')
"#).unwrap();
        let mut cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            root,
        )
        .unwrap();
        if !cfg.python.is_file() {
            eprintln!("SKIPPED nav receipt subprocess: no discovered Python");
            return;
        }
        for spelling in [
            "runs/nav_dm4.png",
            "./runs/nav_dm4.png",
            "runs//nav_dm4.png",
        ] {
            let result = super::nav_generate(&cfg, "map.bsp", " DM4 ", None, Some(spelling), false)
                .await
                .unwrap();
            assert!(result.ok && result.preview_generated, "{result:?}");
        }
        // Success without a new receipt and spawn failure cannot reuse one.
        std::fs::write(&script, "import sys,pathlib\nqc=pathlib.Path(sys.argv[3])\nqc.write_bytes(b'fresh')\npathlib.Path(str(qc)+'.json').write_bytes(b'fresh')\nprint('no preview this run')").unwrap();
        let result = super::nav_generate(&cfg, "map.bsp", "dm4", None, None, false)
            .await
            .unwrap();
        assert!(result.ok && !result.preview_generated, "{result:?}");
        cfg.python = root.join("missing-python");
        assert!(
            super::nav_generate(&cfg, "map.bsp", "dm4", None, None, false)
                .await
                .is_err()
        );
    }
    #[tokio::test]
    async fn rejects_bad_names_and_outputs_before_starting_python() {
        let dir = crate::test_support::TestDir::new("nav-output").unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join("tools")).unwrap();
        std::fs::write(root.join("map.bsp"), "bsp").unwrap();
        std::fs::write(
            root.join("tools/argus_navgen.py"),
            "raise RuntimeError('must not run')",
        )
        .unwrap();
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([("ARGUS_ROOT".into(), root.display().to_string())]),
            root,
        )
        .unwrap();
        for (map, qc, png) in [
            ("../escape", None, None),
            ("bad\"name", None, None),
            ("dispatch", None, None),
            ("my-map", None, None),
            ("dm4", Some("../outside.qc"), None),
            ("dm4", Some("tools/argus_navgen.py"), None),
            ("dm4", None, Some("runs/../tape.log")),
        ] {
            let error = super::nav_generate(&cfg, "map.bsp", map, qc, png, false)
                .await
                .unwrap_err();
            assert!(
                !error.contains("spawn ARGUS_PYTHON"),
                "validation was bypassed: {error}"
            );
            assert!(
                !root.join("src").exists(),
                "validation created an output directory"
            );
            assert!(
                !root.join("runs").exists(),
                "validation created an output directory"
            );
        }
    }
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
