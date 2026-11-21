//! Gated lab checks. Ignored unless the required env is present.

use argus_mcp::compile::compile_qc;
use argus_mcp::config::Config;

fn lab_configured() -> bool {
    [
        "ARGUS_ROOT",
        "ARGUS_FTEQCC",
        "ARGUS_ENGINE",
        "ARGUS_BASEDIR",
        "ARGUS_PYTHON",
    ]
    .iter()
    .all(|k| std::env::var(k).map(|v| !v.is_empty()).unwrap_or(false))
}

#[test]
fn config_check_when_env_set() {
    if !lab_configured() {
        eprintln!("SKIPPED config_loads_when_env_set: ARGUS_* env not set");
        return;
    }
    let cfg = Config::load().expect("config should load when env is set");
    cfg.require_ready().expect("paths should exist");
    let report = Config::report();
    assert!(report.complete);
}

// A test run must not change the shipped build. This used to call
// compile_qc(install = true), which copies into game/argus, the basedir
// game dir and the rerelease Saved Games dir, so `cargo test` on a
// configured box installed whatever happened to be in the working tree.
#[test]
fn compile_qc_when_env_set() {
    if !lab_configured() {
        eprintln!("SKIPPED compile_qc_when_env_set: ARGUS_* env not set");
        return;
    }
    let mut cfg = Config::load().unwrap();
    cfg.require_ready().unwrap();
    let tmp = std::env::temp_dir().join(format!("argus-it-compile-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&tmp);
    std::fs::create_dir_all(&tmp).unwrap();
    cfg.progs = tmp.join("progs.dat");
    let result = compile_qc(&cfg, false);
    assert!(result.ok, "compile failed: {result:?}");
    assert!(result.progs_bytes.unwrap_or(0) > 0);
    assert!(
        result.installed_to.is_empty(),
        "install = false must copy nowhere, got {:?}",
        result.installed_to
    );
    let _ = std::fs::remove_dir_all(&tmp);
}

#[test]
#[ignore = "requires a configured compiler, Quake engine and registered Quake PAKs"]
fn campaign_stdout_is_one_json_document_with_or_without_compile() {
    use std::fs;
    use std::net::UdpSocket;
    use std::path::{Path, PathBuf};
    use std::process::Command;

    struct TestRoot(PathBuf);
    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    let cfg = Config::load().expect("configured lab");
    cfg.require_ready().unwrap();
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let name = format!("argus-campaign-json-{}", std::process::id());
    let root = std::env::temp_dir().join(&name);
    fs::create_dir(&root).unwrap();
    let root = TestRoot(root);
    let base = root.0.join("engine");
    let game = base.join(&name);
    fs::create_dir_all(base.join("id1")).unwrap();
    fs::create_dir(&game).unwrap();
    for pak in ["id1/pak0.pak", "id1/pak1.pak"] {
        fs::copy(cfg.basedir.join(pak), base.join(pak)).unwrap();
    }
    for dir in ["src", "src/lq1", "src/monsters"] {
        fs::create_dir(root.0.join(dir)).unwrap();
        for entry in fs::read_dir(source.join(dir)).unwrap() {
            let entry = entry.unwrap();
            if entry.file_type().unwrap().is_file() {
                fs::copy(entry.path(), root.0.join(dir).join(entry.file_name())).unwrap();
            }
        }
    }
    for file in ["autoexec.cfg", "progs.dat"] {
        fs::copy(source.join("game/argus").join(file), game.join(file)).unwrap();
    }

    for compile in [false, true] {
        let port = UdpSocket::bind("127.0.0.1:0")
            .unwrap()
            .local_addr()
            .unwrap()
            .port();
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_argus-mcp"));
        cmd.current_dir(&root.0)
            .env("ARGUS_ROOT", &root.0)
            .env("ARGUS_SRC", root.0.join("src"))
            .env("ARGUS_MAPS", root.0.join("maps"))
            .env("ARGUS_PROGS", root.0.join("lq1/progs.dat"))
            .env("ARGUS_RUNS", root.0.join("runs"))
            .env("ARGUS_BASEDIR", &base)
            .env("ARGUS_GAME", &name)
            .env("ARGUS_ENGINE", &cfg.engine)
            .env("ARGUS_FTEQCC", &cfg.fteqcc)
            .env("ARGUS_PYTHON", &cfg.python)
            .args(["campaign", "e1m1", "--json", "--duration", "10", "--port"])
            .arg(port.to_string());
        if !compile {
            cmd.arg("--no-compile");
        }
        let output = cmd.output().unwrap();
        let stderr = String::from_utf8_lossy(&output.stderr);
        let report: argus_mcp::campaign::CampaignReport = serde_json::from_slice(&output.stdout)
            .unwrap_or_else(|err| {
                panic!(
                    "{err}; campaign stderr: {stderr}; stdout: {:?}",
                    String::from_utf8_lossy(&output.stdout)
                )
            });
        assert_eq!(report.map, "e1m1");
        assert_ne!(
            report.fail_reason,
            Some(argus_mcp::campaign::CampaignFailReason::KeyUnclaimed)
        );
        assert_eq!(output.status.code(), Some(i32::from(!report.ok)));
        assert!(stderr.contains("Running campaign match"));
        assert_eq!(stderr.contains("Compiling QuakeC"), compile);
    }
}
