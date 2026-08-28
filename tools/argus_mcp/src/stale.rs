//! Staleness self-awareness. Windows locks a running exe, so every
//! lab improvement lands in target-stage and waits for a client
//! restart - and historically the OLD server kept serving briefs
//! with a straight face (the goal_reach mislabels stayed live for
//! days after their fix was staged). Two teeth against that:
//!
//! 1. At startup, if a newer staged build exists, SWAP it in for the
//!    next restart automatically: the running image keeps executing
//!    (Windows allows renaming a running exe, not overwriting it),
//!    the on-disk path gets the new build, and no one has to
//!    remember the manual copy again.
//! 2. Every JSON tool response carries a `lab_stale` banner for the
//!    rest of the session, so a brief can never silently be the old
//!    parser's opinion.
//!
//! The swap used to require the running image to live under
//! `target/release`. The Windows lab client launches a copy at
//! `~/.grok/bin/argus-mcp.exe`, a path that layout never matched, so
//! staged 0.22 sat in the tree while the client kept a week-old
//! binary. When ARGUS_ROOT is set, the staged twin is also resolved
//! from the tree even if the running exe lives somewhere else.

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

static NOTE: OnceLock<Option<String>> = OnceLock::new();

fn staged_exe_name() -> &'static str {
    if cfg!(windows) {
        "argus-mcp.exe"
    } else {
        "argus-mcp"
    }
}

/// Staged binary under ARGUS_ROOT, if that env is set and the file exists.
pub fn staged_from_root(root: &Path) -> Option<PathBuf> {
    let p = root
        .join("tools")
        .join("argus_mcp")
        .join("target-stage")
        .join("release")
        .join(staged_exe_name());
    if p.exists() {
        Some(p)
    } else {
        None
    }
}

/// The staged twin of the running exe.
///
/// Prefer the cargo layout (`.../target/release` -> `.../target-stage/release`).
/// If the running image is a client copy (not under `target/release`), fall
/// back to `ARGUS_ROOT/tools/argus_mcp/target-stage/release`.
pub fn staged_twin_for(exe: &Path, root: Option<&Path>) -> Option<PathBuf> {
    if let Some(from_layout) = staged_twin_layout(exe) {
        if from_layout != exe {
            return Some(from_layout);
        }
    }
    let staged = staged_from_root(root?)?;
    if staged == exe {
        return None;
    }
    Some(staged)
}

/// The staged twin of the running exe, if the layout matches
/// (`.../target/release/argus-mcp.exe` ->
///  `.../target-stage/release/argus-mcp.exe`).
fn staged_twin_layout(exe: &Path) -> Option<PathBuf> {
    let file = exe.file_name()?;
    let release = exe.parent()?; // .../target/release
    let target = release.parent()?; // .../target
    if target.file_name()?.to_string_lossy() != "target" {
        return None;
    }
    let crate_dir = target.parent()?;
    let staged = crate_dir.join("target-stage").join("release").join(file);
    if staged == exe {
        return None;
    }
    Some(staged)
}

fn staged_twin(exe: &PathBuf) -> Option<PathBuf> {
    let root = std::env::var_os("ARGUS_ROOT").map(PathBuf::from);
    staged_twin_for(exe, root.as_deref())
}

/// Run once at startup: detect a newer staged build, swap it into
/// place for the NEXT restart, and remember the banner for this
/// session. Safe to call again (cached).
pub fn detect_and_swap() -> Option<String> {
    NOTE.get_or_init(|| {
        let exe = std::env::current_exe().ok()?;
        let staged = staged_twin(&exe)?;
        let live_m = std::fs::metadata(&exe).and_then(|m| m.modified()).ok()?;
        let staged_m = std::fs::metadata(&staged).and_then(|m| m.modified()).ok()?;
        if staged_m <= live_m {
            return None;
        }
        // newer staged build: rename the running image aside and put
        // the staged bytes on the served path
        let prev = exe.with_extension("prev.exe");
        let _ = std::fs::remove_file(&prev);
        let swapped = std::fs::rename(&exe, &prev).is_ok()
            && std::fs::copy(&staged, &exe).is_ok();
        Some(if swapped {
            "STALE BINARY: this session still runs the previous build (its briefs lack the newest lab features). The staged build has been swapped into place automatically - restart the MCP client to arm it.".to_string()
        } else {
            "STALE BINARY: a newer staged build exists at target-stage and could not be auto-swapped. This session's briefs lack the newest lab features - swap and restart the MCP client.".to_string()
        })
    })
    .clone()
}

/// The cached banner for response stamping.
pub fn banner() -> Option<String> {
    detect_and_swap()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn touch(p: &Path) {
        if let Some(parent) = p.parent() {
            fs::create_dir_all(parent).unwrap();
        }
        fs::write(p, b"x").unwrap();
    }

    #[test]
    fn layout_release_finds_stage() {
        let tmp = std::env::temp_dir().join(format!("argus-stale-layout-{}", std::process::id()));
        let _ = fs::remove_dir_all(&tmp);
        let exe = tmp
            .join("tools")
            .join("argus_mcp")
            .join("target")
            .join("release")
            .join(staged_exe_name());
        let staged = tmp
            .join("tools")
            .join("argus_mcp")
            .join("target-stage")
            .join("release")
            .join(staged_exe_name());
        touch(&exe);
        touch(&staged);
        let found = staged_twin_for(&exe, None).expect("layout twin");
        assert_eq!(found, staged);
        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn grok_bin_copy_finds_stage_via_root() {
        let tmp = std::env::temp_dir().join(format!("argus-stale-grok-{}", std::process::id()));
        let _ = fs::remove_dir_all(&tmp);
        let exe = tmp.join("grok-bin").join(staged_exe_name());
        let staged = tmp
            .join("tools")
            .join("argus_mcp")
            .join("target-stage")
            .join("release")
            .join(staged_exe_name());
        touch(&exe);
        touch(&staged);
        assert!(
            staged_twin_for(&exe, None).is_none(),
            "without ARGUS_ROOT a grok-bin copy has no twin"
        );
        let found = staged_twin_for(&exe, Some(&tmp)).expect("root twin");
        assert_eq!(found, staged);
        let _ = fs::remove_dir_all(&tmp);
    }
}
