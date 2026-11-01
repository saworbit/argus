//! Failures shared by MCP inspection surfaces. Never classify error prose.

use crate::config::Config;
use rmcp::{
    model::{CallToolResult, ContentBlock},
    ErrorData,
};
use serde::Serialize;

#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Kind {
    NotFound,
    BadArgs,
    Unconfigured,
    Internal,
}

#[derive(Clone, Debug)]
pub struct Failure {
    pub kind: Kind,
    pub error: String,
}

impl Failure {
    pub fn new(kind: Kind, error: impl Into<String>) -> Self {
        Self {
            kind,
            error: error.into(),
        }
    }
    pub fn bad(error: impl Into<String>) -> Self {
        Self::new(Kind::BadArgs, error)
    }
    pub fn missing(error: impl Into<String>) -> Self {
        Self::new(Kind::NotFound, error)
    }
    pub fn config(error: impl std::fmt::Display) -> Self {
        Self::new(Kind::Unconfigured, error.to_string())
    }
    pub fn body(&self) -> serde_json::Value {
        let hint = match self.kind {
            Kind::Unconfigured => "config_check, then set ARGUS_ROOT or ARGUS_MCP_CONFIG",
            Kind::Internal => "check the named file and lab diagnostics; see what=lab",
            Kind::NotFound | Kind::BadArgs => "see what=help for names and resource templates",
        };
        serde_json::json!({"error": self.error, "hint": hint, "kind": self.kind})
    }
    pub fn resource(self) -> ErrorData {
        let data = Some(self.body());
        match self.kind {
            Kind::NotFound => ErrorData::resource_not_found(self.error, data),
            Kind::BadArgs => ErrorData::invalid_params(self.error, data),
            Kind::Unconfigured | Kind::Internal => ErrorData::internal_error(self.error, data),
        }
    }
    pub fn prompt(mut self) -> ErrorData {
        if self.kind == Kind::NotFound {
            self.kind = Kind::BadArgs;
        }
        self.resource()
    }
    pub fn tool(self) -> CallToolResult {
        CallToolResult::error(vec![ContentBlock::text(self.body().to_string())])
    }
}
impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.error.fmt(f)
    }
}
impl From<String> for Failure {
    fn from(error: String) -> Self {
        Self::new(Kind::Internal, error)
    }
}
impl From<&str> for Failure {
    fn from(error: &str) -> Self {
        Self::from(error.to_owned())
    }
}

pub fn read_config() -> Result<Config, Failure> {
    checked_config(Config::load_for_reads().map_err(Failure::config)?)
}
pub fn checked_config(cfg: Config) -> Result<Config, Failure> {
    if !cfg.root.is_dir() {
        return Err(Failure::config(format!(
            "ARGUS_ROOT is not a directory: {}",
            cfg.root.display()
        )));
    }
    Ok(cfg)
}

pub fn map(cfg: &Config, name: &str) -> Result<crate::cartograph::MapAtlas, Failure> {
    if name.trim().is_empty() {
        return Err(Failure::bad("map name is empty"));
    }
    inspect_candidates(&[
        name.into(),
        cfg.root.join(name),
        cfg.maps.join(name),
        cfg.maps
            .join(format!("{}.bsp", name.trim().to_ascii_lowercase())),
    ])?;
    // Direct paths remain supported. A catalog match includes PAK-only maps.
    let base = std::path::Path::new(name)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(name)
        .to_ascii_lowercase();
    let base = base.strip_suffix(".bsp").unwrap_or(&base);
    if crate::paths::resolve_input(cfg, name).is_err()
        && !crate::cartograph::list_maps(cfg)?
            .iter()
            .any(|m| m.name.eq_ignore_ascii_case(base))
    {
        return Err(Failure::missing(format!("BSP not found: {name}")));
    }
    crate::cartograph::cartograph(cfg, name).map_err(Into::into)
}

pub fn run(cfg: &Config, name: &str, map: Option<&str>) -> Result<std::path::PathBuf, Failure> {
    let name = name.trim();
    if name.is_empty() {
        return Err(Failure::bad("run name is empty"));
    }
    if !["latest", "baseline", "shipped"]
        .iter()
        .any(|s| name.eq_ignore_ascii_case(s))
    {
        inspect_candidates(&[
            name.into(),
            cfg.root.join(name),
            cfg.maps.join(name),
            cfg.runs.join(name),
            cfg.runs.join(format!("{name}.log")),
        ])?;
    }
    if name.eq_ignore_ascii_case("latest") {
        match std::fs::read_dir(&cfg.runs) {
            Ok(entries) => {
                for entry in entries {
                    entry.map_err(|e| Failure::from(e.to_string()))?;
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                return Err(Failure::missing("no runs directory"))
            }
            Err(e) => return Err(Failure::from(format!("{}: {e}", cfg.runs.display()))),
        }
    }
    if (name.eq_ignore_ascii_case("baseline") || name.eq_ignore_ascii_case("shipped"))
        && map.is_none()
    {
        return Err(Failure::bad(
            "baseline requires a map or a candidate log with a map header",
        ));
    }
    crate::intel::resolve_run_ref(cfg, name, map).map_err(Failure::missing)
}

fn inspect_candidates(paths: &[std::path::PathBuf]) -> Result<(), Failure> {
    for path in paths {
        match std::fs::metadata(path) {
            Ok(meta) if !meta.is_file() => {
                return Err(format!("not a file: {}", path.display()).into())
            }
            Ok(_) => return Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(format!("{}: {e}", path.display()).into()),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rmcp::model::ErrorCode;

    #[test]
    fn configuration_errors_have_one_payload_on_three_surfaces() {
        let failure = Failure::config("missing ARGUS_ROOT");
        let prompt = failure.clone().prompt();
        let resource = failure.clone().resource();
        let tool = failure.tool();
        assert_eq!(prompt.code, ErrorCode::INTERNAL_ERROR);
        assert_eq!(resource.code, ErrorCode::INTERNAL_ERROR);
        assert_eq!(prompt.data, resource.data);
        assert_eq!(tool.is_error, Some(true));
        let text = tool.content[0].as_text().unwrap();
        let body: serde_json::Value = serde_json::from_str(&text.text).unwrap();
        assert_eq!(Some(body.clone()), resource.data);
        assert_eq!(body["kind"], "unconfigured");
        assert!(body["hint"].as_str().unwrap().contains("ARGUS_ROOT"));
    }

    #[test]
    fn missing_targets_and_bad_arguments_are_distinct_from_internal_errors() {
        assert_eq!(
            Failure::missing("absent").resource().code,
            ErrorCode::RESOURCE_NOT_FOUND
        );
        assert_eq!(
            Failure::missing("absent").prompt().code,
            ErrorCode::INVALID_PARAMS
        );
        assert_eq!(
            Failure::bad("wrong shape").resource().code,
            ErrorCode::INVALID_PARAMS
        );
        assert_eq!(
            Failure::from("corrupt JSON").resource().code,
            ErrorCode::INTERNAL_ERROR
        );
    }
}
