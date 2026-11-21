use std::process::{Command, Output};

fn cli(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_argus-mcp"))
        .args(args)
        .env("ARGUS_FTEQCC", "missing-compiler")
        .output()
        .expect("run argus-mcp")
}

#[test]
fn benchmark_rejects_invalid_options_before_loading_the_suite_or_compiling() {
    for (args, expected) in [
        (&["benchmark"][..], "benchmark requires a suite path"),
        (
            &["benchmark", "--no-compile"][..],
            "benchmark requires a suite path",
        ),
        (
            &["benchmark", "missing-suite.json", "--no-compille"][..],
            "unknown benchmark option: --no-compille",
        ),
        (
            &["benchmark", "missing-suite.json", "0"][..],
            "benchmark limit must be at least 1",
        ),
    ] {
        let output = cli(args);
        assert_eq!(output.status.code(), Some(1));
        assert!(output.stdout.is_empty());
        assert_eq!(
            String::from_utf8_lossy(&output.stderr).trim(),
            format!("Error: {expected}")
        );
    }
}

#[test]
fn match_help_uses_the_current_duration_limits() {
    use argus_mcp::match_ctrl::{DURATION_MAX, DURATION_MIN};

    let output = cli(&["match", "--help"]);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stdout)
        .contains(&format!("{DURATION_MIN}..={DURATION_MAX} seconds")));
}

#[test]
fn identity_reports_matching_and_stale_checkouts_without_a_compiler() {
    use argus_mcp::build_identity::{BUILD_SOURCE, RUNNING_VERSION};
    use std::path::Path;

    let checkout = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    for (root, expected_authoritative) in
        [(checkout.clone(), true), (checkout.join("missing"), false)]
    {
        let output = Command::new(env!("CARGO_BIN_EXE_argus-mcp"))
            .args(["identity", "--json"])
            .env("ARGUS_ROOT", root)
            .env("ARGUS_FTEQCC", "missing-compiler")
            .output()
            .expect("run argus-mcp");
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        let identity: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(identity["running_version"], RUNNING_VERSION);
        assert_eq!(identity["build_source"], BUILD_SOURCE);
        assert_eq!(identity["authoritative"], expected_authoritative);
        if expected_authoritative {
            assert_eq!(identity["checkout_version"], RUNNING_VERSION);
            assert_eq!(identity["checkout_source"], BUILD_SOURCE);
        } else {
            assert!(identity["checkout_version"].is_null());
            assert!(identity["checkout_source"].is_null());
            assert!(identity["warning"].as_str().unwrap().contains("--force"));
        }
    }
}
