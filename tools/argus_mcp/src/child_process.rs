use std::io::{self, Read};
use std::process::{Child, Command, Output, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

// NTSTATUS 0xc0000142, observed from Git-for-Windows when the parallel Rust
// suite briefly exhausts process-loader resources. The child was never able to
// run, so retrying is safe; no other exit status is retried.
const WINDOWS_DLL_INIT_FAILED: i32 = -1_073_741_502;
const MAX_ATTEMPTS: u32 = 4;

fn loader_retry_delay(code: Option<i32>, attempt: u32, windows: bool) -> Option<Duration> {
    (windows && code == Some(WINDOWS_DLL_INIT_FAILED) && attempt + 1 < MAX_ATTEMPTS)
        .then(|| Duration::from_millis(25 * (1 << attempt)))
}

pub(crate) fn windows_loader_retry_delay(code: Option<i32>, attempt: u32) -> Option<Duration> {
    loader_retry_delay(code, attempt, cfg!(windows))
}

/// The longest any lab git child may run. Every call is a local index or
/// object read that finishes in well under a second; a wedged index lock, a
/// credential or LFS hook or an AV scan must not hold a runtime worker for as
/// long as git takes (#813).
pub(crate) const GIT_DEADLINE: Duration = Duration::from_secs(30);

/// Kill `child` if it is still running at `deadline`, unless `done` is set
/// first. The caller sets `done` once it has the child's output, then joins
/// the returned thread. Returns whether the watchdog killed the child.
pub(crate) fn kill_at_deadline(
    child: Arc<Mutex<Child>>,
    deadline: Duration,
    done: Arc<AtomicBool>,
) -> thread::JoinHandle<bool> {
    thread::spawn(move || {
        let started = Instant::now();
        while started.elapsed() < deadline {
            if done.load(Ordering::Acquire) {
                return false;
            }
            thread::sleep(Duration::from_millis(10));
        }
        if done.load(Ordering::Acquire) {
            return false;
        }
        let mut child = child.lock().unwrap_or_else(|p| p.into_inner());
        match child.try_wait() {
            Ok(Some(_)) => false,
            _ => child.kill().is_ok(),
        }
    })
}

/// `command.output()` with a deadline: the child is killed and an error
/// returned once `deadline` passes. stdin is closed so the child cannot wait
/// on input that never comes.
pub(crate) fn output_with_deadline(
    command: &mut Command,
    deadline: Duration,
) -> io::Result<Output> {
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let mut stdout = child.stdout.take().expect("piped stdout");
    let mut stderr = child.stderr.take().expect("piped stderr");
    let out_reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout.read_to_end(&mut bytes).map(|_| bytes)
    });
    let err_reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr.read_to_end(&mut bytes).map(|_| bytes)
    });
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            // The readers end when the pipes close. They are not joined: a
            // hook started by git can hold a pipe after git itself is gone.
            drop((out_reader, err_reader));
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("child timed out after {}s", deadline.as_secs_f64()),
            ));
        }
        thread::sleep(Duration::from_millis(5));
    };
    let stdout = out_reader
        .join()
        .map_err(|_| io::Error::other("stdout reader panicked"))??;
    let stderr = err_reader
        .join()
        .map_err(|_| io::Error::other("stderr reader panicked"))??;
    Ok(Output {
        status,
        stdout,
        stderr,
    })
}

/// A git child's output, bounded by GIT_DEADLINE, retried only on the
/// Windows loader failure.
pub(crate) fn output_with_windows_loader_retry(command: &mut Command) -> io::Result<Output> {
    for attempt in 0..MAX_ATTEMPTS {
        let output = output_with_deadline(command, GIT_DEADLINE)?;
        match windows_loader_retry_delay(output.status.code(), attempt) {
            Some(delay) => thread::sleep(delay),
            None => return Ok(output),
        }
    }
    unreachable!("the bounded process retry loop always returns")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sleeper(seconds: u32) -> Command {
        if cfg!(windows) {
            let mut c = Command::new("powershell");
            c.args([
                "-NoProfile",
                "-Command",
                &format!("Start-Sleep -Seconds {seconds}"),
            ]);
            c
        } else {
            let mut c = Command::new("sleep");
            c.arg(seconds.to_string());
            c
        }
    }

    #[test]
    fn a_child_past_its_deadline_is_killed_and_reported() {
        let started = Instant::now();
        let error = output_with_deadline(&mut sleeper(30), Duration::from_millis(500)).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "{:?}",
            started.elapsed()
        );
    }

    #[test]
    fn a_child_inside_its_deadline_returns_its_output() {
        let mut command = if cfg!(windows) {
            let mut c = Command::new("cmd");
            c.args(["/C", "echo argus"]);
            c
        } else {
            let mut c = Command::new("echo");
            c.arg("argus");
            c
        };
        let output = output_with_deadline(&mut command, Duration::from_secs(20)).unwrap();
        assert!(output.status.success());
        assert!(String::from_utf8_lossy(&output.stdout).contains("argus"));
    }

    #[test]
    fn the_watchdog_kills_a_running_child_and_spares_a_finished_one() {
        let child = Arc::new(Mutex::new(sleeper(30).spawn().unwrap()));
        let started = Instant::now();
        let killed = kill_at_deadline(
            child.clone(),
            Duration::from_millis(300),
            Arc::new(AtomicBool::new(false)),
        );
        assert!(killed.join().unwrap());
        child.lock().unwrap().wait().unwrap();
        assert!(started.elapsed() < Duration::from_secs(10));

        let child = Arc::new(Mutex::new(sleeper(30).spawn().unwrap()));
        let done = Arc::new(AtomicBool::new(true));
        assert!(
            !kill_at_deadline(child.clone(), Duration::from_millis(300), done)
                .join()
                .unwrap()
        );
        let mut c = child.lock().unwrap();
        assert!(
            c.try_wait().unwrap().is_none(),
            "a finished caller's child was killed"
        );
        let _ = c.kill();
        let _ = c.wait();
    }

    #[test]
    fn only_the_windows_loader_failure_is_retryable() {
        assert_eq!(
            loader_retry_delay(Some(WINDOWS_DLL_INIT_FAILED), 0, true),
            Some(Duration::from_millis(25))
        );
        assert_eq!(
            loader_retry_delay(Some(WINDOWS_DLL_INIT_FAILED), 1, true),
            Some(Duration::from_millis(50))
        );
        assert_eq!(
            loader_retry_delay(Some(WINDOWS_DLL_INIT_FAILED), 2, true),
            Some(Duration::from_millis(100))
        );
        assert_eq!(
            loader_retry_delay(Some(WINDOWS_DLL_INIT_FAILED), 3, true),
            None,
            "the fourth failed attempt is final"
        );
        assert_eq!(loader_retry_delay(Some(1), 0, true), None);
        assert_eq!(loader_retry_delay(Some(0), 0, true), None);
        assert_eq!(
            loader_retry_delay(Some(WINDOWS_DLL_INIT_FAILED), 0, false),
            None,
            "the NTSTATUS is meaningful only on Windows"
        );
    }
}
