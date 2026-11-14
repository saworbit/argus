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
    /// A success event with finite, nonnegative game time within the task budget.
    pub completed: bool,
    /// Reported engine time, retained even when late completion is rejected.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub game_sec: Option<f32>,
    pub wall_sec: f32,
    /// Why a task never started, when the harness could not confirm a step.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
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

fn verify_graph(cfg: &Config, suite: &TaskSuite) -> Result<(), String> {
    let path = cfg.src.join(format!("argus_nav_{}.qc.json", suite.map));
    let bytes = std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let actual = format!("{:x}", md5::compute(bytes));
    if actual != suite.graph_md5.to_ascii_lowercase() {
        return Err(format!(
            "task suite graph is stale: expected {}, current {actual}",
            suite.graph_md5
        ));
    }
    Ok(())
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

fn parse_vec(text: &str) -> Option<[f32; 3]> {
    let mut it = text.split_whitespace().map(|v| v.parse::<f32>().ok());
    Some([it.next()??, it.next()??, it.next()??])
}

/// The quoted vector after `key` in `line`, as in `pos '1 2 3'`.
fn quoted_vec(line: &str, key: &str) -> Option<[f32; 3]> {
    let rest = &line[line.find(key)? + key.len()..];
    let rest = rest.trim_start().strip_prefix('\'')?;
    parse_vec(&rest[..rest.find('\'')?])
}

fn near(a: [f32; 3], b: [f32; 3], horizontal: f32, vertical: f32) -> bool {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt() < horizontal
        && (a[2] - b[2]).abs() < vertical
}

/// Whether `bot` started the task after `mark`: a route whose start node is
/// at the task start and whose goal node is at the task goal. That one line
/// proves both the placement and the goal landed. A bot moves between its
/// placement and its next 2 Hz ARGLOG row, so a position check alone misses
/// placements that worked. Before the goal impulse lands the bot shops for
/// ordinary goals, whose routes end elsewhere. A `routefail` counts when an
/// ARGLOG row after `mark` puts the bot near the start, since it carries no
/// endpoints of its own.
fn started_task(log: &str, mark: usize, bot: &str, start: [f32; 3], goal: [f32; 3]) -> bool {
    let route = format!("ARGEVT {bot} route ");
    let failed = format!("ARGEVT {bot} routefail");
    let row = format!("ARGLOG {bot} t ");
    let mut near_start = false;
    for line in lines_after(log, mark) {
        if line.starts_with(&row) {
            near_start |= quoted_vec(line, " pos ").is_some_and(|p| near(p, start, 256.0, 72.0));
        } else if line.starts_with(&route) {
            let from = quoted_vec(line, " start ");
            let to = quoted_vec(line, " goal ");
            if from.is_some_and(|f| near(f, start, 160.0, 72.0))
                && to.is_some_and(|g| near(g, goal, 128.0, 96.0))
            {
                return true;
            }
        } else if line.starts_with(&failed) && near_start {
            return true;
        }
    }
    false
}

/// The roster's bots: named scoreboard rows other than the puppet.
fn roster_bots(names: &std::collections::BTreeMap<u8, String>) -> Vec<String> {
    names
        .values()
        .filter(|n| !n.trim().is_empty() && n.as_str() != "labprobe")
        .cloned()
        .collect()
}

/// Run `attempt` until `check` passes on the log written after it, up to
/// STEP_ATTEMPTS times, pumping `client` while it waits. Each attempt takes
/// a fresh mark, so a confirmation is always newer than the attempt it
/// confirms.
fn confirm<C>(
    client: &mut C,
    read_log: &dyn Fn() -> String,
    pump: &dyn Fn(&mut C),
    wait: Duration,
    mut attempt: impl FnMut(&mut C, u32) -> Result<(), String>,
    check: impl Fn(&str, usize, u32) -> bool,
) -> Result<bool, String> {
    for n in 1..=STEP_ATTEMPTS as u32 {
        let mark = read_log().lines().count();
        attempt(client, n)?;
        let started = Instant::now();
        while started.elapsed() < wait {
            pump(client);
            if check(&read_log(), mark, n) {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

/// Fire `impulse` until `check` passes, through the live match's log.
fn impulse_confirmed(
    ctrl: &MatchCtrl,
    client: &mut NetClient,
    impulse: u8,
    check: impl Fn(&str, usize) -> bool,
) -> Result<bool, String> {
    confirm(
        client,
        &|| ctrl.log_text().unwrap_or_default(),
        &|c: &mut NetClient| c.pump(Duration::from_millis(100)),
        STEP_WAIT,
        |c, _| {
            c.set_impulse(impulse);
            Ok(())
        },
        |log, mark, _| check(log, mark),
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

    // Keep slot zero and remove the free-running opponents one at a time,
    // firing again only while more than one bot remains, so a late impulse
    // cannot take the task bot too. scratch1 147 is the server-admin gate
    // for roster impulses.
    command_confirmed(ctrl, &mut client, "scratch1 147", &mut seq).await?;
    for _ in 0..STEP_ATTEMPTS * 2 {
        let before = roster_bots(&client.world.names).len();
        if before <= 1 {
            break;
        }
        client.set_impulse(102);
        let started = Instant::now();
        while started.elapsed() < STEP_WAIT && roster_bots(&client.world.names).len() >= before {
            client.pump(Duration::from_millis(100));
        }
    }
    let bots = roster_bots(&client.world.names);
    let [bot] = bots.as_slice() else {
        return Err(format!(
            "could not reduce the roster to the task bot; it still holds {bots:?}"
        ));
    };
    let bot = bot.clone();

    let mut results = Vec::new();
    for task in tasks {
        // Place, then assign the goal at once, and confirm both from the
        // route that starts the task. Every attempt places again, so a bot
        // that wandered off before its goal landed starts over.
        let first_print = client.world.prints.len();
        let mut began = false;
        for _ in 0..STEP_ATTEMPTS {
            command_confirmed(
                ctrl,
                &mut client,
                &command_point(3841, task.start),
                &mut seq,
            )
            .await?;
            let mark = ctrl.log_text().unwrap_or_default().lines().count();
            client.set_impulse(217);
            client.pump(Duration::from_millis(250));
            command_confirmed(ctrl, &mut client, &command_point(3842, task.goal), &mut seq).await?;
            began = impulse_confirmed(ctrl, &mut client, 217, |log, _| {
                started_task(log, mark, &bot, task.start, task.goal)
            })?;
            if began {
                break;
            }
        }
        let note = (!began).then(|| format!("{bot} never started a route from the task start"));

        let started = Instant::now();
        let wall_limit = Duration::from_secs_f32(task.budget_sec + 3.0);
        let mut outcome = None;
        while note.is_none() && started.elapsed() < wall_limit && !client.world.disconnected {
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
            completed,
            game_sec: outcome.map(|_| game_sec),
            wall_sec: started.elapsed().as_secs_f32(),
            note,
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
    verify_graph(cfg, suite)?;
    let count = limit.unwrap_or(suite.tasks.len()).min(suite.tasks.len());
    if count == 0 {
        return Err("benchmark limit must be at least 1".into());
    }
    let tasks = &suite.tasks[..count];
    let seconds = tasks
        .iter()
        .map(|task| task.budget_sec.ceil() as u32 + 4)
        .sum::<u32>()
        .saturating_add(30)
        .min(590);
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
    let _ = ctrl.stop(Duration::from_secs(3)).await;
    result
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
                completed: true,
                game_sec: Some(4.0),
                wall_sec: 4.0,
                note: None,
            },
            TaskResult {
                name: "heldout_route".into(),
                split: "heldout".into(),
                completed: false,
                game_sec: Some(12.0),
                wall_sec: 12.0,
                note: None,
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
                    completed,
                    game_sec: seconds,
                    wall_sec: 0.1,
                    note: None,
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
ARGLOG Joe Rogan t 4.5 pos '485 -703 56' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0
ARGEVT Joe Rogan route 7 start '485 -703 56' goal '261 -703 328'
ARGEVT Joe Rogan route 3 start '485 -703 56' goal '900 0 0'
";
        assert!(echoed(log, 0, "ARGUS_BENCH_ACK 1"));
        assert!(!echoed(log, 1, "ARGUS_BENCH_ACK 1"));
        assert!(!echoed(log, 0, "ARGUS_BENCH_ACK 11"));
        let goal = [261.0, -703.0, 328.0];
        let start = [480.0, -700.0, 60.0];
        // a spaced name is matched whole, and only a route from the start
        // to the goal counts
        assert!(started_task(log, 0, "Joe Rogan", start, goal));
        assert!(!started_task(log, 0, "Joe", start, goal));
        assert!(!started_task(log, 0, "Joe Rogan", [0.0, 0.0, 56.0], goal));
        assert!(!started_task(
            log,
            0,
            "Joe Rogan",
            start,
            [900.0, 900.0, 0.0]
        ));
        assert!(!started_task(log, 3, "Joe Rogan", start, goal));
        // a routefail counts only once a row after the mark puts the bot
        // near the start, as a bot that ran on after its placement still is
        let ran_on =
            "ARGLOG Carmack t 52.6 pos '-25.5 -551.7 -16.0' spd 451\nARGEVT Carmack routefail\n";
        assert!(started_task(
            ran_on,
            0,
            "Carmack",
            [69.0, -671.0, -16.0],
            goal
        ));
        assert!(!started_task(
            "ARGEVT Carmack routefail\n",
            0,
            "Carmack",
            [69.0, -671.0, -16.0],
            goal
        ));
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

    /// The harness fires again until the log confirms the step, and a
    /// confirmation written before an attempt does not count (#776).
    #[test]
    fn confirm_retries_until_the_log_answers_and_ignores_stale_lines() {
        use std::cell::RefCell;
        let start = [485.0, -703.0, 56.0];
        let goal = [261.0, -703.0, 328.0];
        let row = "ARGEVT Carmack route 7 start '485 -703 56' goal '261 -703 328'\n";
        // A stale row before the first attempt, then nothing until the third.
        let log = RefCell::new(row.to_string());
        let mut fired = 0u32;
        let ok = confirm(
            &mut fired,
            &|| log.borrow().clone(),
            &|_| {},
            Duration::from_millis(20),
            |count: &mut u32, n| {
                *count += 1;
                if n == 3 {
                    log.borrow_mut().push_str(row);
                }
                Ok(())
            },
            |text, mark, _| started_task(text, mark, "Carmack", start, goal),
        )
        .unwrap();
        assert!(ok);
        assert_eq!(fired, 3);

        let mut fired = 0u32;
        let never = confirm(
            &mut fired,
            &|| log.borrow().clone(),
            &|_| {},
            Duration::from_millis(20),
            |count: &mut u32, _| {
                *count += 1;
                Ok(())
            },
            |text, mark, _| started_task(text, mark, "Carmack", start, goal),
        )
        .unwrap();
        assert!(!never);
        assert_eq!(fired as usize, STEP_ATTEMPTS);
    }
}
