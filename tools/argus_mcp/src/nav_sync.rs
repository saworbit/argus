//! Register generated `argus_nav_<map>.qc` in the dispatcher and progs.src.

use crate::config::Config;
use serde::Serialize;
use std::fs;

/// Independent build entries required to register a map.
#[derive(Debug, Clone, Copy)]
pub struct Registration {
    /// A map-name branch is present in the dispatcher outside comments.
    pub branch: bool,
    /// The generated QC filename occupies a complete progs.src line.
    pub progs: bool,
}

impl Registration {
    /// Both the dispatcher branch and the compiler input must be present.
    pub fn complete(self) -> bool {
        self.branch && self.progs
    }
}

/// Check both build files; missing or unreadable files count as absent entries.
pub fn registration(cfg: &Config, map: &str) -> Registration {
    registration_text(
        &fs::read_to_string(cfg.src.join("argus_nav_dispatch.qc")).unwrap_or_default(),
        &fs::read_to_string(cfg.src.join("progs.src")).unwrap_or_default(),
        map,
    )
}

pub(crate) fn registration_text(dispatch: &str, progs: &str, map: &str) -> Registration {
    static COMMENTS: std::sync::OnceLock<regex::Regex> = std::sync::OnceLock::new();
    let comments = COMMENTS.get_or_init(|| {
        regex::Regex::new(r#"(?s)"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\r\n]*"#).unwrap()
    });
    let strip = |text: &str| {
        comments
            .replace_all(text, |caps: &regex::Captures<'_>| {
                if caps[0].starts_with('"') {
                    caps[0].to_string()
                } else {
                    " ".into()
                }
            })
            .into_owned()
    };
    let dispatch = strip(dispatch);
    let progs = strip(progs);
    Registration {
        branch: dispatch.contains(&format!("mapname == \"{map}\"")),
        progs: progs
            .lines()
            .any(|line| line.trim() == format!("argus_nav_{map}.qc")),
    }
}

async fn require_playable_first_registration(cfg: &Config, map: &str) -> Result<(), String> {
    let bsp = cfg.maps.join(format!("{map}.bsp"));
    let graph = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    if !bsp.is_file() || !graph.is_file() {
        return Err(format!(
            "{map} is experimental: need {} and {} before registration",
            bsp.display(),
            graph.display()
        ));
    }
    let script = cfg.root.join("tools").join("argus_mapgate.py");
    if !script.is_file() || !cfg.python.is_file() {
        return Err(format!(
            "{map} is experimental: the playability gate needs ARGUS_PYTHON"
        ));
    }
    let output = crate::python_helper::run(
        cfg,
        &script,
        &[&bsp, &graph],
        crate::python_helper::MAPGATE_DEADLINE,
    )
    .await?;
    if output.status.success() {
        return Ok(());
    }
    let stdout = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let reason = stdout
        .lines()
        .filter(|line| !line.trim().is_empty())
        .collect::<Vec<_>>()
        .join("; ");
    Err(format!("{map} is experimental: {reason}"))
}

#[derive(Debug, Clone, Serialize)]
pub struct NavSyncReport {
    pub ok: bool,
    pub maps: Vec<String>,
    pub added_dispatch: Vec<String>,
    pub added_progs: Vec<String>,
    pub already: Vec<String>,
    pub headline: String,
}

pub async fn nav_sync_dispatch(cfg: &Config) -> Result<NavSyncReport, String> {
    let mut maps = Vec::new();
    let rd = fs::read_dir(&cfg.src).map_err(|e| format!("ARGUS_SRC: {e}"))?;
    for ent in rd {
        let ent = ent.map_err(|e| format!("read ARGUS_SRC entry: {e}"))?;
        let name = ent.file_name().to_string_lossy().into_owned();
        if let Some(map) = name
            .strip_prefix("argus_nav_")
            .and_then(|s| s.strip_suffix(".qc"))
        {
            if map == "dispatch" {
                continue;
            }
            let normalized =
                crate::paths::map_name(map).map_err(|e| format!("refused {name}: {e}"))?;
            if normalized != map {
                return Err(format!(
                    "refused {name}: regenerate with canonical map name {normalized}"
                ));
            }
            maps.push(normalized);
        }
    }
    maps.sort();
    if maps.is_empty() {
        return Err("no argus_nav_<map>.qc files under ARGUS_SRC".into());
    }

    let mut added_dispatch = Vec::new();
    let mut added_progs = Vec::new();
    let mut already = Vec::new();

    let disp_path = cfg.src.join("argus_nav_dispatch.qc");
    let mut disp =
        fs::read_to_string(&disp_path).map_err(|e| format!("{}: {e}", disp_path.display()))?;
    let progs_path = cfg.src.join("progs.src");
    let mut progs =
        fs::read_to_string(&progs_path).map_err(|e| format!("{}: {e}", progs_path.display()))?;

    let mut publication = crate::python_helper::Outputs::new()?;
    let staged_dispatch = publication.add(&disp_path, false)?;
    let staged_progs = publication.add(&progs_path, false)?;
    for map in &maps {
        let spawn = format!("Argus_Nav_Spawn_{map}");
        let state = registration_text(&disp, &progs, map);
        let has_branch = state.branch;
        let qc_line = format!("argus_nav_{map}.qc");
        let has_qc = state.progs;
        if !(has_branch && has_qc) {
            require_playable_first_registration(cfg, map).await?;
        }
        if has_branch {
            already.push(map.clone());
        } else {
            disp = insert_dispatch_branch(&disp, map, &spawn)?;
            added_dispatch.push(map.clone());
        }
        if !has_qc {
            progs = insert_progs_line(&progs, &qc_line)?;
            added_progs.push(map.clone());
        }
    }

    if !added_dispatch.is_empty() {
        fs::write(staged_dispatch, disp).map_err(|e| format!("stage dispatch: {e}"))?;
    }
    if !added_progs.is_empty() {
        fs::write(staged_progs, progs).map_err(|e| format!("stage progs.src: {e}"))?;
    }
    publication.publish()?;

    let headline = if added_dispatch.is_empty() && added_progs.is_empty() {
        format!("dispatcher already covers {}", maps.join(", "))
    } else {
        format!(
            "registered {} dispatch branch(es), {} progs.src line(s)",
            added_dispatch.len(),
            added_progs.len()
        )
    };
    Ok(NavSyncReport {
        ok: true,
        maps,
        added_dispatch,
        added_progs,
        already,
        headline,
    })
}

fn insert_dispatch_branch(src: &str, map: &str, spawn: &str) -> Result<String, String> {
    // Insert before the closing `};` of Argus_Nav_Spawn.
    let needle = "};";
    let Some(idx) = src.rfind(needle) else {
        return Err("argus_nav_dispatch.qc: no closing };".into());
    };
    let indent = "    ";
    let branch = format!("{indent}else if (mapname == \"{map}\")\n{indent}    {spawn} ();\n");
    let mut out = String::new();
    out.push_str(&src[..idx]);
    out.push_str(&branch);
    out.push_str(&src[idx..]);
    Ok(out)
}

fn insert_progs_line(src: &str, qc_line: &str) -> Result<String, String> {
    if let Some(idx) = src.find("argus_nav_dispatch.qc") {
        let mut out = String::new();
        out.push_str(&src[..idx]);
        out.push_str(qc_line);
        out.push('\n');
        out.push_str(&src[idx..]);
        return Ok(out);
    }
    Err("progs.src has no argus_nav_dispatch.qc line to insert before".into())
}

#[cfg(test)]
mod tests {
    #[tokio::test]
    async fn invalid_nav_filename_is_reported_before_registration_writes() {
        let dir = crate::test_support::TestDir::new("nav-invalid-name").unwrap();
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([(
                "ARGUS_ROOT".into(),
                dir.path().display().to_string(),
            )]),
            dir.path(),
        )
        .unwrap();
        fs::create_dir_all(&cfg.src).unwrap();
        fs::write(cfg.src.join("argus_nav_my-map.qc"), "graph").unwrap();
        for name in ["argus_nav_dispatch.qc", "progs.src"] {
            fs::write(cfg.src.join(name), "unchanged").unwrap();
        }
        let error = nav_sync_dispatch(&cfg).await.unwrap_err();
        assert!(error.contains("argus_nav_my-map.qc"), "{error}");
        for name in ["argus_nav_dispatch.qc", "progs.src"] {
            assert_eq!(fs::read_to_string(cfg.src.join(name)).unwrap(), "unchanged");
        }
    }
    use super::*;

    #[test]
    fn registration_string_and_comment_parity() {
        let cases: serde_json::Value =
            serde_json::from_str(include_str!("../../testdata/registration.json")).unwrap();
        for case in cases.as_array().unwrap() {
            let state = registration_text(
                case["dispatch"].as_str().unwrap(),
                case["progs"].as_str().unwrap(),
                "fixture",
            );
            assert_eq!(
                serde_json::json!([state.branch, state.progs]),
                case["expected"],
                "{case}"
            );
        }
    }

    #[test]
    fn registration_ignores_comments_and_requires_an_exact_progs_line() {
        let branch = "if (mapname == \"fixture\") spawn ();";
        for (dispatch, progs, expected) in [
            (branch, "argus_nav_fixture.qc\n", (true, true)),
            (branch, "", (true, false)),
            ("", "argus_nav_fixture.qc\n", (false, true)),
            ("// if (mapname == \"fixture\")", "", (false, false)),
            ("/* if (mapname == \"fixture\") */", "", (false, false)),
            (branch, "// argus_nav_fixture.qc\n", (true, false)),
            (branch, "argus_nav_fixture.qc.bak\n", (true, false)),
        ] {
            let state = registration_text(dispatch, progs, "fixture");
            assert_eq!((state.branch, state.progs), expected);
        }
    }

    #[test]
    fn registration_requires_both_build_entries_on_read_surfaces() {
        let root = crate::test_support::TestDir::new("nav-registration").unwrap();
        let mut cfg = Config::load_for_reads().unwrap();
        cfg.root = root.path().to_path_buf();
        cfg.src = cfg.root.join("src");
        cfg.maps = cfg.root.join("maps");
        cfg.basedir = cfg.root.join("engine");
        fs::create_dir_all(&cfg.src).unwrap();
        fs::create_dir_all(&cfg.maps).unwrap();
        fs::write(
            cfg.maps.join("fixture.bsp"),
            crate::bsp::write_mini_bsp(
                "{\n\"classname\" \"worldspawn\"\n}\n",
                [0.0; 3],
                [128.0; 3],
            ),
        )
        .unwrap();
        fs::write(
            cfg.src.join("argus_nav_fixture.qc.json"),
            r#"{"nodes":[[0,0,24]],"links":[]}"#,
        )
        .unwrap();
        fs::write(
            cfg.src.join("argus_nav_dispatch.qc"),
            "if (mapname == \"fixture\") Argus_Nav_Spawn_fixture ();\n",
        )
        .unwrap();
        for (index, (progs, expected)) in [
            ("argus_nav_dispatch.qc\n", false),
            ("argus_nav_fixture.qc\nargus_nav_dispatch.qc\n", true),
        ]
        .into_iter()
        .enumerate()
        {
            fs::write(cfg.src.join("progs.src"), progs).unwrap();
            fs::OpenOptions::new()
                .write(true)
                .open(cfg.src.join("progs.src"))
                .unwrap()
                .set_modified(
                    std::time::UNIX_EPOCH + std::time::Duration::from_secs(100 + index as u64),
                )
                .unwrap();
            let atlas = crate::cartograph::cartograph(&cfg, "fixture").unwrap();
            assert_eq!(atlas.dispatcher_known, expected);
            let lab = crate::lab::lab_status(&cfg, None);
            assert_eq!(
                lab.maps
                    .iter()
                    .find(|m| m.name == "fixture")
                    .unwrap()
                    .dispatcher,
                expected
            );
        }
    }

    #[test]
    fn inserts_branch_before_close() {
        let src = "void() Argus_Nav_Spawn =\n{\n    if (mapname == \"dm4\")\n        Argus_Nav_Spawn_dm4 ();\n};\n";
        let out = insert_dispatch_branch(src, "e1m1", "Argus_Nav_Spawn_e1m1").unwrap();
        assert!(out.contains("mapname == \"e1m1\""));
        assert!(out.contains("Argus_Nav_Spawn_e1m1"));
        assert!(out.find("e1m1").unwrap() < out.rfind("};").unwrap());
    }

    #[test]
    fn inserts_progs_before_dispatch() {
        let src = "argus_nav_dm4.qc\nargus_nav_dispatch.qc\nargus.qc\n";
        let out = insert_progs_line(src, "argus_nav_e1m1.qc").unwrap();
        assert!(out.contains("argus_nav_e1m1.qc\nargus_nav_dispatch.qc"));
    }

    #[tokio::test]
    async fn sync_does_not_bypass_the_first_registration_gate() {
        let temp = std::env::temp_dir().join(format!("argus-nav-sync-gate-{}", std::process::id()));
        let _ = fs::remove_dir_all(&temp);
        let src = temp.join("src");
        let maps = temp.join("maps");
        fs::create_dir_all(&src).unwrap();
        fs::create_dir_all(&maps).unwrap();
        fs::write(src.join("argus_nav_newmap.qc"), "fixture").unwrap();
        fs::write(
            src.join("argus_nav_newmap.qc.json"),
            r#"{"nodes": [], "links": []}"#,
        )
        .unwrap();
        fs::write(
            src.join("argus_nav_dispatch.qc"),
            "void() Argus_Nav_Spawn =\n{\n};\n",
        )
        .unwrap();
        fs::write(src.join("progs.src"), "argus_nav_dispatch.qc\n").unwrap();
        let mut cfg = Config::load_for_reads().expect("repo config");
        cfg.src = src.clone();
        cfg.maps = maps;

        let err = nav_sync_dispatch(&cfg).await.unwrap_err();

        assert!(err.contains("newmap is experimental"), "{err}");
        assert!(!fs::read_to_string(src.join("progs.src"))
            .unwrap()
            .contains("argus_nav_newmap.qc"));
        let _ = fs::remove_dir_all(&temp);
    }
}
