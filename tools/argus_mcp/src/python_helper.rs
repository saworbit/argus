//! One async owner and deadline for lab Python children.
use crate::config::Config;
use std::path::{Path, PathBuf};
use std::process::{Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::io::AsyncReadExt;
use tokio::process::Command;

pub(crate) const NAV_DEADLINE: Duration = Duration::from_secs(180);
pub(crate) const ANALYZE_DEADLINE: Duration = Duration::from_secs(60);
pub(crate) const MAPGATE_DEADLINE: Duration = Duration::from_secs(30);

pub(crate) async fn run(
    cfg: &Config,
    script: &Path,
    args: &[&Path],
    deadline: Duration,
) -> Result<Output, String> {
    let mut command = Command::new(&cfg.python);
    command
        .arg(script)
        .args(args)
        .current_dir(&cfg.root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let mut child = command
        .spawn()
        .map_err(|e| format!("{}: failed to spawn ARGUS_PYTHON: {e}", script.display()))?;
    let mut stdout = child.stdout.take().expect("piped stdout");
    let mut stderr = child.stderr.take().expect("piped stderr");
    let mut out = Vec::new();
    let mut err = Vec::new();
    let result = tokio::time::timeout(deadline, async {
        tokio::try_join!(
            stdout.read_to_end(&mut out),
            stderr.read_to_end(&mut err),
            child.wait()
        )
    })
    .await;
    match result {
        Ok(Ok((_, _, status))) => Ok(Output {
            status,
            stdout: out,
            stderr: err,
        }),
        failure => {
            let mut message = match failure {
                Err(_) => format!(
                    "{} timed out after {}s",
                    script.display(),
                    deadline.as_secs_f64()
                ),
                Ok(Err(e)) => format!("{} capture failed: {e}", script.display()),
                _ => unreachable!(),
            };
            if let Err(e) = child.kill().await {
                message.push_str(&format!("; child cleanup failed: {e}"));
            }
            Err(message)
        }
    }
}

fn bytes(path: &Path) -> Result<Option<Vec<u8>>, String> {
    if path
        .symlink_metadata()
        .is_ok_and(|m| m.file_type().is_symlink())
    {
        return Err(format!("refusing helper output alias: {}", path.display()));
    }
    match std::fs::read(path) {
        Ok(data) => Ok(Some(data)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("{}: {e}", path.display())),
    }
}

static NEXT: AtomicU64 = AtomicU64::new(0);
struct File {
    target: PathBuf,
    staged: PathBuf,
    before: Option<Vec<u8>>,
    required: bool,
}

/// Only private files reach a running child. Publication has no await point.
pub(crate) struct Outputs {
    dir: PathBuf,
    files: Vec<File>,
}
impl Outputs {
    pub(crate) fn new() -> Result<Self, String> {
        let parent = std::env::temp_dir()
            .canonicalize()
            .map_err(|e| e.to_string())?;
        loop {
            let dir = parent.join(format!(
                "argus-helper-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            match std::fs::create_dir(&dir) {
                Ok(()) => {
                    return Ok(Self {
                        dir,
                        files: Vec::new(),
                    })
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(e) => return Err(format!("create helper workspace: {e}")),
            }
        }
    }
    pub(crate) fn input(&self, path: &Path) -> Result<(), String> {
        if let Some(data) = bytes(path)? {
            std::fs::write(
                self.dir.join(path.file_name().ok_or("missing input name")?),
                data,
            )
            .map_err(|e| e.to_string())?;
        }
        Ok(())
    }
    pub(crate) fn add(&mut self, target: &Path, required: bool) -> Result<PathBuf, String> {
        let before = bytes(target)?;
        let target = crate::paths::canonical_target(target)?;
        let staged = self
            .dir
            .join(target.file_name().ok_or("missing output name")?);
        if self.files.iter().any(|f| f.staged == staged) {
            return Err("colliding helper outputs".into());
        }
        self.files.push(File {
            target,
            staged: staged.clone(),
            before,
            required,
        });
        Ok(staged)
    }
    pub(crate) fn publish(&self) -> Result<(), String> {
        self.publish_with(|path, data| std::fs::write(path, data))
    }
    fn publish_with(
        &self,
        mut write: impl FnMut(&Path, &[u8]) -> std::io::Result<()>,
    ) -> Result<(), String> {
        let mut pending = Vec::new();
        for file in &self.files {
            if crate::paths::canonical_target(&file.target)? != file.target {
                return Err(format!(
                    "output alias changed during helper: {}",
                    file.target.display()
                ));
            }
            if bytes(&file.target)? != file.before {
                return Err(format!(
                    "output changed during helper: {}",
                    file.target.display()
                ));
            }
            match bytes(&file.staged)? {
                Some(data) => pending.push((file, data)),
                None if file.required => {
                    return Err(format!("helper did not write {}", file.staged.display()))
                }
                None => {}
            }
        }
        for (index, (file, data)) in pending.iter().enumerate() {
            if let Err(e) = write(&file.target, data) {
                let mut error = format!("publish {}: {e}", file.target.display());
                for (file, _) in &pending[..=index] {
                    let rollback = match &file.before {
                        Some(data) => std::fs::write(&file.target, data),
                        None => match std::fs::remove_file(&file.target) {
                            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
                            result => result,
                        },
                    };
                    if let Err(e) = rollback {
                        error.push_str(&format!("; rollback {}: {e}", file.target.display()));
                    }
                }
                return Err(error);
            }
        }
        Ok(())
    }
}
impl Drop for Outputs {
    fn drop(&mut self) {
        // `dir` is an absolute child of canonical temp_dir, exclusively created
        // above. Refuse replacement aliases before recursive cleanup.
        let cleanup = || -> std::io::Result<()> {
            if self.dir.symlink_metadata()?.file_type().is_symlink()
                || self.dir.canonicalize()? != self.dir
            {
                return Err(std::io::Error::other("helper workspace changed ownership"));
            }
            std::fs::remove_dir_all(&self.dir)
        };
        if let Err(e) = cleanup() {
            eprintln!("helper workspace cleanup {}: {e}", self.dir.display());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn publication_preflights_changes_and_rolls_back_partial_writes() {
        let root = crate::test_support::TestDir::new("helper-publish").unwrap();
        let a = root.path().join("a");
        let b = root.path().join("b");
        std::fs::write(&a, "old").unwrap();
        let mut outputs = Outputs::new().unwrap();
        let sa = outputs.add(&a, true).unwrap();
        let sb = outputs.add(&b, true).unwrap();
        std::fs::write(sa, "new").unwrap();
        std::fs::write(sb, "new").unwrap();
        let mut calls = 0;
        let error = outputs
            .publish_with(|p, data| {
                calls += 1;
                std::fs::write(p, data)?;
                if calls == 2 {
                    return Err(std::io::Error::other("injected write failure"));
                }
                Ok(())
            })
            .unwrap_err();
        assert!(error.contains("injected write failure"));
        assert_eq!(std::fs::read(&a).unwrap(), b"old");
        assert!(!b.exists());
        std::fs::write(&a, "external").unwrap();
        assert!(outputs
            .publish()
            .unwrap_err()
            .contains("changed during helper"));
        assert!(!b.exists());
    }

    fn config() -> Config {
        crate::config::Config::load_for_reads().unwrap()
    }
    async fn wait_file(path: &Path) {
        tokio::time::timeout(Duration::from_secs(5), async {
            while !path.exists() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("helper did not start");
    }
    #[tokio::test(flavor = "current_thread")]
    async fn sleeping_helper_yields_and_is_killed_on_deadline_and_cancel() {
        let cfg = config();
        assert!(
            cfg.python.is_file(),
            "Python required for helper lifetime regression"
        );
        let root = crate::test_support::TestDir::new("helper-lifetime").unwrap();
        let script = root.path().join("wait.py");
        std::fs::write(&script, "import pathlib,sys,time\npathlib.Path(sys.argv[1]).write_text('started')\ntime.sleep(1.5)\npathlib.Path(sys.argv[2]).write_text('orphan')\n").unwrap();
        let started = root.path().join("started");
        let orphan = root.path().join("orphan");
        let args = [&started as &Path, &orphan as &Path];
        let work = run(&cfg, &script, &args, Duration::from_millis(400));
        let observer = async {
            wait_file(&started).await;
            assert!(!orphan.exists());
        };
        let (result, ()) = tokio::join!(work, observer);
        assert!(result.unwrap_err().contains("timed out"));
        std::fs::remove_file(&started).unwrap();
        let c = cfg.clone();
        let s = script.clone();
        let a = started.clone();
        let b = orphan.clone();
        let task =
            tokio::spawn(async move { run(&c, &s, &[&a, &b], Duration::from_secs(10)).await });
        wait_file(&started).await;
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        tokio::time::sleep(Duration::from_millis(1700)).await;
        assert!(
            !orphan.exists(),
            "cancelled or timed-out Python survived its owner"
        );
    }
    #[tokio::test]
    async fn captures_both_streams_nonzero_exit_and_null_stdin() {
        let cfg = config();
        let root = crate::test_support::TestDir::new("helper-capture").unwrap();
        let script = root.path().join("capture.py");
        std::fs::write(&script, "import sys\nassert sys.stdin.read()==''\nsys.stdout.write('o'*200000)\nsys.stderr.write('e'*200000)\nsys.exit(7)\n").unwrap();
        let out = run(&cfg, &script, &[], Duration::from_secs(5))
            .await
            .unwrap();
        assert_eq!(out.status.code(), Some(7));
        assert_eq!(out.stdout.len(), 200000);
        assert_eq!(out.stderr.len(), 200000);
    }
}
