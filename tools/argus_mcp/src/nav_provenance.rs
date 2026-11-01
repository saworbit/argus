//! Frozen navigation inputs associated with a compiled program and one tape.

use crate::config::Config;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct MapSnapshot {
    pub map: String,
    pub program_md5: String,
    pub inputs_md5: String,
    pub in_progs_src: bool,
    pub in_dispatcher: bool,
    pub qc_present: bool,
    pub graph: Option<Value>,
    #[serde(default)]
    pub loaded_in_tape: Option<bool>,
}

impl MapSnapshot {
    pub fn runtime_navigation(&self) -> bool {
        self.in_progs_src && self.in_dispatcher && self.qc_present
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BuildSnapshot {
    schema: u32,
    inputs_md5: String,
    maps: BTreeMap<String, MapSnapshot>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct TapeSnapshot {
    schema: u32,
    log_md5: String,
    navigation: Option<MapSnapshot>,
}

#[derive(Clone, Debug, Serialize)]
pub struct Inventory {
    pub map: String,
    pub qc_on_disk: bool,
    pub json_on_disk: bool,
    pub in_progs_src: bool,
    pub in_dispatcher: bool,
    /// None means no compile receipt for the installed program. Never infer it.
    pub installed_navigation: Option<bool>,
}

#[derive(Clone, Debug, Serialize)]
pub struct CoverageSource {
    pub spatial_source: &'static str,
    pub runtime_navigation: Option<bool>,
    pub loaded_in_tape: Option<bool>,
    pub eligible_for_navigation_claims: bool,
    pub program_md5: Option<String>,
    pub inputs_md5: Option<String>,
    pub graph_md5: Option<String>,
    pub build_in_progs_src: Option<bool>,
    pub build_in_dispatcher: Option<bool>,
}

impl CoverageSource {
    pub fn new(snapshot: Option<&MapSnapshot>) -> Self {
        let frozen = snapshot.filter(|s| s.graph.is_some());
        let graph_md5 = frozen
            .and_then(|s| s.graph.as_ref())
            .and_then(|graph| graph_digest(graph).ok());
        Self {
            spatial_source: if frozen.is_some() {
                "build_snapshot"
            } else {
                "current_tree_diagnostic"
            },
            runtime_navigation: snapshot.map(|s| s.runtime_navigation()),
            loaded_in_tape: snapshot.and_then(|s| s.loaded_in_tape),
            eligible_for_navigation_claims: graph_md5.is_some()
                && frozen.is_some_and(|s| s.runtime_navigation() && s.loaded_in_tape == Some(true)),
            program_md5: snapshot.map(|s| s.program_md5.clone()),
            inputs_md5: snapshot.map(|s| s.inputs_md5.clone()),
            graph_md5,
            build_in_progs_src: snapshot.map(|s| s.in_progs_src),
            build_in_dispatcher: snapshot.map(|s| s.in_dispatcher),
        }
    }
}

fn digest(bytes: &[u8]) -> String {
    format!("{:x}", md5::compute(bytes))
}

pub fn graph_digest(graph: &Value) -> Result<String, serde_json::Error> {
    serde_json::to_vec(graph).map(|bytes| digest(&bytes))
}

fn inputs(src: &Path) -> Result<BTreeMap<String, Vec<u8>>, String> {
    fn visit(root: &Path, dir: &Path, out: &mut BTreeMap<String, Vec<u8>>) -> Result<(), String> {
        for entry in fs::read_dir(dir).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            let kind = entry.file_type().map_err(|e| e.to_string())?;
            if kind.is_symlink() {
                return Err(format!("cannot freeze linked source: {}", path.display()));
            }
            if kind.is_dir() {
                visit(root, &path, out)?;
            } else if path
                .extension()
                .is_some_and(|e| e == "qc" || e == "src" || e == "json")
            {
                let name = path
                    .strip_prefix(root)
                    .map_err(|e| e.to_string())?
                    .to_string_lossy()
                    .replace('\\', "/");
                out.insert(
                    name,
                    fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?,
                );
            }
        }
        Ok(())
    }
    let mut out = BTreeMap::new();
    visit(src, src, &mut out)?;
    Ok(out)
}

pub fn capture(cfg: &Config) -> Result<BuildSnapshot, String> {
    let files = inputs(&cfg.src)?;
    let mut hash = md5::Context::new();
    for (name, bytes) in &files {
        hash.consume(name);
        hash.consume([0]);
        hash.consume(bytes);
    }
    let inputs_md5 = format!("{:x}", hash.finalize());
    let progs = String::from_utf8_lossy(
        files
            .get("progs.src")
            .ok_or("no progs.src for navigation snapshot")?,
    );
    let dispatch = files
        .get("argus_nav_dispatch.qc")
        .map(|v| String::from_utf8_lossy(v))
        .unwrap_or_default();
    let mut maps = BTreeMap::new();
    for (name, bytes) in &files {
        let Some(map) = name
            .strip_prefix("argus_nav_")
            .and_then(|s| s.strip_suffix(".qc.json"))
        else {
            continue;
        };
        let map = crate::paths::map_name(map)?;
        let registered = crate::nav_sync::registration_text(&dispatch, &progs, &map);
        maps.insert(
            map.clone(),
            MapSnapshot {
                qc_present: files.contains_key(&format!("argus_nav_{map}.qc")),
                map,
                program_md5: String::new(),
                inputs_md5: inputs_md5.clone(),
                in_progs_src: registered.progs,
                in_dispatcher: registered.branch,
                graph: Some(serde_json::from_slice(bytes).map_err(|e| format!("{name}: {e}"))?),
                loaded_in_tape: None,
            },
        );
    }
    Ok(BuildSnapshot {
        schema: 1,
        inputs_md5,
        maps,
    })
}

fn build_path(cfg: &Config, program_md5: &str) -> PathBuf {
    cfg.root
        .join("backups/navigation_builds")
        .join(format!("{program_md5}.json"))
}

/// Called only after compiler success, before installation, under its lock.
pub fn record_build(cfg: &Config, before: BuildSnapshot) -> Result<(), String> {
    if capture(cfg)?.inputs_md5 != before.inputs_md5 {
        return Err("source changed during compilation; navigation provenance withheld".into());
    }
    let mut snapshot = before;
    let program = digest(&fs::read(&cfg.progs).map_err(|e| e.to_string())?);
    for map in snapshot.maps.values_mut() {
        map.program_md5.clone_from(&program);
    }
    let path = build_path(cfg, &program);
    // A content-addressed receipt is immutable. A later JSON edit must not
    // relabel an older binary or its already harvested tapes.
    if path.exists() {
        return load_build(cfg, &program).map(|_| ());
    }
    write_json(&path, &snapshot)
}

fn load_build(cfg: &Config, program: &str) -> Result<BuildSnapshot, String> {
    decode_build(
        &fs::read(build_path(cfg, program)).map_err(|e| e.to_string())?,
        program,
    )
}

fn decode_build(bytes: &[u8], program: &str) -> Result<BuildSnapshot, String> {
    let snapshot: BuildSnapshot = serde_json::from_slice(bytes).map_err(|e| e.to_string())?;
    if snapshot.schema != 1
        || snapshot.maps.iter().any(|(name, m)| {
            m.program_md5 != program || m.map != *name || m.inputs_md5 != snapshot.inputs_md5
        })
    {
        return Err("navigation build receipt does not match program".into());
    }
    Ok(snapshot)
}

pub fn for_launch(cfg: &Config, map: &str) -> Option<MapSnapshot> {
    fn optional(path: &Path) -> Result<Option<Vec<u8>>, String> {
        match fs::read(path) {
            Ok(bytes) => Ok(Some(bytes)),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(format!("{}: {e}", path.display())),
        }
    }
    let read = || -> Result<Option<MapSnapshot>, String> {
        let Some(program) = optional(&cfg.basedir.join(&cfg.game).join("progs.dat"))? else {
            return Ok(None);
        };
        let program = digest(&program);
        let Some(receipt) = optional(&build_path(cfg, &program))? else {
            return Ok(None);
        };
        Ok(decode_build(&receipt, &program)?.maps.remove(map))
    };
    match read() {
        Ok(snapshot) => snapshot,
        Err(error) => {
            eprintln!("navigation build provenance unavailable: {error}");
            None
        }
    }
}

pub fn inventory(cfg: &Config, map: &str) -> Inventory {
    let registration = crate::nav_sync::registration(cfg, map);
    Inventory {
        map: map.into(),
        qc_on_disk: cfg.src.join(format!("argus_nav_{map}.qc")).is_file(),
        json_on_disk: cfg.src.join(format!("argus_nav_{map}.qc.json")).is_file(),
        in_progs_src: registration.progs,
        in_dispatcher: registration.branch,
        installed_navigation: for_launch(cfg, map).map(|s| s.runtime_navigation()),
    }
}

pub fn record_tape(
    path: &Path,
    body: &[u8],
    navigation: Option<&MapSnapshot>,
) -> Result<(), String> {
    let mut navigation = navigation.cloned();
    if let Some(snapshot) = &mut navigation {
        let nodes = snapshot
            .graph
            .as_ref()
            .and_then(|g| g["nodes"].as_array())
            .map_or(0, Vec::len);
        snapshot.loaded_in_tape = Some(
            nodes > 0
                && String::from_utf8_lossy(body).lines().any(|line| {
                    let Some(rest) = line.trim().strip_prefix("ARGNAV ") else {
                        return false;
                    };
                    let mut fields = rest.split_whitespace();
                    fields.next().and_then(|s| s.parse::<usize>().ok()) == Some(nodes)
                        && fields.next() == Some("nodes,")
                }),
        );
    }
    write_json(
        &path.with_extension("nav.json"),
        &TapeSnapshot {
            schema: 1,
            log_md5: digest(body),
            navigation,
        },
    )
}

pub fn read_tape(path: &Path, map: &str) -> Result<Option<MapSnapshot>, String> {
    let bytes = match fs::read(path.with_extension("nav.json")) {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.to_string()),
    };
    let snapshot: TapeSnapshot = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if snapshot.schema != 1
        || snapshot.log_md5 != digest(&fs::read(path).map_err(|e| e.to_string())?)
    {
        return Err("navigation receipt does not match this tape".into());
    }
    if snapshot.navigation.as_ref().is_some_and(|n| n.map != map) {
        return Err("navigation receipt names a different map".into());
    }
    Ok(snapshot.navigation)
}

fn write_json(path: &Path, value: &impl Serialize) -> Result<(), String> {
    use std::io::Write;
    let bytes = serde_json::to_vec(value).map_err(|e| e.to_string())?;
    let parent = path.parent().ok_or("receipt has no parent")?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let temp = path.with_extension(format!("{}.tmp", std::process::id()));
    let mut owned = false;
    let result = (|| {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)
            .map_err(|e| e.to_string())?;
        owned = true;
        file.write_all(&bytes).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        drop(file);
        fs::rename(&temp, path).map_err(|e| e.to_string())
    })();
    if result.is_err() && owned && temp.exists() {
        fs::remove_file(&temp).map_err(|e| format!("{result:?}; receipt cleanup failed: {e}"))?;
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::TestDir;
    use std::collections::HashMap;

    fn setup(dir: &TestDir, included: bool, dispatched: bool) -> Config {
        let cfg = crate::config::load_for_reads_from(
            &HashMap::from([("ARGUS_ROOT".into(), dir.path().display().to_string())]),
            dir.path(),
        )
        .unwrap();
        fs::create_dir_all(&cfg.src).unwrap();
        fs::create_dir_all(cfg.progs.parent().unwrap()).unwrap();
        fs::write(&cfg.progs, b"compiled program").unwrap();
        fs::write(
            cfg.src.join("progs.src"),
            if included {
                "argus_nav_test.qc\n"
            } else {
                "// argus_nav_test.qc\n"
            },
        )
        .unwrap();
        fs::write(
            cfg.src.join("argus_nav_dispatch.qc"),
            if dispatched {
                "if (mapname == \"test\") Argus_Nav_Spawn_test ();"
            } else {
                "// if (mapname == \"test\") Argus_Nav_Spawn_test ();"
            },
        )
        .unwrap();
        fs::write(cfg.src.join("argus_nav_test.qc"), "generated QC").unwrap();
        fs::write(
            cfg.src.join("argus_nav_test.qc.json"),
            r#"{"nodes":[[0,0,24]],"links":[]}"#,
        )
        .unwrap();
        cfg
    }

    fn install_fake(cfg: &mut Config) {
        cfg.basedir = cfg.root.join("engine");
        let dest = cfg.basedir.join(&cfg.game).join("progs.dat");
        fs::create_dir_all(dest.parent().unwrap()).unwrap();
        fs::copy(&cfg.progs, dest).unwrap();
    }

    #[test]
    fn registration_halves_are_frozen_independently() {
        for (included, dispatched) in [(false, false), (false, true), (true, false), (true, true)] {
            let dir = TestDir::new("nav-registration-proof").unwrap();
            let mut cfg = setup(&dir, included, dispatched);
            let capture = capture(&cfg).unwrap();
            record_build(&cfg, capture).unwrap();
            install_fake(&mut cfg);
            let mut snapshot = for_launch(&cfg, "test").unwrap();
            assert!(!CoverageSource::new(Some(&snapshot)).eligible_for_navigation_claims);
            snapshot.loaded_in_tape = Some(true);
            assert_eq!(snapshot.in_progs_src, included);
            assert_eq!(snapshot.in_dispatcher, dispatched);
            assert_eq!(snapshot.runtime_navigation(), included && dispatched);
            assert_eq!(
                CoverageSource::new(Some(&snapshot)).eligible_for_navigation_claims,
                included && dispatched
            );
        }
    }

    #[test]
    fn current_registration_is_never_proof_for_an_unrecorded_binary() {
        let dir = TestDir::new("nav-unknown-build").unwrap();
        let mut cfg = setup(&dir, true, true);
        install_fake(&mut cfg);
        let current = inventory(&cfg, "test");
        assert!(
            current.json_on_disk
                && current.qc_on_disk
                && current.in_progs_src
                && current.in_dispatcher
        );
        assert_eq!(current.installed_navigation, None);
        assert!(for_launch(&cfg, "test").is_none());
        assert!(!CoverageSource::new(None).eligible_for_navigation_claims);
    }

    #[test]
    fn historical_tape_keeps_its_build_graph_after_current_tree_changes() {
        let dir = TestDir::new("nav-history").unwrap();
        let mut cfg = setup(&dir, true, true);
        record_build(&cfg, capture(&cfg).unwrap()).unwrap();
        install_fake(&mut cfg);
        let old = for_launch(&cfg, "test").unwrap();
        let tape = dir.path().join("historic.log");
        let body = b"ARGUS init on test\nARGNAV 1 nodes, 0 links\nARGLOG Reap t 1.0 pos '0 0 24' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\nARGLOG Reap t 2.0 pos '0 0 24' spd 100 yaw 0 mode 2 st 0 gl 0 hp 100 frg 0\n";
        fs::write(&tape, body).unwrap();
        record_tape(&tape, body, Some(&old)).unwrap();
        fs::write(cfg.src.join("progs.src"), "// now unregistered\n").unwrap();
        fs::write(
            cfg.src.join("argus_nav_test.qc.json"),
            r#"{"nodes":[[9000,0,24]],"links":[]}"#,
        )
        .unwrap();
        let frozen = read_tape(&tape, "test").unwrap().unwrap();
        assert_eq!(frozen.graph.as_ref().unwrap()["nodes"][0][0], 0);
        assert!(frozen.runtime_navigation());
        assert!(!inventory(&cfg, "test").in_progs_src);
        let brief = crate::intel::brief_run(&cfg, tape.to_str().unwrap(), None).unwrap();
        let coverage = brief.nav_coverage.unwrap();
        assert_eq!(
            coverage.pct, 100,
            "proximity must use the old graph, not today's distant node"
        );
        assert_eq!(coverage.provenance.spatial_source, "build_snapshot");
        assert_eq!(coverage.provenance.runtime_navigation, Some(true));
        assert!(!coverage.current_tree.in_progs_src);

        // Recompiling identical program bytes must not overwrite their first receipt.
        record_build(&cfg, capture(&cfg).unwrap()).unwrap();
        assert_eq!(for_launch(&cfg, "test").unwrap(), old);
        assert!(read_tape(&tape, "dm4").is_err());
        fs::write(&tape, b"different tape").unwrap();
        assert!(read_tape(&tape, "test")
            .unwrap_err()
            .contains("does not match"));
    }

    #[test]
    fn changed_sources_do_not_get_a_build_receipt() {
        let dir = TestDir::new("nav-source-race").unwrap();
        let cfg = setup(&dir, true, true);
        let before = capture(&cfg).unwrap();
        fs::write(cfg.src.join("argus_nav_test.qc"), "changed during compile").unwrap();
        assert!(record_build(&cfg, before)
            .unwrap_err()
            .contains("source changed"));
        assert!(!cfg.root.join("backups/navigation_builds").exists());
    }

    #[test]
    fn a_formerly_uncompiled_graph_stays_uncompiled_after_registration() {
        let dir = TestDir::new("nav-old-uncompiled").unwrap();
        let mut cfg = setup(&dir, false, false);
        record_build(&cfg, capture(&cfg).unwrap()).unwrap();
        install_fake(&mut cfg);
        let old = for_launch(&cfg, "test").unwrap();
        let tape = dir.path().join("old.log");
        fs::write(&tape, b"old tape").unwrap();
        record_tape(&tape, b"old tape", Some(&old)).unwrap();
        fs::write(cfg.src.join("progs.src"), "argus_nav_test.qc\n").unwrap();
        fs::write(
            cfg.src.join("argus_nav_dispatch.qc"),
            "if (mapname == \"test\") Argus_Nav_Spawn_test ();",
        )
        .unwrap();
        let current = inventory(&cfg, "test");
        assert!(current.in_progs_src && current.in_dispatcher);
        assert_eq!(current.installed_navigation, Some(false));
        let historical = read_tape(&tape, "test").unwrap().unwrap();
        assert!(!historical.runtime_navigation());
        assert!(!CoverageSource::new(Some(&historical)).eligible_for_navigation_claims);
    }

    #[test]
    fn a_preexisting_temporary_receipt_is_not_ours_to_delete() {
        let dir = TestDir::new("nav-receipt-owner").unwrap();
        let tape = dir.path().join("test.log");
        let receipt = tape.with_extension("nav.json");
        let temp = receipt.with_extension(format!("{}.tmp", std::process::id()));
        fs::write(&temp, b"other writer").unwrap();
        assert!(record_tape(&tape, b"body", None).is_err());
        assert_eq!(fs::read(&temp).unwrap(), b"other writer");
        assert!(!receipt.exists());
    }
}
