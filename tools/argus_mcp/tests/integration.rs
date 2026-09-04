//! Gated lab checks. Ignored unless the required env is present.

use argus_mcp::compile::compile_qc;
use argus_mcp::config::Config;

fn lab_configured() -> bool {
    ["ARGUS_ROOT", "ARGUS_FTEQCC", "ARGUS_ENGINE", "ARGUS_BASEDIR", "ARGUS_PYTHON"]
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
