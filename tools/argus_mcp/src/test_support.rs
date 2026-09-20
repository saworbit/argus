use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, MutexGuard};
use std::time::{SystemTime, UNIX_EPOCH};

static GIT_TEST_LOCK: Mutex<()> = Mutex::new(());
static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

/// Git-for-Windows processes from otherwise independent fixture repositories
/// have intermittently collided under the crate's default parallel test run.
/// One crate-wide lock covers the complete lifetime of every Git-backed test;
/// module-local locks leave the cross-module race intact.
pub(crate) fn git_test_lock() -> MutexGuard<'static, ()> {
    GIT_TEST_LOCK.lock().unwrap_or_else(|p| p.into_inner())
}

/// A collision-proof test directory that is removed on both success and panic.
pub(crate) struct TestDir {
    path: PathBuf,
}

impl TestDir {
    pub(crate) fn new(tag: &str) -> std::io::Result<Self> {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "argus-{tag}-{}-{stamp}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir_all(&path)?;
        Ok(Self { path })
    }

    pub(crate) fn path(&self) -> &Path {
        &self.path
    }
}

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}

/// Run a fixture Git command without discarding the only useful evidence when
/// it fails. Callers may skip only the initial `git init` when Git is absent;
/// every later fixture command should surface this error verbatim.
pub(crate) fn run_git(root: &Path, args: &[&str]) -> Result<(), String> {
    let mut command = Command::new("git");
    command.arg("-C").arg(root).args(args);
    let output = crate::child_process::output_with_windows_loader_retry(&mut command)
        .map_err(|error| format!("git {args:?} in {}: {error}", root.display()))?;
    if output.status.success() {
        return Ok(());
    }
    Err(format!(
        "git {args:?} in {} exited {}\nstdout:\n{}\nstderr:\n{}",
        root.display(),
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_directories_are_unique_and_clean_themselves() {
        let first = TestDir::new("lifetime").unwrap();
        let second = TestDir::new("lifetime").unwrap();
        assert_ne!(first.path(), second.path());
        let first_path = first.path().to_path_buf();
        drop(first);
        assert!(!first_path.exists(), "temporary repository survived drop");
    }

    #[test]
    fn failed_git_commands_keep_the_diagnostic_streams() {
        let _gate = git_test_lock();
        let root = TestDir::new("git-error").unwrap();
        let error = run_git(root.path(), &["argus-definitely-not-a-command"]).unwrap_err();
        assert!(error.contains("argus-definitely-not-a-command"), "{error}");
        assert!(error.contains("exited"), "{error}");
        assert!(error.contains("stdout:"), "{error}");
        assert!(error.contains("stderr:"), "{error}");
    }
}
