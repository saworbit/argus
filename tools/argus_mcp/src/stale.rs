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

use std::path::PathBuf;
use std::sync::OnceLock;

static NOTE: OnceLock<Option<String>> = OnceLock::new();

/// The staged twin of the running exe, if the layout matches
/// (`.../target/release/argus-mcp.exe` ->
///  `.../target-stage/release/argus-mcp.exe`).
fn staged_twin(exe: &PathBuf) -> Option<PathBuf> {
    let file = exe.file_name()?;
    let release = exe.parent()?; // .../target/release
    let target = release.parent()?; // .../target
    if target.file_name()?.to_string_lossy() != "target" {
        return None;
    }
    let crate_dir = target.parent()?;
    let staged = crate_dir.join("target-stage").join("release").join(file);
    if staged == *exe {
        return None;
    }
    Some(staged)
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
