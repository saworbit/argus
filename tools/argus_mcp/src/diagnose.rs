//! Turn a dead match log into one actionable sentence.

pub fn diagnose_log(text: &str) -> Option<String> {
    let lower = text.to_ascii_lowercase();
    if text.contains("Error getting # of console events") {
        return Some(
            "engine Host_Error on piped stdin (GetNumberOfConsoleInputEvents). \
Windows spawn must not inherit the MCP stdio pipe."
                .into(),
        );
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
        return Some("id1 PAK missing under ARGUS_BASEDIR. Copy licensed pak0/pak1 into basedir/id1.".into());
    }
    if text.contains("QUAKE ERROR") || text.contains("Host_Error") || text.contains("Sys_Error") {
        let line = text
            .lines()
            .find(|l| {
                l.contains("QUAKE ERROR") || l.contains("Host_Error") || l.contains("Sys_Error")
            })
            .unwrap_or("engine error");
        return Some(format!("engine error: {}", line.trim()));
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
