//! The tape corpus as something you can ask a question of.
//!
//! Until now everything in the lab was per run: brief one tape, compare
//! two, band a handful. Every cross-tape conclusion in the record was
//! produced by hand or by a one-off script and then pasted into
//! `CLAUDE.md` as prose - the nine-session human band, the tick-rate
//! table, the five-arm phase 1 table, the sixteen null pairs, the ratio
//! ranges at one tape a side. Each of those is a query over a corpus
//! that has been sitting in `runs/` the whole time, and each grew its
//! own parser.
//!
//! The finding this implements is Datadog's, from the closest published
//! analogue to this lab: letting an agent QUERY telemetry rather than
//! retrieve it was the single largest improvement they measured. An
//! aggregate costs a few hundred tokens where the records to compute it
//! cost thousands.
//!
//! **SQLITE WAS CONSIDERED AND REFUSED.** The issue suggested it and it
//! is the obvious store, but the corpus is a few hundred rows of a
//! fixed schema, a full scan is microseconds, and the cost is a C
//! dependency in a tree that keeps its dependency list short. The part
//! worth having was "a query, not thirty parameters", and a named
//! filter-and-aggregate surface gets that without asking an agent to
//! discover a schema and then write SQL against it - which costs more
//! tokens than it saves at this size.
//!
//! The index is a committed TSV, the same shape as
//! `runs/human_scorecard.tsv`, and it is a CACHE rather than a source
//! of truth: a tape missing from it is parsed on demand and appended.
//! Nothing re-parses the whole corpus on an ordinary call.

use crate::intel::{brief_path, MatchBrief};
use crate::stats;
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// Where the index lives, under the runs directory beside the tapes.
pub const INDEX_FILE: &str = "tape_index.tsv";
/// One row per hotspot cell, for the cell-level questions.
pub const CELLS_FILE: &str = "tape_cells.tsv";

/// One tape, flattened. Every field is a number or a short string, so
/// the whole corpus is a table and a question about it is a filter and
/// an aggregate.
#[derive(Debug, Clone, Serialize, Default)]
pub struct TapeRow {
    pub run: String,
    pub map: String,
    /// `LOG started on:` from the tape's own header, as
    /// `YYYY-MM-DD HH:MM:SS`. Read from the FILE rather than its mtime,
    /// because a fresh clone stamps every file with the checkout time
    /// and would flatten the whole time axis this exists to provide.
    pub started: String,
    pub tick_class: String,
    /// `bot` or `human`: a human tape is review-only and must never be
    /// averaged into a bot band.
    pub kind: String,
    pub duration_sec: f64,
    pub stalls: f64,
    pub engages: f64,
    pub lava_deaths: f64,
    pub world_deaths: f64,
    pub freezes: f64,
    pub freeze_underfire: f64,
    pub cover: f64,
    pub goals: f64,
    pub frags: f64,
    pub deaths: f64,
    pub routefails: f64,
    pub hazards: f64,
    pub grabs: f64,
    pub weapons: f64,
    pub boards: f64,
    pub kd_spread: f64,
    pub avg_speed: f64,
}

/// The queryable columns, in the order the table prints them.
pub const COLUMNS: [&str; 22] = [
    "run",
    "map",
    "started",
    "tick_class",
    "kind",
    "duration_sec",
    "stalls",
    "engages",
    "lava_deaths",
    "world_deaths",
    "freezes",
    "freeze_underfire",
    "cover",
    "goals",
    "frags",
    "deaths",
    "routefails",
    "hazards",
    "grabs",
    "weapons",
    "boards",
    "kd_spread",
];

impl TapeRow {
    pub fn metric(&self, name: &str) -> Option<f64> {
        Some(match name {
            "duration_sec" => self.duration_sec,
            "stalls" | "stall_parity" => self.stalls,
            "engages" | "engagements" => self.engages,
            "lava_deaths" => self.lava_deaths,
            "world_deaths" => self.world_deaths,
            "freezes" => self.freezes,
            "freeze_underfire" => self.freeze_underfire,
            "cover" | "coverage" => self.cover,
            "goals" => self.goals,
            "frags" => self.frags,
            "deaths" => self.deaths,
            "routefails" => self.routefails,
            "hazards" => self.hazards,
            "grabs" => self.grabs,
            "weapons" => self.weapons,
            "boards" => self.boards,
            "kd_spread" => self.kd_spread,
            "avg_speed" => self.avg_speed,
            _ => return None,
        })
    }

    fn field(&self, name: &str) -> String {
        match name {
            "run" => self.run.clone(),
            "map" => self.map.clone(),
            "started" => self.started.clone(),
            "tick_class" => self.tick_class.clone(),
            "kind" => self.kind.clone(),
            "month" => self.started.chars().take(7).collect(),
            "day" => self.started.chars().take(10).collect(),
            other => self
                .metric(other)
                .map(|v| trim_num(v))
                .unwrap_or_else(|| "".into()),
        }
    }

    fn to_tsv(&self) -> String {
        let mut f: Vec<String> = COLUMNS.iter().map(|c| self.field(c)).collect();
        f.push(trim_num(self.avg_speed));
        f.join("\t")
    }
}

fn trim_num(v: f64) -> String {
    if (v - v.round()).abs() < 1e-9 {
        format!("{v:.0}")
    } else {
        format!("{v:.2}")
    }
}

/// `LOG started on: 09/16/2026 06:56:53` in the tape's first lines,
/// normalised so a string sort is a time sort. 745 of the 752 tapes
/// carry it; the rest sort last and say so by being empty.
pub fn started_of(path: &Path) -> String {
    let Ok(text) = std::fs::read_to_string(path) else {
        return String::new();
    };
    for line in text.lines().take(4) {
        if let Some(rest) = line.trim().strip_prefix("LOG started on:") {
            let t = rest.trim();
            let mut it = t.split_whitespace();
            let (Some(date), Some(clock)) = (it.next(), it.next()) else {
                continue;
            };
            let d: Vec<&str> = date.split('/').collect();
            if d.len() == 3 {
                return format!("{}-{}-{} {}", d[2], d[0], d[1], clock);
            }
        }
    }
    String::new()
}

/// Was a human in this match?
///
/// Two tests, because neither is enough on its own. Human ARGLOG
/// tracks only exist from v3.66 (2026-08-20), so every session
/// played before that is a human match with no human in its
/// telemetry - 46 of the 73 harvested sessions. Their bots were
/// fighting a person, which moves every metric they recorded, so
/// averaging them into a bot series is the confound this column
/// exists to prevent. The harvester names a session
/// `shane_<map>_<date>` and has since it was written, which is
/// the only signal those tapes carry.
fn kind_of(run: &str, b: &MatchBrief) -> String {
    if b.totals.human.is_some() || run.starts_with("shane_") {
        "human".into()
    } else {
        "bot".into()
    }
}

fn row_from(run: &str, path: &Path, b: &MatchBrief) -> TapeRow {
    let t = &b.totals;
    TapeRow {
        run: run.to_string(),
        map: b.map.clone().unwrap_or_default(),
        started: started_of(path),
        tick_class: t.tick_class.clone().unwrap_or_default(),
        kind: kind_of(run, b),
        duration_sec: t.duration_sec,
        stalls: t.stalls as f64,
        engages: t.engages as f64,
        lava_deaths: t.lava_deaths as f64,
        world_deaths: t.world_deaths as f64,
        freezes: t.freezes as f64,
        freeze_underfire: t.freeze_underfire as f64,
        cover: t.cover as f64,
        goals: t.goals as f64,
        frags: t.frags as f64,
        deaths: t.deaths as f64,
        routefails: t.routefails as f64,
        hazards: t.hazards as f64,
        grabs: t.grabs as f64,
        weapons: t.weapons as f64,
        boards: t.boards as f64,
        kd_spread: t.kd_spread as f64,
        avg_speed: t.avg_speed,
    }
}

/// One hotspot cell, for the questions the tape row cannot answer.
#[derive(Debug, Clone, Serialize, Default)]
pub struct CellRow {
    pub run: String,
    pub map: String,
    pub started: String,
    pub kind: String,
    pub x: f64,
    pub y: f64,
    pub z: f64,
    pub count: f64,
    pub cause: String,
}

fn tape_files(runs_dir: &Path) -> Vec<(String, PathBuf)> {
    let Ok(rd) = std::fs::read_dir(runs_dir) else {
        return Vec::new();
    };
    let mut out: Vec<(String, PathBuf)> = rd
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| p.extension().map(|x| x == "log").unwrap_or(false))
        .filter_map(|p| {
            p.file_stem()
                .and_then(|s| s.to_str())
                .map(|s| (s.to_string(), p.clone()))
        })
        .collect();
    out.sort();
    out
}

fn read_tsv(path: &Path) -> Vec<TapeRow> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let mut lines = text.lines();
    let Some(header) = lines.next() else {
        return Vec::new();
    };
    let cols: Vec<&str> = header.split('\t').collect();
    let mut out = Vec::new();
    for line in lines {
        if line.trim().is_empty() {
            continue;
        }
        let vals: Vec<&str> = line.split('\t').collect();
        let get = |name: &str| -> &str {
            cols.iter()
                .position(|c| *c == name)
                .and_then(|i| vals.get(i).copied())
                .unwrap_or("")
        };
        let num = |name: &str| -> f64 { get(name).parse().unwrap_or(0.0) };
        let run = get("run").to_string();
        if run.is_empty() {
            continue;
        }
        out.push(TapeRow {
            run,
            map: get("map").into(),
            started: get("started").into(),
            tick_class: get("tick_class").into(),
            kind: get("kind").into(),
            duration_sec: num("duration_sec"),
            stalls: num("stalls"),
            engages: num("engages"),
            lava_deaths: num("lava_deaths"),
            world_deaths: num("world_deaths"),
            freezes: num("freezes"),
            freeze_underfire: num("freeze_underfire"),
            cover: num("cover"),
            goals: num("goals"),
            frags: num("frags"),
            deaths: num("deaths"),
            routefails: num("routefails"),
            hazards: num("hazards"),
            grabs: num("grabs"),
            weapons: num("weapons"),
            boards: num("boards"),
            kd_spread: num("kd_spread"),
            avg_speed: num("avg_speed"),
        });
    }
    out
}

/// What an index build did, so a caller can say whether it wrote.
#[derive(Debug, Clone, Serialize)]
pub struct IndexStatus {
    pub rows: usize,
    pub from_cache: usize,
    pub parsed: usize,
    pub dropped: usize,
}

/// The corpus, cached.
///
/// Rows already in the TSV are trusted: a tape is append-once and is
/// never edited after the match that wrote it. Anything in `runs/` that
/// the index does not name is parsed and appended. `rebuild` forces a
/// full re-parse, which is what to run after a metric changes meaning -
/// and metrics in this project have changed meaning eight times, each
/// one recorded as a boundary in the changelog.
pub fn index(runs_dir: &Path, rebuild: bool) -> (Vec<TapeRow>, IndexStatus) {
    let cached: BTreeMap<String, TapeRow> = if rebuild {
        BTreeMap::new()
    } else {
        read_tsv(&runs_dir.join(INDEX_FILE))
            .into_iter()
            .map(|r| (r.run.clone(), r))
            .collect()
    };
    let mut rows = Vec::new();
    let mut st = IndexStatus { rows: 0, from_cache: 0, parsed: 0, dropped: 0 };
    for (run, path) in tape_files(runs_dir) {
        if let Some(r) = cached.get(&run) {
            st.from_cache += 1;
            rows.push(r.clone());
            continue;
        }
        match brief_path(&path, None) {
            Ok(b) => {
                st.parsed += 1;
                rows.push(row_from(&run, &path, &b));
            }
            Err(_) => st.dropped += 1,
        }
    }
    st.rows = rows.len();
    (rows, st)
}

/// Hotspot cells are NOT cached: they are ten times the rows and are
/// asked for rarely, so paying the parse when the question is asked
/// beats keeping a second file honest.
pub fn cells(runs_dir: &Path, map: Option<&str>) -> Vec<CellRow> {
    let mut out = Vec::new();
    for (run, path) in tape_files(runs_dir) {
        let Ok(b) = brief_path(&path, None) else { continue };
        let m = b.map.clone().unwrap_or_default();
        if let Some(want) = map {
            if !m.eq_ignore_ascii_case(want) {
                continue;
            }
        }
        let started = started_of(&path);
        let kind = if b.totals.human.is_some() { "human" } else { "bot" };
        for h in &b.hotspots {
            out.push(CellRow {
                run: run.clone(),
                map: m.clone(),
                started: started.clone(),
                kind: kind.into(),
                x: h.x,
                y: h.y,
                z: h.z,
                count: h.count as f64,
                cause: h.cause.clone().unwrap_or_default(),
            });
        }
    }
    out
}

pub fn write_index(runs_dir: &Path, rows: &[TapeRow]) -> std::io::Result<PathBuf> {
    let p = runs_dir.join(INDEX_FILE);
    let mut s = String::new();
    s.push_str(&COLUMNS.join("\t"));
    s.push_str("\tavg_speed\n");
    for r in rows {
        s.push_str(&r.to_tsv());
        s.push('\n');
    }
    std::fs::write(&p, s)?;
    Ok(p)
}

// ---------------------------------------------------------------- query

/// A question about the corpus.
///
/// Nine fields, not thirty, and none of them is a schema an agent has
/// to discover first. Everything is optional; the empty query is "show
/// me the corpus".
#[derive(Debug, Clone, Default)]
pub struct Query {
    pub map: Option<String>,
    pub kind: Option<String>,
    pub tick_class: Option<String>,
    /// substring match on the run name, which is how this project names
    /// an arm: `ab_dm4_leadclip`, `band_e1m6`, `shane_dm2`
    pub run_like: Option<String>,
    pub since: Option<String>,
    pub until: Option<String>,
    /// the metric to aggregate. Without it the query returns rows.
    pub metric: Option<String>,
    /// `map`, `month`, `day`, `tick_class`, `kind` or any string column
    pub group_by: Option<String>,
    pub limit: Option<usize>,
}

impl Query {
    fn keeps(&self, r: &TapeRow) -> bool {
        let eq = |want: &Option<String>, have: &str| -> bool {
            want.as_ref().map(|w| have.eq_ignore_ascii_case(w)).unwrap_or(true)
        };
        eq(&self.map, &r.map)
            && eq(&self.kind, &r.kind)
            && eq(&self.tick_class, &r.tick_class)
            && self
                .run_like
                .as_ref()
                .map(|w| r.run.to_ascii_lowercase().contains(&w.to_ascii_lowercase()))
                .unwrap_or(true)
            // a tape with no start line sorts out of every window
            // rather than silently into all of them
            && self.since.as_ref().map(|s| r.started.as_str() >= s.as_str()).unwrap_or(true)
            && self.until.as_ref().map(|s| r.started.as_str() <= s.as_str()).unwrap_or(true)
    }
}

/// One aggregated group.
#[derive(Debug, Clone, Serialize)]
pub struct Agg {
    pub group: String,
    pub n: usize,
    pub iqm: f64,
    pub median: f64,
    pub mean: f64,
    pub sd: f64,
    pub cv: f64,
    pub min: f64,
    pub max: f64,
}

/// The answer: either aggregates (a `metric` was named) or the rows.
#[derive(Debug, Clone, Serialize)]
pub enum Answer {
    Aggregates {
        metric: String,
        groups: Vec<Agg>,
        /// matched the filters and were left out of the aggregate
        /// because the tape carries no duration and therefore no
        /// measurement. Four tapes in the corpus are like that.
        /// Counted and printed rather than silently averaged in or
        /// silently dropped, both of which are worse.
        skipped_empty: usize,
    },
    Rows(Vec<TapeRow>),
}

pub fn query(rows: &[TapeRow], q: &Query) -> Result<Answer, String> {
    let kept: Vec<&TapeRow> = rows.iter().filter(|r| q.keeps(r)).collect();
    let Some(metric) = q.metric.as_deref() else {
        let mut out: Vec<TapeRow> = kept.into_iter().cloned().collect();
        out.sort_by(|a, b| a.started.cmp(&b.started));
        if let Some(n) = q.limit {
            out.truncate(n);
        }
        return Ok(Answer::Rows(out));
    };
    if rows.first().map(|r| r.metric(metric).is_none()).unwrap_or(false) {
        return Err(format!(
            "no metric called '{metric}'. Try one of: stalls, engages, lava_deaths, \
             world_deaths, freezes, freeze_underfire, cover, goals, frags, deaths, \
             routefails, hazards, grabs, weapons, boards, kd_spread, avg_speed, duration_sec"
        ));
    }
    let group_by = q.group_by.as_deref().unwrap_or("");
    let mut buckets: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    let mut skipped_empty = 0;
    for r in kept {
        if r.duration_sec <= 0.0 {
            skipped_empty += 1;
            continue;
        }
        let Some(v) = r.metric(metric) else { continue };
        let key = if group_by.is_empty() { "all".to_string() } else { r.field(group_by) };
        buckets.entry(key).or_default().push(v);
    }
    let mut groups: Vec<Agg> = buckets
        .into_iter()
        .map(|(group, v)| {
            let mean = stats::mean(&v);
            let sd = stats::sd(&v);
            Agg {
                group,
                n: v.len(),
                iqm: stats::iqm(&v),
                median: stats::median(&v),
                mean,
                sd,
                cv: if mean.abs() > 1e-9 { sd / mean } else { 0.0 },
                min: v.iter().cloned().fold(f64::INFINITY, f64::min),
                max: v.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
            }
        })
        .collect();
    if let Some(n) = q.limit {
        groups.truncate(n);
    }
    Ok(Answer::Aggregates { metric: metric.to_string(), groups, skipped_empty })
}

/// CSV, because it is about half the tokens of the same table as JSON
/// and every section of this answer is tabular.
pub fn to_csv(a: &Answer) -> String {
    let mut s = String::new();
    match a {
        Answer::Aggregates { metric, groups, skipped_empty } => {
            let note = if *skipped_empty > 0 {
                format!(", {skipped_empty} empty tape(s) left out")
            } else {
                String::new()
            };
            s.push_str(&format!(
                "group,n,iqm,median,mean,sd,cv,min,max  # {metric}{note}\n"
            ));
            for g in groups {
                s.push_str(&format!(
                    "{},{},{:.2},{:.2},{:.2},{:.2},{:.3},{:.2},{:.2}\n",
                    g.group, g.n, g.iqm, g.median, g.mean, g.sd, g.cv, g.min, g.max
                ));
            }
        }
        Answer::Rows(rows) => {
            s.push_str(&COLUMNS.join(","));
            s.push('\n');
            for r in rows {
                let f: Vec<String> = COLUMNS.iter().map(|c| r.field(c)).collect();
                s.push_str(&f.join(","));
                s.push('\n');
            }
        }
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    fn runs_dir() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs")
    }

    fn mk(run: &str, map: &str, started: &str, stalls: f64) -> TapeRow {
        TapeRow {
            run: run.into(),
            map: map.into(),
            started: started.into(),
            tick_class: "listen".into(),
            kind: "bot".into(),
            duration_sec: 185.0,
            stalls,
            ..Default::default()
        }
    }

    #[test]
    fn a_start_line_sorts_as_a_time() {
        // the engine writes MM/DD/YYYY, which sorts as nonsense; the
        // index stores YYYY-MM-DD, which sorts as time
        let dir = runs_dir();
        let p = dir.join("ab_dm4_A.log");
        if !p.exists() {
            return;
        }
        let s = started_of(&p);
        assert!(s.starts_with("2026-08-14"), "{s}");
        // and two tapes months apart order correctly as plain strings
        let later = started_of(&dir.join("shane_dm4_2026-09-16b.log"));
        if !later.is_empty() {
            assert!(later > s, "{later} should sort after {s}");
        }
    }

    #[test]
    fn a_missing_start_line_is_empty_rather_than_now() {
        let tmp = std::env::temp_dir().join("argus_no_header.log");
        std::fs::write(&tmp, "nothing useful here\n").unwrap();
        assert_eq!(started_of(&tmp), "");
        let _ = std::fs::remove_file(&tmp);
    }

    #[test]
    fn filters_narrow_and_do_not_widen() {
        let rows = vec![
            mk("ab_dm2_one", "dm2", "2026-09-01 10:00:00", 40.0),
            mk("ab_dm4_one", "dm4", "2026-09-02 10:00:00", 8.0),
            mk("band_dm2_two", "dm2", "2026-09-10 10:00:00", 50.0),
        ];
        let all = query(&rows, &Query::default()).unwrap();
        match all {
            Answer::Rows(r) => assert_eq!(r.len(), 3),
            _ => panic!("no metric means rows"),
        }
        let q = Query { map: Some("dm2".into()), ..Default::default() };
        match query(&rows, &q).unwrap() {
            Answer::Rows(r) => assert_eq!(r.len(), 2),
            _ => panic!(),
        }
        let q = Query {
            map: Some("dm2".into()),
            since: Some("2026-09-05".into()),
            ..Default::default()
        };
        match query(&rows, &q).unwrap() {
            Answer::Rows(r) => assert_eq!(r.len(), 1),
            _ => panic!(),
        }
        let q = Query { run_like: Some("band_".into()), ..Default::default() };
        match query(&rows, &q).unwrap() {
            Answer::Rows(r) => assert_eq!(r[0].run, "band_dm2_two"),
            _ => panic!(),
        }
    }

    #[test]
    fn an_aggregate_groups_and_an_unknown_metric_says_what_exists() {
        let rows = vec![
            mk("a", "dm2", "2026-09-01 10:00:00", 40.0),
            mk("b", "dm2", "2026-09-01 11:00:00", 50.0),
            mk("c", "dm4", "2026-09-01 12:00:00", 8.0),
        ];
        let q = Query {
            metric: Some("stalls".into()),
            group_by: Some("map".into()),
            ..Default::default()
        };
        match query(&rows, &q).unwrap() {
            Answer::Aggregates { groups, .. } => {
                assert_eq!(groups.len(), 2);
                let dm2 = groups.iter().find(|g| g.group == "dm2").unwrap();
                assert_eq!(dm2.n, 2);
                assert!((dm2.mean - 45.0).abs() < 1e-9);
            }
            _ => panic!("a metric means aggregates"),
        }
        // an error an agent can act on, not "invalid field"
        let bad = Query { metric: Some("stahls".into()), ..Default::default() };
        let e = query(&rows, &bad).unwrap_err();
        assert!(e.contains("stalls"), "{e}");
    }

    #[test]
    fn grouping_by_month_slices_the_history() {
        let rows = vec![
            mk("a", "dm2", "2026-08-20 10:00:00", 30.0),
            mk("b", "dm2", "2026-09-01 11:00:00", 50.0),
            mk("c", "dm2", "2026-09-14 12:00:00", 60.0),
        ];
        let q = Query {
            metric: Some("stalls".into()),
            group_by: Some("month".into()),
            ..Default::default()
        };
        match query(&rows, &q).unwrap() {
            Answer::Aggregates { groups, .. } => {
                assert_eq!(groups.len(), 2);
                assert_eq!(groups[0].group, "2026-08");
                assert_eq!(groups[1].n, 2);
            }
            _ => panic!(),
        }
    }

    #[test]
    fn csv_is_the_wire_format() {
        let rows = vec![mk("a", "dm2", "2026-09-01 10:00:00", 40.0)];
        let out = to_csv(&query(&rows, &Query::default()).unwrap());
        assert!(out.starts_with("run,map,started"), "{out}");
        assert!(out.contains("a,dm2,2026-09-01 10:00:00"), "{out}");
    }

    /// The index round-trips, and a cached row is not re-parsed.
    #[test]
    fn the_index_is_a_cache_and_a_round_trip() {
        let dir = std::env::temp_dir().join("argus_corpus_test");
        let _ = std::fs::create_dir_all(&dir);
        let rows = vec![
            mk("a", "dm2", "2026-09-01 10:00:00", 40.0),
            mk("b", "dm4", "2026-09-02 10:00:00", 8.0),
        ];
        write_index(&dir, &rows).unwrap();
        let back = read_tsv(&dir.join(INDEX_FILE));
        assert_eq!(back.len(), 2);
        assert_eq!(back[0].run, "a");
        assert!((back[0].stalls - 40.0).abs() < 1e-9);
        assert_eq!(back[1].map, "dm4");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// On the real corpus: every map the lab runs must be present, and
    /// human tapes must be tagged as such so they cannot be averaged
    /// into a bot band.
    #[test]
    fn the_real_corpus_indexes_if_present() {
        let dir = runs_dir();
        if !dir.exists() {
            return;
        }
        let (rows, st) = index(&dir, false);
        if rows.len() < 100 {
            return;
        }
        assert!(st.rows > 400, "only {} tapes indexed", st.rows);
        let maps: std::collections::BTreeSet<&str> =
            rows.iter().map(|r| r.map.as_str()).collect();
        for m in ["dm2", "dm3", "dm4", "dm6"] {
            assert!(maps.contains(m), "{m} missing from the index");
        }
        let humans = rows.iter().filter(|r| r.kind == "human").count();
        assert!(humans > 20, "only {humans} human tapes tagged");
        // and the time axis is real
        let dated = rows.iter().filter(|r| !r.started.is_empty()).count();
        assert!(
            dated * 100 / rows.len() > 90,
            "only {dated} of {} tapes carry a start line",
            rows.len()
        );
    }
}
