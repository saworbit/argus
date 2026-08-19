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
        return;
    }
    let cfg = Config::load().expect("config should load when env is set");
    cfg.require_ready().expect("paths should exist");
    let report = Config::report();
    assert!(report.complete);
}

#[test]
fn compile_qc_when_env_set() {
    if !lab_configured() {
        return;
    }
    let cfg = Config::load().unwrap();
    cfg.require_ready().unwrap();
    let result = compile_qc(&cfg, true);
    assert!(result.ok, "compile failed: {result:?}");
    assert!(result.progs_bytes.unwrap_or(0) > 0);
    assert!(!result.installed_to.is_empty());
    for p in &result.installed_to {
        assert!(
            std::path::Path::new(p).exists(),
            "install path missing: {p}"
        );
    }
}
