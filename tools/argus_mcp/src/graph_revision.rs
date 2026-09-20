//! Typed, read-only views over committed nav graphs and mill verdicts.
//!
//! The JSON and its Git history remain the source of truth.  Content hashes
//! make stable resource ids; Git commits only provide provenance and the old
//! bytes needed for a diff.

use crate::config::Config;
use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::io::{BufRead, BufReader, Read, Write};
use std::path::Path;
use std::process::{Command, Stdio};

const NAV_STEP: f64 = 18.0;
const SIDECARS: &[&str] = &["probe", "proven", "costs", "mined"];

#[derive(Debug, Clone, Serialize)]
pub struct ArtifactInput {
    pub kind: String,
    pub md5: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RevisionInputs {
    pub trace_inputs: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bsp_hash: Option<String>,
    pub sidecars: Vec<ArtifactInput>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RevisionSummary {
    pub id: String,
    pub map: String,
    pub graph_md5: String,
    pub uri: String,
    pub working_tree: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub commit: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub committed_at: Option<String>,
    pub nodes: usize,
    pub links: usize,
    pub inputs: RevisionInputs,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct GraphLink {
    pub id: String,
    pub from_node: usize,
    pub to_node: usize,
    pub from: [f64; 3],
    pub to: [f64; 3],
    pub kind: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct GraphRevision {
    #[serde(flatten)]
    pub summary: RevisionSummary,
    pub links: Vec<GraphLink>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ProbeVerdict {
    pub link_id: String,
    pub outcome: String,
    pub reason: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub kind: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub count: Option<u64>,
    pub revision: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recorded_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TypeChange {
    pub id: String,
    pub from_kind: String,
    pub to_kind: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct GraphDiff {
    pub map: String,
    pub from: String,
    pub to: String,
    pub added: Vec<GraphLink>,
    pub removed: Vec<GraphLink>,
    pub type_changed: Vec<TypeChange>,
    pub verdicts: Vec<ProbeVerdict>,
}

#[derive(Clone)]
struct Source {
    bytes: Vec<u8>,
    sidecars: BTreeMap<String, Vec<u8>>,
    working_tree: bool,
    commit: Option<String>,
    committed_at: Option<String>,
}

fn valid_map(map: &str) -> Result<String, String> {
    let map = map.trim().to_ascii_lowercase();
    if map.is_empty()
        || !map
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
    {
        return Err("map must be a short name such as dm4".into());
    }
    Ok(map)
}

fn graph_path(map: &str) -> String {
    format!("src/argus_nav_{map}.qc.json")
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", md5::compute(bytes))
}

fn git(root: &Path, args: &[&str]) -> Option<Vec<u8>> {
    let mut command = Command::new("git");
    command.arg("-C").arg(root).args(args);
    let out = crate::child_process::output_with_windows_loader_retry(&mut command).ok()?;
    out.status.success().then_some(out.stdout)
}

fn git_batch(root: &Path, specs: &[String]) -> BTreeMap<String, Vec<u8>> {
    let mut out = BTreeMap::new();
    let Ok(mut child) = Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["cat-file", "--batch"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    else {
        return out;
    };
    let Some(mut stdin) = child.stdin.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return out;
    };
    for spec in specs {
        if writeln!(stdin, "{spec}").is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return out;
        }
    }
    drop(stdin);
    let Some(stdout) = child.stdout.take() else {
        let _ = child.kill();
        let _ = child.wait();
        return out;
    };
    let mut reader = BufReader::new(stdout);
    for spec in specs {
        let mut header = String::new();
        if reader
            .read_line(&mut header)
            .ok()
            .filter(|n| *n > 0)
            .is_none()
        {
            break;
        }
        if header.trim_end().ends_with(" missing") {
            continue;
        }
        let Some(size) = header
            .split_whitespace()
            .last()
            .and_then(|n| n.parse::<usize>().ok())
        else {
            break;
        };
        let mut bytes = vec![0; size];
        if reader.read_exact(&mut bytes).is_err() {
            break;
        }
        let mut newline = [0u8; 1];
        if reader.read_exact(&mut newline).is_err() {
            break;
        }
        out.insert(spec.clone(), bytes);
    }
    let _ = child.wait();
    out
}

fn history_sources(cfg: &Config, map: &str) -> Result<Vec<Source>, String> {
    let rel = graph_path(map);
    let current = cfg.root.join(&rel);
    let mut sources = Vec::new();
    if let Ok(bytes) = std::fs::read(&current) {
        let sidecars = SIDECARS
            .iter()
            .filter_map(|kind| {
                std::fs::read(cfg.root.join(format!("src/argus_nav_{map}.{kind}.json")))
                    .ok()
                    .map(|bytes| ((*kind).to_string(), bytes))
            })
            .collect();
        sources.push(Source {
            bytes,
            sidecars,
            working_tree: true,
            commit: None,
            committed_at: None,
        });
    }

    if let Some(raw) = git(
        &cfg.root,
        &["log", "--format=%H%x09%cI", "--", rel.as_str()],
    ) {
        let commits: Vec<(String, Option<String>)> = String::from_utf8_lossy(&raw)
            .lines()
            .filter_map(|line| {
                let mut fields = line.splitn(2, '\t');
                let commit = fields.next()?.to_string();
                (!commit.is_empty()).then(|| (commit, fields.next().map(str::to_string)))
            })
            .collect();
        let mut specs = Vec::new();
        for (commit, _) in &commits {
            specs.push(format!("{commit}:{rel}"));
            specs.extend(
                SIDECARS
                    .iter()
                    .map(|kind| format!("{commit}:src/argus_nav_{map}.{kind}.json")),
            );
        }
        let objects = git_batch(&cfg.root, &specs);
        for (commit, committed_at) in commits {
            let graph_spec = format!("{commit}:{rel}");
            let Some(bytes) = objects.get(&graph_spec).cloned() else {
                continue;
            };
            let sidecars = SIDECARS
                .iter()
                .filter_map(|kind| {
                    let spec = format!("{commit}:src/argus_nav_{map}.{kind}.json");
                    objects
                        .get(&spec)
                        .cloned()
                        .map(|bytes| ((*kind).to_string(), bytes))
                })
                .collect();
            sources.push(Source {
                bytes,
                sidecars,
                working_tree: false,
                commit: Some(commit),
                committed_at,
            });
        }
    }
    if sources.is_empty() {
        return Err(format!("no nav JSON for {map} ({})", current.display()));
    }

    // The working file normally equals HEAD. Keep one content revision and
    // retain both facts: it is current and it came from this commit.
    let mut unique: Vec<Source> = Vec::new();
    for source in sources {
        let hash = digest(&source.bytes);
        if let Some(prior) = unique.iter_mut().find(|p| digest(&p.bytes) == hash) {
            prior.working_tree |= source.working_tree;
            if prior.commit.is_none() {
                prior.commit = source.commit;
                prior.committed_at = source.committed_at;
            }
        } else {
            unique.push(source);
        }
    }
    Ok(unique)
}

fn source_sidecar(kind: &str, source: &Source) -> Option<Vec<u8>> {
    source.sidecars.get(kind).cloned()
}

fn sidecar_time(
    cfg: &Config,
    map: &str,
    kind: &str,
    source: &Source,
    bytes: &[u8],
) -> Option<String> {
    let rel = format!("src/argus_nav_{map}.{kind}.json");
    if source.working_tree {
        let committed = git(&cfg.root, &["show", &format!("HEAD:{rel}")]);
        if committed.as_deref() == Some(bytes) {
            let raw = git(&cfg.root, &["log", "-1", "--format=%cI", "--", &rel])?;
            return Some(String::from_utf8_lossy(&raw).trim().to_string());
        }
        let modified = std::fs::metadata(cfg.root.join(&rel))
            .ok()?
            .modified()
            .ok()?;
        let when: chrono::DateTime<chrono::Utc> = modified.into();
        return Some(when.to_rfc3339_opts(chrono::SecondsFormat::Secs, true));
    }
    let commit = source.commit.as_deref()?;
    let raw = git(
        &cfg.root,
        &["log", "-1", "--format=%cI", commit, "--", &rel],
    )?;
    let value = String::from_utf8_lossy(&raw).trim().to_string();
    (!value.is_empty()).then_some(value)
}

fn point(v: &Value) -> Option<[f64; 3]> {
    let a = v.as_array()?;
    Some([
        a.first()?.as_f64()?,
        a.get(1)?.as_f64()?,
        a.get(2)?.as_f64()?,
    ])
}

fn point_text(p: [f64; 3]) -> String {
    serde_json::to_string(&p).unwrap_or_else(|_| "[0,0,0]".into())
}

fn link_id(from: [f64; 3], to: [f64; 3]) -> String {
    format!("{}->{}", point_text(from), point_text(to))
}

fn pair(v: &Value) -> Option<([f64; 3], [f64; 3])> {
    let a = v.as_array()?;
    Some((point(a.first()?)?, point(a.get(1)?)?))
}

fn parse_links(v: &Value) -> Result<(usize, BTreeMap<String, GraphLink>), String> {
    let nodes: Vec<[f64; 3]> = v
        .get("nodes")
        .and_then(Value::as_array)
        .ok_or("nav json missing nodes")?
        .iter()
        .filter_map(point)
        .collect();
    if nodes.is_empty() {
        return Err("nav json has no nodes".into());
    }
    let mut links = BTreeMap::new();
    let mut put = |row: &Value, forced: Option<&str>| -> Result<(), String> {
        let a = row.as_array().ok_or("bad nav link")?;
        let from = a.first().and_then(Value::as_u64).ok_or("bad link from")? as usize;
        let to = a.get(1).and_then(Value::as_u64).ok_or("bad link to")? as usize;
        if from >= nodes.len() || to >= nodes.len() {
            return Err(format!(
                "link {from}->{to} is outside {} nodes",
                nodes.len()
            ));
        }
        let kind = forced.unwrap_or_else(|| {
            if nodes[from][2] - nodes[to][2] > NAV_STEP {
                "drop"
            } else {
                "walk"
            }
        });
        let id = link_id(nodes[from], nodes[to]);
        links.insert(
            id.clone(),
            GraphLink {
                id,
                from_node: from,
                to_node: to,
                from: nodes[from],
                to: nodes[to],
                kind: kind.into(),
            },
        );
        Ok(())
    };
    for (key, kind) in [
        ("links", None),
        ("jlinks", Some("jump")),
        ("teles", Some("tele")),
        ("rjlinks", Some("rocket")),
        ("liftlinks", Some("lift")),
        ("swimlinks", Some("swim")),
        ("doorlinks", Some("door")),
        ("trainlinks", Some("train")),
        ("sprintlinks", Some("sprint")),
    ] {
        if let Some(rows) = v.get(key).and_then(Value::as_array) {
            for row in rows {
                put(row, kind)?;
            }
        }
    }
    Ok((nodes.len(), links))
}

fn revision_from_source(map: &str, source: &Source) -> Result<GraphRevision, String> {
    let graph_md5 = digest(&source.bytes);
    let id = format!("{map}@{graph_md5}");
    let v: Value = serde_json::from_slice(&source.bytes).map_err(|e| format!("nav json: {e}"))?;
    let (nodes, links) = parse_links(&v)?;
    let trace_inputs = v
        .get("trace_inputs")
        .and_then(Value::as_array)
        .map(|a| {
            a.iter()
                .filter_map(Value::as_str)
                .map(str::to_string)
                .collect()
        })
        .unwrap_or_default();
    let bsp_hash = v
        .get("bsp_hash")
        .or_else(|| v.get("bsp_md5"))
        .and_then(Value::as_str)
        .map(str::to_string);
    let sidecars = SIDECARS
        .iter()
        .filter_map(|kind| {
            source_sidecar(kind, source).map(|bytes| ArtifactInput {
                kind: (*kind).into(),
                md5: digest(&bytes),
            })
        })
        .collect();
    Ok(GraphRevision {
        summary: RevisionSummary {
            uri: format!("argus://graph/{map}/{graph_md5}"),
            id,
            map: map.into(),
            graph_md5,
            working_tree: source.working_tree,
            commit: source.commit.clone(),
            committed_at: source.committed_at.clone(),
            nodes,
            links: links.len(),
            inputs: RevisionInputs {
                trace_inputs,
                bsp_hash,
                sidecars,
            },
        },
        links: links.into_values().collect(),
    })
}

pub fn list_revisions(cfg: &Config, map: &str) -> Result<Vec<RevisionSummary>, String> {
    let map = valid_map(map)?;
    history_sources(cfg, &map)?
        .iter()
        .map(|s| revision_from_source(&map, s).map(|r| r.summary))
        .collect()
}

fn split_id(id: &str) -> Result<(String, String), String> {
    let (map, hash) = id
        .split_once('@')
        .ok_or("revision id must be map@content-hash")?;
    let map = valid_map(map)?;
    if hash.len() != 32 || !hash.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err("revision id must end in a 32-character content hash".into());
    }
    Ok((map, hash.to_ascii_lowercase()))
}

pub fn get_revision(cfg: &Config, id: &str) -> Result<GraphRevision, String> {
    let (map, wanted) = split_id(id)?;
    for source in history_sources(cfg, &map)? {
        if digest(&source.bytes) == wanted {
            return revision_from_source(&map, &source);
        }
    }
    Err(format!("unknown graph revision {id}"))
}

fn verdicts_from_source(
    cfg: &Config,
    revision: &GraphRevision,
    source: &Source,
) -> Result<Vec<ProbeVerdict>, String> {
    let mut out = Vec::new();
    if let Some(bytes) = source_sidecar("probe", source) {
        let recorded_at = sidecar_time(cfg, &revision.summary.map, "probe", source, &bytes);
        let v: Value = serde_json::from_slice(&bytes).map_err(|e| format!("probe json: {e}"))?;
        for (field, outcome) in [("failed", "failed"), ("passed", "passed")] {
            if let Some(rows) = v.get(field).and_then(Value::as_array) {
                for row in rows {
                    if let Some((from, to)) = pair(row) {
                        out.push(ProbeVerdict {
                            link_id: link_id(from, to),
                            outcome: outcome.into(),
                            reason: format!("recorded in probe.json {field}"),
                            kind: Some("walk".into()),
                            count: None,
                            revision: revision.summary.id.clone(),
                            recorded_at: recorded_at.clone(),
                        });
                    }
                }
            }
        }
        if let Some(rows) = v.get("typed_failed").and_then(Value::as_array) {
            for row in rows {
                if let (Some(from), Some(to)) = (
                    row.get("from").and_then(point),
                    row.get("to").and_then(point),
                ) {
                    let kind = row.get("kind").and_then(Value::as_str).unwrap_or("typed");
                    out.push(ProbeVerdict {
                        link_id: link_id(from, to),
                        outcome: "failed".into(),
                        reason: "recorded in probe.json typed_failed".into(),
                        kind: Some(kind.into()),
                        count: None,
                        revision: revision.summary.id.clone(),
                        recorded_at: recorded_at.clone(),
                    });
                }
            }
        }
    }
    if let Some(bytes) = source_sidecar("proven", source) {
        let recorded_at = sidecar_time(cfg, &revision.summary.map, "proven", source, &bytes);
        let v: Value = serde_json::from_slice(&bytes).map_err(|e| format!("proven json: {e}"))?;
        if let Some(rows) = v.as_array() {
            for row in rows {
                if let Some((from, to)) = row.get("value").and_then(pair) {
                    let count = row
                        .get("Count")
                        .or_else(|| row.get("count"))
                        .and_then(Value::as_u64);
                    out.push(ProbeVerdict {
                        link_id: link_id(from, to),
                        outcome: "proven".into(),
                        reason: count
                            .map(|n| format!("recorded in proven.json {n} times"))
                            .unwrap_or_else(|| "recorded in proven.json".into()),
                        kind: Some("walk".into()),
                        count,
                        revision: revision.summary.id.clone(),
                        recorded_at: recorded_at.clone(),
                    });
                }
            }
        }
    }
    out.sort_by(|a, b| (&a.link_id, &a.outcome).cmp(&(&b.link_id, &b.outcome)));
    out.dedup_by(|a, b| a == b);
    Ok(out)
}

pub fn probe_verdicts(cfg: &Config, id: &str) -> Result<Vec<ProbeVerdict>, String> {
    let (map, wanted) = split_id(id)?;
    let source = history_sources(cfg, &map)?
        .into_iter()
        .find(|s| digest(&s.bytes) == wanted)
        .ok_or_else(|| format!("unknown graph revision {id}"))?;
    let revision = revision_from_source(&map, &source)?;
    verdicts_from_source(cfg, &revision, &source)
}

pub fn diff(
    cfg: &Config,
    from_id: &str,
    to_id: &str,
    only: Option<&str>,
) -> Result<GraphDiff, String> {
    let (from_map, from_hash) = split_id(from_id)?;
    let (to_map, to_hash) = split_id(to_id)?;
    if from_map != to_map {
        return Err("graph revisions must name the same map".into());
    }
    let sources = history_sources(cfg, &from_map)?;
    let from_source = sources
        .iter()
        .find(|s| digest(&s.bytes) == from_hash)
        .ok_or_else(|| format!("unknown graph revision {from_id}"))?;
    let to_source = sources
        .iter()
        .find(|s| digest(&s.bytes) == to_hash)
        .ok_or_else(|| format!("unknown graph revision {to_id}"))?;
    let from = revision_from_source(&from_map, from_source)?;
    let to = revision_from_source(&to_map, to_source)?;
    let a: BTreeMap<_, _> = from
        .links
        .iter()
        .map(|l| (l.id.clone(), l.clone()))
        .collect();
    let b: BTreeMap<_, _> = to.links.iter().map(|l| (l.id.clone(), l.clone())).collect();
    if let Some(id) = only {
        if !a.contains_key(id) && !b.contains_key(id) {
            return Err(format!("link {id} is absent from both graph revisions"));
        }
    }
    let include = |id: &str| only.map(|wanted| wanted == id).unwrap_or(true);
    let added = b
        .iter()
        .filter(|(id, _)| !a.contains_key(*id) && include(id))
        .map(|(_, link)| link.clone())
        .collect::<Vec<_>>();
    let removed = a
        .iter()
        .filter(|(id, _)| !b.contains_key(*id) && include(id))
        .map(|(_, link)| link.clone())
        .collect::<Vec<_>>();
    let type_changed = a
        .iter()
        .filter_map(|(id, old)| {
            let new = b.get(id)?;
            (old.kind != new.kind && include(id)).then(|| TypeChange {
                id: id.clone(),
                from_kind: old.kind.clone(),
                to_kind: new.kind.clone(),
            })
        })
        .collect::<Vec<_>>();
    let changed: BTreeSet<_> = added
        .iter()
        .chain(&removed)
        .map(|l| l.id.as_str())
        .chain(type_changed.iter().map(|l| l.id.as_str()))
        .collect();
    let mut verdicts = verdicts_from_source(cfg, &from, from_source)?;
    verdicts.extend(verdicts_from_source(cfg, &to, to_source)?);
    verdicts.retain(|v| changed.contains(v.link_id.as_str()));
    verdicts.sort_by(|a, b| {
        (&a.link_id, &a.revision, &a.outcome).cmp(&(&b.link_id, &b.revision, &b.outcome))
    });
    verdicts.dedup_by(|a, b| a == b);
    Ok(GraphDiff {
        map: from.summary.map.clone(),
        from: from.summary.id,
        to: to.summary.id,
        added,
        removed,
        type_changed,
        verdicts,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{git_test_lock, run_git, TestDir};
    use std::fs;

    fn graph(kind: &str, extra: bool) -> String {
        let typed = if kind == "jump" {
            r#", "jlinks": [[0,1]]"#
        } else {
            ""
        };
        let extra_link = if extra { ",[1,0,0]" } else { "" };
        format!(
            r#"{{"nodes":[[0,0,20],[1,0,0]],"links":[[0,1,0]{extra_link}]{typed},"trace_inputs":["one.tracks.json"]}}"#
        )
    }

    fn cfg(root: &Path) -> Config {
        Config {
            root: root.into(),
            fteqcc: Default::default(),
            engine: Default::default(),
            basedir: Default::default(),
            python: Default::default(),
            game: "argus".into(),
            src: root.join("src"),
            runs: root.join("runs"),
            progs: root.join("progs.dat"),
            maps: root.join("maps"),
        }
    }

    fn repo() -> (TestDir, Config) {
        let root = TestDir::new("graph-revision").unwrap();
        fs::create_dir_all(root.path().join("src")).unwrap();
        run_git(root.path(), &["init", "-q"]).unwrap();
        run_git(root.path(), &["config", "user.name", "Argus test"]).unwrap();
        run_git(
            root.path(),
            &["config", "user.email", "argus-test@example.invalid"],
        )
        .unwrap();
        let path = root.path().join("src/argus_nav_dm4.qc.json");
        fs::write(&path, graph("walk", false)).unwrap();
        run_git(root.path(), &["add", "."]).unwrap();
        run_git(root.path(), &["commit", "-q", "-m", "first"]).unwrap();
        fs::write(&path, graph("jump", true)).unwrap();
        fs::write(
            root.path().join("src/argus_nav_dm4.probe.json"),
            r#"{"failed":[[[0,0,20],[1,0,0]]],"passed":[]}"#,
        )
        .unwrap();
        run_git(root.path(), &["add", "."]).unwrap();
        run_git(root.path(), &["commit", "-q", "-m", "second"]).unwrap();
        let c = cfg(root.path());
        (root, c)
    }

    #[test]
    fn listed_revision_ids_round_trip() {
        let _gate = git_test_lock();
        let (_root, cfg) = repo();
        let revisions = list_revisions(&cfg, "dm4").unwrap();
        assert_eq!(revisions.len(), 2);
        for summary in revisions {
            let loaded = get_revision(&cfg, &summary.id).unwrap();
            assert_eq!(loaded.summary.graph_md5, summary.graph_md5);
        }
    }

    #[test]
    fn shipped_dm4_revision_round_trips_if_present() {
        let _gate = git_test_lock();
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        if !root.join("src/argus_nav_dm4.qc.json").exists() {
            return;
        }
        let cfg = cfg(&root);
        let listed = list_revisions(&cfg, "dm4").unwrap();
        assert!(!listed.is_empty());
        let loaded = get_revision(&cfg, &listed[0].id).unwrap();
        assert_eq!(loaded.summary.id, listed[0].id);
        assert!(!loaded.links.is_empty());
    }

    #[test]
    fn diff_only_names_links_from_either_json_and_types_changes() {
        let _gate = git_test_lock();
        let (_root, cfg) = repo();
        let revisions = list_revisions(&cfg, "dm4").unwrap();
        let newest = &revisions[0].id;
        let oldest = &revisions[1].id;
        let got = diff(&cfg, oldest, newest, None).unwrap();
        assert_eq!(got.added.len(), 1);
        assert_eq!(got.type_changed.len(), 1);
        assert_eq!(got.verdicts.len(), 1);
        assert_eq!(got.verdicts[0].link_id, "[0.0,0.0,20.0]->[1.0,0.0,0.0]");
        let known: BTreeSet<_> = get_revision(&cfg, oldest)
            .unwrap()
            .links
            .into_iter()
            .chain(get_revision(&cfg, newest).unwrap().links)
            .map(|l| l.id)
            .collect();
        assert!(got.added.iter().all(|l| known.contains(&l.id)));
        assert!(got.removed.iter().all(|l| known.contains(&l.id)));
        assert!(got.type_changed.iter().all(|l| known.contains(&l.id)));
    }

    #[test]
    fn link_absent_from_both_revisions_fails_closed() {
        let _gate = git_test_lock();
        let (_root, cfg) = repo();
        let revisions = list_revisions(&cfg, "dm4").unwrap();
        let err = diff(
            &cfg,
            &revisions[1].id,
            &revisions[0].id,
            Some("[9,9,9]->[8,8,8]"),
        )
        .unwrap_err();
        assert!(err.contains("absent from both"));
    }
}
