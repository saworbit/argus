//! Fixed navigation tasks: an absolute, low-variance complement to matches.
//!
//! A real Argus bot is placed at a declared nav coordinate and assigned a
//! synthetic goal while the NetQuake puppet observes completion. The task
//! manifest pins the nav JSON hash and labels train/held-out routes so tuning
//! cannot silently change the yardstick it is judged against.

use std::path::Path;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use crate::config::Config;
use crate::match_ctrl::MatchCtrl;
use crate::nav_provenance::{self, MapSnapshot};
use crate::netclient::NetClient;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TaskSuite {
    pub schema_version: u32,
    pub name: String,
    pub map: String,
    pub graph_md5: String,
    #[serde(default = "default_skill")]
    pub skill: u32,
    pub tasks: Vec<NavigationTask>,
}

fn default_skill() -> u32 {
    2
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct NavigationTask {
    pub name: String,
    pub start: [f32; 3],
    pub goal: [f32; 3],
    pub budget_sec: f32,
    pub split: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct TaskResult {
    pub name: String,
    pub split: String,
    /// Bot origin recorded by the server when it assigned the goal.
    pub verified_start: [f32; 3],
    /// A success event with finite, nonnegative game time within the task budget.
    pub completed: bool,
    /// Reported engine time, retained even when late completion is rejected.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub game_sec: Option<f32>,
    pub wall_sec: f32,
}

#[derive(Debug, Clone, Serialize)]
pub struct SplitSummary {
    pub tasks: usize,
    pub completed: usize,
    pub completion_rate: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub median_game_sec: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct BenchmarkReport {
    pub suite: String,
    pub map: String,
    pub graph_md5: String,
    pub skill: u32,
    pub results: Vec<TaskResult>,
    pub all: SplitSummary,
    pub train: SplitSummary,
    pub heldout: SplitSummary,
}

pub fn load_suite(path: &Path) -> Result<TaskSuite, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut suite: TaskSuite =
        serde_json::from_str(&text).map_err(|e| format!("task suite: {e}"))?;
    suite.map = crate::paths::map_name(&suite.map)?;
    validate_suite(&suite)?;
    Ok(suite)
}

pub fn validate_suite(suite: &TaskSuite) -> Result<(), String> {
    if suite.schema_version != 1 {
        return Err("task suite schema_version must be 1".into());
    }
    crate::engine::validate_map(&suite.map)?;
    if suite.name.is_empty()
        || !suite
            .name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return Err("task suite name must use letters, digits, dash or underscore".into());
    }
    if suite.skill > 3 {
        return Err("task suite skill must be 0..3".into());
    }
    if suite.graph_md5.len() != 32 || !suite.graph_md5.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("task suite graph_md5 must be 32 hexadecimal characters".into());
    }
    if suite.tasks.is_empty() || suite.tasks.len() > 40 {
        return Err("task suite must contain 1..=40 tasks".into());
    }
    let mut names = std::collections::HashSet::new();
    for task in &suite.tasks {
        if task.name.is_empty() || !names.insert(task.name.as_str()) {
            return Err("task names must be non-empty and unique".into());
        }
        if task.split != "train" && task.split != "heldout" {
            return Err(format!("{}: split must be train or heldout", task.name));
        }
        if !(2.0..=60.0).contains(&task.budget_sec) || !task.budget_sec.is_finite() {
            return Err(format!("{}: budget_sec must be 2..=60", task.name));
        }
        if task
            .start
            .iter()
            .chain(task.goal.iter())
            .any(|value| !value.is_finite())
        {
            return Err(format!("{}: coordinates must be finite", task.name));
        }
    }
    Ok(())
}

fn verify_graph(src: &Path, suite: &TaskSuite) -> Result<serde_json::Value, String> {
    let path = src.join(format!("argus_nav_{}.qc.json", suite.map));
    let bytes = std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let actual = format!("{:x}", md5::compute(&bytes));
    if !actual.eq_ignore_ascii_case(&suite.graph_md5) {
        return Err(format!(
            "task suite graph is stale: expected {}, current {actual}",
            suite.graph_md5
        ));
    }
    serde_json::from_slice(&bytes).map_err(|e| format!("{}: {e}", path.display()))
}

fn verify_program_graph(
    snapshot: Option<MapSnapshot>,
    graph: &serde_json::Value,
) -> Result<MapSnapshot, String> {
    let snapshot = snapshot.ok_or(
        "no benchmark graph receipt for the installed program. Compile and install through the lab",
    )?;
    if !snapshot.runtime_navigation() || snapshot.graph.as_ref() != Some(graph) {
        return Err("the installed program's graph does not match the benchmark pin".into());
    }
    Ok(snapshot)
}

fn verify_recorded_graph(
    path: &Path,
    map: &str,
    live_text: &str,
    mut expected: MapSnapshot,
) -> Result<(), String> {
    let recorded = crate::paths::read_engine_text(path).map_err(|e| e.to_string())?;
    // A retained tape from an older run can share the name and graph.
    let prefix = live_text
        .rsplit_once('\n')
        .map_or(live_text, |(lines, _)| lines);
    if !recorded.starts_with(prefix) {
        return Err("retained tape does not match the current run".into());
    }
    expected.loaded_in_tape = Some(true);
    if nav_provenance::read_tape(path, map)? != Some(expected) {
        return Err("tape did not confirm the benchmark graph for the launched program".into());
    }
    Ok(())
}

fn verify_recorded_map(text: &str, requested: &str) -> Result<(), String> {
    let tape = crate::parse_arglog::parse_tape(text);
    if !tape.failed_spawns.is_empty() {
        return Err(format!(
            "engine refused to spawn {}",
            tape.failed_spawns.join(", ")
        ));
    }
    // Check every initialisation. The brief can pick one level from a mixed
    // tape, and a switch before the first sample need not create a segment.
    let maps: Vec<_> = text
        .lines()
        .filter_map(|line| line.strip_prefix("ARGUS init on "))
        .map(str::trim)
        .collect();
    match maps.as_slice() {
        [map] if map.eq_ignore_ascii_case(requested) && tape.segments == 1 => Ok(()),
        [] => Err(format!("requested '{requested}', no confirmed map in tape")),
        _ => Err(format!(
            "requested one run on '{requested}', map starts: {}",
            maps.join(", ")
        )),
    }
}

fn command_point(mode: u32, point: [f32; 3]) -> String {
    format!(
        "scratch1 {mode}; scratch2 {}; scratch3 {}; scratch4 {}",
        point[0], point[1], point[2]
    )
}

fn parse_task_print(line: &str) -> Option<(bool, f32)> {
    let mut fields = line.split_whitespace();
    if fields.next()? != "ARGTASK" || fields.next()? != "0" {
        return None;
    }
    let completed = match fields.next()? {
        "complete" => true,
        "timeout" => false,
        _ => return None,
    };
    let seconds = fields.next()?.parse().ok()?;
    Some((completed, seconds))
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let middle = values.len() / 2;
    if values.len().is_multiple_of(2) {
        Some((values[middle - 1] + values[middle]) / 2.0)
    } else {
        Some(values[middle])
    }
}

fn summarize<'a>(results: impl Iterator<Item = &'a TaskResult>) -> SplitSummary {
    let rows: Vec<&TaskResult> = results.collect();
    let times: Vec<f64> = rows
        .iter()
        .filter_map(|row| row.completed.then_some(row.game_sec).flatten())
        .map(f64::from)
        .collect();
    let completed = rows.iter().filter(|row| row.completed).count();
    SplitSummary {
        tasks: rows.len(),
        completed,
        completion_rate: if rows.is_empty() {
            0.0
        } else {
            completed as f64 / rows.len() as f64
        },
        median_game_sec: median(times),
    }
}

fn report(suite: &TaskSuite, mut results: Vec<TaskResult>) -> BenchmarkReport {
    // The wall timeout includes transport grace. Only engine game time
    // decides whether a completed route met its manifest budget.
    for result in &mut results {
        result.completed &= suite
            .tasks
            .iter()
            .find(|task| task.name == result.name)
            .is_some_and(|task| {
                result.game_sec.is_some_and(|seconds| {
                    seconds.is_finite() && seconds >= 0.0 && seconds <= task.budget_sec
                })
            });
    }
    BenchmarkReport {
        suite: suite.name.clone(),
        map: suite.map.clone(),
        graph_md5: suite.graph_md5.clone(),
        skill: suite.skill,
        all: summarize(results.iter()),
        train: summarize(results.iter().filter(|row| row.split == "train")),
        heldout: summarize(results.iter().filter(|row| row.split == "heldout")),
        results,
    }
}

/// How many times a step's impulse is fired before the task is given up.
const STEP_ATTEMPTS: usize = 4;
/// How long one attempt waits for its confirmation in the server log.
const STEP_WAIT: Duration = Duration::from_millis(1500);

/// Lines of `log` after the first `mark` lines.
fn lines_after(log: &str, mark: usize) -> impl Iterator<Item = &str> {
    log.lines().skip(mark)
}

/// Whether the console echoed `token` after `mark`. Console lines run in
/// order, so the echo proves the commands before it on the same line ran.
fn echoed(log: &str, mark: usize, token: &str) -> bool {
    lines_after(log, mark).any(|line| line.trim() == token)
}

/// Match the engine's one-decimal vtos rounding on each coordinate.
fn confirmed_point(text: &str, expected: [f32; 3]) -> Option<[f32; 3]> {
    let mut fields = text
        .strip_prefix('\'')?
        .strip_suffix('\'')?
        .split_whitespace();
    let point = [
        fields.next()?.parse::<f32>().ok()?,
        fields.next()?.parse::<f32>().ok()?,
        fields.next()?.parse::<f32>().ok()?,
    ];
    (fields.next().is_none()
        && point
            .iter()
            .zip(expected)
            .all(|(actual, wanted)| (actual - wanted).abs() <= 0.051))
    .then_some(point)
}

fn staged_task(log: &str, mark: usize, start: [f32; 3]) -> Option<[f32; 3]> {
    lines_after(log, mark)
        .find_map(|line| confirmed_point(line.strip_prefix("ARGTASK 0 staged ")?, start))
}

fn started_task(log: &str, mark: usize, start: [f32; 3], goal: [f32; 3]) -> Option<[f32; 3]> {
    lines_after(log, mark).find_map(|line| {
        let (origin, marker) = line
            .strip_prefix("ARGTASK 0 start ")?
            .split_once(" goal ")?;
        confirmed_point(marker, goal)?;
        confirmed_point(origin, start)
    })
}

/// The roster's bots: named scoreboard rows other than the puppet.
fn roster_bots(names: &std::collections::BTreeMap<u8, String>) -> Vec<String> {
    names
        .values()
        .filter(|n| !n.trim().is_empty() && n.as_str() != "labprobe")
        .cloned()
        .collect()
}

fn verify_solo_roster(log: &str, bot: &str) -> Result<(), String> {
    let spawned: Vec<_> = log
        .lines()
        .filter_map(|line| line.strip_prefix("ARGEVT ")?.strip_suffix(" spawned"))
        .collect();
    if spawned.as_slice() != [bot] {
        return Err(format!(
            "benchmark requires one bot from map start, saw [{}]",
            spawned.join(", ")
        ));
    }
    Ok(())
}

/// Run `attempt` until `check` passes on the log written after it, up to
/// STEP_ATTEMPTS times, pumping `client` while it waits. A delayed receipt
/// from any retry of this step still counts. Earlier steps are before `mark`.
fn confirm<C, T>(
    client: &mut C,
    read_log: &dyn Fn() -> String,
    pump: &dyn Fn(&mut C),
    wait: Duration,
    mut attempt: impl FnMut(&mut C) -> Result<(), String>,
    check: impl Fn(&str, usize) -> Option<T>,
) -> Result<Option<T>, String> {
    let mark = read_log().lines().count();
    for _ in 0..STEP_ATTEMPTS {
        attempt(client)?;
        let started = Instant::now();
        while started.elapsed() < wait {
            pump(client);
            if let Some(value) = check(&read_log(), mark) {
                return Ok(Some(value));
            }
        }
    }
    Ok(check(&read_log(), mark))
}

/// Fire `impulse` until `check` passes, through the live match's log.
fn impulse_confirmed<T>(
    ctrl: &MatchCtrl,
    client: &mut NetClient,
    impulse: u8,
    check: impl Fn(&str, usize) -> Option<T>,
) -> Result<Option<T>, String> {
    confirm(
        client,
        &|| ctrl.log_text().unwrap_or_default(),
        &|c: &mut NetClient| c.pump(Duration::from_millis(100)),
        STEP_WAIT,
        |c| {
            c.set_impulse(impulse);
            Ok(())
        },
        check,
    )
}

/// Send console `line` and wait until the server echoes a marker after it,
/// resending if the line was lost. A fixed 150 ms sleep let the next impulse
/// run on the previous cvars whenever the console was slow (#776).
async fn command_confirmed(
    ctrl: &mut MatchCtrl,
    client: &mut NetClient,
    line: &str,
    seq: &mut u32,
) -> Result<(), String> {
    for _ in 0..STEP_ATTEMPTS {
        *seq += 1;
        let token = format!("ARGUS_BENCH_ACK {seq}");
        let mark = ctrl.log_text().unwrap_or_default().lines().count();
        ctrl.command(&format!("{line}; echo {token}")).await?;
        let started = Instant::now();
        while started.elapsed() < STEP_WAIT {
            client.pump(Duration::from_millis(100));
            if echoed(&ctrl.log_text().unwrap_or_default(), mark, &token) {
                return Ok(());
            }
        }
    }
    Err(format!("the server console never confirmed: {line}"))
}

async fn run_connected(
    ctrl: &mut MatchCtrl,
    suite: &TaskSuite,
    tasks: &[NavigationTask],
) -> Result<BenchmarkReport, String> {
    tokio::time::sleep(Duration::from_secs(4)).await;
    let mut client = NetClient::connect_match(ctrl, "labprobe")?;
    client.pump(Duration::from_secs(3));
    if client.world.signon < 3 {
        return Err(format!("signon stalled at {}", client.world.signon));
    }
    let mut seq = 0u32;

    let bots = roster_bots(&client.world.names);
    let [bot] = bots.as_slice() else {
        return Err(format!(
            "benchmark requires one visible task bot, saw {bots:?}"
        ));
    };
    verify_solo_roster(&ctrl.log_text().unwrap_or_default(), bot)?;

    let mut results = Vec::new();
    for task in tasks {
        command_confirmed(
            ctrl,
            &mut client,
            &command_point(3841, task.start),
            &mut seq,
        )
        .await?;
        impulse_confirmed(ctrl, &mut client, 217, |log, mark| {
            staged_task(log, mark, task.start)
        })?
        .ok_or_else(|| format!("{}: {bot} did not confirm the staged start", task.name))?;

        command_confirmed(ctrl, &mut client, &command_point(3842, task.goal), &mut seq).await?;
        let first_print = client.world.prints.len();
        let verified_start = impulse_confirmed(ctrl, &mut client, 217, |log, mark| {
            started_task(log, mark, task.start, task.goal)
        })?
        .ok_or_else(|| format!("{}: {bot} did not confirm placement and goal", task.name))?;

        let started = Instant::now();
        let wall_limit = Duration::from_secs_f32(task.budget_sec + 3.0);
        let mut outcome = None;
        while started.elapsed() < wall_limit && !client.world.disconnected {
            client.pump(Duration::from_millis(200));
            outcome = client.world.prints[first_print..]
                .iter()
                .find_map(|(_, line)| parse_task_print(line));
            if outcome.is_some() {
                break;
            }
        }
        if outcome.is_none() {
            command_confirmed(ctrl, &mut client, "scratch1 3840", &mut seq).await?;
            client.set_impulse(217);
            client.pump(Duration::from_millis(300));
        }
        let (completed, game_sec) = outcome.unwrap_or((false, task.budget_sec));
        results.push(TaskResult {
            name: task.name.clone(),
            split: task.split.clone(),
            verified_start,
            completed,
            game_sec: outcome.map(|_| game_sec),
            wall_sec: started.elapsed().as_secs_f32(),
        });
    }
    client.disconnect();
    Ok(report(suite, results))
}

pub async fn run_suite(
    cfg: &Config,
    suite: &TaskSuite,
    limit: Option<usize>,
) -> Result<BenchmarkReport, String> {
    let mut ctrl = crate::match_ctrl::MatchCtrl::default();
    run_suite_with_ctrl(cfg, suite, limit, &mut ctrl).await
}

/// Use the caller-selected controller for both the engine and protocol client.
pub async fn run_suite_with_ctrl(
    cfg: &Config,
    suite: &TaskSuite,
    limit: Option<usize>,
    ctrl: &mut crate::match_ctrl::MatchCtrl,
) -> Result<BenchmarkReport, String> {
    let mut normalized = suite.clone();
    normalized.map = crate::paths::map_name(&suite.map)?;
    let suite = &normalized;
    validate_suite(suite)?;
    let graph = verify_graph(&cfg.src, suite)?;
    let count = limit.unwrap_or(suite.tasks.len()).min(suite.tasks.len());
    if count == 0 {
        return Err("benchmark limit must be at least 1".into());
    }
    let program = verify_program_graph(nav_provenance::for_launch(cfg, &suite.map), &graph)?;
    let tasks = &suite.tasks[..count];
    let seconds = tasks
        .iter()
        .map(|task| task.budget_sec.ceil() as u32 + 4)
        .sum::<u32>()
        .saturating_add(30)
        .min(590);
    ctrl.use_benchmark_roster_once();
    ctrl.start(
        cfg,
        &suite.map,
        Some(seconds),
        Some(&format!("benchmark_{}", suite.name)),
        Some(4),
        Some(suite.skill),
        Some(false),
    )
    .await
    .map_err(|e| format!("engine start: {e}"))?;
    let result = run_connected(ctrl, suite, tasks).await;
    // The live log belongs to this run even if harvest preserves an older
    // tape with the same name. Stop still owns cleanup and raw tape harvest.
    let text = ctrl.log_text().unwrap_or_default();
    let stopped = ctrl.stop(Duration::from_secs(3)).await;
    let log_path = stopped?.log_path.ok_or("benchmark retained no tape path")?;
    let result = result.map_err(|reason| format!("{reason}. Tape at {log_path}"))?;
    verify_recorded_map(&text, &suite.map)
        .map_err(|reason| format!("WRONG MAP: {reason}. Tape at {log_path}"))?;
    verify_recorded_graph(Path::new(&log_path), &suite.map, &text, program)
        .map_err(|reason| format!("BENCHMARK GRAPH: {reason}. Tape at {log_path}"))?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn suite() -> TaskSuite {
        TaskSuite {
            schema_version: 1,
            name: "dm4_fixed".into(),
            map: "dm4".into(),
            graph_md5: "0123456789abcdef0123456789abcdef".into(),
            skill: 2,
            tasks: vec![
                NavigationTask {
                    name: "train_route".into(),
                    start: [0.0, 0.0, 24.0],
                    goal: [128.0, 0.0, 24.0],
                    budget_sec: 10.0,
                    split: "train".into(),
                },
                NavigationTask {
                    name: "heldout_route".into(),
                    start: [0.0, 0.0, 24.0],
                    goal: [0.0, 128.0, 24.0],
                    budget_sec: 12.0,
                    split: "heldout".into(),
                },
            ],
        }
    }

    #[test]
    fn suite_validation_guards_the_fixed_yardstick() {
        let mut value = suite();
        assert!(validate_suite(&value).is_ok());
        value.tasks[1].name = value.tasks[0].name.clone();
        assert!(validate_suite(&value).unwrap_err().contains("unique"));
        value = suite();
        value.tasks[0].split = "testish".into();
        assert!(validate_suite(&value)
            .unwrap_err()
            .contains("train or heldout"));
        value = suite();
        value.tasks[0].start[1] = f32::NAN;
        assert!(validate_suite(&value).unwrap_err().contains("finite"));
    }

    #[test]
    fn benchmark_graph_pin_matches_the_shared_cases() {
        let cases: serde_json::Value =
            serde_json::from_str(include_str!("../testdata/benchmark_graph_pins.json")).unwrap();
        let dir = crate::test_support::TestDir::new("benchmark-graph-pin").unwrap();
        std::fs::write(
            dir.path().join("argus_nav_dm4.qc.json"),
            cases["graph"].as_str().unwrap(),
        )
        .unwrap();
        let mut suite = suite();
        for case in cases["cases"].as_array().unwrap() {
            suite.graph_md5 = case["pin"].as_str().unwrap().into();
            assert_eq!(
                (validate_suite(&suite).is_ok() && verify_graph(dir.path(), &suite).is_ok()),
                case["matches"].as_bool().unwrap(),
                "{case}"
            );
        }
    }

    #[test]
    fn benchmark_requires_one_confirmed_manifest_map() {
        assert!(verify_recorded_map("SpawnServer: dm4\nARGUS init on DM4\n", "dm4").is_ok());
        for (log, reason) in [
            ("SpawnServer: dm4\n", "no confirmed map"),
            ("ARGUS init on dm2\n", "map starts: dm2"),
            (
                "ARGUS init on dm4\nARGUS init on dm2\n",
                "map starts: dm4, dm2",
            ),
            (
                "ARGUS init on dm4\nARGUS init on dm4\n",
                "map starts: dm4, dm4",
            ),
            (
                "Couldn't spawn server maps/dm2.bsp\nARGUS init on dm4\n",
                "refused to spawn dm2",
            ),
        ] {
            assert!(verify_recorded_map(log, "dm4")
                .unwrap_err()
                .contains(reason));
        }
    }

    fn registered_graph() -> MapSnapshot {
        MapSnapshot {
            map: "dm4".into(),
            program_md5: "program".into(),
            inputs_md5: "inputs".into(),
            in_progs_src: true,
            in_dispatcher: true,
            qc_present: true,
            graph: Some(serde_json::json!({"nodes": [[0, 0, 24]], "links": []})),
            loaded_in_tape: None,
        }
    }

    #[test]
    fn benchmark_checks_the_installed_graph_and_registration() {
        let mut snapshot = registered_graph();
        let graph = snapshot.graph.clone().unwrap();
        assert!(verify_program_graph(None, &graph).is_err());
        assert!(verify_program_graph(Some(snapshot.clone()), &graph).is_ok());
        let other = serde_json::json!({"nodes": [[32, 0, 24]], "links": []});
        assert!(verify_program_graph(Some(snapshot.clone()), &other).is_err());
        snapshot.in_dispatcher = false;
        assert!(verify_program_graph(Some(snapshot), &graph).is_err());
    }

    #[test]
    fn benchmark_requires_a_current_tape_with_the_launched_graph() {
        let dir = crate::test_support::TestDir::new("benchmark-graph-proof").unwrap();
        let path = dir.path().join("benchmark.log");
        let snapshot = registered_graph();
        let no_graph = "ARGUS init on dm4\n";
        let loaded = "ARGNAV 1 nodes, 0 links\nARGUS init on dm4\n";
        std::fs::write(&path, no_graph).unwrap();
        nav_provenance::record_tape(&path, no_graph.as_bytes(), Some(&snapshot)).unwrap();
        assert!(verify_recorded_graph(&path, "dm4", no_graph, snapshot.clone()).is_err());
        std::fs::write(&path, loaded).unwrap();
        nav_provenance::record_tape(&path, loaded.as_bytes(), Some(&snapshot)).unwrap();
        assert!(verify_recorded_graph(&path, "dm4", loaded, snapshot.clone()).is_ok());
        assert!(verify_recorded_graph(&path, "dm4", no_graph, snapshot.clone()).is_err());
        let mut other_program = snapshot;
        other_program.program_md5 = "other program".into();
        assert!(verify_recorded_graph(&path, "dm4", loaded, other_program).is_err());
    }

    #[test]
    fn task_prints_distinguish_completion_from_timeout() {
        assert_eq!(
            parse_task_print("ARGTASK 0 complete 7.5"),
            Some((true, 7.5))
        );
        assert_eq!(
            parse_task_print("ARGTASK 0 timeout 60"),
            Some((false, 60.0))
        );
        assert_eq!(parse_task_print("ARGTASK 1 complete 2"), None);
    }

    #[test]
    fn report_keeps_train_and_heldout_apart() {
        let rows = vec![
            TaskResult {
                name: "train_route".into(),
                split: "train".into(),
                verified_start: [0.0, 0.0, 24.0],
                completed: true,
                game_sec: Some(4.0),
                wall_sec: 4.0,
            },
            TaskResult {
                name: "heldout_route".into(),
                split: "heldout".into(),
                verified_start: [0.0, 0.0, 24.0],
                completed: false,
                game_sec: Some(12.0),
                wall_sec: 12.0,
            },
        ];
        let report = report(&suite(), rows);
        assert_eq!(report.all.completed, 1);
        assert_eq!(report.train.completion_rate, 1.0);
        assert_eq!(report.heldout.completion_rate, 0.0);
        assert_eq!(report.train.median_game_sec, Some(4.0));
        assert_eq!(report.heldout.median_game_sec, None);
    }

    #[test]
    fn report_scores_completion_against_game_time_budget() {
        for (completed, seconds, expected) in [
            (true, Some(9.9), true),
            (true, Some(10.0), true),
            (true, Some(10.1), false),
            (false, Some(4.0), false),
            (true, None, false),
            (true, Some(f32::NAN), false),
            (true, Some(f32::INFINITY), false),
            (true, Some(-1.0), false),
        ] {
            let value = report(
                &suite(),
                vec![TaskResult {
                    name: "train_route".into(),
                    split: "train".into(),
                    verified_start: [0.0, 0.0, 24.0],
                    completed,
                    game_sec: seconds,
                    wall_sec: 0.1,
                }],
            );
            assert_eq!(value.results[0].completed, expected, "elapsed {seconds:?}");
            assert_eq!(value.all.completed, usize::from(expected));
            assert_eq!(
                value.train.completion_rate,
                if expected { 1.0 } else { 0.0 }
            );
            assert_eq!(value.train.median_game_sec.is_some(), expected);
            if seconds.is_some_and(|s| s.is_finite()) {
                assert_eq!(value.results[0].game_sec, seconds);
            }
        }
    }

    #[test]
    fn step_checks_read_only_lines_after_their_mark() {
        let log = "\
ARGUS_BENCH_ACK 1
ARGTASK 0 staged '480.0 -700.0 60.0'
ARGTASK 0 start '480.0 -700.0 60.0' goal '261.0 -703.0 328.0'
";
        assert!(echoed(log, 0, "ARGUS_BENCH_ACK 1"));
        assert!(!echoed(log, 1, "ARGUS_BENCH_ACK 1"));
        assert!(!echoed(log, 0, "ARGUS_BENCH_ACK 11"));
        let start = [480.01, -700.02, 60.04];
        let goal = [261.0, -703.0, 328.0];
        assert_eq!(staged_task(log, 1, start), Some([480.0, -700.0, 60.0]));
        assert_eq!(staged_task(log, 2, start), None);
        assert_eq!(
            started_task(log, 2, start, goal),
            Some([480.0, -700.0, 60.0])
        );
        assert_eq!(started_task(log, 3, start, goal), None);
        assert_eq!(started_task(log, 2, [480.1, -700.0, 60.0], goal), None);
        assert_eq!(started_task(log, 2, start, [261.0, -703.1, 328.0]), None);
        assert_eq!(
            started_task(&log.replace("ARGTASK 0", "ARGTASK 1"), 0, start, goal),
            None
        );
        assert_eq!(
            started_task(&log.replace("480.0", "NaN"), 0, start, goal),
            None
        );
        assert_eq!(
            started_task(&log.replace("60.0'", "60.0 99.0'"), 0, start, goal),
            None
        );
    }

    #[test]
    fn nearby_route_does_not_confirm_task_placement() {
        let displaced = "ARGLOG Carmack t 9.1 pos '552.3 280.3 -712.0' spd 300\n\
                         ARGEVT Carmack route 12 start '577.0 289.0 -712.0' goal '1249.0 -127.0 -552.0'\n";
        assert_eq!(
            started_task(
                displaced,
                0,
                [673.0, 321.0, -712.0],
                [1249.0, -127.0, -552.0],
            ),
            None
        );
    }

    #[test]
    fn roster_bots_leave_out_the_puppet_and_blank_rows() {
        let names = std::collections::BTreeMap::from([
            (0u8, "labprobe".to_string()),
            (5u8, String::new()),
            (6u8, "Joe Rogan".to_string()),
            (7u8, "Carmack".to_string()),
        ]);
        assert_eq!(roster_bots(&names), vec!["Joe Rogan", "Carmack"]);
    }

    #[test]
    fn solo_benchmark_requires_the_same_bot_from_map_start() {
        let single = "ARGEVT Carmack spawned\nARGEVT Carmack respawn\n";
        assert!(verify_solo_roster(single, "Carmack").is_ok());
        assert!(verify_solo_roster(single, "Joe Rogan").is_err());
        assert!(verify_solo_roster("", "Carmack").is_err());
        // The scoreboard can hide a bot. Its spawn before signon still
        // invalidates the one-bot setup even if it is gone at assignment.
        let initial_fight = format!("{single}ARGEVT Joe Rogan spawned\n");
        assert!(verify_solo_roster(&initial_fight, "Carmack").is_err());
    }

    /// The harness fires again until the log confirms the step, and a
    /// confirmation written before an attempt does not count (#776).
    #[test]
    fn confirm_retries_until_the_log_answers_and_ignores_stale_lines() {
        use std::cell::RefCell;
        let start = [485.0, -703.0, 56.0];
        let goal = [261.0, -703.0, 328.0];
        let row = "ARGTASK 0 start '485 -703 56' goal '261 -703 328'\n";
        // A stale row before the first attempt, then nothing until the third.
        let log = RefCell::new(row.to_string());
        let mut fired = 0u32;
        let ok = confirm(
            &mut fired,
            &|| log.borrow().clone(),
            &|_| {},
            Duration::from_millis(20),
            |count: &mut u32| {
                *count += 1;
                if *count == 3 {
                    log.borrow_mut().push_str(row);
                }
                Ok(())
            },
            |text, mark| started_task(text, mark, start, goal),
        )
        .unwrap();
        assert_eq!(ok, Some(start));
        assert_eq!(fired, 3);

        let mut fired = 0u32;
        let never = confirm(
            &mut fired,
            &|| log.borrow().clone(),
            &|_| {},
            Duration::from_millis(20),
            |count: &mut u32| {
                *count += 1;
                Ok(())
            },
            |text, mark| started_task(text, mark, start, goal),
        )
        .unwrap();
        assert_eq!(never, None);
        assert_eq!(fired as usize, STEP_ATTEMPTS);
    }

    #[test]
    fn one_shot_receipt_remains_valid_across_retries() {
        use std::cell::RefCell;
        let log = RefCell::new(String::new());
        let start = [485.0, -703.0, 56.0];
        let goal = [261.0, -703.0, 328.0];
        let mut fired = 0u32;
        let result = confirm(
            &mut fired,
            &|| log.borrow().clone(),
            &|_| {},
            Duration::ZERO,
            |count: &mut u32| {
                *count += 1;
                if *count == 1 {
                    log.borrow_mut()
                        .push_str("ARGTASK 0 start '485 -703 56' goal '261 -703 328'\n");
                }
                Ok(())
            },
            |text, mark| started_task(text, mark, start, goal),
        )
        .unwrap();
        assert_eq!(result, Some(start));
    }
}
