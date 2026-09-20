use std::io;
use std::process::{Command, Output};
use std::thread;
use std::time::Duration;

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

pub(crate) fn output_with_windows_loader_retry(command: &mut Command) -> io::Result<Output> {
    for attempt in 0..MAX_ATTEMPTS {
        let output = command.output()?;
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
