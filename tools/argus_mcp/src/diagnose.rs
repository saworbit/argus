//! Turn a dead match log into one actionable sentence.

const CONSOLE_PIPE_ERROR: &str = "Error getting # of console events";
const CONSOLE_PIPE_HELP: &str =
    "engine Host_Error on piped stdin (GetNumberOfConsoleInputEvents). \
Windows spawn must not inherit the MCP stdio pipe.";

pub fn fatal_engine_error(text: &str) -> Option<String> {
    let line = text.lines().map(str::trim).find(|line| {
        ["QUAKE ERROR:", "Host_Error:", "Sys_Error:"]
            .into_iter()
            .any(|prefix| line.starts_with(prefix))
    })?;
    if line.contains(CONSOLE_PIPE_ERROR) {
        return Some(CONSOLE_PIPE_HELP.into());
    }
    Some(format!("engine error: {line}"))
}

pub fn diagnose_log(text: &str) -> Option<String> {
    if let Some(fatal) = fatal_engine_error(text) {
        return Some(fatal);
    }
    let lower = text.to_ascii_lowercase();
    if text.contains(CONSOLE_PIPE_ERROR) {
        return Some(CONSOLE_PIPE_HELP.into());
    }
    if lower.contains("couldn't exec") || lower.contains("could not exec") {
        return Some("engine could not exec a cfg or map; check ARGUS_BASEDIR and -game.".into());
    }
    if lower.contains("can't find") && lower.contains("map")
        || lower.contains("couldn't find") && (lower.contains(".bsp") || lower.contains("maps/"))
    {
        return Some("map not found. cartograph or list_maps, then extract from id1 PAK.".into());
    }
    if lower.contains("couldn't load") && (lower.contains("pak") || lower.contains("id1")) {
        return Some(
            "id1 PAK missing under ARGUS_BASEDIR. Copy licensed pak0/pak1 into basedir/id1.".into(),
        );
    }
    if text.contains("Server spawned") && !text.contains("ARGLOG") && !text.contains("ARGEVT") {
        return Some(
            "server spawned then died before ARGLOG. On Windows this was usually inherited stdin; \
if this build still does that, file a bug. Otherwise check skill/map and autoexec.cfg."
                .into(),
        );
    }
    if text.trim().is_empty() {
        return Some(
            "qconsole.log empty: -condebug never wrote. Check ARGUS_ENGINE exists and cwd is writable."
                .into(),
        );
    }
    None
}

pub fn log_has_tape(text: &str) -> bool {
    text.contains("ARGLOG") || text.contains("ARGEVT")
}

pub fn tail_nonempty(text: &str, n: usize) -> Vec<String> {
    text.lines()
        .map(str::trim)
        .filter(|l| !l.is_empty())
        .rev()
        .take(n)
        .map(str::to_string)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flags_console_pipe() {
        let d = diagnose_log("QUAKE ERROR: Error getting # of console events").unwrap();
        assert!(d.contains("piped stdin"));
    }

    #[test]
    fn fatal_engine_records_take_precedence_over_boot_warnings() {
        let text = "couldn't exec quake.rc\n  Host_Error: Program error\n";
        assert_eq!(
            diagnose_log(text).as_deref(),
            Some("engine error: Host_Error: Program error")
        );
        assert!(fatal_engine_error("player: I saw Host_Error: Program error").is_none());
        assert!(fatal_engine_error("Sys_Error: no free memory").is_some());
    }

    #[test]
    fn flags_empty() {
        let d = diagnose_log("   \n").unwrap();
        assert!(d.contains("empty"));
    }

    #[test]
    fn flags_spawn_then_silence() {
        let d = diagnose_log("Server spawned.\n").unwrap();
        assert!(d.contains("ARGLOG"));
    }

    #[test]
    fn tape_is_healthy() {
        assert!(log_has_tape("ARGLOG Reap t 1.0 pos '0 0 0'"));
        assert!(diagnose_log("ARGLOG Reap t 1.0 pos '0 0 0'").is_none());
    }
}
