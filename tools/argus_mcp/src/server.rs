use crate::analyze::analyze_match;
use crate::cartograph::{
    atlas_brief, cartograph as map_cartograph, inspect_entities, list_maps as map_list,
};
use crate::compile::compile_qc;
use crate::compile::compile_qc_dir;
use crate::config::Config;
use crate::intel::{
    brief_lite, brief_run as intel_brief, compare_lite, compare_runs as intel_compare,
    compare_runs_scaled as intel_compare_scaled, sim_report, want_full, QUALITY_BARS,
};
use crate::lab::{cartograph_all as all_atlases, lab_status as build_lab};
use crate::learn::learn_hotspots;
use crate::live::{knobs, snapshot, validate_tune};
use crate::match_ctrl::{list_runs, MatchCtrl, DURATION_MAX, DURATION_MIN};
use crate::nav_graph::{around_point, item_view, node_deep, route_ref};
use crate::nav_sync::nav_sync_dispatch;
use crate::navgen::nav_generate;
use crate::project::{project_view, see_vocab};
use crate::qc_index::{index_argus, qc_file_slice, qc_find, qc_read, qc_search};
use crate::see_alias::normalize_see;
use crate::session::{ExperimentRecord, SessionSeen};
use crate::tape_view::{bot_deep, load_named_tape, plan_view, split_tape_bot, timeline};
use rmcp::handler::server::tool::ToolRouter;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{
    CallToolResult, CompleteRequestParams, CompleteResult, CompletionInfo, ContentBlock,
    ElicitRequestParams, ElicitResult, ElicitationAction, ElicitationSchema, EnumSchema,
    Implementation, JsonObject, ListResourceTemplatesResult, ListResourcesResult,
    PaginatedRequestParams, PrimitiveSchemaDefinition, ProgressNotificationParam, PromptMessage,
    ReadResourceRequestParams, ReadResourceResponse, ReadResourceResult, Reference,
    RequestMetaObject, ResourceUpdatedNotificationParam, Role, ServerCapabilities, ServerInfo,
    SubscribeRequestParams, SubscriptionFilter, ToolAnnotations, UnsubscribeRequestParams,
};
use rmcp::service::{ElicitationMode, RequestContext, RoleServer, SubscriptionContext};
use rmcp::ErrorData as McpError;
use rmcp::{
    prompt, prompt_handler, prompt_router, schemars, tool, tool_handler, tool_router, Peer,
    ServerHandler,
};
use serde::Deserialize;
use serde::Serialize;
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::Mutex;

const SERVER_NAME: &str = env!("CARGO_PKG_NAME");
const SERVER_VERSION: &str = env!("CARGO_PKG_VERSION");

const READ_ONLY_TOOLS: &[&str] = &[
    "bot_capture_pov_frame",
    "brief_run",
    "bsp_inspect_entities",
    "cartograph_all",
    "compare_runs",
    "config_check",
    "corpus",
    "lab_status",
    "list_maps",
    "list_runs",
    "live_snapshot",
    "match_status",
    "mill",
    "knobs",
    "qc_find",
    "qc_index",
    "qc_read",
    "quality_bars",
    "see",
    "suggest_next",
];

const MUTATING_TOOLS: &[&str] = &[
    "analyze_match",
    "baseline_set",
    "bot_simulate_match",
    "campaign_experiment",
    "cartograph",
    "compile_qc",
    "experiment",
    "learn_hotspots",
    "match_command",
    "match_run",
    "match_start",
    "match_stop",
    "matrix_experiment",
    "nav_generate",
    "nav_sync_dispatch",
    "probe",
    "quake_compile_qc",
    "rcon_exec",
    "ship",
    "tune",
];

fn server_instructions() -> String {
    format!(
        "Argus lab {SERVER_VERSION}. Do not invent a fteqcc/quakespasm/python pipeline. \
First call: see what=project. Then see what=map / path / fn / search. After a QC \
edit: experiment or matrix_experiment. Live: tune. Incremental logs: match_status \
since_line. Session demos: see what=demo (harvest first with \
tools/harvest_session.py). Trust next_steps and the brief's \
cause/reach_pct/item_control fields. Prefer native tools over extras."
    )
}

#[derive(Clone)]
pub struct Argus {
    pub matches: Arc<Mutex<MatchCtrl>>,
    pub session: Arc<Mutex<SessionSeen>>,
    /// Serialises whole matches WITHOUT blocking the read paths. The
    /// `matches` mutex used to do both jobs, so match_status,
    /// match_stop, tune, live_snapshot, see what=live and shutdown all
    /// queued behind a running match_run. Only the run paths take this.
    pub run_gate: Arc<Mutex<()>>,
    legacy_subscriptions: Arc<Mutex<HashMap<String, tokio::task::AbortHandle>>>,
}

#[derive(Clone)]
struct ProgressReporter {
    token: Option<rmcp::model::ProgressToken>,
    peer: Peer<RoleServer>,
}

impl ProgressReporter {
    fn new(meta: RequestMetaObject, peer: Peer<RoleServer>) -> Self {
        Self {
            token: meta.get_progress_token(),
            peer,
        }
    }

    async fn send(&self, progress: f64, total: f64, message: impl Into<String>) {
        let Some(notification) =
            progress_notification(self.token.as_ref(), progress, total, message.into())
        else {
            return;
        };
        let _ = self.peer.notify_progress(notification).await;
    }
}

fn progress_notification(
    token: Option<&rmcp::model::ProgressToken>,
    progress: f64,
    total: f64,
    message: String,
) -> Option<ProgressNotificationParam> {
    token.map(|token| {
        ProgressNotificationParam::new(token.clone(), progress)
            .with_total(total)
            .with_message(message)
    })
}

#[derive(Clone)]
struct MatchProgress {
    reporter: ProgressReporter,
    start: f64,
    span: f64,
    total: f64,
    label: String,
}

impl Argus {
    pub fn new() -> Self {
        // restarts are the norm here (every staged binary needs one):
        // the last-seen memory survives them on disk
        let seen = crate::session::session_path()
            .map(|p| SessionSeen::load(&p))
            .unwrap_or_default();
        Self {
            matches: Arc::new(Mutex::new(MatchCtrl::default())),
            run_gate: Arc::new(Mutex::new(())),
            session: Arc::new(Mutex::new(seen)),
            legacy_subscriptions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Attach one explicit safety contract to every generated route. Keeping
    /// the partition here makes the whole tool surface reviewable at once and
    /// makes a newly added, unclassified tool fail immediately in tests and at
    /// startup instead of inheriting the protocol's destructive defaults.
    fn annotated_tool_router() -> ToolRouter<Self> {
        let mut router = Self::tool_router();
        for (name, route) in &mut router.map {
            let read_only = READ_ONLY_TOOLS.contains(&name.as_ref());
            let mutating = MUTATING_TOOLS.contains(&name.as_ref());
            assert_ne!(
                read_only, mutating,
                "MCP tool {name} must appear in exactly one safety class"
            );
            route.attr.annotations = Some(ToolAnnotations::from_raw(
                Some(name.to_string()),
                Some(read_only),
                Some(mutating),
                Some(read_only),
                Some(false),
            ));
        }
        router
    }

    /// Drive a match WITHOUT holding the MatchCtrl mutex for its whole
    /// length. The lock is taken to start it, released while it runs
    /// and taken again to stop it, so match_status, match_stop, tune,
    /// live_snapshot and see what=live stay answerable during a
    /// match_run and shutdown can reach the engine.
    // This is the lock-safe adapter for the public match tool fields. Keeping
    // them explicit makes it harder for start and finish to disagree.
    #[allow(clippy::too_many_arguments)]
    async fn drive_match(
        &self,
        cfg: &crate::config::Config,
        map: &str,
        duration_sec: u32,
        run_name: Option<&str>,
        slots: Option<u32>,
        skill: Option<u32>,
        coop: Option<bool>,
        progress: Option<MatchProgress>,
    ) -> Result<crate::match_ctrl::MatchRunResult, String> {
        let _one_at_a_time = self.run_gate.lock().await;
        if let Some(p) = &progress {
            p.reporter
                .send(p.start, p.total, format!("starting {}", p.label))
                .await;
        }
        {
            let mut g = self.matches.lock().await;
            g.begin(cfg, map, duration_sec, run_name, slots, skill, coop)
                .await?;
        }
        let limit = duration_sec as u64;
        let mut last_reported = u64::MAX;
        loop {
            let (running, elapsed) = {
                let mut g = self.matches.lock().await;
                g.poll()
            };
            if !running || elapsed >= limit || crate::match_ctrl::live_cancelled() {
                break;
            }
            if elapsed != last_reported {
                if let Some(p) = &progress {
                    let fraction = if limit == 0 {
                        1.0
                    } else {
                        (elapsed as f64 / limit as f64).clamp(0.0, 1.0)
                    };
                    p.reporter
                        .send(
                            p.start + p.span * fraction,
                            p.total,
                            format!("{}: {elapsed}/{limit}s", p.label),
                        )
                        .await;
                }
                last_reported = elapsed;
            }
            tokio::time::sleep(std::time::Duration::from_millis(400)).await;
        }
        let mut g = self.matches.lock().await;
        let result = g.finish(cfg, map).await;
        drop(g);
        if let Some(p) = &progress {
            p.reporter
                .send(p.start + p.span, p.total, format!("finished {}", p.label))
                .await;
        }
        result
    }

    pub async fn shutdown(&self) {
        // kill the engine first and without the lock. A client that
        // closes stdio mid match leaves match_run holding the mutex,
        // and the old lock-then-shutdown queued behind it until the
        // match ended, or never, if the client killed us outright.
        crate::match_ctrl::cancel_live();
        if let Ok(mut g) =
            tokio::time::timeout(std::time::Duration::from_secs(10), self.matches.lock()).await
        {
            g.shutdown().await;
        }
    }

    fn persist_session(seen: &SessionSeen) {
        if let Some(p) = crate::session::session_path() {
            seen.save(&p);
        }
    }

    async fn note_see(&self, what: &str, name: Option<&str>) {
        let mut s = self.session.lock().await;
        s.note_see(what, name);
        Self::persist_session(&s);
    }

    async fn live_resource_snapshot(&self, uris: &[String]) -> BTreeMap<String, String> {
        let mut snapshot = BTreeMap::new();
        if uris.iter().any(|uri| uri == "argus://last") {
            let session = self.session.lock().await.clone();
            if let Ok(value) = serde_json::to_string(&session) {
                snapshot.insert("argus://last".into(), value);
            }
        }
        if uris.iter().any(|uri| uri == "argus://lab") {
            if let Some(cfg) = Config::load_for_reads()
                .ok()
                .filter(|cfg| cfg.root.exists())
            {
                let live = {
                    let mut matches = self.matches.lock().await;
                    matches.reap();
                    matches.status()
                };
                if let Ok(value) = serde_json::to_string(&build_lab(&cfg, Some(live))) {
                    snapshot.insert("argus://lab".into(), value);
                }
            }
        }
        snapshot
    }
}

const LIVE_RESOURCE_URIS: [&str; 2] = ["argus://last", "argus://lab"];

fn changed_resource_uris(
    previous: &mut BTreeMap<String, String>,
    current: BTreeMap<String, String>,
) -> Vec<String> {
    let changed = current
        .iter()
        .filter(|(uri, value)| previous.get(*uri) != Some(*value))
        .map(|(uri, _)| uri.clone())
        .collect();
    *previous = current;
    changed
}

fn configured_baseline_maps(cfg: &Config) -> Vec<String> {
    let mut maps: Vec<String> = crate::intel::all_baseline_bands(cfg)
        .into_iter()
        .filter(|(_, runs)| {
            runs.iter()
                .any(|run| crate::paths::resolve_log(cfg, run).is_ok())
        })
        .map(|(map, _)| map)
        .collect();
    maps.sort_by_key(|map| map.to_ascii_lowercase());
    maps.dedup_by(|a, b| a.eq_ignore_ascii_case(b));
    maps
}

fn accepted_elicited_map(result: ElicitResult, offered: &[String]) -> Option<String> {
    if result.action != ElicitationAction::Accept {
        return None;
    }
    let content = result.content?;
    let selected = content.get("map")?.as_str()?.trim();
    offered
        .iter()
        .find(|map| map.eq_ignore_ascii_case(selected))
        .cloned()
}

async fn elicit_baseline_map(peer: &Peer<RoleServer>, offered: &[String]) -> Option<String> {
    if offered.is_empty()
        || !peer
            .supported_elicitation_modes()
            .contains(&ElicitationMode::Form)
    {
        return None;
    }
    let schema = baseline_elicitation_schema(offered)?;
    let result = peer
        .create_elicitation_with_timeout(
            ElicitRequestParams::FormElicitationParams {
                meta: None,
                message: "The candidate tape does not identify a map. Choose the configured baseline map to compare against.".into(),
                requested_schema: schema,
            },
            Some(Duration::from_secs(30)),
        )
        .await
        .ok()?;
    accepted_elicited_map(result, offered)
}

fn baseline_elicitation_schema(offered: &[String]) -> Option<ElicitationSchema> {
    if offered.is_empty() {
        return None;
    }
    let options = EnumSchema::builder(offered.to_vec())
        .title("Baseline map")
        .description("Map whose configured baseline band should be used")
        .build();
    ElicitationSchema::builder()
        .required_property("map", PrimitiveSchemaDefinition::Enum(options))
        .build()
        .ok()
}

fn json_ok<T: Serialize>(value: &T) -> Result<CallToolResult, McpError> {
    json_ok_pngs(value, &[])
}

fn json_value<T: Serialize>(value: &T) -> Result<serde_json::Value, McpError> {
    let mut v =
        serde_json::to_value(value).map_err(|e| McpError::internal_error(e.to_string(), None))?;
    // a stale server must never hand out an unmarked opinion: the
    // banner rides every object response for the whole session
    if let (Some(note), serde_json::Value::Object(map)) = (crate::stale::banner(), &mut v) {
        map.insert("lab_stale".into(), serde_json::Value::String(note));
    }
    Ok(v)
}

fn json_ok_pngs<T: Serialize>(value: &T, pngs: &[&str]) -> Result<CallToolResult, McpError> {
    let v = json_value(value)?;
    let text = serde_json::to_string_pretty(&v)
        .map_err(|e| McpError::internal_error(e.to_string(), None))?;
    let mut blocks = vec![ContentBlock::text(text)];
    for p in pngs {
        if let Some(img) = png_block(p) {
            blocks.push(img);
        }
    }
    Ok(CallToolResult::success(blocks))
}

fn report_output_schema() -> Arc<JsonObject> {
    let serde_json::Value::Object(schema) = serde_json::json!({
        "type": "object",
        "required": ["format", "detail", "data"],
        "properties": {
            "format": {"type": "string", "enum": ["json", "csv"]},
            "detail": {"type": "string", "enum": ["brief", "full", "table"]},
            "data": {}
        },
        "additionalProperties": false
    }) else {
        unreachable!("the report output schema is an object")
    };
    Arc::new(schema)
}

fn report_json_ok<T: Serialize>(
    value: &T,
    detail: &'static str,
) -> Result<CallToolResult, McpError> {
    let value = json_value(value)?;
    let text = serde_json::to_string_pretty(&value)
        .map_err(|e| McpError::internal_error(e.to_string(), None))?;
    let mut result = CallToolResult::success(vec![ContentBlock::text(text)]);
    result.structured_content = Some(serde_json::json!({
        "format": "json",
        "detail": detail,
        "data": value,
    }));
    Ok(result)
}

fn csv_text(body: String) -> String {
    match crate::stale::banner() {
        Some(note) => format!("# lab_stale: {note}\n{body}"),
        None => body,
    }
}

fn report_csv_ok(body: String) -> Result<CallToolResult, McpError> {
    let text = csv_text(body);
    let mut result = CallToolResult::success(vec![ContentBlock::text(text.clone())]);
    result.structured_content = Some(serde_json::json!({
        "format": "csv",
        "detail": "table",
        "data": text,
    }));
    Ok(result)
}

/// CSV rather than JSON, because every one of these answers is a
/// table and a table costs about half the tokens as CSV. The
/// stale banner still rides along, as a comment line, because a
/// stale server must never hand out an unmarked opinion.
fn csv_ok(body: String) -> Result<CallToolResult, McpError> {
    let text = csv_text(body);
    Ok(CallToolResult::success(vec![ContentBlock::text(text)]))
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
        return "config_check, then set the named ARGUS_* key in env or tools/argus_mcp.toml"
            .into();
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
    #[schemars(
        description = "Ignored; id-format output is required. Accepted for spec compatibility."
    )]
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
    #[schemars(
        description = "Also pass --register: first registration requires current reach and mill evidence before wiring progs.src and argus_nav_dispatch.qc"
    )]
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
    #[schemars(
        description = "json (default) or csv. The per-bot rows, hotspots, kill matrix and event counts are tables, and a table as CSV is about half the tokens."
    )]
    pub format: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
/// EVERY FIELD HERE IS PAID FOR ON EVERY REQUEST, whether or not
/// this tool is called, so the descriptions say what a caller cannot
/// guess and nothing else. Measured: this tool was 2126 bytes of a
/// 19,397 byte surface, the most expensive schema in the server and
/// more than the three parked extras put together, because it
/// explained each view twice. The prose belongs in the tool
/// description and the operator guide.
pub struct CorpusArgs {
    #[schemars(description = "tapes (default) | cells | changes | bisect")]
    pub what: Option<String>,
    pub map: Option<String>,
    #[schemars(
        description = "bot (default) or human. Never average a human tape into a bot series."
    )]
    pub kind: Option<String>,
    #[schemars(
        description = "listen | dedicated_fast | dedicated_slow. One class at a time is how to be sure a step is not the frame rate."
    )]
    pub tick_class: Option<String>,
    #[schemars(description = "substring of the run name, eg ab_dm4_leadclip")]
    pub run_like: Option<String>,
    #[schemars(description = "YYYY-MM-DD")]
    pub since: Option<String>,
    #[schemars(description = "YYYY-MM-DD")]
    pub until: Option<String>,
    #[schemars(
        description = "stalls|engages|lava_deaths|world_deaths|freezes|freeze_underfire|cover|goals|frags|deaths|routefails|hazards|grabs|weapons|boards|kd_spread|avg_speed. Without one, the matching tapes."
    )]
    pub metric: Option<String>,
    #[schemars(description = "map|month|day|tick_class|kind|run")]
    pub group_by: Option<String>,
    pub limit: Option<u32>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CompareArgs {
    #[schemars(
        description = "Baseline: path, run name, or 'baseline'/'shipped'. Default baseline."
    )]
    pub log_a: Option<String>,
    #[schemars(description = "Candidate: path, run name, or 'latest'")]
    pub log_b: String,
    pub map: Option<String>,
    #[schemars(description = "brief (default, verdict+gates) or full (both MatchBriefs)")]
    pub detail: Option<String>,
    #[schemars(
        description = "json (default) or csv. Every large part of this answer is a table, and a table as CSV is about half the tokens of the same table as JSON."
    )]
    pub format: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct HarvestPromptArgs {
    #[schemars(
        description = "Archive tag such as vNNN; letters, digits, underscore, dash and dot"
    )]
    pub tag: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct ValidateChangePromptArgs {
    #[schemars(description = "Short description of the change under test")]
    pub change: String,
    #[schemars(description = "Comma-separated map plan; use at least two maps (default dm2,dm4)")]
    pub maps: Option<String>,
    #[schemars(description = "Pre-registered metric the change is expected to move")]
    pub primary: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CartographArgs {
    #[schemars(
        description = "BSP path, short name (dm4), or maps/dm4.bsp. Ingests from ARGUS_MAPS or extracts from id1 PAK0/PAK1."
    )]
    pub bsp: String,
    #[serde(default)]
    #[schemars(description = "Also run argus_navgen.py after ingest")]
    pub generate_nav: Option<bool>,
    #[serde(default)]
    #[schemars(
        description = "With generate_nav: request registration; a new map stays experimental until current reach and mill evidence pass"
    )]
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
    #[schemars(
        description = "Whitelisted console line: skill 0-3, fraglimit N, timelimit N, developer 0|1, deathmatch 1, map NAME, scratch1-4 N (scratch1 1 arms the ARGDBG decision tape), status, serverinfo, edicts, edict N, edictcount, profile, serverprofile, notarget, sv_freezenonclients 0|1"
    )]
    pub command: String,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct SeeArgs {
    #[serde(default)]
    #[schemars(
        description = "What to open: help|project|lab|map|recipe|node|path|item|fn|file|search|const|live|bot|timeline|around|plan|status|run|last|knobs. Empty defaults to project."
    )]
    pub what: String,
    #[schemars(
        description = "Name: bot (Reap), function (Argus_MoveHazard), const (AR_JUMPVEL), map (dm4), node (dm4:56), run (latest)"
    )]
    pub name: Option<String>,
    #[schemars(description = "For map: brief (default) or full")]
    pub detail: Option<String>,
    #[schemars(
        description = "For status/live: return log lines after this 0-based count. 0 or omit = last 40."
    )]
    pub since_line: Option<u32>,
}

impl Default for Argus {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct MillArgs {
    #[serde(default)]
    #[schemars(description = "revisions (default) | diff")]
    pub what: String,
    #[schemars(description = "Map short name for revisions, e.g. dm4")]
    pub map: Option<String>,
    #[schemars(description = "Older map@content-hash id for diff")]
    pub revision_a: Option<String>,
    #[schemars(description = "Newer map@content-hash id for diff")]
    pub revision_b: Option<String>,
    #[schemars(description = "Optional coordinate link id; absent from both fails closed")]
    pub link: Option<String>,
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
    #[schemars(
        description = "Wall-clock seconds, 10-185. Default 30. Compare is duration-scaled against the shipped baseline."
    )]
    pub duration_sec: Option<u32>,
    #[schemars(description = "Compile first. Default true.")]
    pub compile: Option<bool>,
    pub skill: Option<u32>,
    #[schemars(description = "Baseline log, run name, or 'baseline'. Default baseline.")]
    pub baseline: Option<String>,
    pub run_name: Option<String>,
    #[schemars(description = "brief (default) or full (compile + match + both briefs)")]
    pub detail: Option<String>,
    #[schemars(
        description = "Candidate matches to run, 1-5. Default 3. One tape cannot tell a change from nothing on this instrument: same-build dm2 stalls run 17 to 100 and dm4 1 to 20. Three narrow every band by 42 per cent."
    )]
    pub repeats: Option<u32>,
    #[schemars(
        description = "PRE-REGISTER the metric this change is expected to move, before the tapes exist: stall_parity | engagements | lava_deaths | freezes. Only that gate can convict; the rest are computed and flagged. Four gates convict a change that does not exist 19 per cent of the time against 0 to 12 per cent each, measured over sixteen byte-identical pairs."
    )]
    pub primary: Option<String>,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
pub struct CampaignExperimentArgs {
    #[schemars(description = "Campaign map name, e.g. start, e1m1, e1m2... e1m7.")]
    pub map: String,
    #[schemars(description = "Wall-clock seconds, 10-300. Default 60.")]
    pub duration_sec: Option<u32>,
    #[schemars(description = "Seat mode: 'solo' (default) or 'companion'.")]
    pub seat: Option<String>,
    pub skill: Option<u32>,
    #[schemars(description = "Compile first. Default true.")]
    pub compile: Option<bool>,
    pub run_name: Option<String>,
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

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct BaselineSetArgs {
    #[schemars(description = "Map short name (dm4)")]
    pub map: String,
    #[schemars(description = "Run name in runs/ (ab_dm4_retreatsupply1)")]
    pub run: String,
}

#[tool_router]
impl Argus {
    #[tool(description = "Resolved Argus lab paths and whether each exists. Never errors.")]
    async fn config_check(&self) -> Result<CallToolResult, McpError> {
        json_ok(&Config::report())
    }

    #[tool(
        description = "Ship the current source: compile, install to every configured location, and return the MD5 of each install for the handoff record. The last manual step of the loop, made one call."
    )]
    async fn ship(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let cfg2 = cfg.clone();
        let result = match tokio::time::timeout(
            Duration::from_secs(90),
            tokio::task::spawn_blocking(move || compile_qc(&cfg2, true)),
        )
        .await
        {
            Ok(j) => j.map_err(|e| McpError::internal_error(e.to_string(), None))?,
            Err(_) => return tool_err("ship timed out after 90s (fteqcc hung)"),
        };
        if !result.ok {
            return json_ok(&serde_json::json!({
                "ok": false,
                "compile": result,
                "hint": "compile failed; nothing installed"
            }));
        }
        let mut installs = Vec::new();
        for p in cfg.install_paths() {
            let md5 = std::fs::read(&p)
                .map(|b| format!("{:X}", md5::compute(&b)))
                .unwrap_or_else(|e| format!("unreadable: {e}"));
            installs.push(serde_json::json!({ "path": p.display().to_string(), "md5": md5 }));
        }
        json_ok(&serde_json::json!({
            "ok": true,
            "installs": installs,
            "note": "record the MD5 in the handoff; refresh the baseline with baseline_set after a green ladder"
        }))
    }

    #[tool(
        description = "Point a map's A/B baseline at a run (writes runs/baselines.json). Do this after a clean ship so gates judge against current metric semantics."
    )]
    async fn baseline_set(
        &self,
        Parameters(args): Parameters<BaselineSetArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let run = args.run.trim().trim_end_matches(".log").to_string();
        if !cfg.runs.join(format!("{run}.log")).exists() {
            return tool_err(format!("no runs/{run}.log - list_runs to see what exists"));
        }
        let path = cfg.runs.join("baselines.json");
        let mut map: serde_json::Map<String, serde_json::Value> = std::fs::read_to_string(&path)
            .ok()
            .and_then(|t| serde_json::from_str(&t).ok())
            .unwrap_or_default();
        let old = map.get(&args.map).cloned();
        map.insert(args.map.clone(), serde_json::Value::String(run.clone()));
        let text = serde_json::to_string_pretty(&serde_json::Value::Object(map))
            .map_err(|e| McpError::internal_error(e.to_string(), None))?;
        if let Err(e) = std::fs::write(&path, text) {
            return tool_err(format!("{}: {e}", path.display()));
        }
        json_ok(&serde_json::json!({
            "ok": true,
            "map": args.map,
            "baseline": run,
            "was": old,
            "file": path.display().to_string()
        }))
    }

    #[tool(
        description = "Compile src/ with fteqcc. Success is the Compile finished / id format line, not the exit code."
    )]
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
            Err(_) => {
                return tool_err("compile_qc timed out after 90s (fteqcc hung or src/ is huge)")
            }
        };
        json_ok(&result)
    }

    #[tool(
        name = "quake_compile_qc",
        description = "Prefer compile_qc. Extra: compile an optional source_directory. Installs only if that dir is ARGUS_SRC."
    )]
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

    #[tool(
        name = "bsp_inspect_entities",
        description = "Prefer see what=map. Extra: raw entity lump + filter_classname."
    )]
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

    #[tool(
        name = "bot_simulate_match",
        description = "Prefer experiment. Extra: batch K/D report. time_dilation is not applied."
    )]
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
        match self
            .drive_match(
                &cfg,
                &args.map_name,
                dur,
                Some(&format!("sim_{}", args.map_name)),
                None,
                None,
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

    #[tool(
        name = "rcon_exec",
        description = "Prefer tune. Extra: whitelist stdin + log tail. Not UDP RCON."
    )]
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

    #[tool(
        name = "bot_capture_pov_frame",
        description = "Prefer analyze_match. Extra: parked POV; returns nav/traj PNG paths."
    )]
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

    #[tool(
        description = "Map cartographer. Default detail=brief: control items snapped to nav (walk/jump/rocket_jump/off_graph), height bands, match recipe. detail=full adds every entity. Ingests path, short name, or id1 PAK."
    )]
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

    #[tool(
        description = "List maps the cartographer can ingest: *.bsp in ARGUS_MAPS plus map names inside id1 PAK files."
    )]
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

    #[tool(
        description = "Generate a per-map nav QC file via argus_navgen.py. Always passes --no-dispatcher; register=true wires a first-time map only after current reach and mill evidence pass."
    )]
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

    #[tool(
        description = "Register argus_nav_<map>.qc files in argus_nav_dispatch.qc and progs.src. A first-time map must have a current playable verdict."
    )]
    async fn nav_sync_dispatch(&self) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match nav_sync_dispatch(&cfg) {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(
        description = "Run a timed dedicated match, harvest runs/<name>.log, return ARGLOG/ARGEVT metrics."
    )]
    async fn match_run(
        &self,
        Parameters(args): Parameters<MatchRunArgs>,
        meta: RequestMetaObject,
        peer: Peer<RoleServer>,
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
        let progress = ProgressReporter::new(meta, peer);
        match self
            .drive_match(
                &cfg,
                &args.map,
                args.duration_sec,
                args.run_name.as_deref(),
                args.dedicated_slots,
                args.skill,
                None,
                Some(MatchProgress {
                    reporter: progress,
                    start: 0.0,
                    span: 1.0,
                    total: 1.0,
                    label: format!("{} match", args.map),
                }),
            )
            .await
        {
            Ok(r) => json_ok(&r),
            Err(e) => tool_err(e),
        }
    }

    #[tool(
        description = "Start a dedicated match and return once the process is up. At most one live match."
    )]
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
                None,
            )
            .await
        {
            Ok(st) => {
                if let Some(d) = args.duration_sec {
                    let matches = self.matches.clone();
                    let run_name = st.run_name.clone();
                    let pid = st.pid;
                    tokio::spawn(async move {
                        tokio::time::sleep(Duration::from_secs(d as u64)).await;
                        let mut g = matches.lock().await;
                        let _ = g
                            .stop_matching(run_name.as_deref(), pid, Duration::from_secs(5))
                            .await;
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

    #[tool(
        description = "Live match status: running, pid, elapsed, log lines. Pass since_line for incremental tails."
    )]
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
        // the owner of a match_run holds the mutex until its match ends,
        // so ask the live child to stop first, without the lock. The
        // owner's own stop path then tidies up and returns.
        let killed = crate::match_ctrl::cancel_live();
        match tokio::time::timeout(
            Duration::from_secs(args.timeout_sec.unwrap_or(5) as u64 + 5),
            self.matches.lock(),
        )
        .await
        {
            Ok(mut g) => match g
                .stop(Duration::from_secs(args.timeout_sec.unwrap_or(5) as u64))
                .await
            {
                Ok(st) => json_ok(&st),
                Err(e) => tool_err(e),
            },
            Err(_) => json_ok(&serde_json::json!({
                "ok": true,
                "running": false,
                "note": "engine killed; the match_run holding the lock is finishing its own harvest",
                "killed_pid": killed,
            })),
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

    #[tool(
        description = "List top-level *.log files in ARGUS_RUNS, newest first. Known baselines carry a note."
    )]
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

    #[tool(
        description = "Brief a harvested log (or see what=run). Default is lite: headline, totals, flags, next_steps.",
        output_schema = report_output_schema()
    )]
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
                if crate::intel::want_csv(args.format.as_deref()) {
                    report_csv_ok(crate::intel::brief_csv(&r))
                } else if want_full(args.detail.as_deref()) {
                    report_json_ok(&r, "full")
                } else {
                    report_json_ok(&brief_lite(&r), "brief")
                }
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(
        description = "A/B two logs. Default is verdict+gates (not two full briefs). detail=full for both tapes.",
        output_schema = report_output_schema()
    )]
    async fn compare_runs(
        &self,
        Parameters(args): Parameters<CompareArgs>,
        peer: Peer<RoleServer>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let mut map = args.map.clone();
        if args.log_a.is_none()
            && map.is_none()
            && matches!(crate::intel::run_map(&cfg, &args.log_b), Ok(None))
        {
            let offered = configured_baseline_maps(&cfg);
            map = elicit_baseline_map(&peer, &offered).await;
        }
        let log_a = args.log_a.as_deref().unwrap_or("baseline");
        match intel_compare(&cfg, log_a, &args.log_b, map.as_deref()) {
            Ok(r) => {
                if crate::intel::want_csv(args.format.as_deref()) {
                    report_csv_ok(crate::intel::compare_csv(&r))
                } else if want_full(args.detail.as_deref()) {
                    report_json_ok(&r, "full")
                } else {
                    report_json_ok(&compare_lite(&r), "brief")
                }
            }
            Err(e) => tool_err(e),
        }
    }

    #[tool(
        description = "Ask the 750+ tape corpus a question instead of briefing one tape at a time. CSV out. tapes: filter and aggregate (n, IQM, median, mean, sd, CV, min, max). cells: the same for hotspot cells. changes: every dated step in the series, with a permutation p and the tick class either side. bisect: localise one step with a noisy oracle, and name where to spend the next tapes. Read-only."
    )]
    async fn corpus(
        &self,
        Parameters(args): Parameters<CorpusArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        let what = args.what.as_deref().unwrap_or("tapes").to_ascii_lowercase();
        let limit = args.limit.map(|v| v as usize);

        if what == "cells" {
            let rows = crate::corpus::cells(&cfg.runs, args.map.as_deref());
            let mut out = String::from("run,map,started,kind,x,y,z,count,cause\n");
            for c in rows.iter().take(limit.unwrap_or(200)) {
                out.push_str(&format!(
                    "{},{},{},{},{:.0},{:.0},{:.0},{:.0},{}\n",
                    c.run, c.map, c.started, c.kind, c.x, c.y, c.z, c.count, c.cause
                ));
            }
            return csv_ok(out);
        }

        let (rows, _) = crate::corpus::index(&cfg.runs, false);
        if what == "tapes" {
            let q = crate::corpus::Query {
                map: args.map.clone(),
                kind: args.kind.clone(),
                tick_class: args.tick_class.clone(),
                run_like: args.run_like.clone(),
                since: args.since.clone(),
                until: args.until.clone(),
                metric: args.metric.clone(),
                group_by: args.group_by.clone(),
                limit,
            };
            return match crate::corpus::query(&rows, &q) {
                Ok(a) => csv_ok(crate::corpus::to_csv(&a)),
                Err(e) => tool_err(e),
            };
        }

        // changes and bisect are both series questions, so they
        // share the filtering: one map, one kind, optionally one
        // tick class, sorted by the tape's own start time.
        let kind = args.kind.clone().unwrap_or_else(|| "bot".into());
        let series = |map: &str| -> Vec<crate::corpus::TapeRow> {
            let mut v: Vec<crate::corpus::TapeRow> = rows
                .iter()
                .filter(|r| {
                    r.map.eq_ignore_ascii_case(map)
                        && r.kind == kind
                        && !r.started.is_empty()
                        && r.duration_sec > 0.0
                        && args
                            .tick_class
                            .as_ref()
                            .map(|t| &r.tick_class == t)
                            .unwrap_or(true)
                        && args.since.as_ref().map(|d| r.started >= *d).unwrap_or(true)
                        && args.until.as_ref().map(|d| r.started <= *d).unwrap_or(true)
                })
                .cloned()
                .collect();
            v.sort_by(|a, b| a.started.cmp(&b.started));
            v
        };
        let maps: Vec<String> = match args.map.clone() {
            Some(m) => vec![m],
            None => {
                let mut m: Vec<String> = rows
                    .iter()
                    .filter(|r| r.kind == kind && !r.map.is_empty())
                    .map(|r| r.map.clone())
                    .collect();
                m.sort();
                m.dedup();
                m
            }
        };

        if what == "bisect" {
            let Some(metric) = args.metric.as_deref() else {
                return tool_err("bisect needs a metric to localise a step in");
            };
            let map = match maps.first() {
                Some(m) => m.clone(),
                None => return tool_err("no tapes match those filters"),
            };
            let out = crate::history::bisect(&series(&map), metric, &map, 5);
            let mut csv = String::from("map,metric,queries,at,date,run,lo,hi,width,settled\n");
            csv.push_str(&format!(
                "{},{},{},{},{},{},{},{},{},{}\n",
                out.map,
                out.metric,
                out.queries,
                out.at,
                out.date,
                out.run,
                out.lo_date,
                out.hi_date,
                out.interval_width,
                out.settled
            ));
            for n in &out.notes {
                csv.push_str(&format!("# {n}\n"));
            }
            return csv_ok(csv);
        }

        if what != "changes" {
            return tool_err(format!(
                "no such corpus view '{what}'. Try tapes, cells, changes or bisect."
            ));
        }
        let metrics: Vec<String> = match args.metric.clone() {
            Some(m) => vec![m],
            None => ["stalls", "engages", "lava_deaths", "cover", "goals"]
                .iter()
                .map(|s| s.to_string())
                .collect(),
        };
        let mut csv = String::from(
            "map,metric,date,run,n_before,n_after,before,after,p,tick_before,tick_after\n",
        );
        for map in &maps {
            let v = series(map);
            for metric in &metrics {
                for st in crate::history::change_points(&v, metric) {
                    csv.push_str(&format!(
                        "{},{},{},{},{},{},{:.1},{:.1},{:.3},{},{}\n",
                        map,
                        metric,
                        st.date,
                        st.run,
                        st.before_n,
                        st.after_n,
                        st.before,
                        st.after,
                        st.p,
                        st.before_tick,
                        st.after_tick
                    ));
                }
            }
        }
        csv_ok(csv)
    }

    #[tool(
        description = "Read graph history or diff two exact nav JSON revisions. Diff output contains only links present in at least one source graph, with matching probe convictions. Read-only."
    )]
    async fn mill(
        &self,
        Parameters(args): Parameters<MillArgs>,
    ) -> Result<CallToolResult, McpError> {
        let cfg = match cfg_read_or_err() {
            Ok(c) => c,
            Err(r) => return Ok(r),
        };
        match args.what.trim().to_ascii_lowercase().as_str() {
            "" | "revisions" => {
                let Some(map) = args.map.as_deref() else {
                    return tool_err("mill revisions needs map=dm4");
                };
                match crate::graph_revision::list_revisions(&cfg, map) {
                    Ok(r) => json_ok(&r),
                    Err(e) => tool_err(e),
                }
            }
            "diff" => {
                let Some(a) = args.revision_a.as_deref() else {
                    return tool_err("mill diff needs revision_a=map@content-hash");
                };
                let Some(b) = args.revision_b.as_deref() else {
                    return tool_err("mill diff needs revision_b=map@content-hash");
                };
                match crate::graph_revision::diff(&cfg, a, b, args.link.as_deref()) {
                    Ok(r) => json_ok(&r),
                    Err(e) => tool_err(e),
                }
            }
            other => tool_err(format!("unknown mill view {other}; use revisions or diff")),
        }
    }

    #[tool(
        description = "Concrete next places to look in the QC given a log or an A/B pair. Prefer this after compare_runs."
    )]

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

    #[tool(
        description = "Lab dashboard: config readiness, maps (BSP/nav/dispatcher), recent runs, live match, and the next recommended tool call."
    )]
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

    #[tool(
        description = "Cartograph every on-disk BSP in ARGUS_MAPS. PAK-only names are skipped until ingested."
    )]
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

    #[tool(
        description = "Find Argus QuakeC functions by name, role (hazard/combat/nav/lifecycle), or comment text."
    )]
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

    #[tool(
        description = "Learn stall/lava/hazard cells across harvested logs. Writes src/argus_nav_<map>.costs.json for navgen; does not write QuakeC."
    )]
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

    #[tool(
        description = "What an LLM can change live vs what needs compile. skill is live (next respawn); AR_* constants are not."
    )]
    async fn knobs(&self) -> Result<CallToolResult, McpError> {
        json_ok(&knobs())
    }

    #[tool(
        description = "Send a whitelisted console cvar/command to the live dedicated server. skill 0-3 applies at next bot respawn. Not a free shell."
    )]
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

    #[tool(
        description = "Last ARGLOG sample per bot from the live match, or the last harvested match if none is running."
    )]
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

    #[tool(
        description = "Read one Argus QuakeC function with file:line and full source. Preferred way to see into the bot."
    )]
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
        description = "One inspect call. what=help|project|lab|map|recipe|node|fn|const|live|bot|status|run|last|knobs. Use this before inventing a pipeline."
    )]
    async fn see(&self, Parameters(args): Parameters<SeeArgs>) -> Result<CallToolResult, McpError> {
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

    #[tool(
        description = "After a QC edit: compile + short match + duration-scaled A/B. Default return is lite (verdict, gates, next)."
    )]
    async fn experiment(
        &self,
        Parameters(args): Parameters<ExperimentArgs>,
        meta: RequestMetaObject,
        peer: Peer<RoleServer>,
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
        let progress = ProgressReporter::new(meta, peer);
        let repeats = args.repeats.unwrap_or(3).clamp(1, 5);
        let compile_units = u32::from(args.compile.unwrap_or(true));
        let total = f64::from(compile_units + repeats + 1);
        progress.send(0.0, total, "preparing experiment").await;
        let mut compile_result = None;
        if args.compile.unwrap_or(true) {
            progress.send(0.0, total, "compiling QuakeC").await;
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
                {
                    let mut s = self.session.lock().await;
                    s.note_experiment(ExperimentRecord {
                        map: args.map.clone(),
                        run_name: String::new(),
                        duration_sec: dur,
                        compile_ok: Some(false),
                        verdict: None,
                        headline: Some("compile failed".into()),
                    });
                    Self::persist_session(&s);
                }
                return json_ok(&serde_json::json!({
                    "ok": false,
                    "stage": "compile",
                    "compile": compiled,
                    "next": "see what=fn name=<the error> and fix QC",
                }));
            }
            compile_result = Some(compiled);
            progress.send(1.0, total, "compile complete").await;
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
        let mut runs = Vec::new();
        for i in 0..repeats {
            // one tape per name, so every tape in the band survives on
            // disk and the verdict can be re-derived later
            let name = if repeats == 1 {
                run_name.clone()
            } else {
                format!("{run_name}{}", i + 1)
            };
            let start = f64::from(compile_units + i);
            match self
                .drive_match(
                    &cfg,
                    &args.map,
                    dur,
                    Some(&name),
                    None,
                    args.skill,
                    None,
                    Some(MatchProgress {
                        reporter: progress.clone(),
                        start,
                        span: 1.0,
                        total,
                        label: format!("{} tape {}/{}", args.map, i + 1, repeats),
                    }),
                )
                .await
            {
                Ok(r) => runs.push(r),
                Err(e) => {
                    if runs.is_empty() {
                        return tool_err(e);
                    }
                    break;
                }
            }
        }
        let ran = runs.last().cloned().expect("at least one match ran");
        let logs: Vec<String> = runs.iter().map(|r| r.log_path.clone()).collect();
        progress
            .send(
                f64::from(compile_units + repeats),
                total,
                "comparing experiment tapes",
            )
            .await;
        let compare = match args.baseline.as_deref() {
            // an explicit baseline is still one named tape against the
            // candidates; "baseline" resolves the map's whole band
            Some(b) if b != "baseline" => {
                intel_compare_scaled(&cfg, b, &ran.log_path, Some(&args.map)).ok()
            }
            _ => crate::intel::compare_runs_band(
                &cfg,
                &logs,
                Some(&args.map),
                args.primary.as_deref(),
            )
            .ok(),
        };
        let verdict = compare
            .as_ref()
            .map(|c| format!("{:?}", c.verdict).to_ascii_lowercase());
        let headline = compare
            .as_ref()
            .map(|c| c.headline.clone())
            .or_else(|| Some(ran.brief.headline.clone()));
        {
            let mut s = self.session.lock().await;
            s.note_experiment(ExperimentRecord {
                map: args.map.clone(),
                run_name: ran.run_name.clone(),
                duration_sec: dur,
                compile_ok: compile_result.as_ref().map(|c| c.ok),
                verdict: verdict.clone(),
                headline: headline.clone(),
            });
            Self::persist_session(&s);
        }
        progress.send(total, total, "experiment complete").await;
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
            "logs": logs,
            "repeats": runs.len(),
            "elapsed_sec": ran.elapsed_sec,
            "compare": compare.as_ref().map(compare_lite),
            "gate_card": compare.as_ref().map(|c| c.gate_card.clone()),
            "match": brief_lite(&ran.brief),
            "next": next,
        }))
    }

    #[tool(
        description = "Run a campaign/co-op experiment and evaluate against win/checkpoint triggers and fail taxonomy (#176)."
    )]
    async fn campaign_experiment(
        &self,
        Parameters(args): Parameters<CampaignExperimentArgs>,
        meta: RequestMetaObject,
        peer: Peer<RoleServer>,
    ) -> Result<CallToolResult, McpError> {
        let dur = args.duration_sec.unwrap_or(60);
        if !(10..=300).contains(&dur) {
            return Err(McpError::invalid_params(
                "campaign duration_sec must be 10..=300",
                None,
            ));
        }
        let seat = args.seat.as_deref().unwrap_or("solo");
        if seat != "solo" && seat != "companion" {
            return Err(McpError::invalid_params(
                "seat must be 'solo' or 'companion'",
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
        let progress = ProgressReporter::new(meta, peer);
        let compile_units = u32::from(args.compile.unwrap_or(true));
        let total = f64::from(compile_units + 2);
        progress.send(0.0, total, "preparing campaign").await;
        let mut compile_result = None;
        if args.compile.unwrap_or(true) {
            progress.send(0.0, total, "compiling QuakeC").await;
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
                    "next": "see what=fn name=<the error> and fix QC",
                }));
            }
            compile_result = Some(compiled);
            progress.send(1.0, total, "compile complete").await;
        }
        let run_name = args
            .run_name
            .clone()
            .unwrap_or_else(|| format!("campaign_{}_{}", args.map, seat));
        {
            let mut g = self.matches.lock().await;
            g.reap();
            if g.status().running {
                let _ = g.stop(Duration::from_secs(3)).await;
            }
        }
        let stop_puppet = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        let puppet_thread = if seat == "companion" {
            let stop_clone = std::sync::Arc::clone(&stop_puppet);
            Some(std::thread::spawn(move || {
                std::thread::sleep(Duration::from_millis(1500));
                if let Ok(mut puppet) =
                    crate::netclient::NetClient::connect("127.0.0.1", 26000, "puppet")
                {
                    while !stop_clone.load(std::sync::atomic::Ordering::Relaxed) {
                        puppet.pump(Duration::from_millis(100));
                    }
                    puppet.disconnect();
                }
            }))
        } else {
            None
        };

        let ran = match self
            .drive_match(
                &cfg,
                &args.map,
                dur,
                Some(&run_name),
                None,
                args.skill,
                Some(true),
                Some(MatchProgress {
                    reporter: progress.clone(),
                    start: f64::from(compile_units),
                    span: 1.0,
                    total,
                    label: format!("{} campaign", args.map),
                }),
            )
            .await
        {
            Ok(r) => r,
            Err(e) => {
                if let Some(th) = puppet_thread {
                    stop_puppet.store(true, std::sync::atomic::Ordering::Relaxed);
                    let _ = th.join();
                }
                return tool_err(e);
            }
        };

        if let Some(th) = puppet_thread {
            stop_puppet.store(true, std::sync::atomic::Ordering::Relaxed);
            let _ = th.join();
        }

        let log_content = match std::fs::read_to_string(&ran.log_path) {
            Ok(c) => c,
            Err(e) => return tool_err(format!("failed to read log {}: {}", ran.log_path, e)),
        };
        progress
            .send(
                f64::from(compile_units + 1),
                total,
                "evaluating campaign log",
            )
            .await;
        let report = crate::campaign::evaluate_campaign_log(
            &log_content,
            &args.map,
            seat,
            &ran.log_path,
            ran.elapsed_sec,
            crate::intel::hull0_for_map(&cfg, &args.map).as_ref(),
        );
        progress.send(total, total, "campaign complete").await;
        json_ok(&serde_json::json!({
            "ok": report.ok,
            "verdict": report.verdict,
            "fail_reason": report.fail_reason,
            "checkpoints": report.checkpoints,
            "escort_break_s": report.escort_break_s,
            "steal_events": report.steal_events,
            "block_events": report.block_events,
            "elapsed_sec": report.elapsed_sec,
            "log_path": report.log_path,
            "summary_line": report.summary_line,
            "compile_ok": compile_result.as_ref().map(|c| c.ok),
        }))
    }

    #[tool(
        description = "Short experiment on several maps after one compile. Default dm2,dm3,dm4,dm6,lqdm2 at 20s each."
    )]
    async fn matrix_experiment(
        &self,
        Parameters(args): Parameters<MatrixArgs>,
        meta: RequestMetaObject,
        peer: Peer<RoleServer>,
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
        let progress = ProgressReporter::new(meta, peer);
        let compile_units = usize::from(args.compile.unwrap_or(true));
        let total = (compile_units + maps.len() + 1) as f64;
        progress.send(0.0, total, "preparing map matrix").await;
        let mut compile_ok = None;
        if args.compile.unwrap_or(true) {
            progress.send(0.0, total, "compiling QuakeC").await;
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
            progress.send(1.0, total, "compile complete").await;
        }
        let mut results = Vec::new();
        for (index, map) in maps.iter().enumerate() {
            {
                let mut g = self.matches.lock().await;
                g.reap();
                if g.status().running {
                    let _ = g.stop(Duration::from_secs(3)).await;
                }
                // mx_<map> is a rolling probe. It is written fresh on
                // every matrix run and several of those tapes are
                // committed as the record of the last one, so this is
                // the one caller that is meant to replace a committed
                // tape and has to say so (#328).
                g.refresh_committed_tape();
            }
            let ran = self
                .drive_match(
                    &cfg,
                    map,
                    dur,
                    Some(&format!("mx_{map}")),
                    None,
                    args.skill,
                    None,
                    Some(MatchProgress {
                        reporter: progress.clone(),
                        start: (compile_units + index) as f64,
                        span: 1.0,
                        total,
                        label: format!("{map} matrix match"),
                    }),
                )
                .await;
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
        progress
            .send(total - 1.0, total, "summarizing map matrix")
            .await;
        progress.send(total, total, "map matrix complete").await;
        json_ok(&serde_json::json!({
            "ok": results.iter().all(|r| r.get("ok").and_then(|v| v.as_bool()).unwrap_or(false)),
            "compile_ok": compile_ok,
            "duration_sec": dur,
            "results": results,
        }))
    }

    #[tool(
        description = "Prefer experiment. Short compile+match+brief with no A/B. duration 10-120s."
    )]
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
        match self
            .drive_match(
                &cfg,
                &args.map,
                dur,
                Some(&format!("probe_{}", args.map)),
                None,
                args.skill,
                None,
                None,
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

    #[tool(
        description = "The Argus A/B quality bars this server uses when briefing and comparing runs."
    )]
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
        let cfg =
            Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
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
        let cfg =
            Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
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
        let cfg =
            Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let atlas =
            map_cartograph(&cfg, &args.bsp).map_err(|e| McpError::invalid_params(e, None))?;
        let body = format!(
            "Review this Argus map brief. Trust reach (walk/jump/rocket_jump/off_graph) and the recipe. Do not invent a nav story that contradicts nearest_node.\n\n{}",
            serde_json::to_string_pretty(&atlas_brief(&atlas)).unwrap_or_default()
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "harvest_before_play",
        description = "Preserve a human play session before any new engine launch truncates qconsole.log"
    )]
    async fn harvest_before_play(
        &self,
        Parameters(args): Parameters<HarvestPromptArgs>,
    ) -> Result<Vec<PromptMessage>, McpError> {
        if !crate::paths::valid_run_name(&args.tag) {
            return Err(McpError::invalid_params(
                "tag must contain only letters, digits, underscore, dash or dot",
                None,
            ));
        }
        let body = format!(
            "Preserve the current human session before doing anything that starts an engine. Run exactly:\n\npython tools/harvest_session.py --tag {}\n\nDo this first: every new engine launch truncates qconsole.log. Confirm the harvester succeeds before using experiment, matrix_experiment, match_start, match_run, probe, soak, cycle, gui, or another engine launcher. Then review the harvested run with brief_run or see what=demo; human tracks are review data, never bot bands or gates.",
            args.tag
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "validate_change",
        description = "Plan a controlled multi-map Argus A/B with enough tapes and valid metric boundaries"
    )]
    async fn validate_change(
        &self,
        Parameters(args): Parameters<ValidateChangePromptArgs>,
    ) -> Result<Vec<PromptMessage>, McpError> {
        let maps = args.maps.as_deref().unwrap_or("dm2,dm4");
        let primary = args
            .primary
            .as_deref()
            .unwrap_or("choose before running tapes");
        let body = format!(
            "Validate this Argus change: {}\nRequested map context: {maps}\nPre-registered primary: {primary}\n\nUse a controlled A/B on at least two maps; one tape never settles a movement question. On dm2 collect at least three candidate tapes and three matching control tapes per arm (experiment map=dm2 repeats=3 primary=<metric> is the candidate-side minimum). Keep code, skill, duration, tick class, and map fixed within each comparison, record the tree state, and use a second map such as dm4 before deciding. Use experiment or matrix_experiment to collect evidence and compare_runs for existing arms. Trust each experiment/compare next_steps and its computed verdict; do not re-parse ARGLOG. Respect the metric boundaries in CLAUDE.md: never compare goal, engagement, raw death-event, distance, or speed counts across a boundary. Human tapes are review-only and never enter bot bands or gates.",
            args.change
        );
        Ok(vec![PromptMessage::new_text(Role::User, body)])
    }

    #[prompt(
        name = "orient",
        description = "Orient an LLM on the Argus tree, live vs compile knobs, and how to test"
    )]
    async fn orient(&self) -> Result<Vec<PromptMessage>, McpError> {
        let cfg =
            Config::load_for_reads().map_err(|e| McpError::invalid_params(e.to_string(), None))?;
        let view = project_view(&cfg);
        let session = self.session.lock().await.clone();
        let body = format!(
            "You are in the Argus lab. Follow tools/argus_mcp/README.md. Do not invent a shell pipeline. First call is already see what=project. Use see / experiment / tune.\n\n{}\n\nSession last-seen:\n{}\n\nQuality bars:\n{}",
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

#[derive(Debug, PartialEq)]
enum CompletionSource {
    Maps,
    MapList,
    Runs(&'static [&'static str]),
    Primary,
    GraphHashes(Option<String>),
}

fn completion_source(request: &CompleteRequestParams) -> Option<CompletionSource> {
    let argument = request.argument.name.as_str();
    match &request.r#ref {
        Reference::Prompt(prompt) => match (prompt.name.as_str(), argument) {
            ("review_run", "log") => Some(CompletionSource::Runs(&[])),
            ("review_ab", "log_a") => Some(CompletionSource::Runs(&["baseline", "shipped"])),
            ("review_ab", "log_b") => Some(CompletionSource::Runs(&["latest"])),
            ("review_ab", "map") | ("review_map", "bsp") => Some(CompletionSource::Maps),
            ("validate_change", "maps") => Some(CompletionSource::MapList),
            ("validate_change", "primary") => Some(CompletionSource::Primary),
            _ => None,
        },
        Reference::Resource(resource) => match (resource.uri.as_str(), argument) {
            ("argus://map/{name}", "name")
            | ("argus://graph-revisions/{map}", "map")
            | ("argus://graph/{map}/{hash}", "map")
            | ("argus://probe-verdicts/{map}/{hash}", "map") => Some(CompletionSource::Maps),
            ("argus://run/{name}", "name") => Some(CompletionSource::Runs(&["latest"])),
            ("argus://graph/{map}/{hash}", "hash")
            | ("argus://probe-verdicts/{map}/{hash}", "hash") => {
                let map = request
                    .context
                    .as_ref()
                    .and_then(|context| context.get_argument("map"))
                    .cloned();
                Some(CompletionSource::GraphHashes(map))
            }
            _ => None,
        },
        _ => None,
    }
}

fn filter_completion_values(
    mut values: Vec<String>,
    partial: &str,
    comma_separated: bool,
) -> CompletionInfo {
    values.sort_by_key(|value| value.to_ascii_lowercase());
    values.dedup_by(|a, b| a.eq_ignore_ascii_case(b));

    let (prefix, needle, prior): (String, &str, Vec<String>) = if comma_separated {
        match partial.rsplit_once(',') {
            Some((head, tail)) => (
                format!("{head},"),
                tail.trim(),
                head.split(',')
                    .map(|value| value.trim().to_ascii_lowercase())
                    .collect(),
            ),
            None => (String::new(), partial.trim(), Vec::new()),
        }
    } else {
        (String::new(), partial, Vec::new())
    };
    let needle = needle.to_ascii_lowercase();
    let mut matches: Vec<String> = values
        .into_iter()
        .filter(|value| value.to_ascii_lowercase().starts_with(&needle))
        .filter(|value| !prior.iter().any(|seen| value.eq_ignore_ascii_case(seen)))
        .map(|value| format!("{prefix}{value}"))
        .collect();
    let total = matches.len();
    matches.truncate(CompletionInfo::MAX_VALUES);
    CompletionInfo::with_pagination(
        matches,
        Some(total as u32),
        total > CompletionInfo::MAX_VALUES,
    )
    .expect("completion values are capped to the protocol limit")
}

fn completion_values(request: &CompleteRequestParams, cfg: Option<&Config>) -> CompletionInfo {
    let Some(source) = completion_source(request) else {
        return CompletionInfo::default();
    };
    let comma_separated = source == CompletionSource::MapList;
    let values = match source {
        CompletionSource::Maps | CompletionSource::MapList => cfg
            .and_then(|cfg| map_list(cfg).ok())
            .unwrap_or_default()
            .into_iter()
            .map(|map| map.name)
            .collect(),
        CompletionSource::Runs(aliases) => {
            let mut values: Vec<String> = aliases.iter().map(|value| (*value).into()).collect();
            values.extend(
                cfg.and_then(|cfg| list_runs(cfg).ok())
                    .unwrap_or_default()
                    .into_iter()
                    .map(|run| {
                        run.name
                            .strip_suffix(".log")
                            .unwrap_or(&run.name)
                            .to_string()
                    }),
            );
            values
        }
        CompletionSource::Primary => ["engagements", "freezes", "lava_deaths", "stall_parity"]
            .into_iter()
            .map(str::to_string)
            .collect(),
        CompletionSource::GraphHashes(map) => match (cfg, map) {
            (Some(cfg), Some(map)) => crate::graph_revision::list_revisions(cfg, &map)
                .unwrap_or_default()
                .into_iter()
                .filter_map(|revision| {
                    revision
                        .id
                        .split_once('@')
                        .map(|(_, hash)| hash.to_string())
                })
                .collect(),
            _ => Vec::new(),
        },
    };
    filter_completion_values(values, &request.argument.value, comma_separated)
}

#[tool_handler(router = Self::annotated_tool_router())]
#[prompt_handler]
impl ServerHandler for Argus {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(
            ServerCapabilities::builder()
                .enable_tools()
                .enable_prompts()
                .enable_resources()
                .enable_resources_subscribe()
                .enable_completions()
                .build(),
        )
        .with_server_info(Implementation::new(SERVER_NAME, SERVER_VERSION))
        .with_instructions(server_instructions())
    }

    async fn complete(
        &self,
        request: CompleteRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> Result<CompleteResult, McpError> {
        let cfg = Config::load_for_reads()
            .ok()
            .filter(|cfg| cfg.root.exists());
        Ok(CompleteResult::new(completion_values(
            &request,
            cfg.as_ref(),
        )))
    }

    async fn list_resources(
        &self,
        _request: Option<PaginatedRequestParams>,
        _context: RequestContext<RoleServer>,
    ) -> Result<ListResourcesResult, McpError> {
        let cfg = Config::load_for_reads().ok();
        Ok(crate::resources::list_static(cfg.as_ref()))
    }

    fn accepted_subscription_filter(
        &self,
        requested: &SubscriptionFilter,
    ) -> Option<SubscriptionFilter> {
        let supported = SubscriptionFilter::builder()
            .resource_subscriptions(LIVE_RESOURCE_URIS)
            .build();
        Some(requested.intersection(&supported))
    }

    async fn listen(&self, context: SubscriptionContext) -> Result<(), McpError> {
        let uris = context
            .accepted()
            .resource_subscriptions
            .clone()
            .unwrap_or_default();
        if uris.is_empty() {
            context.cancelled().await;
            return Ok(());
        }
        let mut previous = self.live_resource_snapshot(&uris).await;
        let mut interval = tokio::time::interval(Duration::from_secs(1));
        loop {
            tokio::select! {
                _ = context.cancelled() => return Ok(()),
                _ = interval.tick() => {
                    let current = self.live_resource_snapshot(&uris).await;
                    for uri in changed_resource_uris(&mut previous, current) {
                        if context.sink().notify_resource_updated(uri).await.is_err() {
                            return Ok(());
                        }
                    }
                }
            }
        }
    }

    #[allow(deprecated)]
    async fn subscribe(
        &self,
        request: SubscribeRequestParams,
        context: RequestContext<RoleServer>,
    ) -> Result<(), McpError> {
        if !LIVE_RESOURCE_URIS.contains(&request.uri.as_str()) {
            return Err(McpError::resource_not_found(
                format!("{} is not a live resource", request.uri),
                None,
            ));
        }
        let key = request.uri;
        let uri = key.clone();
        let uris = vec![uri.clone()];
        let server = self.clone();
        let peer = context.peer.clone();
        let task = tokio::spawn(async move {
            let mut previous = server.live_resource_snapshot(&uris).await;
            let mut interval = tokio::time::interval(Duration::from_secs(1));
            loop {
                interval.tick().await;
                let current = server.live_resource_snapshot(&uris).await;
                if changed_resource_uris(&mut previous, current).is_empty() {
                    continue;
                }
                if peer
                    .notify_resource_updated(ResourceUpdatedNotificationParam::new(uri.clone()))
                    .await
                    .is_err()
                {
                    break;
                }
            }
        });
        let mut subscriptions = self.legacy_subscriptions.lock().await;
        if let Some(old) = subscriptions.insert(key, task.abort_handle()) {
            old.abort();
        }
        Ok(())
    }

    #[allow(deprecated)]
    async fn unsubscribe(
        &self,
        request: UnsubscribeRequestParams,
        _context: RequestContext<RoleServer>,
    ) -> Result<(), McpError> {
        if let Some(task) = self.legacy_subscriptions.lock().await.remove(&request.uri) {
            task.abort();
        }
        Ok(())
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
        let live = if request.uri == "argus://lab" {
            let mut matches = self.matches.lock().await;
            matches.reap();
            Some(matches.status())
        } else {
            None
        };
        let session = self.session.lock().await.clone();
        match crate::resources::read_uri_with_live(&request.uri, cfg.as_ref(), &session, live) {
            Ok(contents) => Ok(ReadResourceResponse::Complete(ReadResourceResult::new(
                contents,
            ))),
            Err(e) => Err(McpError::resource_not_found(e, None)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{git_test_lock, run_git, TestDir};
    use rmcp::model::{ArgumentInfo, CompletionContext};
    use std::collections::HashMap;
    use std::fs;
    use std::path::Path;

    fn prompt_text(messages: &[PromptMessage]) -> &str {
        match &messages.first().expect("one prompt message").content {
            ContentBlock::Text(text) => &text.text,
            other => panic!("expected text prompt, got {other:?}"),
        }
    }

    #[test]
    fn progress_notifications_are_opt_in_and_keep_stage_values() {
        assert!(progress_notification(None, 1.0, 3.0, "compile".into()).is_none());

        let token = rmcp::model::ProgressToken(rmcp::model::NumberOrString::String("run-7".into()));
        let stages = [
            (0.0, "compile"),
            (1.0, "match"),
            (2.5, "analyze"),
            (3.0, "done"),
        ];
        let notifications: Vec<_> = stages
            .iter()
            .map(|(value, message)| {
                progress_notification(Some(&token), *value, 3.0, (*message).into()).unwrap()
            })
            .collect();

        assert!(notifications
            .windows(2)
            .all(|pair| pair[0].progress <= pair[1].progress));
        assert!(notifications.iter().all(|item| item.total == Some(3.0)));
        assert_eq!(notifications[2].message.as_deref(), Some("analyze"));
        assert_eq!(notifications[3].progress_token, token);
    }

    fn result_text(result: &CallToolResult) -> &str {
        result
            .content
            .first()
            .and_then(ContentBlock::as_text)
            .map(|text| text.text.as_str())
            .expect("one text result")
    }

    #[test]
    fn server_metadata_uses_package_version() {
        let info = Argus::new().get_info();
        let instructions = info.instructions.expect("server instructions");

        assert_eq!(info.server_info.name, env!("CARGO_PKG_NAME"));
        assert_eq!(info.server_info.version, env!("CARGO_PKG_VERSION"));
        assert!(
            instructions.starts_with(&format!("Argus lab {}.", env!("CARGO_PKG_VERSION"))),
            "instructions advertise a different lab version: {instructions}"
        );
        assert!(info.capabilities.completions.is_some());
        assert_eq!(
            info.capabilities
                .resources
                .and_then(|resources| resources.subscribe),
            Some(true)
        );
    }

    #[test]
    fn live_subscription_filter_accepts_only_live_resources() {
        let requested = SubscriptionFilter::builder()
            .resource_subscriptions([
                "argus://last",
                "argus://lab",
                "argus://project",
                "argus://run/latest",
            ])
            .build();
        let accepted = Argus::new()
            .accepted_subscription_filter(&requested)
            .unwrap();
        assert_eq!(
            accepted.resource_subscriptions.unwrap(),
            ["argus://last", "argus://lab"]
        );
    }

    #[test]
    fn resource_change_detection_is_quiet_until_values_move() {
        let mut previous = BTreeMap::from([
            ("argus://lab".into(), "ready".into()),
            ("argus://last".into(), "dm4".into()),
        ]);
        let unchanged = previous.clone();
        assert!(changed_resource_uris(&mut previous, unchanged).is_empty());

        let current = BTreeMap::from([
            ("argus://lab".into(), "running".into()),
            ("argus://last".into(), "dm4".into()),
        ]);
        assert_eq!(
            changed_resource_uris(&mut previous, current),
            ["argus://lab"]
        );
    }

    #[test]
    fn baseline_elicitation_offers_only_usable_configured_maps() {
        let root = TestDir::new("server-elicitation").unwrap();
        fs::create_dir_all(root.path().join("runs")).unwrap();
        fs::create_dir_all(root.path().join("src")).unwrap();
        fs::write(root.path().join("runs/base_dm4.log"), "").unwrap();
        fs::write(
            root.path().join("runs/baselines.json"),
            r#"{"dm2":["missing"],"dm4":["base_dm4"]}"#,
        )
        .unwrap();
        let offered = configured_baseline_maps(&completion_cfg(root.path()));
        assert_eq!(offered, ["dm4"]);

        let schema = serde_json::to_value(baseline_elicitation_schema(&offered).unwrap()).unwrap();
        assert_eq!(
            schema["properties"]["map"]["enum"],
            serde_json::json!(["dm4"])
        );
        assert!(baseline_elicitation_schema(&[]).is_none());
    }

    #[test]
    fn elicited_baseline_map_accepts_only_a_valid_accept_action() {
        let offered = vec!["dm2".into(), "dm4".into()];
        let accepted = ElicitResult::new(ElicitationAction::Accept)
            .with_content(serde_json::json!({"map": "DM4"}));
        assert_eq!(
            accepted_elicited_map(accepted, &offered).as_deref(),
            Some("dm4")
        );

        for result in [
            ElicitResult::new(ElicitationAction::Decline),
            ElicitResult::new(ElicitationAction::Cancel),
            ElicitResult::new(ElicitationAction::Accept)
                .with_content(serde_json::json!({"map": "e1m1"})),
            ElicitResult::new(ElicitationAction::Accept)
                .with_content(serde_json::json!({"wrong": "dm4"})),
        ] {
            assert!(accepted_elicited_map(result, &offered).is_none());
        }
    }

    fn completion_cfg(root: &Path) -> Config {
        Config {
            root: root.into(),
            fteqcc: Default::default(),
            engine: Default::default(),
            basedir: root.into(),
            python: Default::default(),
            game: "argus".into(),
            src: root.join("src"),
            runs: root.join("runs"),
            progs: root.join("progs.dat"),
            maps: root.join("maps"),
        }
    }

    #[test]
    fn completion_routes_and_filters_prompt_names() {
        let root = TestDir::new("server-completion").unwrap();
        fs::create_dir_all(root.path().join("maps")).unwrap();
        fs::create_dir_all(root.path().join("runs")).unwrap();
        fs::create_dir_all(root.path().join("src")).unwrap();
        fs::write(root.path().join("maps/dm4.bsp"), []).unwrap();
        fs::write(root.path().join("maps/dm2.bsp"), []).unwrap();
        fs::write(root.path().join("runs/ab_dm4_alpha.log"), "").unwrap();
        fs::write(root.path().join("runs/other.log"), "").unwrap();
        let cfg = completion_cfg(root.path());

        let maps = CompleteRequestParams::new(
            Reference::for_prompt("review_map"),
            ArgumentInfo::new("bsp", "dm"),
        );
        assert_eq!(completion_values(&maps, Some(&cfg)).values, ["dm2", "dm4"]);

        let runs = CompleteRequestParams::new(
            Reference::for_prompt("review_ab"),
            ArgumentInfo::new("log_a", "ab_"),
        );
        assert_eq!(
            completion_values(&runs, Some(&cfg)).values,
            ["ab_dm4_alpha"]
        );
        let baseline = CompleteRequestParams::new(
            Reference::for_prompt("review_ab"),
            ArgumentInfo::new("log_a", "b"),
        );
        assert_eq!(
            completion_values(&baseline, Some(&cfg)).values,
            ["baseline"]
        );

        let list = CompleteRequestParams::new(
            Reference::for_prompt("validate_change"),
            ArgumentInfo::new("maps", "dm2,d"),
        );
        assert_eq!(
            completion_values(&list, Some(&cfg)).values,
            ["dm2,dm4"],
            "a comma-separated completion preserves prior maps and omits duplicates"
        );

        let unknown = CompleteRequestParams::new(
            Reference::for_prompt("orient"),
            ArgumentInfo::new("map", "dm"),
        );
        assert!(completion_values(&unknown, Some(&cfg)).values.is_empty());
    }

    #[test]
    fn completion_routes_resource_names_and_contextual_hashes() {
        let _gate = git_test_lock();
        let root = TestDir::new("server-completion-revision").unwrap();
        fs::create_dir_all(root.path().join("maps")).unwrap();
        fs::create_dir_all(root.path().join("runs")).unwrap();
        fs::create_dir_all(root.path().join("src")).unwrap();
        fs::write(root.path().join("maps/dm4.bsp"), []).unwrap();
        fs::write(
            root.path().join("src/argus_nav_dm4.qc.json"),
            r#"{"nodes":[[0,0,0]],"links":[],"trace_inputs":[]}"#,
        )
        .unwrap();
        run_git(root.path(), &["init", "-q"]).unwrap();
        run_git(root.path(), &["config", "user.name", "Argus test"]).unwrap();
        run_git(
            root.path(),
            &["config", "user.email", "argus-test@example.invalid"],
        )
        .unwrap();
        run_git(root.path(), &["add", "."]).unwrap();
        run_git(root.path(), &["commit", "-q", "-m", "graph"]).unwrap();
        let cfg = completion_cfg(root.path());

        let map = CompleteRequestParams::new(
            Reference::for_resource("argus://graph/{map}/{hash}"),
            ArgumentInfo::new("map", "dm"),
        );
        assert_eq!(completion_values(&map, Some(&cfg)).values, ["dm4"]);

        let mut context = HashMap::new();
        context.insert("map".into(), "dm4".into());
        let hash = CompleteRequestParams::new(
            Reference::for_resource("argus://graph/{map}/{hash}"),
            ArgumentInfo::new("hash", ""),
        )
        .with_context(CompletionContext::with_arguments(context));
        let hashes = completion_values(&hash, Some(&cfg)).values;
        assert_eq!(hashes.len(), 1);
        assert_eq!(hashes[0].len(), 32);
        assert!(hashes[0].bytes().all(|byte| byte.is_ascii_hexdigit()));
    }

    #[test]
    fn completion_is_sorted_deduplicated_and_protocol_bounded() {
        let mut values: Vec<String> = (0..105).map(|n| format!("value{n:03}")).collect();
        values.push("VALUE000".into());
        let completion = filter_completion_values(values, "value", false);
        assert_eq!(completion.values.len(), CompletionInfo::MAX_VALUES);
        assert_eq!(completion.total, Some(105));
        assert_eq!(completion.has_more, Some(true));
        assert!(completion.values.windows(2).all(|pair| pair[0] < pair[1]));

        let primary = CompleteRequestParams::new(
            Reference::for_prompt("validate_change"),
            ArgumentInfo::new("primary", "la"),
        );
        assert_eq!(
            completion_values(&primary, None).values,
            ["lava_deaths"],
            "static completions do not require lab config"
        );
    }

    #[test]
    fn safety_prompts_publish_concise_metadata() {
        let prompts = Argus::prompt_router().list_all();
        let names: Vec<_> = prompts.iter().map(|prompt| prompt.name.as_str()).collect();
        assert_eq!(
            names,
            [
                "harvest_before_play",
                "orient",
                "review_ab",
                "review_map",
                "review_run",
                "validate_change",
            ]
        );

        let harvest = prompts
            .iter()
            .find(|prompt| prompt.name == "harvest_before_play")
            .unwrap();
        let harvest_args = harvest.arguments.as_ref().unwrap();
        assert!(harvest
            .description
            .as_deref()
            .unwrap()
            .contains("before any new engine launch"));
        assert_eq!(harvest_args.len(), 1);
        assert_eq!(harvest_args[0].name, "tag");
        assert_eq!(harvest_args[0].required, Some(true));
        assert!(harvest_args[0]
            .description
            .as_deref()
            .unwrap()
            .contains("vNNN"));

        let validate = prompts
            .iter()
            .find(|prompt| prompt.name == "validate_change")
            .unwrap();
        let validate_args = validate.arguments.as_ref().unwrap();
        assert!(validate
            .description
            .as_deref()
            .unwrap()
            .contains("multi-map"));
        assert_eq!(
            validate_args
                .iter()
                .map(|argument| argument.name.as_str())
                .collect::<Vec<_>>(),
            ["change", "maps", "primary"]
        );
        assert_eq!(validate_args[0].required, Some(true));
        assert_eq!(validate_args[1].required, Some(false));
        assert_eq!(validate_args[2].required, Some(false));
    }

    #[tokio::test]
    async fn safety_prompt_bodies_preserve_the_lab_invariants() {
        let server = Argus::new();
        let harvest = server
            .harvest_before_play(Parameters(HarvestPromptArgs { tag: "vNNN".into() }))
            .await
            .unwrap();
        let harvest = prompt_text(&harvest);
        assert!(harvest.contains("python tools/harvest_session.py --tag vNNN"));
        assert!(harvest.contains("before doing anything that starts an engine"));
        assert!(harvest.contains("every new engine launch truncates qconsole.log"));

        let validate = server
            .validate_change(Parameters(ValidateChangePromptArgs {
                change: "movement tuning".into(),
                maps: Some("dm2,dm4".into()),
                primary: Some("stall_parity".into()),
            }))
            .await
            .unwrap();
        let validate = prompt_text(&validate);
        assert!(validate.contains("at least two maps"));
        assert!(
            validate.contains("at least three candidate tapes and three matching control tapes")
        );
        assert!(validate.contains("Trust each experiment/compare next_steps"));
        assert!(validate.contains("Respect the metric boundaries in CLAUDE.md"));
        assert!(validate.contains("Human tapes are review-only"));
    }

    #[tokio::test]
    async fn harvest_prompt_rejects_a_command_shaped_tag() {
        let error = Argus::new()
            .harvest_before_play(Parameters(HarvestPromptArgs {
                tag: "v1\nmap dm4".into(),
            }))
            .await
            .unwrap_err();
        assert!(error.message.contains("tag must contain only"));
    }

    /// WHAT THE TOOL SURFACE COSTS, measured rather than argued.
    ///
    /// Every exposed tool is paid for on every request through its
    /// schema, whether or not it is ever called. This prints the bill
    /// and fails if the surface grows past a bound, so adding a tool is
    /// a decision someone makes on purpose rather than a drift.
    ///
    /// Bytes stand in for tokens: the payload is ASCII JSON, so the
    /// ratio is roughly four to one throughout and the comparison
    /// between tools is exact either way.
    #[test]
    fn the_tool_surface_has_a_measured_price() {
        let router = Argus::annotated_tool_router();
        let tools = router.list_all();
        assert!(tools.len() > 20, "only {} tools", tools.len());
        let mut rows: Vec<(usize, String)> = tools
            .iter()
            .map(|t| {
                let n = serde_json::to_string(t).map(|s| s.len()).unwrap_or(0);
                (n, t.name.to_string())
            })
            .collect();
        rows.sort_by_key(|row| std::cmp::Reverse(row.0));
        let total: usize = rows.iter().map(|(n, _)| n).sum();
        eprintln!("tool surface: {} tools, {total} bytes", rows.len());
        for (n, name) in rows.iter().take(10) {
            eprintln!("  {n:6}  {name}");
        }
        // If this fails, the question is whether the new tool earns its
        // rent, not whether to raise the bound.
        // 25,181 bytes over 40 tools, measured 2026-09-21 after the two
        // core briefing routes gained their report-envelope output schemas.
        // That is about 6,300 tokens on EVERY request. The bound sits
        // just above the measured surface on purpose: a bound three
        // times the actual is not a bound. If this fails, the question
        // is whether the metadata or tool earns its rent, not whether
        // to raise the number.
        assert!(total < 25_500, "the tool surface costs {total} bytes");
    }

    #[test]
    fn every_tool_publishes_an_explicit_safety_contract() {
        let router = Argus::annotated_tool_router();
        let tools = router.list_all();

        assert_eq!(tools.len(), READ_ONLY_TOOLS.len() + MUTATING_TOOLS.len());
        for tool in &tools {
            let annotations = tool
                .annotations
                .as_ref()
                .unwrap_or_else(|| panic!("{} has no safety annotations", tool.name));
            let read_only = READ_ONLY_TOOLS.contains(&tool.name.as_ref());
            assert_eq!(annotations.title.as_deref(), Some(tool.name.as_ref()));
            assert_eq!(annotations.read_only_hint, Some(read_only), "{}", tool.name);
            assert_eq!(
                annotations.destructive_hint,
                Some(!read_only),
                "{}",
                tool.name
            );
            assert_eq!(
                annotations.idempotent_hint,
                Some(read_only),
                "{}",
                tool.name
            );
            assert_eq!(annotations.open_world_hint, Some(false), "{}", tool.name);
        }

        for name in ["ship", "baseline_set", "match_start", "match_stop", "tune"] {
            let tool = tools.iter().find(|tool| tool.name == name).unwrap();
            let annotations = tool.annotations.as_ref().unwrap();
            assert_eq!(annotations.read_only_hint, Some(false), "{name}");
            assert_eq!(annotations.destructive_hint, Some(true), "{name}");
            assert_eq!(annotations.idempotent_hint, Some(false), "{name}");
        }

        let see = tools.iter().find(|tool| tool.name == "see").unwrap();
        assert_eq!(see.annotations.as_ref().unwrap().read_only_hint, Some(true));
    }

    #[test]
    fn briefing_tools_publish_the_report_envelope_schema() {
        let tools = Argus::annotated_tool_router().list_all();
        for name in ["brief_run", "compare_runs"] {
            let tool = tools.iter().find(|tool| tool.name == name).unwrap();
            let schema = tool
                .output_schema
                .as_ref()
                .unwrap_or_else(|| panic!("{name} has no output schema"));
            assert_eq!(schema.get("type"), Some(&serde_json::json!("object")));
            assert_eq!(
                schema.get("required"),
                Some(&serde_json::json!(["format", "detail", "data"]))
            );
            assert_eq!(
                schema.get("additionalProperties"),
                Some(&serde_json::json!(false))
            );
            let properties = schema["properties"].as_object().unwrap();
            assert_eq!(
                properties["format"]["enum"],
                serde_json::json!(["json", "csv"])
            );
            assert_eq!(
                properties["detail"]["enum"],
                serde_json::json!(["brief", "full", "table"])
            );
        }
    }

    #[test]
    fn report_helpers_keep_text_and_structured_data_in_lockstep() {
        for detail in ["brief", "full"] {
            let result = report_json_ok(&serde_json::json!({"answer": 42}), detail).unwrap();
            let text_value: serde_json::Value = serde_json::from_str(result_text(&result)).unwrap();
            assert_eq!(
                result.structured_content,
                Some(serde_json::json!({
                    "format": "json",
                    "detail": detail,
                    "data": text_value,
                }))
            );
            assert_eq!(result.is_error, Some(false));
        }

        let newline = char::from(10).to_string();
        let csv = ["name,value", "argus,42", ""].join(&newline);
        let result = report_csv_ok(csv).unwrap();
        let text = result_text(&result);
        assert_eq!(
            result.structured_content,
            Some(serde_json::json!({
                "format": "csv",
                "detail": "table",
                "data": text,
            }))
        );

        let error = tool_err("fixture failure").unwrap();
        assert_eq!(error.is_error, Some(true));
        assert!(error.structured_content.is_none());
    }
}
