use std::io;
use std::process::{Command, Output};
use std::thread;
use std::time::Duration;

// NTSTATUS 0xc0000142, observed from Git-for-Windows when the parallel Rust
// suite briefly exhausts process-loader resources. The child was never able to
// run, so retrying is safe; no other exit status is retried.
const WINDOWS_DLL_INIT_FAILED: i32 = -1_073_741_502;
const MAX_ATTEMPTS: u32 = 4;

fn is_windows_dll_init_failure(code: Option<i32>) -> bool {
    cfg!(windows) && code == Some(WINDOWS_DLL_INIT_FAILED)
}

pub(crate) fn output_with_windows_loader_retry(command: &mut Command) -> io::Result<Output> {
    for attempt in 0..MAX_ATTEMPTS {
        let output = command.output()?;
        if !is_windows_dll_init_failure(output.status.code()) || attempt + 1 == MAX_ATTEMPTS {
            return Ok(output);
        }
        thread::sleep(Duration::from_millis(25 * (1 << attempt)));
    }
    unreachable!("the bounded process retry loop always returns")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_windows_loader_failure_is_retryable() {
        assert!(!is_windows_dll_init_failure(Some(1)));
        assert!(!is_windows_dll_init_failure(Some(0)));
        #[cfg(windows)]
        assert!(is_windows_dll_init_failure(Some(-1_073_741_502)));
    }
}
