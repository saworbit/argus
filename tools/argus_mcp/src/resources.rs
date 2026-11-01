//! MCP resources: a client can open argus://project without a tool call.

use crate::cartograph::{atlas_brief, list_maps};
use crate::config::Config;
use crate::inspection_error::Failure;
use crate::intel::{brief_run, QUALITY_BARS};
use crate::lab::lab_status;
use crate::live::knobs;
use crate::match_ctrl::list_runs;
use crate::project::{project_view, see_vocab};
use crate::qc_index::{index_argus, qc_read};
use crate::session::SessionSeen;
use rmcp::model::{
    ListResourceTemplatesResult, ListResourcesResult, Resource, ResourceContents, ResourceTemplate,
};
use serde::Serialize;

#[derive(Serialize)]
struct Catalog<T> {
    kind: &'static str,
    aliases: Vec<&'static str>,
    values: T,
}

#[derive(Serialize)]
struct BaselineCatalogEntry {
    map: String,
    runs: Vec<String>,
}

fn extensionless(name: &str) -> String {
    name.strip_suffix(".log").unwrap_or(name).to_string()
}

fn map_catalog(cfg: &Config) -> Result<Catalog<Vec<String>>, String> {
    let values = list_maps(cfg)?.into_iter().map(|map| map.name).collect();
    Ok(Catalog {
        kind: "maps",
        aliases: Vec::new(),
        values,
    })
}

fn run_catalog(cfg: &Config) -> Result<Catalog<Vec<String>>, String> {
    let mut values: Vec<String> = list_runs(cfg)?
        .into_iter()
        .map(|run| extensionless(&run.name))
        .collect();
    values.sort_by_key(|run| run.to_ascii_lowercase());
    values.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    Ok(Catalog {
        kind: "runs",
        aliases: vec!["latest"],
        values,
    })
}

fn baseline_catalog(cfg: &Config) -> Catalog<Vec<BaselineCatalogEntry>> {
    let values = crate::intel::all_baseline_bands(cfg)
        .into_iter()
        .map(|(map, runs)| BaselineCatalogEntry {
            map,
            runs: runs.into_iter().map(|run| extensionless(&run)).collect(),
        })
        .collect();
    Catalog {
        kind: "baselines",
        aliases: vec!["baseline", "shipped"],
        values,
    }
}

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
            "Config readiness, maps, recent runs, next call. Subscriptions notify match/session changes only; re-read after navigation, registration, config or external run changes.",
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
        res(
            "argus://catalog/maps",
            "map-catalog",
            "Map value catalog",
            "Exact map names accepted by lab tools",
        ),
        res(
            "argus://catalog/runs",
            "run-catalog",
            "Run value catalog",
            "Extensionless run names and aliases accepted by lab tools",
        ),
        res(
            "argus://catalog/baselines",
            "baseline-catalog",
            "Baseline value catalog",
            "Configured map-to-baseline-band relationships",
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
        ResourceTemplate::new("argus://graph-revisions/{map}", "graph-revisions")
            .with_title("Graph revisions")
            .with_description("Content-hash ids for committed nav JSON revisions.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://graph/{map}/{hash}", "graph")
            .with_title("Graph revision")
            .with_description("Typed links from one exact nav JSON revision.")
            .with_mime_type("application/json"),
        ResourceTemplate::new("argus://probe-verdicts/{map}/{hash}", "probe-verdicts")
            .with_title("Probe verdicts")
            .with_description("Walk and typed-link evidence recorded beside a graph revision.")
            .with_mime_type("application/json"),
    ];
    ListResourceTemplatesResult::with_all_items(tmpls)
}

fn json_text(uri: &str, value: &impl Serialize) -> Result<ResourceContents, Failure> {
    let text = serde_json::to_string_pretty(value).map_err(|e| Failure::from(e.to_string()))?;
    Ok(ResourceContents::text(text, uri).with_mime_type("application/json"))
}

fn plain_text(uri: &str, text: impl Into<String>) -> ResourceContents {
    ResourceContents::text(text, uri)
}

pub fn read_uri(
    uri: &str,
    cfg: Option<&Config>,
    session: &SessionSeen,
) -> Result<Vec<ResourceContents>, Failure> {
    read_uri_with_live(uri, cfg, session, None)
}

pub fn read_uri_with_live(
    uri: &str,
    cfg: Option<&Config>,
    session: &SessionSeen,
    live: Option<crate::match_ctrl::MatchStatus>,
) -> Result<Vec<ResourceContents>, Failure> {
    read_uri_with_config(
        uri,
        cfg.ok_or_else(|| Failure::config("ARGUS_ROOT is required")),
        session,
        live,
    )
}

pub fn read_uri_with_config(
    uri: &str,
    cfg: Result<&Config, Failure>,
    session: &SessionSeen,
    live: Option<crate::match_ctrl::MatchStatus>,
) -> Result<Vec<ResourceContents>, Failure> {
    let uri = uri.trim();
    for prefix in [
        "map",
        "fn",
        "run",
        "path",
        "search",
        "const",
        "graph-revisions",
        "graph",
        "probe-verdicts",
    ] {
        if uri == format!("argus://{prefix}/") {
            return Err(Failure::bad("resource variable is empty"));
        }
    }
    match uri {
        "argus://project" => {
            let cfg = cfg.clone()?;
            Ok(vec![json_text(uri, &project_view(cfg))?])
        }
        "argus://lab" => {
            let cfg = cfg.clone()?;
            Ok(vec![json_text(uri, &lab_status(cfg, live))?])
        }
        "argus://knobs" => Ok(vec![json_text(uri, &knobs())?]),
        "argus://last" => Ok(vec![json_text(uri, session)?]),
        "argus://quality" => Ok(vec![plain_text(uri, QUALITY_BARS)]),
        "argus://help" => Ok(vec![json_text(uri, &see_vocab())?]),
        "argus://catalog/maps" => {
            let cfg = cfg.clone()?;
            Ok(vec![json_text(uri, &map_catalog(cfg)?)?])
        }
        "argus://catalog/runs" => {
            let cfg = cfg.clone()?;
            Ok(vec![json_text(uri, &run_catalog(cfg)?)?])
        }
        "argus://catalog/baselines" => {
            let cfg = cfg.clone()?;
            Ok(vec![json_text(uri, &baseline_catalog(cfg))?])
        }
        other => {
            if let Some(map) = other.strip_prefix("argus://graph-revisions/") {
                let cfg = cfg.clone()?;
                let revisions = crate::graph_revision::list_revisions_checked(cfg, map)?;
                return Ok(vec![json_text(uri, &revisions)?]);
            }
            if let Some(spec) = other.strip_prefix("argus://graph/") {
                let cfg = cfg.clone()?;
                let (map, hash) = spec.split_once('/').ok_or_else(|| {
                    Failure::bad("graph resource must be argus://graph/{map}/{hash}")
                })?;
                check_revision(cfg, map, hash)?;
                let revision = crate::graph_revision::get_revision(cfg, &format!("{map}@{hash}"))?;
                return Ok(vec![json_text(uri, &revision)?]);
            }
            if let Some(spec) = other.strip_prefix("argus://probe-verdicts/") {
                let cfg = cfg.clone()?;
                let (map, hash) = spec.split_once('/').ok_or_else(|| {
                    Failure::bad("verdict resource must be argus://probe-verdicts/{map}/{hash}")
                })?;
                check_revision(cfg, map, hash)?;
                let verdicts =
                    crate::graph_revision::probe_verdicts(cfg, &format!("{map}@{hash}"))?;
                return Ok(vec![json_text(uri, &verdicts)?]);
            }
            if let Some(name) = other.strip_prefix("argus://map/") {
                let cfg = cfg.clone()?;
                let atlas = crate::inspection_error::map(cfg, name)?;
                return Ok(vec![json_text(uri, &atlas_brief(&atlas))?]);
            }
            if let Some(name) = other.strip_prefix("argus://fn/") {
                let cfg = cfg.clone()?;
                if name.is_empty() {
                    return Err(Failure::bad("function name is empty"));
                }
                let idx = index_argus(cfg)?;
                if !idx.functions.iter().any(|f| {
                    !f.proto
                        && f.name
                            .to_ascii_lowercase()
                            .contains(&name.to_ascii_lowercase())
                }) {
                    return Err(Failure::missing(format!(
                        "no Argus function matching {name}"
                    )));
                }
                let src = qc_read(cfg, name)?;
                return Ok(vec![json_text(uri, &src)?]);
            }
            if let Some(name) = other.strip_prefix("argus://run/") {
                let cfg = cfg.clone()?;
                let path = crate::inspection_error::run(cfg, name, None)?;
                let brief = brief_run(cfg, &path.to_string_lossy(), None)?;
                return Ok(vec![json_text(uri, &brief)?]);
            }
            if let Some(spec) = other.strip_prefix("argus://path/") {
                let cfg = cfg.clone()?;
                let route = crate::nav_view::route_checked(cfg, spec)?;
                return Ok(vec![json_text(uri, &route)?]);
            }
            if let Some(needle) = other.strip_prefix("argus://search/") {
                let cfg = cfg.clone()?;
                let hits = crate::qc_index::qc_search(cfg, needle, 24)?;
                return Ok(vec![json_text(uri, &hits)?]);
            }
            if let Some(name) = other.strip_prefix("argus://const/") {
                let cfg = cfg.clone()?;
                let idx = index_argus(cfg)?;
                let q = name.to_ascii_lowercase();
                let hits: Vec<_> = idx
                    .constants
                    .into_iter()
                    .filter(|c| c.name.to_ascii_lowercase().contains(&q))
                    .collect();
                return Ok(vec![json_text(uri, &hits)?]);
            }
            Err(Failure::missing(format!(
                "unknown resource {other}; try argus://project or see what=help"
            )))
        }
    }
}

fn check_revision(cfg: &Config, map: &str, hash: &str) -> Result<(), Failure> {
    crate::paths::map_name(map).map_err(Failure::bad)?;
    if hash.len() != 32 || !hash.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err(Failure::bad(
            "revision requires a 32-character content hash",
        ));
    }
    let revisions = crate::graph_revision::list_revisions_checked(cfg, map)?;
    if !revisions
        .iter()
        .any(|r| r.graph_md5.eq_ignore_ascii_case(hash))
    {
        return Err(Failure::missing(format!(
            "unknown graph revision {map}@{hash}"
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::TestDir;
    use std::fs;

    fn catalog_cfg(root: &std::path::Path) -> Config {
        Config {
            root: root.into(),
            fteqcc: Default::default(),
            engine: Default::default(),
            basedir: root.into(),
            python: Default::default(),
            game: "argus".into(),
            src: root.join("src"),
            runs: root.join("runs"),
            progs: root.join("progs.dat"),
            maps: root.join("maps"),
        }
    }

    #[test]
    fn lists_core_uris() {
        let listed = list_static(None);
        let lab = listed
            .resources
            .iter()
            .find(|resource| resource.uri == "argus://lab")
            .unwrap();
        let description = lab.description.as_deref().unwrap();
        assert!(description.contains("match/session changes only"));
        assert!(description.contains("re-read after navigation, registration, config"));
        let uris: Vec<_> = listed.resources.iter().map(|r| r.uri.as_str()).collect();
        assert!(uris.contains(&"argus://project"));
        assert!(uris.contains(&"argus://knobs"));
        assert!(uris.contains(&"argus://last"));
        assert!(uris.contains(&"argus://catalog/maps"));
        assert!(uris.contains(&"argus://catalog/runs"));
        assert!(uris.contains(&"argus://catalog/baselines"));
    }

    #[test]
    fn lists_graph_resource_templates() {
        let listed = list_templates();
        let uris: Vec<_> = listed
            .resource_templates
            .iter()
            .map(|r| r.uri_template.as_str())
            .collect();
        assert!(uris.contains(&"argus://graph-revisions/{map}"));
        assert!(uris.contains(&"argus://graph/{map}/{hash}"));
        assert!(uris.contains(&"argus://probe-verdicts/{map}/{hash}"));
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

    #[test]
    fn catalogs_are_sorted_extensionless_and_keep_baseline_bands() {
        let root = TestDir::new("resource-catalogs").unwrap();
        for name in ["maps", "runs", "src"] {
            fs::create_dir_all(root.path().join(name)).unwrap();
        }
        fs::write(root.path().join("maps/dm4.bsp"), []).unwrap();
        fs::write(root.path().join("maps/dm2.bsp"), []).unwrap();
        fs::write(root.path().join("runs/zeta.log"), "").unwrap();
        fs::write(root.path().join("runs/alpha.log"), "").unwrap();
        fs::write(
            root.path().join("runs/baselines.json"),
            r#"{"dm4":["zeta.log","alpha"]}"#,
        )
        .unwrap();
        let cfg = catalog_cfg(root.path());

        let maps = serde_json::to_value(map_catalog(&cfg).unwrap()).unwrap();
        assert_eq!(maps["kind"], "maps");
        assert_eq!(maps["values"], serde_json::json!(["dm2", "dm4"]));

        let runs = serde_json::to_value(run_catalog(&cfg).unwrap()).unwrap();
        assert_eq!(runs["aliases"], serde_json::json!(["latest"]));
        assert_eq!(runs["values"], serde_json::json!(["alpha", "zeta"]));

        let baselines = serde_json::to_value(baseline_catalog(&cfg)).unwrap();
        assert_eq!(
            baselines["aliases"],
            serde_json::json!(["baseline", "shipped"])
        );
        assert_eq!(baselines["values"][0]["map"], "dm4");
        assert_eq!(
            baselines["values"][0]["runs"],
            serde_json::json!(["zeta", "alpha"])
        );
    }

    #[test]
    fn catalogs_fail_without_read_configuration() {
        let session = SessionSeen::default();
        for uri in [
            "argus://catalog/maps",
            "argus://catalog/runs",
            "argus://catalog/baselines",
        ] {
            assert!(read_uri(uri, None, &session).is_err(), "{uri}");
        }
    }

    #[test]
    fn resource_errors_keep_their_cause() {
        use crate::inspection_error::Kind;
        let dir = TestDir::new("resource-errors").unwrap();
        let cfg = catalog_cfg(dir.path());
        fs::create_dir_all(&cfg.src).unwrap();
        fs::create_dir_all(&cfg.maps).unwrap();
        fs::create_dir_all(&cfg.runs).unwrap();
        fs::write(
            cfg.src.join("argus.qc"),
            "void() Argus_Example = { return; };\n",
        )
        .unwrap();
        fs::write(cfg.maps.join("broken.bsp"), "broken BSP").unwrap();
        fs::write(cfg.src.join("argus_nav_broken.qc.json"), "{broken").unwrap();
        fs::write(
            cfg.src.join("argus_nav_valid.qc.json"),
            r#"{"nodes":[[0,0,0]],"links":[]}"#,
        )
        .unwrap();
        fs::create_dir(cfg.src.join("argus_nav_unreadable.qc.json")).unwrap();
        fs::create_dir(cfg.runs.join("unreadable.log")).unwrap();
        let session = SessionSeen::default();
        for (uri, kind) in [
            ("argus://unknown", Kind::NotFound),
            ("argus://map/absent", Kind::NotFound),
            ("argus://fn/Absent", Kind::NotFound),
            ("argus://run/absent", Kind::NotFound),
            ("argus://graph-revisions/absent", Kind::NotFound),
            (
                "argus://graph/valid/00000000000000000000000000000000",
                Kind::NotFound,
            ),
            ("argus://path/absent:0->1", Kind::NotFound),
            ("argus://graph/broken/not-a-hash", Kind::BadArgs),
            ("argus://path/nonsense", Kind::BadArgs),
            ("argus://path/valid:0->99", Kind::BadArgs),
            ("argus://fn/", Kind::BadArgs),
            ("argus://map/broken", Kind::Internal),
            ("argus://graph-revisions/broken", Kind::Internal),
            ("argus://graph-revisions/unreadable", Kind::Internal),
            ("argus://path/broken:0->1", Kind::Internal),
            ("argus://run/unreadable.log", Kind::Internal),
        ] {
            let error = read_uri(uri, Some(&cfg), &session).unwrap_err();
            assert_eq!(error.kind, kind, "{uri}: {error}");
        }
        let error = Failure::config("missing ARGUS_ROOT");
        let result = read_uri_with_config("argus://project", Err(error.clone()), &session, None)
            .unwrap_err();
        assert_eq!(result.kind, Kind::Unconfigured);
        assert_eq!(result.error, error.error);
        assert!(read_uri_with_config("argus://help", Err(error), &session, None).is_ok());
    }
}
