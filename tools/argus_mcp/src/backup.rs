//! Dated backups of progs.dat and generated nav, plus restore.

use crate::config::Config;
use chrono::Local;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackupManifest {
    pub id: String,
    pub created: String,
    pub files: Vec<BackupFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackupFile {
    pub rel: String,
    pub restore_to: String,
    pub bytes: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct BackupEntry {
    pub id: String,
    pub created: String,
    pub files: usize,
    pub path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct BackupResult {
    pub ok: bool,
    pub id: String,
    pub path: String,
    pub files: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

pub fn backups_dir(cfg: &Config) -> PathBuf {
    cfg.root.join("backups")
}

pub fn list_backups(cfg: &Config) -> Vec<BackupEntry> {
    let dir = backups_dir(cfg);
    let mut out = Vec::new();
    let Ok(rd) = fs::read_dir(&dir) else {
        return out;
    };
    for ent in rd.flatten() {
        let path = ent.path();
        if !path.is_dir() {
            continue;
        }
        let id = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();
        if id.is_empty() || id.starts_with('.') {
            continue;
        }
        let man = read_manifest(&path).unwrap_or(BackupManifest {
            id: id.clone(),
            created: id.clone(),
            files: Vec::new(),
        });
        out.push(BackupEntry {
            id: man.id,
            created: man.created,
            files: man.files.len(),
            path: path.display().to_string(),
        });
    }
    out.sort_by(|a, b| b.id.cmp(&a.id));
    out
}

pub fn take_backup(cfg: &Config) -> BackupResult {
    let id = Local::now().format("%Y%m%d-%H%M%S").to_string();
    let dest = backups_dir(cfg).join(&id);
    if let Err(e) = fs::create_dir_all(&dest) {
        return BackupResult {
            ok: false,
            id,
            path: dest.display().to_string(),
            files: 0,
            error: Some(format!("create backup dir: {e}")),
        };
    }
    let mut files = Vec::new();
    for (src, rel) in backup_sources(cfg) {
        if !src.is_file() {
            continue;
        }
        let target = dest.join(&rel);
        if let Some(parent) = target.parent() {
            let _ = fs::create_dir_all(parent);
        }
        match fs::copy(&src, &target) {
            Ok(n) => files.push(BackupFile {
                rel,
                restore_to: src.display().to_string(),
                bytes: n,
            }),
            Err(e) => {
                return BackupResult {
                    ok: false,
                    id,
                    path: dest.display().to_string(),
                    files: files.len(),
                    error: Some(format!("copy {}: {e}", src.display())),
                };
            }
        }
    }
    let man = BackupManifest {
        id: id.clone(),
        created: id.clone(),
        files: files.clone(),
    };
    let _ = fs::write(
        dest.join("manifest.json"),
        serde_json::to_string_pretty(&man).unwrap_or_else(|_| "{}".into()),
    );
    BackupResult {
        ok: true,
        id,
        path: dest.display().to_string(),
        files: files.len(),
        error: None,
    }
}

pub fn restore_backup(cfg: &Config, id: &str) -> Result<BackupResult, String> {
    let id = safe_backup_id(id).ok_or("bad backup id")?;
    let dir = backups_dir(cfg).join(&id);
    if !dir.is_dir() {
        return Err(format!("no backup {id}"));
    }
    let man = read_manifest(&dir).ok_or("backup has no manifest.json")?;
    let mut restored = 0u32;
    // A `?` on each copy used to abandon the restore midway with no
    // rollback and no account of what had already landed. Try them all
    // and report what failed.
    let mut failed: Vec<String> = Vec::new();
    for f in &man.files {
        let rel = safe_rel(&f.rel).ok_or_else(|| format!("unsafe path in manifest: {}", f.rel))?;
        let src = dir.join(&rel);
        if !src.is_file() {
            failed.push(format!("{}: missing from the backup", f.rel));
            continue;
        }
        let dest = restore_dest(cfg, &f.restore_to, &rel)?;
        if let Some(parent) = dest.parent() {
            let _ = fs::create_dir_all(parent);
        }
        match fs::copy(&src, &dest) {
            Ok(_) => restored += 1,
            Err(e) => failed.push(format!("{}: {e}", dest.display())),
        }
    }
    Ok(BackupResult {
        ok: failed.is_empty(),
        id,
        path: dir.display().to_string(),
        files: restored as usize,
        error: if failed.is_empty() {
            None
        } else {
            Some(format!(
                "restored {restored} of {}, failed: {}",
                man.files.len(),
                failed.join("; ")
            ))
        },
    })
}

fn backup_sources(cfg: &Config) -> Vec<(PathBuf, String)> {
    let mut out = vec![
        (cfg.progs.clone(), rel_under(&cfg.root, &cfg.progs)),
        (
            cfg.src.join("progs.src"),
            "src/progs.src".into(),
        ),
        (
            cfg.src.join("argus_nav_dispatch.qc"),
            "src/argus_nav_dispatch.qc".into(),
        ),
    ];
    // Key install paths by INDEX when they sit outside the root.
    // rel_under falls back to the bare file name, so with a basedir
    // outside the repo the lab install and the rerelease copy both
    // keyed as "progs.dat" and the dedup below silently dropped one -
    // missing from the backup and from every later restore, with
    // ok: true reported.
    for (i, dest) in cfg.install_paths().into_iter().enumerate() {
        let key = match dest.strip_prefix(&cfg.root) {
            Ok(p) => p.to_string_lossy().replace('\\', "/"),
            Err(_) => format!(
                "install{i}/{}",
                dest.file_name()
                    .and_then(|s| s.to_str())
                    .unwrap_or("progs.dat")
            ),
        };
        out.push((dest, key));
    }
    if let Ok(rd) = fs::read_dir(&cfg.src) {
        for ent in rd.flatten() {
            let p = ent.path();
            let name = p
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_string();
            if name.starts_with("argus_nav_") && name.ends_with(".qc") {
                out.push((p, format!("src/{name}")));
            }
        }
    }
    out.sort_by(|a, b| a.1.cmp(&b.1));
    out.dedup_by(|a, b| a.1 == b.1);
    out
}

fn rel_under(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_else(|_| {
            path.file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("file")
                .to_string()
        })
}

fn read_manifest(dir: &Path) -> Option<BackupManifest> {
    let text = fs::read_to_string(dir.join("manifest.json")).ok()?;
    serde_json::from_str(&text).ok()
}

pub fn safe_backup_id(id: &str) -> Option<String> {
    let id = id.trim();
    if id.is_empty() || id.len() > 32 {
        return None;
    }
    if !id
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return None;
    }
    if id.contains("..") {
        return None;
    }
    Some(id.to_string())
}

fn restore_dest(cfg: &Config, restore_to: &str, rel: &str) -> Result<std::path::PathBuf, String> {
    if !restore_to.is_empty() {
        let dest = std::path::PathBuf::from(restore_to);
        if dest_allowed(cfg, &dest) {
            return Ok(dest);
        }
        return Err(format!("restore path not allowed: {restore_to}"));
    }
    Ok(cfg.root.join(rel))
}

fn dest_allowed(cfg: &Config, dest: &Path) -> bool {
    let dest = dest.to_path_buf();
    if dest.starts_with(&cfg.root) {
        return true;
    }
    if !cfg.basedir.as_os_str().is_empty() && dest.starts_with(&cfg.basedir) {
        return true;
    }
    let s = dest.to_string_lossy();
    s.contains("Nightdive Studios") && s.contains("Quake")
}

fn safe_rel(rel: &str) -> Option<String> {
    let rel = rel.replace('\\', "/");
    if rel.is_empty() || rel.starts_with('/') || rel.contains("..") {
        return None;
    }
    Some(rel)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::load_for_reads_from;
    use std::collections::HashMap;

    #[test]
    fn backup_and_restore_roundtrip() {
        let root = std::env::temp_dir().join(format!("argus-bak-{}", std::process::id()));
        let src = root.join("src");
        let lq1 = root.join("lq1");
        fs::create_dir_all(&src).unwrap();
        fs::create_dir_all(&lq1).unwrap();
        fs::write(lq1.join("progs.dat"), b"PROGS-A").unwrap();
        fs::write(src.join("progs.src"), b"src-a").unwrap();
        fs::write(src.join("argus_nav_dispatch.qc"), b"disp-a").unwrap();
        fs::write(src.join("argus_nav_dm4.qc"), b"nav-a").unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let taken = take_backup(&cfg);
        assert!(taken.ok, "{taken:?}");
        assert!(taken.files >= 3);

        fs::write(lq1.join("progs.dat"), b"PROGS-B").unwrap();
        fs::write(src.join("argus_nav_dm4.qc"), b"nav-b").unwrap();
        restore_backup(&cfg, &taken.id).unwrap();
        assert_eq!(fs::read(lq1.join("progs.dat")).unwrap(), b"PROGS-A");
        assert_eq!(fs::read(src.join("argus_nav_dm4.qc")).unwrap(), b"nav-a");
        assert!(safe_backup_id("../x").is_none());
        assert!(safe_rel("../etc/passwd").is_none());
        let _ = fs::remove_dir_all(&root);
    }

    // #215: rel_under falls back to the bare file name for any path
    // outside the root, so two out-of-tree installs both keyed as
    // "progs.dat" and the dedup dropped one - missing from the backup
    // and from every later restore, with ok: true reported.
    #[test]
    fn two_installs_outside_the_root_both_survive() {
        let base = std::env::temp_dir().join(format!("argus-bak2-{}", std::process::id()));
        let root = base.join("repo");
        let outside = base.join("steam");
        fs::create_dir_all(root.join("src")).unwrap();
        fs::create_dir_all(root.join("lq1")).unwrap();
        fs::create_dir_all(outside.join("argus")).unwrap();
        fs::write(root.join("lq1/progs.dat"), b"PROGS").unwrap();
        fs::write(outside.join("argus/progs.dat"), b"OUTSIDE").unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        env.insert("ARGUS_BASEDIR".into(), outside.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();

        let keys: Vec<String> = backup_sources(&cfg).into_iter().map(|(_, k)| k).collect();
        let mut uniq = keys.clone();
        uniq.sort();
        uniq.dedup();
        assert_eq!(keys.len(), uniq.len(), "duplicate manifest keys: {keys:?}");

        let outside_keys: Vec<&String> = keys
            .iter()
            .filter(|k| k.starts_with("install"))
            .collect();
        assert!(
            !outside_keys.is_empty(),
            "an out-of-tree install must get an indexed key, got {keys:?}"
        );

        let taken = take_backup(&cfg);
        assert!(taken.ok, "{taken:?}");
        fs::write(outside.join("argus/progs.dat"), b"CLOBBERED").unwrap();
        let r = restore_backup(&cfg, &taken.id).unwrap();
        assert!(r.ok, "{r:?}");
        assert_eq!(
            fs::read(outside.join("argus/progs.dat")).unwrap(),
            b"OUTSIDE",
            "the out-of-tree install must come back"
        );
        let _ = fs::remove_dir_all(&base);
    }
}
