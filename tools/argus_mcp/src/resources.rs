//! MCP resources: a client can open argus://project without a tool call.

use crate::cartograph::{atlas_brief, cartograph, list_maps};
use crate::config::Config;
use crate::intel::{brief_run, QUALITY_BARS};
use crate::lab::lab_status;
use crate::live::knobs;
use crate::project::{project_view, see_vocab};
use crate::qc_index::{index_argus, qc_read};
use crate::session::SessionSeen;
use rmcp::model::{
    ListResourceTemplatesResult, ListResourcesResult, Resource, ResourceContents, ResourceTemplate,
};
use serde::Serialize;

fn res(uri: &str, name: &str, title: &str, desc: &str) -> Resource {
    Resource::new(uri, name)
        .with_title(title)
        .with_description(desc)
        .with_mime_type("application/json")
}

/// Static catalogue plus any on-disk maps the cartographer already knows.
pub fn list_static(cfg: Option<&Config>) -> ListResourcesResult {
    let mut resources = vec![
        res(
            "argus://project",
            "project",
            "Argus project",
            "QC files, maps, how to see / adjust / test",
        ),
        res(
            "argus://lab",
            "lab",
            "Lab dashboard",
            "Config readiness, maps, recent runs, next call",
        ),
        res(
            "argus://knobs",
            "knobs",
            "Live knobs",
            "What can change without a recompile",
        ),
        res(
            "argus://last",
            "last",
            "Session last-seen",
            "Last map, function, run, experiment this process opened",
        ),
        res(
            "argus://quality",
            "quality",
            "Quality bars",
            "A/B bars this lab uses",
        ),
        res(
            "argus://help",
            "help",
            "Inspect vocabulary",
            "see what=... and resource URIs",
        ),
    ];
    if let Some(cfg) = cfg {
        if let Ok(maps) = list_maps(cfg) {
            for m in maps.into_iter().take(12) {
                resources.push(res(
                    &format!("argus://map/{}", m.name),
                    &m.name,
                    &format!("map {}", m.name),
                    "Cartographer brief",
                ));
            }
        }
    }
    ListResourcesResult::with_all_items(resources)
}

pub fn list_templates() -> ListResourceTemplatesResult {
    let tmpls = vec![
        ResourceTemplate::new("argus://map/{name}", "map")
            .with_title("Map atlas")
            .with_description("Cartographer brief. name is dm4, dm2, dm6, lqdm2.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://fn/{name}", "fn")
            .with_title("QuakeC function")
            .with_description("Full source of one Argus_ function.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://run/{name}", "run")
            .with_title("Harvested match")
            .with_description("Brief a log. name is a run (ab_dm4_parity) or latest.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://const/{name}", "const")
            .with_title("AR_* constant")
            .with_description("Substring match on compiled-in constants.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://path/{spec}", "path")
            .with_title("Nav route")
            .with_description("BFS. spec is dm4:56-72 or dm4:quad->lg.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://search/{needle}", "search")
            .with_title("QC search")
            .with_description("Grep Argus QuakeC.")
            .with_mime_type("application/json"),
    ];
    ListResourceTemplatesResult::with_all_items(tmpls)
}

fn json_text(uri: &str, value: &impl Serialize) -> ResourceContents {
    let text = serde_json::to_string_pretty(value).unwrap_or_else(|_| "{}".into());
    ResourceContents::text(text, uri).with_mime_type("application/json")
}

fn plain_text(uri: &str, text: impl Into<String>) -> ResourceContents {
    ResourceContents::text(text, uri)
}

pub fn read_uri(
    uri: &str,
    cfg: Option<&Config>,
    session: &SessionSeen,
) -> Result<Vec<ResourceContents>, String> {
    let uri = uri.trim();
    match uri {
        "argus://project" => {
            let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://project")?;
            Ok(vec![json_text(uri, &project_view(cfg))])
        }
        "argus://lab" => {
            let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://lab")?;
            Ok(vec![json_text(uri, &lab_status(cfg, None))])
        }
        "argus://knobs" => Ok(vec![json_text(uri, &knobs())]),
        "argus://last" => Ok(vec![json_text(uri, session)]),
        "argus://quality" => Ok(vec![plain_text(uri, QUALITY_BARS)]),
        "argus://help" => Ok(vec![json_text(uri, &see_vocab())]),
        other => {
            if let Some(name) = other.strip_prefix("argus://map/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://map")?;
                let atlas = cartograph(cfg, name)?;
                return Ok(vec![json_text(uri, &atlas_brief(&atlas))]);
            }
            if let Some(name) = other.strip_prefix("argus://fn/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://fn")?;
                let src = qc_read(cfg, name)?;
                return Ok(vec![json_text(uri, &src)]);
            }
            if let Some(name) = other.strip_prefix("argus://run/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://run")?;
                let brief = brief_run(cfg, name, None)?;
                return Ok(vec![json_text(uri, &brief)]);
            }
            if let Some(spec) = other.strip_prefix("argus://path/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://path")?;
                let route = crate::nav_graph::route_ref(cfg, spec)?;
                return Ok(vec![json_text(uri, &route)]);
            }
            if let Some(needle) = other.strip_prefix("argus://search/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://search")?;
                let hits = crate::qc_index::qc_search(cfg, needle, 24)?;
                return Ok(vec![json_text(uri, &hits)]);
            }
            if let Some(name) = other.strip_prefix("argus://const/") {
                let cfg = cfg.ok_or("ARGUS_ROOT is required for argus://const")?;
                let idx = index_argus(cfg)?;
                let q = name.to_ascii_lowercase();
                let hits: Vec<_> = idx
                    .constants
                    .into_iter()
                    .filter(|c| c.name.to_ascii_lowercase().contains(&q))
                    .collect();
                return Ok(vec![json_text(uri, &hits)]);
            }
            Err(format!(
                "unknown resource {other}; try argus://project or see what=help"
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lists_core_uris() {
        let listed = list_static(None);
        let uris: Vec<_> = listed.resources.iter().map(|r| r.uri.as_str()).collect();
        assert!(uris.contains(&"argus://project"));
        assert!(uris.contains(&"argus://knobs"));
        assert!(uris.contains(&"argus://last"));
    }

    #[test]
    fn reads_knobs_without_config() {
        let session = SessionSeen::default();
        let got = read_uri("argus://knobs", None, &session).unwrap();
        assert_eq!(got.len(), 1);
    }

    #[test]
    fn rejects_unknown() {
        let session = SessionSeen::default();
        assert!(read_uri("argus://nope", None, &session).is_err());
    }
}
