//! A live run's claim on its run directory (#832).
//!
//! QuakeSpasm truncates `qconsole.log` in its working directory when it
//! starts, and every lab match runs in `runs/<run>/`. A second match given
//! the same run name while the first was alive therefore cut the head off
//! the live tape (three e1m7 band tapes lost their first 5.8 s, ARGNAV and
//! `ARGUS init` included, and briefed with exit code 0). The controller now
//! takes a lease on the directory before it spawns anything: a `.lease` file
//! created exclusively and holding the owning process id. A lease whose
//! owner has gone is stale and is taken over; a live one refuses the start.

use std::io::Write;
use std::path::{Path, PathBuf};

pub const LEASE_FILE: &str = ".lease";

#[derive(Debug)]
pub struct RunLease {
    path: PathBuf,
}

impl RunLease {
    /// Claim `run_dir` for this process, or say who holds it.
    pub fn acquire(run_dir: &Path, run_name: &str) -> Result<RunLease, String> {
        std::fs::create_dir_all(run_dir)
            .map_err(|e| format!("create run dir {}: {e}", run_dir.display()))?;
        let path = run_dir.join(LEASE_FILE);
        for _ in 0..2 {
            match std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)
            {
                Ok(mut file) => {
                    let _ = writeln!(file, "{}", std::process::id());
                    return Ok(RunLease { path });
                }
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    let holder = std::fs::read_to_string(&path)
                        .ok()
                        .and_then(|s| s.trim().parse::<u32>().ok());
                    // created but not yet written: another start is mid-claim
                    let young = std::fs::metadata(&path)
                        .and_then(|m| m.modified())
                        .ok()
                        .and_then(|m| m.elapsed().ok())
                        .is_some_and(|age| age < std::time::Duration::from_secs(10));
                    match holder {
                        Some(pid) if process_alive(pid) => {
                            return Err(format!(
                                "run {run_name} is live: runs/{run_name}/ is held by lab \
                                 process {pid}. A second engine there would truncate its \
                                 qconsole.log; pick another run name or stop that match"
                            ));
                        }
                        None if young => {
                            return Err(format!(
                                "run {run_name} is being claimed by another start right now"
                            ));
                        }
                        // the owner died without releasing: stale, take it over
                        _ => {
                            let _ = std::fs::remove_file(&path);
                        }
                    }
                }
                Err(e) => return Err(format!("lease {}: {e}", path.display())),
            }
        }
        Err(format!(
            "could not take the lease on runs/{run_name}/ (another start raced this one)"
        ))
    }
}

impl Drop for RunLease {
    fn drop(&mut self) {
        // only our own claim: a lease taken over after we were presumed
        // dead belongs to its new owner
        let mine = std::fs::read_to_string(&self.path)
            .ok()
            .and_then(|s| s.trim().parse::<u32>().ok())
            == Some(std::process::id());
        if mine {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

/// Whether a process with this id is running.
#[cfg(windows)]
pub fn process_alive(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::Threading::{
        GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
    };
    const STILL_ACTIVE: u32 = 259;
    if pid == std::process::id() {
        return true;
    }
    unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle.is_null() {
            return false;
        }
        let mut code = 0u32;
        let ok = GetExitCodeProcess(handle, &mut code);
        CloseHandle(handle);
        ok != 0 && code == STILL_ACTIVE
    }
}

/// Whether a process with this id is running.
#[cfg(not(windows))]
pub fn process_alive(pid: u32) -> bool {
    if pid == std::process::id() {
        return true;
    }
    let proc_root = Path::new("/proc");
    // without procfs there is no cheap answer; treat the lease as stale
    // rather than wedge every later start on it
    proc_root.is_dir() && proc_root.join(pid.to_string()).exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dir(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("argus-lease-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        d
    }

    #[test]
    fn a_live_run_refuses_a_second_start_and_release_frees_it() {
        let d = dir("live");
        let first = RunLease::acquire(&d, "probe").unwrap();
        let err = RunLease::acquire(&d, "probe").unwrap_err();
        assert!(err.contains("run probe is live"), "{err}");
        assert!(err.contains(&std::process::id().to_string()), "{err}");
        drop(first);
        assert!(!d.join(LEASE_FILE).exists());
        let again = RunLease::acquire(&d, "probe").unwrap();
        drop(again);
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn a_dead_owner_is_taken_over() {
        let d = dir("stale");
        std::fs::create_dir_all(&d).unwrap();
        // pid 0 never names a live user process on either platform
        std::fs::write(d.join(LEASE_FILE), "0\n").unwrap();
        let lease = RunLease::acquire(&d, "probe").expect("stale lease taken over");
        let held = std::fs::read_to_string(d.join(LEASE_FILE)).unwrap();
        assert_eq!(held.trim(), std::process::id().to_string());
        drop(lease);
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn a_fresh_unreadable_lease_is_a_claim_in_progress() {
        let d = dir("garbage");
        std::fs::create_dir_all(&d).unwrap();
        std::fs::write(d.join(LEASE_FILE), "not a pid").unwrap();
        let err = RunLease::acquire(&d, "probe").unwrap_err();
        assert!(err.contains("being claimed"), "{err}");
        let _ = std::fs::remove_dir_all(d);
    }

    #[test]
    fn a_lease_taken_over_is_not_removed_by_its_old_owner() {
        let d = dir("takeover");
        let lease = RunLease::acquire(&d, "probe").unwrap();
        std::fs::write(d.join(LEASE_FILE), "1\n").unwrap();
        drop(lease);
        assert!(
            d.join(LEASE_FILE).exists(),
            "another owner's lease survives"
        );
        let _ = std::fs::remove_dir_all(d);
    }
}
