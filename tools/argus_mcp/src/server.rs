use crate::analyze::analyze_match;
use crate::cartograph::{
    atlas_brief, cartograph as map_cartograph, inspect_entities, list_maps as map_list,
};
use crate::compile::compile_qc;
use crate::config::Config;
use crate::compile::compile_qc_dir;
use crate::intel::{
    brief_lite, brief_run as intel_brief, compare_lite, compare_runs as intel_compare,
    compare_runs_scaled as intel_compare_scaled, sim_report, want_full, QUALITY_BARS,
};
use crate::live::{knobs, snapshot, validate_tune};
use crate::lab::{cartograph_all as all_atlases, lab_status as build_lab};
use crate::learn::learn_hotspots;
use crate::match_ctrl::{list_runs, MatchCtrl, DURATION_MAX, DURATION_MIN};
use crate::project::{project_view, see_vocab};
use crate::see_alias::normalize_see;
use crate::nav_graph::{around_point, item_view, node_deep, route_ref};
use crate::qc_index::{index_argus, qc_file_slice, qc_find, qc_read, qc_search};
use crate::nav_sync::nav_sync_dispatch;
use crate::tape_view::{bot_deep, load_named_tape, plan_view, split_tape_bot, timeline};
use crate::navgen::nav_generate;
use crate::session::{ExperimentRecord, SessionSeen};
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{
    CallToolResult, ContentBlock, Implementation, ListResourceTemplatesResult, ListResourcesResult,
    PaginatedRequestParams, PromptMessage, ReadResourceRequestParams, ReadResourceResponse,
    ReadResourceResult, Role, ServerCapabilities, ServerInfo,
};
use rmcp::service::{RequestContext, RoleServer};
use rmcp::ErrorData as McpError;
use rmcp::{
    prompt, prompt_handler, prompt_router, schemars, tool, tool_handler, tool_router, ServerHandler,
};
use serde::Deserialize;
use serde::Serialize;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct Argus {
    pub matches: Arc<Mutex<MatchCtrl>>,
    pub session: Arc<Mutex<SessionSeen>>,
}

impl Argus {
    pub fn new() -> Self {
        Self {
            matches: Arc::new(Mutex::new(MatchCtrl::default())),
            session: Arc::new(Mutex::new(SessionSeen::default())),
        }
    }

    pub async fn shutdown(&self) {
        self.matches.lock().await.shutdown().await;
    }

    async fn note_see(&self, what: &str, name: Option<&str>) {
        self.session.lock().await.note_see(what, name);
    }
}

fn json_ok<T: Serialize>(value: &T) -> Result<CallToolResult, McpError> {
    json_ok_pngs(value, &[])
}

fn json_ok_pngs<T: Serialize>(value: &T, pngs: &[&str]) -> Result<CallToolResult, McpError> {
    let text = serde_json::to_string_pretty(value)
        .map_err(|e| McpError::internal_error(e.to_string(), None))?;
    let mut blocks = vec![ContentBlock::text(text)];
    for p in pngs {
        if let Some(img) = png_block(p) {
            blocks.push(img);
        }
    }
    Ok(CallToolResult::success(blocks))
}

fn png_block(path: &str) -> Option<ContentBlock> {
    let bytes = std::fs::read(path).ok()?;
    if bytes.is_empty() || bytes.len() > 1_500_000 {
        return None;
    }
    use base64::Engine;
    let b64 = base64::engine::general_purpose::STANDARD.encode(bytes);
    Some(ContentBlock::image(b64, "image/png"))
}

fn tool_err(msg: impl Into<String>) -> Result<CallToolResult, McpError> {
    let error = msg.into();
    let hint = hint_for(&error);
    let body = serde_json::json!({ "error": error, "hint": hint });
    Ok(CallToolResult::error(vec![ContentBlock::text(
        serde_json::to_string_pretty(&body).unwrap_or(error),
    )]))
}

fn hint_for(error: &str) -> String {
    let e = error.to_ascii_lowercase();
    if e.contains("argus_") && (e.contains("missing") || e.contains("does not exist")) {
        return "config_check, then set the named ARGUS_* key in env or tools/argus_mcp.toml".into();
    }
    if e.contains("no arglog") || e.contains("piped stdin") || e.contains("console events") {
        return "see what=last for the log tail. On Windows this build uses CREATE_NEW_CONSOLE without inheriting the MCP pipe. Pass skill= on experiment.".into();
    }
    if e.contains("already running") {
        return "match_stop, then retry. start() reaps a dead child automatically.".into();
    }
    if e.contains("no match") {
        return "experiment or match_start first. Then tune command=\"skill 3\" (Windows injects via AttachConsole).".into();
    }
    if e.contains("no argus function") {
        return "qc_find query=Argus_ or see what=fn name=Argus_".into();
    }
    if e.contains("map") && e.contains("short name") {
        return "use map=dm4, not a path".into();
    }
    "see what=help".into()
}

fn cfg_or_err() -> Result<Config, CallToolResult> {
    match Config::load() {
        Ok(cfg) => match cfg.require_ready() {
            Ok(()) => Ok(cfg),
            Err(e) => Err(CallToolResult::error(vec![ContentBlock::text(format!(
                "{e}. hint: config_check or see what=project"
            ))])),
        },
        Err(e) => Err(CallToolResult::error(vec![ContentBlock::text(format!(
            "{e}. hint: set ARGUS_ROOT and the five lab keys"
        ))])),
    }
}

fn cfg_read_or_err() -> Result<Config, CallToolResult> {
    match Config::load_for_reads() {
        Ok(cfg) => {
            if !cfg.root.exists() {
                return Err(CallToolResult::error(vec![ContentBlock::text(
                    "config path for ARGUS_ROOT does not exist".to_string(),
                )]));
            }
            Ok(cfg)
        }
        Err(e) => Err(CallToolResult::error(vec![ContentBlock::text(format!(
            "{e}. hint: set ARGUS_ROOT"
        ))])),
    }
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CompileArgs {
    #[serde(default)]
    #[schemars(description = "Copy progs.dat to game/argus and the basedir game dir")]
    pub install: Option<bool>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SpecCompileArgs {
    #[schemars(description = "Ignored; ARGUS_SRC is used. Accepted for spec compatibility.")]
    pub source_directory: Option<String>,
    #[schemars(description = "Ignored; id-format output is required. Accepted for spec compatibility.")]
    pub optimization_level: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SpecInspectArgs {
    pub map_name: String,
    pub filter_classname: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SpecSimulateArgs {
    pub map_name: String,
    pub duration_seconds: Option<u32>,
    #[schemars(description = "Ignored; Reap, Omi, Zeus are compiled in.")]
    pub bot_count: Option<u32>,
    #[schemars(description = "Ignored; 100x dilation would change frametime and break A/B.")]
    pub time_dilation: Option<f64>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SpecRconArgs {
    pub command: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SpecPovArgs {
    pub bot_client_id: Option<i32>,
    pub render_debug_overlays: Option<bool>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct NavArgs {
    #[schemars(description = "BSP path or short map name (dm4)")]
    pub bsp: String,
    #[schemars(description = "Map name used in the generated QC symbol")]
    pub map: String,
    pub out_qc: Option<String>,
    pub out_png: Option<String>,
    #[schemars(description = "Also pass --register: idempotently wire the map into progs.src and argus_nav_dispatch.qc (recompile still manual)")]
    pub register: Option<bool>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MatchRunArgs {
    pub map: String,
    #[schemars(description = "Wall-clock seconds, 10 to 600")]
    pub duration_sec: u32,
    pub run_name: Option<String>,
    pub dedicated_slots: Option<u32>,
    #[schemars(description = "skill 0-3; applied at spawn via Argus_SetSkill")]
    pub skill: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MatchStartArgs {
    pub map: String,
    pub duration_sec: Option<u32>,
    pub run_name: Option<String>,
    pub dedicated_slots: Option<u32>,
    #[schemars(description = "skill 0-3; applied at spawn via Argus_SetSkill")]
    pub skill: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MatchCommandArgs {
    #[schemars(description = "One console line, no newlines")]
    pub command: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MatchStopArgs {
    pub timeout_sec: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct AnalyzeArgs {
    pub bsp: String,
    pub log_a: String,
    pub out_png: String,
    pub log_b: Option<String>,
    pub nav_json: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MapArgs {
    #[schemars(description = "BSP path or short name (dm4)")]
    pub bsp: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct BriefArgs {
    #[schemars(description = "Log path or run name (ab_dm4_parity)")]
    pub log: String,
    pub map: Option<String>,
    #[schemars(description = "brief (default) or full")]
    pub detail: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CompareArgs {
    #[schemars(description = "Baseline: path, run name, or 'baseline'/'shipped'. Default baseline.")]
    pub log_a: Option<String>,
    #[schemars(description = "Candidate: path, run name, or 'latest'")]
    pub log_b: String,
    pub map: Option<String>,
    #[schemars(description = "brief (default, verdict+gates) or full (both MatchBriefs)")]
    pub detail: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CartographArgs {
    #[schemars(description = "BSP path, short name (dm4), or maps/dm4.bsp. Ingests from ARGUS_MAPS or extracts from id1 PAK0/PAK1.")]
    pub bsp: String,
    #[serde(default)]
    #[schemars(description = "Also run argus_navgen.py after ingest")]
    pub generate_nav: Option<bool>,
    #[serde(default)]
    #[schemars(description = "With generate_nav: also --register into progs.src and the dispatcher")]
    pub register: Option<bool>,
    #[serde(default)]
    #[schemars(description = "brief (default, LLM-sized) or full (every entity)")]
    pub detail: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct QcFindArgs {
    #[schemars(description = "Function name, role (hazard/combat/nav), or blurb substring")]
    pub query: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct TuneArgs {
    #[schemars(description = "Whitelisted console line: skill 0-3, fraglimit N, timelimit N, developer 0|1, deathmatch 1, map NAME, status, serverinfo")]
    pub command: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SeeArgs {
    #[serde(default)]
    #[schemars(description = "What to open: help|project|lab|map|recipe|node|path|item|fn|file|search|const|live|bot|timeline|around|plan|status|run|last|knobs. Empty defaults to project.")]
    pub what: String,
    #[schemars(description = "Name: bot (Reap), function (Argus_MoveHazard), const (AR_JUMPVEL), map (dm4), node (dm4:56), run (latest)")]
    pub name: Option<String>,
    #[schemars(description = "For map: brief (default) or full")]
    pub detail: Option<String>,
    #[schemars(description = "For status/live: return log lines after this 0-based count. 0 or omit = last 40.")]
    pub since_line: Option<u32>,
}

#[derive(Debug, Default, Deserialize, schemars::JsonSchema)]
pub struct MatchStatusArgs {
    #[schemars(description = "Return only lines after this 0-based count. Omit for last 40.")]
    pub since_line: Option<u32>,
}

#[derive(Debug, Default, Deserialize, schemars::JsonSchema)]
pub struct LiveSnapshotArgs {
    #[schemars(description = "Only parse ARGLOG after this 0-based line count.")]
    pub since_line: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ExperimentArgs {
    pub map: String,
    #[schemars(description = "Wall-clock seconds, 10-185. Default 30. Compare is duration-scaled against the shipped baseline.")]
    pub duration_sec: Option<u32>,
    #[schemars(description = "Compile first. Default true.")]
    pub compile: Option<bool>,
    pub skill: Option<u32>,
    #[schemars(description = "Baseline log, run name, or 'baseline'. Default baseline.")]
    pub baseline: Option<String>,
    pub run_name: Option<String>,
    #[schemars(description = "brief (default) or full (compile + match + both briefs)")]
    pub detail: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MatrixArgs {
    #[schemars(description = "Maps to probe. Default dm2,dm3,dm4,dm6,lqdm2.")]
    pub maps: Option<Vec<String>>,
    #[schemars(description = "Wall-clock seconds per map, 10-60. Default 20.")]
    pub duration_sec: Option<u32>,
    pub skill: Option<u32>,
    #[schemars(description = "Compile first. Default true.")]
    pub compile: Option<bool>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct QcReadArgs {
    #[schemars(description = "Argus function name, e.g. Argus_MoveHazard")]
    pub name: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ProbeArgs {
    pub map: String,
    #[schemars(description = "Wall-clock seconds, 10-120. Default 20.")]
    pub duration_sec: Option<u32>,
    #[schemars(description = "Compile first")]
    pub compile: Option<bool>,
    pub skill: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct LearnArgs {
    #[schemars(description = "Map short name (dm4)")]
    pub map: String,
    #[schemars(description = "Max harvested logs to fold in, default 8")]
    pub max_logs: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SuggestArgs {
    #[schemars(description = "One log to brief, or omit and pass log_a/log_b")]
    pub log: Option<String>,
    pub log_a: Option<String>,
    pub log_b: Option<String>,
    pub map: Option<String>,
}

#[tool_router]
impl Argus {
    #[tool(description = "Resolved Argus lab paths and whether each exists. Never errors.")]
    async fn config_check(&self) -> Result<CallToolResult, McpError> {
        json_ok(&Config::report())
    }

    #[tool(description = "Compile src/ with fteqcc. Success is the Compile finished / id format line, not the exit code.")]
    async fn compile_qc(
        &self,
        Parameters(args): Parameters<CompileArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let result = match tokio::time::timeout(
            Duration::from_secs(90),
            tokio::task::spawn_blocking(move || compile_qc(&cfg, args.install.unwrap_or(true))),
        )
        .await
        {
            Ok(j) => j.map_err(|e| McpError::internal_error(e.to_string(), None))?,
            Err(_) => return tool_err("compile_qc timed out after 90s (fteqcc hung or src/ is huge)"),
        };
        json_ok(&result)
    }

    #[tool(name = "quake_compile_qc", description = "Prefer compile_qc. Extra: compile an optional source_directory. Installs only if that dir is ARGUS_SRC.")]
    async fn quake_compile_qc(
        &self,
        Parameters(args): Parameters<SpecCompileArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let src = args
            .source_directory
            .as_deref()
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| cfg.src.clone());
        let install = src == cfg.src;
        let opt = args.optimization_level.clone();
        let src_display = src.display().to_string();
        let result = tokio::task::spawn_blocking(move || compile_qc_dir(&cfg, &src, install))
            .await
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        json_ok(&serde_json::json!({
            "compile": result,
            "source_directory": src_display,
            "installed": install,
            "optimization_level_requested": opt,
            "optimization_level_applied": "id-format (no -O3)",
        }))
    }

    #[tool(name = "bsp_inspect_entities", description = "Prefer see what=map. Extra: raw entity lump + filter_classname.")]
    async fn bsp_inspect_entities(
        &self,
        Parameters(args): Parameters<SpecInspectArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match inspect_entities(&cfg, &args.map_name, args.filter_classname.as_deref()) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(name = "bot_simulate_match", description = "Prefer experiment. Extra: batch K/D report. time_dilation is not applied.")]
    async fn bot_simulate_match(
        &self,
        Parameters(args): Parameters<SpecSimulateArgs>,
    ) -> Result<CallToolResult, McpError> {
        let dur = args.duration_seconds.unwrap_or(300);
        if !(DURATION_MIN..=DURATION_MAX).contains(&dur) {
            return Err(McpError::invalid_params(
                format!("duration_seconds must be {DURATION_MIN}..={DURATION_MAX}"),
                None,
            ));
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut g = self.matches.lock().await;
        match g
            .run(
                &cfg,
                &args.map_name,
                dur,
                Some(&format!("sim_{}", args.map_name)),
                None,
                None,
            )
            .await
        {
            Ok(r) => json_ok(&serde_json::json!({
                "ok": r.ok,
                "bot_count_requested": args.bot_count,
                "bot_count_actual": 3,
                "time_dilation_requested": args.time_dilation,
                "time_dilation_applied": 1.0,
                "time_dilation_note": "100x host_framerate parked: it would change frametime",
                "report": sim_report(&r.brief),
                "brief": r.brief,
                "log_path": r.log_path,
            })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(name = "rcon_exec", description = "Prefer tune. Extra: whitelist stdin + log tail. Not UDP RCON.")]
    async fn rcon_exec(
        &self,
        Parameters(args): Parameters<SpecRconArgs>,
    ) -> Result<CallToolResult, McpError> {
        let line = match validate_tune(&args.command) {
            Ok(l) => l,
            Err(e) => return tool_err(format!("{e} (rcon_exec is not a free shell)")),
        };
        let mut g = self.matches.lock().await;
        match g.command(&line).await {
            Ok(()) => {
                tokio::time::sleep(Duration::from_millis(200)).await;
                let st = g.status();
                json_ok(&serde_json::json!({
                    "ok": true,
                    "sent": line,
                    "transport": "dedicated-stdin",
                    "recent_lines": st.recent_lines,
                }))
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(name = "bot_capture_pov_frame", description = "Prefer analyze_match. Extra: parked POV; returns nav/traj PNG paths.")]
    async fn bot_capture_pov_frame(
        &self,
        Parameters(args): Parameters<SpecPovArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let nav = cfg.runs.join("nav_dm4.png");
        let traj = cfg.runs.join("shane_dm4_traj.png");
        json_ok(&serde_json::json!({
            "ok": false,
            "parked": true,
            "bot_client_id": args.bot_client_id.unwrap_or(1),
            "reason": "POV capture needs a rendering client and screenshot builtins. Argus dedicated QuakeSpasm has neither. Use analyze_match PNG or nav PNG.",
            "substitutes": {
                "nav_png": if nav.is_file() { Some(nav.display().to_string()) } else { None },
                "traj_png": if traj.is_file() { Some(traj.display().to_string()) } else { None },
                "tool": "analyze_match",
            }
        }))
    }

    #[tool(description = "Map cartographer. Default detail=brief: control items snapped to nav (walk/jump/rocket_jump/off_graph), height bands, match recipe. detail=full adds every entity. Ingests path, short name, or id1 PAK.")]
    async fn cartograph(
        &self,
        Parameters(args): Parameters<CartographArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let atlas = match map_cartograph(&cfg, &args.bsp) {
            Ok(a) => a,
            Err(e) => return tool_err(e),
        };
        let want_full = args
            .detail
            .as_deref()
            .map(|d| d.eq_ignore_ascii_case("full"))
            .unwrap_or(false);
        if args.generate_nav.unwrap_or(false) {
            let full = match cfg_or_err() {
                Ok(c) => c,
                Err(r) => return Ok(r),
            };
            match crate::navgen::nav_generate(
                &full,
                &atlas.bsp_path,
                &atlas.map,
                None,
                None,
                args.register.unwrap_or(true),
            ) {
                Ok(nav) => {
                    if want_full {
                        return json_ok(&serde_json::json!({
                            "atlas": atlas,
                            "navgen": nav,
                        }));
                    }
                    return json_ok(&serde_json::json!({
                        "atlas": atlas_brief(&atlas),
                        "navgen": nav,
                    }));
                }
                Err(e) => return tool_err(e),
            }
        }
        if want_full {
            json_ok(&atlas)
        } else {
            json_ok(&atlas_brief(&atlas))
        }
    }

    #[tool(description = "List maps the cartographer can ingest: *.bsp in ARGUS_MAPS plus map names inside id1 PAK files.")]
    async fn list_maps(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match map_list(&cfg) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Generate a per-map nav QC file via argus_navgen.py. Always passes --no-dispatcher; register=true also wires progs.src and the dispatcher.")]
    async fn nav_generate(
        &self,
        Parameters(args): Parameters<NavArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match nav_generate(
            &cfg,
            &args.bsp,
            &args.map,
            args.out_qc.as_deref(),
            args.out_png.as_deref(),
            args.register.unwrap_or(false),
        ) {
            Ok(r) => json_ok_pngs(&r, &[r.out_png.as_str()]),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Register argus_nav_<map>.qc files in argus_nav_dispatch.qc and progs.src. Does not generate nav.")]
    async fn nav_sync_dispatch(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match nav_sync_dispatch(&cfg) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Run a timed dedicated match, harvest runs/<name>.log, return ARGLOG/ARGEVT metrics.")]
    async fn match_run(
        &self,
        Parameters(args): Parameters<MatchRunArgs>,
    ) -> Result<CallToolResult, McpError> {
        if !(DURATION_MIN..=DURATION_MAX).contains(&args.duration_sec) {
            return Err(McpError::invalid_params(
                format!("duration_sec must be {DURATION_MIN}..={DURATION_MAX}"),
                None,
            ));
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut g = self.matches.lock().await;
        match g
            .run(
                &cfg,
                &args.map,
                args.duration_sec,
                args.run_name.as_deref(),
                args.dedicated_slots,
                args.skill,
            )
            .await
        {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Start a dedicated match and return once the process is up. At most one live match.")]
    async fn match_start(
        &self,
        Parameters(args): Parameters<MatchStartArgs>,
    ) -> Result<CallToolResult, McpError> {
        if let Some(d) = args.duration_sec {
            if !(DURATION_MIN..=DURATION_MAX).contains(&d) {
                return Err(McpError::invalid_params(
                    format!("duration_sec must be {DURATION_MIN}..={DURATION_MAX}"),
                    None,
                ));
            }
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut g = self.matches.lock().await;
        match g
            .start(
                &cfg,
                &args.map,
                args.duration_sec,
                args.run_name.as_deref(),
                args.dedicated_slots,
                args.skill,
            )
            .await
        {
            Ok(st) => {
                if let Some(d) = args.duration_sec {
                    let matches = self.matches.clone();
                    tokio::spawn(async move {
                        tokio::time::sleep(Duration::from_secs(d as u64)).await;
                        let mut g = matches.lock().await;
                        let _ = g.stop(Duration::from_secs(5)).await;
                    });
                }
                json_ok(&st)
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Send one console line to the live dedicated server stdin.")]
    async fn match_command(
        &self,
        Parameters(args): Parameters<MatchCommandArgs>,
    ) -> Result<CallToolResult, McpError> {
        let mut g = self.matches.lock().await;
        match g.command(&args.command).await {
            Ok(()) => json_ok(&serde_json::json!({ "ok": true, "command": args.command })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Live match status: running, pid, elapsed, log lines. Pass since_line for incremental tails.")]
    async fn match_status(
        &self,
        Parameters(args): Parameters<MatchStatusArgs>,
    ) -> Result<CallToolResult, McpError> {
        let mut g = self.matches.lock().await;
        json_ok(&g.status_since(args.since_line))
    }

    #[tool(description = "Stop the live match (quit, then kill). Always safe. Harvests the log.")]
    async fn match_stop(
        &self,
        Parameters(args): Parameters<MatchStopArgs>,
    ) -> Result<CallToolResult, McpError> {
        let mut g = self.matches.lock().await;
        match g
            .stop(Duration::from_secs(args.timeout_sec.unwrap_or(5) as u64))
            .await
        {
            Ok(st) => json_ok(&st),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Plot a match (or A/B pair) and return structured ARGLOG/ARGEVT metrics.")]
    async fn analyze_match(
        &self,
        Parameters(args): Parameters<AnalyzeArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match analyze_match(
            &cfg,
            &args.bsp,
            &args.log_a,
            &args.out_png,
            args.log_b.as_deref(),
            args.nav_json.as_deref(),
        ) {
            Ok(r) => json_ok_pngs(&r, &[r.out_png.as_str()]),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List top-level *.log files in ARGUS_RUNS, newest first. Known baselines carry a note.")]
    async fn list_runs(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match list_runs(&cfg) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Brief a harvested log (or see what=run). Default is lite: headline, totals, flags, next_steps.")]
    async fn brief_run(
        &self,
        Parameters(args): Parameters<BriefArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match intel_brief(&cfg, &args.log, args.map.as_deref()) {
            Ok(r) => {
                if want_full(args.detail.as_deref()) {
                    json_ok(&r)
                } else {
                    json_ok(&brief_lite(&r))
                }
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "A/B two logs. Default is verdict+gates (not two full briefs). detail=full for both tapes.")]
    async fn compare_runs(
        &self,
        Parameters(args): Parameters<CompareArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let log_a = args.log_a.as_deref().unwrap_or("baseline");
        match intel_compare(&cfg, log_a, &args.log_b, args.map.as_deref()) {
            Ok(r) => {
                if want_full(args.detail.as_deref()) {
                    json_ok(&r)
                } else {
                    json_ok(&compare_lite(&r))
                }
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Concrete next places to look in the QC given a log or an A/B pair. Prefer this after compare_runs.")]
    async fn suggest_next(
        &self,
        Parameters(args): Parameters<SuggestArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        if let Some(b) = args.log_b.as_deref() {
            let a = args.log_a.as_deref().unwrap_or("baseline");
            match intel_compare(&cfg, a, b, args.map.as_deref()) {
                Ok(r) => json_ok(&r.next_steps),
                Err(e) => tool_err(e),
            }
        } else if let Some(log) = args.log.as_deref() {
            match intel_brief(&cfg, log, args.map.as_deref()) {
                Ok(r) => json_ok(&r.next_steps),
                Err(e) => tool_err(e),
            }
        } else {
            tool_err("pass log, or log_b (optional log_a, default baseline)")
        }
    }

    #[tool(description = "Lab dashboard: config readiness, maps (BSP/nav/dispatcher), recent runs, live match, and the next recommended tool call.")]
    async fn lab_status(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let live = {
            let mut g = self.matches.lock().await;
            let st = g.status();
            if st.running || st.log_path.is_some() {
                Some(st)
            } else {
                None
            }
        };
        json_ok(&build_lab(&cfg, live))
    }

    #[tool(description = "Cartograph every on-disk BSP in ARGUS_MAPS. PAK-only names are skipped until ingested.")]
    async fn cartograph_all(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match all_atlases(&cfg) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Find Argus QuakeC functions by name, role (hazard/combat/nav/lifecycle), or comment text.")]
    async fn qc_find(
        &self,
        Parameters(args): Parameters<QcFindArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match index_argus(&cfg) {
            Ok(idx) => {
                let hits: Vec<_> = qc_find(&idx, &args.query).into_iter().cloned().collect();
                json_ok(&hits)
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Index Argus QuakeC functions and AR_* constants with file:line.")]
    async fn qc_index(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match index_argus(&cfg) {
            Ok(idx) => json_ok(&idx),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Learn stall/lava/hazard cells across harvested logs. Writes src/argus_nav_<map>.costs.json for navgen; does not write QuakeC.")]
    async fn learn_hotspots(
        &self,
        Parameters(args): Parameters<LearnArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match learn_hotspots(&cfg, &args.map, args.max_logs.unwrap_or(8) as usize) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "What an LLM can change live vs what needs compile. skill is live (next respawn); AR_* constants are not.")]
    async fn knobs(&self) -> Result<CallToolResult, McpError> {
        json_ok(&knobs())
    }

    #[tool(description = "Send a whitelisted console cvar/command to the live dedicated server. skill 0-3 applies at next bot respawn. Not a free shell.")]
    async fn tune(
        &self,
        Parameters(args): Parameters<TuneArgs>,
    ) -> Result<CallToolResult, McpError> {
        let line = match validate_tune(&args.command) {
            Ok(l) => l,
            Err(e) => return tool_err(e),
        };
        let mut g = self.matches.lock().await;
        match g.command(&line).await {
            Ok(()) => json_ok(&serde_json::json!({
                "ok": true,
                "sent": line,
                "note": if line.to_ascii_lowercase().starts_with("skill") {
                    "skill applies at the next bot respawn (Argus_SetSkill)"
                } else {
                    "sent to dedicated stdin"
                },
            })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Last ARGLOG sample per bot from the live match, or the last harvested match if none is running.")]
    async fn live_snapshot(
        &self,
        Parameters(args): Parameters<LiveSnapshotArgs>,
    ) -> Result<CallToolResult, McpError> {
        let g = self.matches.lock().await;
        match g.log_text() {
            Some(text) if text.contains("ARGLOG") => {
                if args.since_line.is_some() {
                    json_ok(&crate::live::snapshot_window(&text, args.since_line))
                } else {
                    json_ok(&snapshot(&text))
                }
            }
            Some(_) => tool_err("match log has no ARGLOG yet; wait a second"),
            None => tool_err("no live or last match log"),
        }
    }

    #[tool(description = "Read one Argus QuakeC function with file:line and full source. Preferred way to see into the bot.")]
    async fn qc_read(
        &self,
        Parameters(args): Parameters<QcReadArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match qc_read(&cfg, &args.name) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(
        description = "One inspect call. what=help|project|lab|map|recipe|node|fn|const|live|bot|status|run|last|knobs. Use this before inventing a pipeline.",
        annotations(title = "see", read_only_hint = true)
    )]
    async fn see(
        &self,
        Parameters(args): Parameters<SeeArgs>,
    ) -> Result<CallToolResult, McpError> {
        let what = normalize_see(&args.what);
        self.note_see(&what, args.name.as_deref()).await;
        match what.as_str() {
            "help" => json_ok(&see_vocab()),
            "project" => {
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                json_ok(&project_view(&cfg))
            }
            "last" => {
                let session = self.session.lock().await.clone();
                let mut g = self.matches.lock().await;
                let status = g.status();
                json_ok(&serde_json::json!({
                    "session": session,
                    "match": if status.running || status.log_path.is_some() {
                        Some(status)
                    } else {
                        None
                    },
                }))
            }
            "knobs" => json_ok(&knobs()),
            "status" => {
                let mut g = self.matches.lock().await;
                json_ok(&g.status_since(args.since_line))
            }
            "lab" => {
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                let live = {
                    let mut g = self.matches.lock().await;
                    let st = g.status();
                    if st.running || st.log_path.is_some() {
                        Some(st)
                    } else {
                        None
                    }
                };
                json_ok(&build_lab(&cfg, live))
            }
            "live" => {
                let g = self.matches.lock().await;
                match g.log_text() {
                    Some(text) if text.contains("ARGLOG") => json_ok(&snapshot(&text)),
                    _ => tool_err("no ARGLOG yet; start a match or see what=last"),
                }
            }
            "bot" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=Reap or latest:Reap", None)
                })?;
                let (bot, log) = split_tape_bot(raw);
                let text = match log {
                    Some(l) => {
                        let cfg = match cfg_read_or_err() {
                            Ok(c) => c,
                            Err(r) => return Ok(r),
                        };
                        match load_named_tape(&cfg, l) {
                            Ok(t) => t,
                            Err(e) => return tool_err(e),
                        }
                    }
                    None => {
                        let g = self.matches.lock().await;
                        match g.log_text() {
                            Some(t) => t,
                            None => return tool_err("no match log; use name=latest:Reap"),
                        }
                    }
                };
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match bot_deep(&cfg, &text, bot) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "timeline" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=Reap or ab_dm4_parity:Omi", None)
                })?;
                let (bot, log) = split_tape_bot(raw);
                let text = match log {
                    Some(l) => {
                        let cfg = match cfg_read_or_err() {
                            Ok(c) => c,
                            Err(r) => return Ok(r),
                        };
                        match load_named_tape(&cfg, l) {
                            Ok(t) => t,
                            Err(e) => return tool_err(e),
                        }
                    }
                    None => {
                        let g = self.matches.lock().await;
                        match g.log_text() {
                            Some(t) => t,
                            None => return tool_err("no match log; use name=latest:Reap"),
                        }
                    }
                };
                json_ok(&timeline(&text, bot, 40))
            }
            "fn" | "qc" => {
                let name = args.name.as_deref().unwrap_or("Argus_");
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match qc_read(&cfg, name) {
                    Ok(r) => json_ok(&r),
                    Err(_) => match index_argus(&cfg) {
                        Ok(idx) => json_ok(&qc_find(&idx, name)),
                        Err(e) => tool_err(e),
                    },
                }
            }
            "const" => {
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match index_argus(&cfg) {
                    Ok(idx) => {
                        let q = args.name.as_deref().unwrap_or("AR_").to_ascii_lowercase();
                        let hits: Vec<_> = idx
                            .constants
                            .into_iter()
                            .filter(|c| c.name.to_ascii_lowercase().contains(&q))
                            .collect();
                        json_ok(&hits)
                    }
                    Err(e) => tool_err(e),
                }
            }
            "run" => {
                let name = args.name.as_deref().unwrap_or("latest");
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match intel_brief(&cfg, name, None) {
                    Ok(r) => {
                        if want_full(args.detail.as_deref()) {
                            json_ok(&r)
                        } else {
                            json_ok(&brief_lite(&r))
                        }
                    }
                    Err(e) => tool_err(e),
                }
            }
            "demo" => {
                let name = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params(
                        "name=<demo> (a .dem in runs/demos or the game dir; record one with '+record <name> <map>')",
                        None,
                    )
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match crate::demo::demo_brief(&cfg, name) {
                    Ok(b) => json_ok(&b),
                    Err(e) => tool_err(e),
                }
            }
            "node" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=dm4:56", None)
                })?;
                let (map, id) = parse_node_ref(raw).ok_or_else(|| {
                    McpError::invalid_params("name=dm4:56", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match node_deep(&cfg, map, id) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "path" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=dm4:56-72 or dm4:quad->lg", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match route_ref(&cfg, raw) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "item" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=dm4:quad or dm4:weapon_lightning", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match item_view(&cfg, raw) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "search" => {
                let needle = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=CONTENT_LAVA", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match qc_search(&cfg, needle, 24) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "file" => {
                let spec = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=argus.qc or argus.qc:120-180", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match qc_file_slice(&cfg, spec) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "around" => {
                let raw = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=dm4:200,-900,24", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match around_point(&cfg, raw) {
                    Ok(v) => json_ok(&v),
                    Err(e) => tool_err(e),
                }
            }
            "plan" => {
                let raw = args.name.as_deref().unwrap_or("latest");
                let text = {
                    let cfg = match cfg_read_or_err() {
                        Ok(c) => c,
                        Err(r) => return Ok(r),
                    };
                    match load_named_tape(&cfg, raw) {
                        Ok(t) => t,
                        Err(_) => {
                            let g = self.matches.lock().await;
                            match g.log_text() {
                                Some(t) => t,
                                None => return tool_err("no tape; pass name=latest or a run"),
                            }
                        }
                    }
                };
                json_ok(&plan_view(&text))
            }
            "map" | "recipe" => {
                let name = args.name.as_deref().ok_or_else(|| {
                    McpError::invalid_params("name=dm4", None)
                })?;
                let cfg = match cfg_read_or_err() {
                    Ok(c) => c,
                    Err(r) => return Ok(r),
                };
                match map_cartograph(&cfg, name) {
                    Ok(a) => {
                        if what == "recipe" {
                            json_ok(&serde_json::json!({ "recipe": a.recipe, "headline": a.headline }))
                        } else if args
                            .detail
                            .as_deref()
                            .map(|d| d.eq_ignore_ascii_case("full"))
                            .unwrap_or(false)
                        {
                            json_ok(&a)
                        } else {
                            json_ok(&atlas_brief(&a))
                        }
                    }
                    Err(e) => tool_err(e),
                }
            }
            _ => tool_err(format!(
                "what={what} is unknown. try help, project, lab, map, node, path, item, fn, file, search, live, bot, timeline, around, plan, run, last, or knobs"
            )),
        }
    }

    #[tool(description = "After a QC edit: compile + short match + duration-scaled A/B. Default return is lite (verdict, gates, next).")]
    async fn experiment(
        &self,
        Parameters(args): Parameters<ExperimentArgs>,
    ) -> Result<CallToolResult, McpError> {
        let dur = args.duration_sec.unwrap_or(30);
        if !(10..=185).contains(&dur) {
            return Err(McpError::invalid_params(
                "experiment duration_sec must be 10..=185",
                None,
            ));
        }
        if let Some(s) = args.skill {
            if s > 3 {
                return Err(McpError::invalid_params("skill must be 0..3", None));
            }
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut compile_result = None;
        if args.compile.unwrap_or(true) {
            let cfg_c = cfg.clone();
            let compiled = match tokio::time::timeout(
                Duration::from_secs(90),
                tokio::task::spawn_blocking(move || compile_qc(&cfg_c, true)),
            )
            .await
            {
                Ok(j) => j.map_err(|e| McpError::internal_error(e.to_string(), None))?,
                Err(_) => return tool_err("compile_qc timed out after 90s"),
            };
            if !compiled.ok {
                self.session.lock().await.note_experiment(ExperimentRecord {
                    map: args.map.clone(),
                    run_name: String::new(),
                    duration_sec: dur,
                    compile_ok: Some(false),
                    verdict: None,
                    headline: Some("compile failed".into()),
                });
                return json_ok(&serde_json::json!({
                    "ok": false,
                    "stage": "compile",
                    "compile": compiled,
                    "next": "see what=fn name=<the error> and fix QC",
                }));
            }
            compile_result = Some(compiled);
        }
        let run_name = args
            .run_name
            .clone()
            .unwrap_or_else(|| format!("exp_{}", args.map));
        {
            let mut g = self.matches.lock().await;
            g.reap();
            if g.status().running {
                let _ = g.stop(Duration::from_secs(3)).await;
            }
        }
        let mut g = self.matches.lock().await;
        let ran = match g
            .run(
                &cfg,
                &args.map,
                dur,
                Some(&run_name),
                None,
                args.skill,
            )
            .await
        {
            Ok(r) => r,
            Err(e) => return tool_err(e),
        };
        drop(g);
        let baseline = args.baseline.as_deref().unwrap_or("baseline");
        let compare = intel_compare_scaled(&cfg, baseline, &ran.log_path, Some(&args.map)).ok();
        let verdict = compare.as_ref().map(|c| format!("{:?}", c.verdict).to_ascii_lowercase());
        let headline = compare
            .as_ref()
            .map(|c| c.headline.clone())
            .or_else(|| Some(ran.brief.headline.clone()));
        self.session.lock().await.note_experiment(ExperimentRecord {
            map: args.map.clone(),
            run_name: ran.run_name.clone(),
            duration_sec: dur,
            compile_ok: compile_result.as_ref().map(|c| c.ok),
            verdict: verdict.clone(),
            headline: headline.clone(),
        });
        if want_full(args.detail.as_deref()) {
            return json_ok(&serde_json::json!({
                "ok": ran.ok,
                "compile": compile_result,
                "match": ran,
                "compare": compare,
            }));
        }
        let next = compare
            .as_ref()
            .and_then(|c| c.next_steps.first())
            .map(|s| format!("qc_read name around {}", s.look_at));
        json_ok(&serde_json::json!({
            "ok": ran.ok,
            "compile_ok": compile_result.as_ref().map(|c| c.ok),
            "log": ran.log_path,
            "elapsed_sec": ran.elapsed_sec,
            "compare": compare.as_ref().map(compare_lite),
            "match": brief_lite(&ran.brief),
            "next": next,
        }))
    }

    #[tool(description = "Short experiment on several maps after one compile. Default dm2,dm3,dm4,dm6,lqdm2 at 20s each.")]
    async fn matrix_experiment(
        &self,
        Parameters(args): Parameters<MatrixArgs>,
    ) -> Result<CallToolResult, McpError> {
        let dur = args.duration_sec.unwrap_or(20);
        if !(10..=60).contains(&dur) {
            return Err(McpError::invalid_params(
                "matrix duration_sec must be 10..=60",
                None,
            ));
        }
        let maps = args.maps.unwrap_or_else(|| {
            vec![
                "dm2".into(),
                "dm3".into(),
                "dm4".into(),
                "dm6".into(),
                "lqdm2".into(),
            ]
        });
        if maps.is_empty() || maps.len() > 6 {
            return Err(McpError::invalid_params("maps must be 1..=6 names", None));
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut compile_ok = None;
        if args.compile.unwrap_or(true) {
            let cfg_c = cfg.clone();
            let compiled = match tokio::time::timeout(
                Duration::from_secs(90),
                tokio::task::spawn_blocking(move || compile_qc(&cfg_c, true)),
            )
            .await
            {
                Ok(j) => j.map_err(|e| McpError::internal_error(e.to_string(), None))?,
                Err(_) => return tool_err("compile_qc timed out after 90s"),
            };
            if !compiled.ok {
                return json_ok(&serde_json::json!({
                    "ok": false,
                    "stage": "compile",
                    "compile": compiled,
                }));
            }
            compile_ok = Some(true);
        }
        let mut results = Vec::new();
        for map in &maps {
            {
                let mut g = self.matches.lock().await;
                g.reap();
                if g.status().running {
                    let _ = g.stop(Duration::from_secs(3)).await;
                }
            }
            let mut g = self.matches.lock().await;
            let ran = g
                .run(
                    &cfg,
                    map,
                    dur,
                    Some(&format!("mx_{map}")),
                    None,
                    args.skill,
                )
                .await;
            drop(g);
            match ran {
                Ok(r) => {
                    let cmp = intel_compare_scaled(&cfg, "baseline", &r.log_path, Some(map)).ok();
                    results.push(serde_json::json!({
                        "map": map,
                        "ok": r.ok,
                        "log": r.log_path,
                        "headline": r.brief.headline,
                        "compare": cmp.as_ref().map(compare_lite),
                    }));
                }
                Err(e) => {
                    results.push(serde_json::json!({
                        "map": map,
                        "ok": false,
                        "error": e,
                    }));
                }
            }
        }
        json_ok(&serde_json::json!({
            "ok": results.iter().all(|r| r.get("ok").and_then(|v| v.as_bool()).unwrap_or(false)),
            "compile_ok": compile_ok,
            "duration_sec": dur,
            "results": results,
        }))
    }

    #[tool(description = "Prefer experiment. Short compile+match+brief with no A/B. duration 10-120s.")]
    async fn probe(
        &self,
        Parameters(args): Parameters<ProbeArgs>,
    ) -> Result<CallToolResult, McpError> {
        let dur = args.duration_sec.unwrap_or(20);
        if !(10..=120).contains(&dur) {
            return Err(McpError::invalid_params(
                "probe duration_sec must be 10..=120",
                None,
            ));
        }
        if let Some(s) = args.skill {
            if s > 3 {
                return Err(McpError::invalid_params("skill must be 0..3", None));
            }
        }
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut compile_result = None;
        if args.compile.unwrap_or(true) {
            let cfg_c = cfg.clone();
            let compiled = tokio::task::spawn_blocking(move || compile_qc(&cfg_c, true))
                .await
                .map_err(|e| McpError::internal_error(e.to_string(), None))?;
            if !compiled.ok {
                return json_ok(&serde_json::json!({
                    "ok": false,
                    "stage": "compile",
                    "compile": compiled,
                }));
            }
            compile_result = Some(compiled);
        }
        let mut g = self.matches.lock().await;
        match g
            .run(
                &cfg,
                &args.map,
                dur,
                Some(&format!("probe_{}", args.map)),
                None,
                args.skill,
            )
            .await
        {
            Ok(r) => json_ok(&serde_json::json!({
                "ok": r.ok,
                "compile_ok": compile_result.as_ref().map(|c| c.ok),
                "log": r.log_path,
                "match": brief_lite(&r.brief),
            })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "The Argus A/B quality bars this server uses when briefing and comparing runs.")]
    async fn quality_bars(&self) -> Result<CallToolResult, McpError> {
        Ok(CallToolResult::success(vec![ContentBlock::text(
            QUALITY_BARS,
        )]))
    }
}

#[prompt_router]
impl Argus {
    #[prompt(
        name = "review_run",
        description = "Review one harvested Argus match against the project quality bars"
    )]
    async fn review_run(
        &self,
        Parameters(args): Parameters<BriefArgs>,
    ) -> Result<Vec<PromptMessage>, McpError> {
        let cfg = Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let brief = intel_brief(&cfg, &args.log, args.map.as_deref())
            .map_err(|e| McpError::invalid_params(e, None))?;
        let body = format!(
            "Review this Argus match. Trust these computed numbers; do not re-parse the log by hand.\n\n{}\n\nQuality bars:\n{}",
            serde_json::to_string_pretty(&brief_lite(&brief)).unwrap_or_default(),
            QUALITY_BARS
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "review_ab",
        description = "Review an Argus A/B pair (baseline vs candidate) with a computed verdict"
    )]
    async fn review_ab(
        &self,
        Parameters(args): Parameters<CompareArgs>,
    ) -> Result<Vec<PromptMessage>, McpError> {
        let cfg = Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let log_a = args.log_a.as_deref().unwrap_or("baseline");
        let report = intel_compare(&cfg, log_a, &args.log_b, args.map.as_deref())
            .map_err(|e| McpError::invalid_params(e, None))?;
        let body = format!(
            "Review this Argus A/B. log_a is the baseline, log_b is the candidate. Trust the verdict and gates; explain them, do not re-count ARGLOG lines.\n\n{}\n\nQuality bars:\n{}",
            serde_json::to_string_pretty(&compare_lite(&report)).unwrap_or_default(),
            QUALITY_BARS
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "review_map",
        description = "Review a map atlas from the cartographer (BSP ingest) for Argus nav and item control"
    )]
    async fn review_map(
        &self,
        Parameters(args): Parameters<MapArgs>,
    ) -> Result<Vec<PromptMessage>, McpError> {
        let cfg = Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let atlas = map_cartograph(&cfg, &args.bsp)
            .map_err(|e| McpError::invalid_params(e, None))?;
        let body = format!(
            "Review this Argus map brief. Trust reach (walk/jump/rocket_jump/off_graph) and the recipe. Do not invent a nav story that contradicts nearest_node.\n\n{}",
            serde_json::to_string_pretty(&atlas_brief(&atlas)).unwrap_or_default()
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "orient",
        description = "Orient an LLM on the Argus tree, live vs compile knobs, and how to test"
    )]
    async fn orient(&self) -> Result<Vec<PromptMessage>, McpError> {
        let cfg = Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let view = project_view(&cfg);
        let session = self.session.lock().await.clone();
        let body = format!(
            "You are in the Argus lab. Follow AGENTS.md. Do not invent a shell pipeline. First call is already see what=project. Use see / experiment / tune.\n\n{}\n\nSession last-seen:\n{}\n\nQuality bars:\n{}",
            serde_json::to_string_pretty(&view).unwrap_or_default(),
            serde_json::to_string_pretty(&session).unwrap_or_default(),
            QUALITY_BARS
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }
}

fn parse_node_ref(raw: &str) -> Option<(&str, u32)> {
    let (map, id) = raw.split_once(':')?;
    let id = id.parse().ok()?;
    if map.is_empty() {
        return None;
    }
    Some((map, id))
}

#[tool_handler(
    name = "argus-mcp",
    version = "0.18.0",
    instructions = "Argus lab 0.18. Do not invent a fteqcc/quakespasm/python pipeline. First call: see what=project. Then see what=map / path / fn / search. After a QC edit: experiment or matrix_experiment. Live: tune. Incremental logs: match_status since_line. Human deploy wizard: argus-mcp gui. Trust next_steps. Prefer native tools over extras."
)]
#[prompt_handler]
impl ServerHandler for Argus {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(
            ServerCapabilities::builder()
                .enable_tools()
                .enable_prompts()
                .enable_resources()
                .build(),
        )
        .with_server_info(Implementation::new("argus-mcp", "0.18.0"))
        .with_instructions(
            "Argus lab 0.18. Do not invent a fteqcc/quakespasm/python pipeline. \
First call: see what=project. Then see what=map / path / fn / search. After a QC \
edit: experiment or matrix_experiment. Live: tune. Incremental logs: match_status \
since_line. Trust next_steps. Prefer native tools over extras.",
        )
    }

    async fn list_resources(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> Result<ListResourcesResult, McpError> {
        let cfg = Config::load_for_reads().ok();
        Ok(crate::resources::list_static(cfg.as_ref()))
    }

    async fn list_resource_templates(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> Result<ListResourceTemplatesResult, McpError> {
        Ok(crate::resources::list_templates())
    }

    async fn read_resource(
        &self,
        request: ReadResourceRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> Result<ReadResourceResponse, McpError> {
        let cfg = Config::load_for_reads().ok();
        let session = self.session.lock().await.clone();
        match crate::resources::read_uri(&request.uri, cfg.as_ref(), &session) {
            Ok(contents) => Ok(ReadResourceResponse::Complete(ReadResourceResult::new(
                contents,
            ))),
            Err(e) => Err(McpError::resource_not_found(e, None)),
        }
    }
}
