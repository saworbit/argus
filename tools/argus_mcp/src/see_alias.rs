//! Forgiving inspect vocabulary so a mistyped see still works.

pub fn normalize_see(what: &str) -> String {
    let w = what.trim().to_ascii_lowercase();
    match w.as_str() {
        "" | "start" | "orient" | "overview" | "proj" | "tree" => "project".into(),
        "dashboard" | "statusboard" => "lab".into(),
        "function" | "func" | "source" | "qc" => "fn".into(),
        "constant" | "constants" | "cvar" | "cvars" => "const".into(),
        "bots" | "snapshot" | "arglog" => "live".into(),
        "match" | "child" | "pid" => "status".into(),
        "tape" | "log" | "brief" => "run".into(),
        "session" | "memory" | "recall" => "last".into(),
        "atlas" | "bsp" | "level" => "map".into(),
        "waypoint" | "wp" => "node".into(),
        "path" | "route" | "walk" => "path".into(),
        "item" | "pickup" | "gun" => "item".into(),
        "search" | "grep" | "find" => "search".into(),
        "file" | "src" => "file".into(),
        "timeline" | "events" | "story" => "timeline".into(),
        "around" | "near" | "pos" | "here" => "around".into(),
        "plan" | "goap" | "goalplan" => "plan".into(),
        "dem" | "demos" | "replay" => "demo".into(),
        "vocab" | "?" => "help".into(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_is_project() {
        assert_eq!(normalize_see(""), "project");
        assert_eq!(normalize_see("  "), "project");
    }

    #[test]
    fn common_aliases() {
        assert_eq!(normalize_see("QC"), "fn");
        assert_eq!(normalize_see("atlas"), "map");
        assert_eq!(normalize_see("session"), "last");
        assert_eq!(normalize_see("fn"), "fn");
    }
}
