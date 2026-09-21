//! Identify the running lab build and refuse verdicts under source skew.

use std::path::Path;

use serde::Serialize;

use crate::config::Config;

pub const RUNNING_VERSION: &str = env!("CARGO_PKG_VERSION");
pub const BUILD_SOURCE: &str = env!("ARGUS_BUILD_SOURCE_FINGERPRINT");

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct LabIdentity {
    pub running_version: String,
    pub build_source: String,
    pub checkout_version: Option<String>,
    pub checkout_source: Option<String>,
    pub authoritative: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub warning: Option<String>,
}

fn checkout_version(manifest_dir: &Path) -> Result<String, String> {
    let path = manifest_dir.join("Cargo.toml");
    let text =
        std::fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?;
    let value: toml::Value =
        toml::from_str(&text).map_err(|error| format!("{}: {error}", path.display()))?;
    value
        .get("package")
        .and_then(|package| package.get("version"))
        .and_then(toml::Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| format!("{} has no package.version", path.display()))
}

fn inspect_dir(manifest_dir: &Path, running_version: &str, build_source: &str) -> LabIdentity {
    let version = checkout_version(manifest_dir).ok();
    let source = crate::source_fingerprint::fingerprint(manifest_dir).ok();
    let authoritative =
        version.as_deref() == Some(running_version) && source.as_deref() == Some(build_source);
    let warning = (!authoritative).then(|| {
        format!(
            "STALE LAB: running argus-mcp {running_version} ({build_source}) does not match checkout {} ({}). Quality-gate verdicts are refused. Run `cargo install --locked --path tools/argus_mcp --root tools/argus_mcp/install`, then restart the MCP client.",
            version.as_deref().unwrap_or("unreadable"),
            source.as_deref().unwrap_or("unreadable")
        )
    });
    LabIdentity {
        running_version: running_version.into(),
        build_source: build_source.into(),
        checkout_version: version,
        checkout_source: source,
        authoritative,
        warning,
    }
}

pub fn inspect(cfg: &Config) -> LabIdentity {
    inspect_dir(
        &cfg.root.join("tools").join("argus_mcp"),
        RUNNING_VERSION,
        BUILD_SOURCE,
    )
}

fn require_identity(identity: LabIdentity) -> Result<LabIdentity, String> {
    if identity.authoritative {
        Ok(identity)
    } else {
        Err(identity
            .warning
            .clone()
            .unwrap_or_else(|| "stale lab".into()))
    }
}

pub fn require_authoritative(cfg: &Config) -> Result<LabIdentity, String> {
    require_identity(inspect(cfg))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_checkout_matches_the_compiled_identity() {
        let identity = inspect_dir(
            Path::new(env!("CARGO_MANIFEST_DIR")),
            RUNNING_VERSION,
            BUILD_SOURCE,
        );
        assert!(identity.authoritative, "{identity:?}");
        assert!(identity.warning.is_none());
    }

    #[test]
    fn older_running_version_is_non_authoritative() {
        let identity = inspect_dir(
            Path::new(env!("CARGO_MANIFEST_DIR")),
            "0.29.0",
            BUILD_SOURCE,
        );
        assert!(!identity.authoritative);
        let refusal = require_identity(identity).unwrap_err();
        assert!(refusal.contains("0.29.0"));
        assert!(refusal.contains("Quality-gate verdicts are refused"));
        assert!(refusal.contains("cargo install --locked"));
    }

    #[test]
    fn different_source_fingerprint_is_non_authoritative() {
        let identity = inspect_dir(
            Path::new(env!("CARGO_MANIFEST_DIR")),
            RUNNING_VERSION,
            "fnv1a64:0000000000000000",
        );
        assert!(!identity.authoritative);
        assert!(identity
            .warning
            .unwrap()
            .contains("Quality-gate verdicts are refused"));
    }
}
