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
    pub completed: bool,
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
    let suite: TaskSuite = serde_json::from_str(&text).map_err(|e| format!("task suite: {e}"))?;
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

fn report(suite: &TaskSuite, results: Vec<TaskResult>) -> BenchmarkReport {
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

async fn run_connected(
    ctrl: &mut MatchCtrl,
    suite: &TaskSuite,
    tasks: &[NavigationTask],
) -> Result<BenchmarkReport, String> {
    tokio::time::sleep(Duration::from_secs(4)).await;
    let mut client = NetClient::connect("127.0.0.1", 26000, "labprobe")?;
    client.pump(Duration::from_secs(3));
    if client.world.signon < 3 {
        return Err(format!("signon stalled at {}", client.world.signon));
    }

    // Keep slot zero and remove the two free-running opponents. scratch1 147
    // is the existing server-admin gate for roster impulses.
    ctrl.command("scratch1 147").await?;
    for _ in 0..2 {
        client.set_impulse(102);
        client.pump(Duration::from_millis(400));
    }

    let mut results = Vec::new();
    for task in tasks {
        ctrl.command(&command_point(3841, task.start)).await?;
        tokio::time::sleep(Duration::from_millis(150)).await;
        client.set_impulse(217);
        client.pump(Duration::from_millis(500));

        let first_print = client.world.prints.len();
        ctrl.command(&command_point(3842, task.goal)).await?;
        tokio::time::sleep(Duration::from_millis(150)).await;
        client.set_impulse(217);
        client.pump(Duration::from_millis(400));

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
            ctrl.command("scratch1 3840").await?;
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
    let mut ctrl = MatchCtrl::default();
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
    let result = run_connected(&mut ctrl, suite, tasks).await;
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
                name: "a".into(),
                split: "train".into(),
                completed: true,
                game_sec: Some(4.0),
                wall_sec: 4.0,
            },
            TaskResult {
                name: "b".into(),
                split: "heldout".into(),
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
}
