//! Index of Argus QuakeC: functions, constants, roles.

use crate::config::Config;
use regex::Regex;
use serde::Serialize;
use std::path::Path;
use std::sync::OnceLock;

#[derive(Debug, Clone, Serialize)]
pub struct QcFn {
    pub name: String,
    pub file: String,
    pub line: u32,
    pub kind: String,
    pub proto: bool,
    pub role: String,
    pub blurb: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct QcConst {
    pub name: String,
    pub file: String,
    pub line: u32,
    pub value: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct QcIndex {
    pub functions: Vec<QcFn>,
    pub constants: Vec<QcConst>,
}

pub fn index_argus(cfg: &Config) -> Result<QcIndex, String> {
    let mut functions = Vec::new();
    let mut constants = Vec::new();
    let names = [
        "argus.qc",
        "argus_nav.qc",
        "argus_nav_dispatch.qc",
        "defs.qc",
        "items.qc",
        "combat.qc",
        "weapons.qc",
        "world.qc",
        "client.qc",
        // the camera is Argus code and every ArgusCam_* lookup used to
        // come back empty; the mover/trigger files are the ones the
        // typed-link work reads constantly.
        "argus_cam.qc",
        "doors.qc",
        "buttons.qc",
        "plats.qc",
        "triggers.qc",
        "player.qc",
    ];
    for name in names {
        let path = cfg.src.join(name);
        if !path.is_file() {
            continue;
        }
        index_file(&path, name, &mut functions, &mut constants)?;
    }
    if functions.is_empty() {
        return Err("no Argus QC found under ARGUS_SRC".into());
    }
    Ok(QcIndex {
        functions,
        constants,
    })
}

pub fn qc_find<'a>(idx: &'a QcIndex, query: &str) -> Vec<&'a QcFn> {
    let q = query.to_ascii_lowercase();
    let mut hits: Vec<&QcFn> = idx
        .functions
        .iter()
        .filter(|f| {
            !f.proto
                && (f.name.to_ascii_lowercase().contains(&q)
                    || f.role.contains(&q)
                    || f.blurb.to_ascii_lowercase().contains(&q)
                    || f.file.to_ascii_lowercase().contains(&q))
        })
        .collect();
    hits.sort_by_key(|f| (f.file.as_str(), f.line));
    hits.truncate(24);
    hits
}

#[derive(Debug, Clone, Serialize)]
pub struct QcSource {
    pub name: String,
    pub file: String,
    pub start_line: u32,
    pub end_line: u32,
    pub role: String,
    pub blurb: String,
    pub source: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub calls: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub called_by: Vec<String>,
}

pub fn qc_read(cfg: &Config, name: &str) -> Result<QcSource, String> {
    let idx = index_argus(cfg)?;
    let f = idx
        .functions
        .iter()
        .find(|f| !f.proto && f.name.eq_ignore_ascii_case(name))
        .or_else(|| {
            let q = name.to_ascii_lowercase();
            idx.functions
                .iter()
                .find(|f| !f.proto && f.name.to_ascii_lowercase().contains(&q))
        })
        .ok_or_else(|| format!("no Argus function matching {name}"))?;
    let path = cfg.src.join(&f.file);
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let (end, body) = slice_function(&text, f.line);
    let calls = calls_in(&body, &f.name);
    let called_by = callers_of(cfg, &idx, &f.name);
    Ok(QcSource {
        name: f.name.clone(),
        file: format!("src/{}", f.file),
        start_line: f.line,
        end_line: end,
        role: f.role.clone(),
        blurb: f.blurb.clone(),
        source: body,
        calls,
        called_by,
    })
}

fn calls_in(body: &str, self_name: &str) -> Vec<String> {
    let re = call_re();
    let mut out = Vec::new();
    for cap in re.captures_iter(body) {
        let n = cap[1].to_string();
        if n != self_name && !out.iter().any(|x| x == &n) {
            out.push(n);
        }
    }
    out.truncate(16);
    out
}

fn callers_of(cfg: &Config, idx: &QcIndex, name: &str) -> Vec<String> {
    let mut out = Vec::new();
    for f in idx.functions.iter().filter(|f| !f.proto && f.name != name) {
        let path = cfg.src.join(&f.file);
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        let (_, body) = slice_function(&text, f.line);
        if body.contains(name) && f.name != name {
            out.push(format!("src/{}:{} {}", f.file, f.line, f.name));
        }
        if out.len() >= 12 {
            break;
        }
    }
    out
}

fn call_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        let extra = TRACKED_EXTRA.join("|");
        Regex::new(&format!(r"\b(Argus\w+|BotLab_\w+|{extra})\s*\(")).expect("call")
    })
}

#[derive(Debug, Clone, Serialize)]
pub struct QcHit {
    pub file: String,
    pub line: u32,
    pub text: String,
}

pub fn qc_search(cfg: &Config, needle: &str, max: usize) -> Result<Vec<QcHit>, String> {
    let needle = needle.trim();
    if needle.len() < 2 {
        return Err("search needle must be at least 2 characters".into());
    }
    let q = needle.to_ascii_lowercase();
    let names = [
        "argus.qc",
        "argus_nav.qc",
        "argus_nav_dispatch.qc",
        "defs.qc",
        "items.qc",
        "combat.qc",
        "weapons.qc",
        "world.qc",
        "client.qc",
        "argus_cam.qc",
        "doors.qc",
        "buttons.qc",
        "plats.qc",
        "triggers.qc",
        "player.qc",
    ];
    let mut hits = Vec::new();
    for name in names {
        let path = cfg.src.join(name);
        let Ok(text) = std::fs::read_to_string(&path) else {
            continue;
        };
        for (i, line) in text.lines().enumerate() {
            if line.to_ascii_lowercase().contains(&q) {
                hits.push(QcHit {
                    file: format!("src/{name}"),
                    line: (i + 1) as u32,
                    text: line.trim().to_string(),
                });
                if hits.len() >= max {
                    return Ok(hits);
                }
            }
        }
    }
    if hits.is_empty() {
        return Err(format!("no hits for {needle} in Argus QC"));
    }
    Ok(hits)
}

#[derive(Debug, Clone, Serialize)]
pub struct QcFileSlice {
    pub file: String,
    pub start_line: u32,
    pub end_line: u32,
    pub source: String,
}

pub fn qc_file_slice(cfg: &Config, spec: &str) -> Result<QcFileSlice, String> {
    let spec = spec.trim().trim_start_matches("src/");
    let (name, range) = spec.split_once(':').map(|(n, r)| (n, Some(r))).unwrap_or((spec, None));
    if name.is_empty() || name.contains("..") || name.contains('/') || name.contains('\\') {
        return Err("name=argus.qc or argus.qc:120-180".into());
    }
    if !name.ends_with(".qc") {
        return Err("file must be a .qc under src/".into());
    }
    let path = cfg.src.join(name);
    let text = std::fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let lines: Vec<&str> = text.lines().collect();
    let (start, end) = if let Some(r) = range {
        let (a, b) = r.split_once('-').unwrap_or((r, r));
        let s: usize = a.parse().unwrap_or(1);
        let e: usize = b.parse().unwrap_or(s);
        (s.max(1), e.min(lines.len()).max(s))
    } else {
        (1, lines.len().min(80))
    };
    let start_i = start.saturating_sub(1);
    let end_i = end.min(lines.len());
    if start_i >= lines.len() {
        return Err(format!("{name} has only {} lines", lines.len()));
    }
    Ok(QcFileSlice {
        file: format!("src/{name}"),
        start_line: (start_i + 1) as u32,
        end_line: end_i as u32,
        source: lines[start_i..end_i].join("\n"),
    })
}

fn slice_function(text: &str, start_line: u32) -> (u32, String) {
    let lines: Vec<&str> = text.lines().collect();
    let start = start_line.saturating_sub(1) as usize;
    if start >= lines.len() {
        return (start_line, String::new());
    }
    let rest = lines[start..].join("\n");
    let end_off = brace_span(&rest);
    let taken = &rest[..=end_off];
    let extra_lines = taken.bytes().filter(|&b| b == b'\n').count();
    let end = start + extra_lines;
    let end = end.min(lines.len().saturating_sub(1));
    let body = lines[start..=end].join("\n");
    ((end + 1) as u32, body)
}

/// Index of the closing `}` that matches the first `{`, ignoring
/// quotes, `//` line comments, and `/* */` block comments.
fn brace_span(text: &str) -> usize {
    let b = text.as_bytes();
    let mut i = 0;
    let mut depth = 0i32;
    let mut seen = false;
    while i < b.len() {
        let c = b[i];
        if c == b'"' {
            i += 1;
            while i < b.len() {
                if b[i] == b'\\' {
                    i += 2;
                    continue;
                }
                if b[i] == b'"' {
                    i += 1;
                    break;
                }
                i += 1;
            }
            continue;
        }
        if c == b'/' && i + 1 < b.len() && b[i + 1] == b'/' {
            while i < b.len() && b[i] != b'\n' {
                i += 1;
            }
            continue;
        }
        if c == b'/' && i + 1 < b.len() && b[i + 1] == b'*' {
            i += 2;
            while i + 1 < b.len() && !(b[i] == b'*' && b[i + 1] == b'/') {
                i += 1;
            }
            i = i.saturating_add(2);
            continue;
        }
        if c == b'{' {
            depth += 1;
            seen = true;
        } else if c == b'}' {
            depth -= 1;
            if seen && depth <= 0 {
                return i;
            }
        }
        i += 1;
    }
    text.len().saturating_sub(1)
}

pub fn look_at(cfg: &Config, needle: &str) -> String {
    let Ok(idx) = index_argus(cfg) else {
        return needle.to_string();
    };
    if let Some(f) = idx
        .functions
        .iter()
        .find(|f| !f.proto && needle.contains(&f.name))
    {
        return format!("src/{}:{} {}", f.file, f.line, f.name);
    }
    needle.to_string()
}

fn index_file(
    path: &Path,
    display: &str,
    functions: &mut Vec<QcFn>,
    constants: &mut Vec<QcConst>,
) -> Result<(), String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    index_text(display, &text, functions, constants);
    Ok(())
}

fn index_text(
    display: &str,
    text: &str,
    functions: &mut Vec<QcFn>,
    constants: &mut Vec<QcConst>,
) {
    let fn_re = fn_re();
    let c_re = const_re();
    let lines: Vec<&str> = text.lines().collect();
    for (i, line) in lines.iter().enumerate() {
        let lineno = (i + 1) as u32;
        if let Some(caps) = fn_re.captures(line) {
            let name = caps[2].to_string();
            if keep_fn(&name) {
                let proto = caps.get(3).map(|m| m.as_str() == ";").unwrap_or(false);
                functions.push(QcFn {
                    role: role_for(&name).to_string(),
                    blurb: preceding_blurb(&lines, i),
                    name,
                    file: display.to_string(),
                    line: lineno,
                    kind: caps[1].to_string(),
                    proto,
                });
            }
        }
        if let Some(caps) = c_re.captures(line) {
            constants.push(QcConst {
                name: caps[1].to_string(),
                file: display.to_string(),
                line: lineno,
                value: caps[2].trim().to_string(),
            });
        }
    }
}

fn preceding_blurb(lines: &[&str], idx: usize) -> String {
    let mut comments = Vec::new();
    let mut i = idx;
    while i > 0 {
        i -= 1;
        let t = lines[i].trim();
        if t.starts_with("//") {
            let body = t.trim_start_matches('/').trim();
            if !body.is_empty() {
                comments.push(body.to_string());
            }
        } else if t.is_empty() {
            continue;
        } else {
            break;
        }
    }
    comments.reverse();
    comments
        .into_iter()
        .take(2)
        .collect::<Vec<_>>()
        .join(" ")
}

const TRACKED_EXTRA: &[&str] = &[
    "weapon_touch",
    "T_Damage",
    "W_FireLightning",
    "W_Attack",
    "PlayerDie",
    "CheckPowerups",
    "WaterMove",
    "PlayerPostThink",
];

fn keep_fn(name: &str) -> bool {
    // "ArgusCam_POV".starts_with("Argus_") is false - the camera and the
    // director sit behind a prefix that never had an underscore, so they
    // were unindexable even once the file was in the list.
    name.starts_with("Argus") || name.starts_with("BotLab_") || TRACKED_EXTRA.contains(&name)
}

fn role_for(name: &str) -> &'static str {
    if name.contains("Hazard") || name.contains("Water") {
        "hazard"
    } else if name.contains("Perceive")
        || name.contains("CanSee")
        || name.contains("Combat")
        || name.contains("Weapon")
        || name.contains("Pain")
        || name.contains("Aim")
    {
        "combat"
    } else if name.contains("Nav")
        || name.contains("Route")
        || name.contains("Goal")
        || name.contains("Pick")
    {
        "nav"
    } else if name.contains("Spawn")
        || name.contains("Respawn")
        || name.contains("Die")
        || name.contains("Init")
        || name.contains("BaseStats")
    {
        "lifecycle"
    } else if name.contains("Physics")
        || name.contains("Friction")
        || name.contains("Accel")
    {
        "physics"
    } else if name.contains("Skill") || name.contains("Chat") {
        "personality"
    } else if name.contains("Score") || name.contains("Telemetry") || name.contains("Event") {
        "lab"
    } else {
        "other"
    }
}

fn fn_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"^(void|float|string|entity)\s*\([^)]*\)\s+(\w+)\s*(=|;)")
            .expect("fn")
    })
}

fn const_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^float\s+(AR_\w+)\s*=\s*([^;]+)").expect("const"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn brace_span_ignores_comments_and_strings() {
        let src = "void() F =\n{\n    dprint (\"{ not a brace\");\n    // }\n    /* } */\n}\nvoid() G =\n{\n};\n";
        let end = brace_span(src);
        let taken = &src[..=end];
        assert!(taken.contains("void() F"));
        assert!(!taken.contains("void() G"), "slicer walked into the next function:\n{taken}");
    }

    #[test]
    fn indexes_sample_qc() {
        let src = r#"
float AR_JUMPVEL     = 270;
// TRUE when walking would end in lava.
float(float myaw, float pdist) Argus_MoveHazard =
{
};
void() PlayerDie;
void() Argus_Perceive =
{
};
"#;
        let mut fns = Vec::new();
        let mut cs = Vec::new();
        index_text("argus.qc", src, &mut fns, &mut cs);
        assert!(cs.iter().any(|c| c.name == "AR_JUMPVEL" && c.value.contains("270")));
        let hz = fns.iter().find(|f| f.name == "Argus_MoveHazard").unwrap();
        assert_eq!(hz.role, "hazard");
        assert!(!hz.proto);
        assert!(hz.blurb.to_ascii_lowercase().contains("lava"));
        assert!(fns.iter().any(|f| f.name == "Argus_Perceive" && f.role == "combat"));
    }

    #[test]
    fn finds_real_tree_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../src/argus.qc");
        if !path.exists() {
            return;
        }
        let root = path.parent().unwrap().parent().unwrap();
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = crate::config::load_for_reads_from(&env, root).unwrap();
        let idx = index_argus(&cfg).unwrap();
        assert!(idx.functions.iter().any(|f| f.name == "Argus_MoveHazard" && !f.proto));
        assert!(idx.constants.iter().any(|c| c.name == "AR_JUMPVEL"));
        let hits = qc_find(&idx, "hazard");
        assert!(hits.iter().any(|f| f.name == "Argus_MoveHazard"));
        let src = qc_read(&cfg, "Argus_MoveHazard").unwrap();
        assert!(src.source.contains("CONTENT_LAVA"));
        assert!(src.start_line > 0 && src.end_line > src.start_line);
        let hits = qc_search(&cfg, "CONTENT_LAVA", 8).unwrap();
        assert!(hits.iter().any(|h| h.file.contains("argus.qc")));
        let slice = qc_file_slice(&cfg, "argus.qc:1-20").unwrap();
        assert_eq!(slice.start_line, 1);
        assert!(!slice.source.is_empty());
    }

    #[test]
    fn extracts_calls() {
        let body = "{\n    if (Argus_MoveHazard(yaw, 32)) {\n        Argus_Physics();\n        PlayerDie();\n    }\n}";
        let c = calls_in(body, "Argus_Think");
        assert!(c.iter().any(|n| n == "Argus_MoveHazard"));
        assert!(c.iter().any(|n| n == "Argus_Physics"));
        assert!(c.iter().any(|n| n == "PlayerDie"));
    }

    #[test]
    fn slice_ignores_braces_in_comments_and_strings() {
        let src = r#"void() Argus_Foo =
{
    // note: { not a block
    stuffcmd(self, "bind 1 {impulse 1}\n");
    /* { still a comment } */
    return;
};
void() Argus_Bar =
{
};
"#;
        let (end, body) = slice_function(src, 2);
        assert!(body.contains("stuffcmd"));
        assert!(body.contains("return;"));
        assert!(!body.contains("Argus_Bar"), "sliced too far: {body}");
        assert!(end < 12);
    }

    #[test]
    fn camera_functions_are_indexed() {
        // #36: argus_cam.qc was missing from index_argus(), so every
        // `see what=fn name=ArgusCam_*` returned nothing.
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join("src");
        let cam = root.join("argus_cam.qc");
        if !cam.is_file() {
            return; // source tree not present (packaged build)
        }
        let mut fns = Vec::new();
        let mut consts = Vec::new();
        index_file(&cam, "argus_cam.qc", &mut fns, &mut consts).expect("index argus_cam.qc");
        assert!(
            fns.iter().any(|f| f.name == "ArgusCam_POV"),
            "ArgusCam_POV not indexed"
        );
        assert!(
            fns.iter().any(|f| f.name.starts_with("ArgusDirector_")),
            "the director is not indexed"
        );
        // and the call regex must reach them too (calls/callers)
        assert!(call_re().is_match("            ArgusCam_POV (self, self.cam_target);"));
    }
}
