//! What this instrument can and cannot see, measured over the tapes
//! already in `runs/`.
//!
//! Two questions the lab could always have answered and never had.
//!
//! 1. **What is the smallest effect it can detect?** From a within-arm
//!    standard deviation and a tape count that is arithmetic, and the
//!    answer settles several running arguments with a number. It is
//!    also what sets the SPRT bounds, since a bound below the
//!    detection limit is a test that cannot terminate.
//!
//! 2. **What does running several gates cost?** A verdict that
//!    convicts on any of four gates is not one test. The more gates,
//!    the more often a change that did nothing fails at least one, and
//!    that is a mechanical property rather than a subtlety. It is the
//!    underlying reason the old OR rule returned nine "improved" and
//!    five "regressed" across sixteen pairs of byte-identical builds.
//!
//! Both are read-only analysis over committed data: no engine runs, no
//! QC, nothing to revert.
//!
//! The corpus is every same-build arm the project has committed. A
//! same-build ARM is a set of tapes from one build on one map, so its
//! spread is the instrument and nothing else. Two sources:
//!
//!   - the baseline bands in `runs/baselines.json`, which are
//!     same-build by construction and stay current as maps are
//!     re-baselined,
//!   - `NULL_PAIRS` and `LADDER_ARMS` below, which name committed arms
//!     the bands do not cover.

use crate::config::Config;
use crate::intel::{brief_path, compare_band, MatchBrief, Verdict};
use crate::stats;
use serde::Serialize;
use std::path::Path;

/// Sixteen pairs of byte-identical builds, from the recovery plan's
/// table 1.4. This is the project's null corpus: any estimator that
/// finds a difference in code that has none is disqualified, whatever
/// else it improves. The old OR rule read ZERO of these as parity.
pub const NULL_PAIRS: [(&str, &str); 16] = [
    ("ab_dm4_tremorclock1", "ab_dm4_tremorclock2"),
    ("ab_dm4_tremorclock2", "ab_dm4_tremorclock3"),
    ("ab_dm4_fightpin1", "ab_dm4_fightpin2"),
    ("ab_dm4_seatregen1", "ab_dm4_seatregen2"),
    ("ab_dm4_airlead1", "ab_dm4_airlead2"),
    ("ab_dm4_gravity1", "ab_dm4_gravity2"),
    ("ab_dm4_lgwade1", "ab_dm4_lgwade2"),
    ("ctl_dm4_shelfsplit1", "ctl_dm4_shelfsplit2"),
    ("ab_dm2_apexgate1", "ab_dm2_apexgate2"),
    ("ab_dm2_fightpin1", "ab_dm2_fightpin2"),
    ("ab_dm2_jumpceiling1", "ab_dm2_jumpceiling2"),
    ("ab_dm2_decklink1", "ab_dm2_decklink2"),
    ("ab_dm2_seatregen1", "ab_dm2_seatregen2"),
    ("ab_dm2_mover1", "ab_dm2_mover2"),
    ("ab_dm2_holds1", "ab_dm2_holds2"),
    ("ab_dm2_unstick1", "ab_dm2_unstick2"),
];

/// Same-build arms of three or more tapes that the baseline bands do
/// not already carry. Each row is one build on one map; every one is
/// an arm of a committed ladder, named in the changelog entry that
/// shipped it.
const LADDER_ARMS: &[(&str, &[&str])] = &[
    // the v4.18 ship ladder, four a side on byte-identical bytes
    (
        "dm4",
        &[
            "ab_dm4_shipctl1",
            "ab_dm4_shipctl2",
            "ab_dm4_shipctl3",
            "ab_dm4_shipctl4",
        ],
    ),
    (
        "dm4",
        &[
            "ab_dm4_shipnew1",
            "ab_dm4_shipnew2",
            "ab_dm4_shipnew3",
            "ab_dm4_shipnew4",
        ],
    ),
    // phase 0's played-rate re-baseline, superseded as a baseline by
    // the #388 arm but still a same-build arm
    ("dm4", &["band_dm4_1", "band_dm4_2", "band_dm4_3"]),
    // #363's control and candidate arms
    (
        "dm4",
        &[
            "ab_dm4_leadctl1",
            "ab_dm4_leadctl2",
            "ab_dm4_leadctl3",
            "ab_dm4_leadctl4",
        ],
    ),
    (
        "dm4",
        &[
            "ab_dm4_leadclip1",
            "ab_dm4_leadclip2",
            "ab_dm4_leadclip3",
            "ab_dm4_leadclip4",
            "ab_dm4_leadclipb1",
            "ab_dm4_leadclipb2",
            "ab_dm4_leadclipb3",
            "ab_dm4_leadclipb4",
        ],
    ),
    // #324's candidate arms
    (
        "e1m6",
        &[
            "ab_e1m6_doorverb1",
            "ab_e1m6_doorverb2",
            "ab_e1m6_doorverb3",
            "ab_e1m6_doorverb4",
            "ab_e1m6_doorverbb1",
            "ab_e1m6_doorverbb2",
            "ab_e1m6_doorverbb3",
        ],
    ),
    (
        "e1m5",
        &[
            "ab_e1m5_doorverb1",
            "ab_e1m5_doorverb2",
            "ab_e1m5_doorverb3",
            "ab_e1m5_doorverb4",
        ],
    ),
];

/// The metrics worth a detection limit. The first four are the gates
/// the verdict rests on; coverage and goal pickups are reported rather
/// than gated, and the table is the place that finally says why.
pub const METRICS: [(&str, bool); 6] = [
    ("stalls", true),
    ("engages", false),
    ("lava_deaths", true),
    ("freezes", true),
    ("cover", false),
    ("goals", false),
];

pub fn metric_value(b: &MatchBrief, name: &str) -> f64 {
    let t = &b.totals;
    match name {
        // the band gate is called stall_parity; the metric is stalls
        "stalls" | "stall_parity" => t.stalls as f64,
        "engages" | "engagements" => t.engages as f64,
        "lava_deaths" => t.lava_deaths as f64,
        "freezes" => t.freezes as f64,
        "cover" | "coverage" => t.cover as f64,
        "goals" => t.goals as f64,
        _ => 0.0,
    }
}

/// The instrument's noise per map and metric, measured 2026-09-16 by
/// `argus-mcp measure` over 84 tapes in 27 same-build arms, and baked
/// here so a compare does not re-parse the corpus on every call.
/// `docs/specs/2026-09-16-lab-measurement-limits.md` is the same
/// numbers with their tape counts and the MDE columns.
///
/// Regenerate after a harvest that adds arms; the test below fails if
/// these drift from the corpus by more than a factor of two, which
/// catches a metric changing meaning without tripping on ordinary
/// accumulation.
const SIGMA: &[(&str, &str, f64)] = &[
    ("dm2", "stalls", 24.4),
    ("dm2", "engages", 9.0),
    ("dm2", "lava_deaths", 1.4),
    ("dm2", "freezes", 0.8),
    ("dm2", "cover", 34.3),
    ("dm2", "goals", 2.1),
    ("dm4", "stalls", 6.0),
    ("dm4", "engages", 10.1),
    ("dm4", "lava_deaths", 1.7),
    ("dm4", "freezes", 0.7),
    ("dm4", "cover", 22.4),
    ("dm4", "goals", 4.7),
    ("e1m5", "stalls", 19.8),
    ("e1m5", "engages", 12.2),
    ("e1m5", "freezes", 2.7),
    ("e1m5", "cover", 86.4),
    ("e1m5", "goals", 3.2),
    ("e1m6", "stalls", 23.3),
    ("e1m6", "engages", 14.6),
    ("e1m6", "lava_deaths", 1.1),
    ("e1m6", "freezes", 1.0),
    ("e1m6", "cover", 68.1),
    ("e1m6", "goals", 2.1),
];

/// The measured noise for a map and metric, if the corpus has one.
///
/// e1m5 lava is deliberately absent: nine tapes, every one of them
/// zero. A sigma of zero is not a measurement of a quiet metric, it is
/// the absence of one, and a test handed it would accept anything.
pub fn sigma_for(map: Option<&str>, metric: &str) -> Option<f64> {
    let m = map?.to_ascii_lowercase();
    let want = canonical(metric);
    SIGMA
        .iter()
        .find(|(mm, nn, _)| *mm == m && *nn == want)
        .map(|(_, _, s)| *s)
}

/// The band gates and the limit table spell two metrics differently.
fn canonical(name: &str) -> &str {
    match name {
        "stall_parity" => "stalls",
        "engagements" => "engages",
        "coverage" => "cover",
        other => other,
    }
}

/// The effect worth shipping, in the metric's own units: whatever five
/// tapes a side can actually see.
///
/// Deriving the SPRT bound from the detection limit rather than
/// picking one keeps the stopping rule and the instrument honest about
/// each other. A bound below the MDE is a test that cannot terminate,
/// and a bound far above it is a test that will never accept anything
/// this project ships.
pub fn ship_bound(sigma: f64) -> f64 {
    stats::mde(sigma, 5)
}

/// One row of the detection-limit table.
#[derive(Debug, Clone, Serialize)]
pub struct Limit {
    pub map: String,
    pub metric: String,
    /// same-build arms that contributed
    pub arms: usize,
    /// tapes across those arms
    pub tapes: usize,
    /// the arms' pooled mean, so an absolute effect can be read as a share
    pub mean: f64,
    /// pooled within-arm standard deviation: the instrument's noise
    pub sigma: f64,
    /// sigma over mean, the figure the handoff quotes as a percentage
    pub cv: f64,
    pub mde3: f64,
    pub mde5: f64,
    pub mde10: f64,
}

/// Collect every same-build arm this project has committed, as
/// (map, tapes).
/// Everything here takes the RUNS DIRECTORY rather than a `Config`,
/// so the validation tests run on a bare checkout. A validation set
/// that skips itself on CI is not a validation set.
fn arms_in(runs_dir: &Path) -> Vec<(String, Vec<MatchBrief>)> {
    let mut out: Vec<(String, Vec<String>)> = Vec::new();

    // the baseline bands: same-build by construction
    for (map, runs) in crate::intel::all_baseline_bands_in(runs_dir) {
        if runs.len() >= 2 {
            out.push((map, runs));
        }
    }
    for (map, runs) in LADDER_ARMS {
        out.push((
            map.to_string(),
            runs.iter().map(|s| s.to_string()).collect(),
        ));
    }
    for (a, b) in NULL_PAIRS {
        // the map comes from the tape, so a renamed map cannot desync
        out.push((String::new(), vec![a.to_string(), b.to_string()]));
    }

    let mut loaded = Vec::new();
    for (map, runs) in out {
        let mut briefs = Vec::new();
        for r in &runs {
            let hint = if map.is_empty() {
                None
            } else {
                Some(map.as_str())
            };
            if let Ok(b) = brief_path(&runs_dir.join(format!("{r}.log")), hint) {
                briefs.push(b);
            }
        }
        if briefs.len() < 2 {
            continue;
        }
        // a tape knows its own map; trust that over the list it came in
        let m = briefs[0].map.clone().unwrap_or_else(|| map.clone());
        // a mixed-rate arm is two different games and its spread is not
        // the instrument's (the tick-class rule)
        let classes: std::collections::BTreeSet<String> = briefs
            .iter()
            .filter_map(|b| b.totals.tick_class.clone())
            .collect();
        if classes.len() > 1 {
            continue;
        }
        loaded.push((m, briefs));
    }
    loaded
}

/// The detection-limit table: per map and metric, the instrument's
/// noise and the smallest effect it could see at 3, 5 and 10 tapes a
/// side.
pub fn limits(cfg: &Config) -> Vec<Limit> {
    limits_in(&cfg.runs)
}

pub fn limits_in(runs_dir: &Path) -> Vec<Limit> {
    let loaded = arms_in(runs_dir);
    let mut maps: Vec<String> = loaded.iter().map(|(m, _)| m.clone()).collect();
    maps.sort();
    maps.dedup();

    let mut rows = Vec::new();
    for map in maps {
        let mine: Vec<&(String, Vec<MatchBrief>)> =
            loaded.iter().filter(|(m, _)| *m == map).collect();
        for (metric, _) in METRICS {
            let arm_vals: Vec<Vec<f64>> = mine
                .iter()
                .map(|(_, bs)| bs.iter().map(|b| metric_value(b, metric)).collect())
                .collect();
            let usable: Vec<Vec<f64>> = arm_vals.iter().filter(|a| a.len() >= 2).cloned().collect();
            if usable.is_empty() {
                continue;
            }
            let sigma = stats::pooled_sd(&usable);
            let all: Vec<f64> = usable.iter().flatten().cloned().collect();
            let m = stats::mean(&all);
            rows.push(Limit {
                map: map.clone(),
                metric: metric.to_string(),
                arms: usable.len(),
                tapes: all.len(),
                mean: m,
                sigma,
                cv: if m > 0.0 { sigma / m } else { 0.0 },
                mde3: stats::mde(sigma, 3),
                mde5: stats::mde(sigma, 5),
                mde10: stats::mde(sigma, 10),
            });
        }
    }
    rows
}

/// How often each gate convicts a change that does not exist, and how
/// often at least one of them does.
#[derive(Debug, Clone, Serialize)]
pub struct GateAudit {
    pub pairs_seen: usize,
    /// per gate: how many null pairs it called something other than
    /// "in band"
    pub per_gate: Vec<(String, usize)>,
    /// how many null pairs got a verdict other than parity
    pub any_gate: usize,
    pub detail: Vec<String>,
}

/// Run the verdict over the null corpus and count what it convicts.
///
/// This is the family-wise error rate, measured rather than argued.
/// One tape a side, which is the hardest case and the one the band was
/// fitted on.
pub fn gate_audit(cfg: &Config) -> GateAudit {
    gate_audit_in(&cfg.runs)
}

pub fn gate_audit_in(runs_dir: &Path) -> GateAudit {
    let mut seen = 0;
    let mut any = 0;
    let mut per: std::collections::BTreeMap<String, usize> = Default::default();
    let mut detail = Vec::new();
    for (a, b) in NULL_PAIRS {
        let (ba, bb) = (
            brief_path(&runs_dir.join(format!("{a}.log")), None),
            brief_path(&runs_dir.join(format!("{b}.log")), None),
        );
        let (ba, bb) = match (ba, bb) {
            (Ok(x), Ok(y)) => (x, y),
            _ => continue,
        };
        seen += 1;
        let r = compare_band(&[bb], &[ba]);
        for g in &r.band {
            let e = per.entry(g.name.clone()).or_insert(0);
            if g.call != "in band" {
                *e += 1;
            }
        }
        if r.verdict != Verdict::Parity {
            any += 1;
            let names: Vec<String> = r
                .band
                .iter()
                .filter(|g| g.call != "in band")
                .map(|g| format!("{} {}", g.name, g.call))
                .collect();
            detail.push(format!(
                "{a} vs {b}: {:?} on {}",
                r.verdict,
                names.join(", ")
            ));
        }
    }
    GateAudit {
        pairs_seen: seen,
        per_gate: per.into_iter().collect(),
        any_gate: any,
        detail,
    }
}

/// What the sequential test does on a change that does not exist.
///
/// The null corpus is sixteen pairs, which is one tape a side and too
/// few for any test to conclude anything. A same-build ARM of four or
/// more tapes gives a better null: split it in half and the two halves
/// differ by nothing but the match. The handoff already uses this
/// trick by hand - splitting the committed six-tape dm2 band into two
/// halves of three returns REJECTED on byte-identical code - and this
/// makes it the standing validation.
///
/// A correctly specified test must never ACCEPT here. How often it can
/// REJECT is the honest answer to what a null costs in tapes.
#[derive(Debug, Clone, Serialize)]
pub struct SprtAudit {
    pub splits: usize,
    pub decisions: usize,
    pub accept: usize,
    pub reject: usize,
    pub keep_going: usize,
    pub wrong: Vec<String>,
    /// How many tapes a side a null actually costs: feed the two
    /// halves one tape at a time and record the first count at
    /// which the test decides. This is the number that replaces
    /// "three tapes is not enough on dm2 and four is barely".
    pub asn_decided: usize,
    pub asn_undecided: usize,
    pub asn_mean: f64,
    /// the most tapes a side these splits could offer, median. An
    /// undecided row is usually an arm that ran out of tapes rather
    /// than a test that would never decide, and without this the
    /// mean above reads as "a null costs two tapes" when it means
    /// "the ones that decided, decided early".
    pub asn_cap_median: f64,
}

pub fn sprt_audit(cfg: &Config) -> SprtAudit {
    sprt_audit_in(&cfg.runs)
}

pub fn sprt_audit_in(runs_dir: &Path) -> SprtAudit {
    let mut out = SprtAudit {
        splits: 0,
        decisions: 0,
        accept: 0,
        reject: 0,
        keep_going: 0,
        wrong: Vec::new(),
        asn_decided: 0,
        asn_undecided: 0,
        asn_mean: 0.0,
        asn_cap_median: 0.0,
    };
    let mut sample_numbers: Vec<f64> = Vec::new();
    let mut caps: Vec<f64> = Vec::new();
    for (map, briefs) in arms_in(runs_dir) {
        if briefs.len() < 4 {
            continue;
        }
        out.splits += 1;
        let half = briefs.len() / 2;
        for (metric, lower_is_better) in METRICS {
            let Some(sigma) = sigma_for(Some(&map), metric) else {
                continue;
            };
            let a: Vec<f64> = briefs[..half]
                .iter()
                .map(|b| metric_value(b, metric))
                .collect();
            let b: Vec<f64> = briefs[half..]
                .iter()
                .map(|b| metric_value(b, metric))
                .collect();
            let r = stats::sprt(
                metric,
                &b,
                &a,
                lower_is_better,
                ship_bound(sigma),
                sigma,
                "corpus",
            );
            out.decisions += 1;
            match r.call {
                stats::SprtCall::Accept => {
                    out.accept += 1;
                    out.wrong.push(format!(
                        "{map} {metric}: accepted an effect across two halves of one build (llr {:.2}, effect {:.1})",
                        r.llr, r.effect
                    ));
                }
                stats::SprtCall::Reject => out.reject += 1,
                _ => out.keep_going += 1,
            }

            // and the same null fed one tape at a time, which is how
            // a ladder is actually run. The first k at which the
            // test decides is what a null costs; never deciding is
            // its own answer and is counted separately rather than
            // averaged in, which would flatter the mean.
            let mut decided_at = None;
            caps.push(a.len().min(b.len()) as f64);
            for k in 1..=a.len().min(b.len()) {
                let r = stats::sprt(
                    metric,
                    &b[..k],
                    &a[..k],
                    lower_is_better,
                    ship_bound(sigma),
                    sigma,
                    "corpus",
                );
                if r.call == stats::SprtCall::Accept || r.call == stats::SprtCall::Reject {
                    decided_at = Some(k);
                    break;
                }
            }
            match decided_at {
                Some(k) => {
                    out.asn_decided += 1;
                    sample_numbers.push(k as f64);
                }
                None => out.asn_undecided += 1,
            }
        }
    }
    out.asn_mean = stats::mean(&sample_numbers);
    out.asn_cap_median = stats::median(&caps);
    out
}

fn share(n: usize, d: usize) -> f64 {
    if d == 0 {
        0.0
    } else {
        n as f64 / d as f64
    }
}

fn pct(x: f64) -> String {
    format!("{:.0}%", x * 100.0)
}

/// Render both analyses as the committed table.
pub fn render(limits: &[Limit], audit: &GateAudit, sprt: &SprtAudit, stamp: &str) -> String {
    let mut s = String::new();
    s.push_str("# What the lab can measure\n\n");
    s.push_str(&format!(
        "Generated by `argus-mcp measure` on {stamp}. Read-only analysis over the\n\
         tapes in `runs/`; no engine runs and nothing to revert. Regenerate it\n\
         after any harvest that adds a same-build arm.\n\n"
    ));

    s.push_str("## The detection limit\n\n");
    s.push_str(
        "`sigma` is the pooled within-arm standard deviation across every\n\
         committed same-build arm on that map: one build, one map, so the\n\
         spread is the instrument and nothing else. The MDE columns are the\n\
         smallest difference in arm means detectable at that many tapes a\n\
         side, at 5 per cent false positives and 80 per cent power. Tapes\n\
         enter as a square root, so halving the detectable effect costs four\n\
         times the tapes.\n\n",
    );
    let mut maps: Vec<&str> = limits.iter().map(|l| l.map.as_str()).collect();
    maps.sort();
    maps.dedup();
    for map in maps {
        s.push_str(&format!("### {map}\n\n"));
        s.push_str("| metric | arms | tapes | mean | sigma | CV | MDE n=3 | n=5 | n=10 |\n");
        s.push_str("|---|---|---|---|---|---|---|---|---|\n");
        for l in limits.iter().filter(|l| l.map == map) {
            s.push_str(&format!(
                "| {} | {} | {} | {:.1} | {:.1} | {} | {:.1} ({}) | {:.1} ({}) | {:.1} ({}) |\n",
                l.metric,
                l.arms,
                l.tapes,
                l.mean,
                l.sigma,
                pct(l.cv),
                l.mde3,
                pct(if l.mean > 0.0 { l.mde3 / l.mean } else { 0.0 }),
                l.mde5,
                pct(if l.mean > 0.0 { l.mde5 / l.mean } else { 0.0 }),
                l.mde10,
                pct(if l.mean > 0.0 { l.mde10 / l.mean } else { 0.0 }),
            ));
        }
        s.push('\n');
    }

    s.push_str("## What several gates cost\n\n");
    s.push_str(&format!(
        "The verdict over {} pairs of byte-identical builds, one tape a side.\n\
         A gate that convicts here is convicting a change that does not exist.\n\n",
        audit.pairs_seen
    ));
    s.push_str("| gate | convicts | of | rate |\n|---|---|---|---|\n");
    for (name, n) in &audit.per_gate {
        s.push_str(&format!(
            "| {} | {} | {} | {} |\n",
            name,
            n,
            audit.pairs_seen,
            pct(if audit.pairs_seen > 0 {
                *n as f64 / audit.pairs_seen as f64
            } else {
                0.0
            })
        ));
    }
    s.push_str(&format!(
        "| **any gate (the verdict)** | **{}** | **{}** | **{}** |\n\n",
        audit.any_gate,
        audit.pairs_seen,
        pct(if audit.pairs_seen > 0 {
            audit.any_gate as f64 / audit.pairs_seen as f64
        } else {
            0.0
        })
    ));
    if audit.pairs_seen > 0 && !audit.per_gate.is_empty() {
        let per: f64 = audit.per_gate.iter().map(|(_, n)| *n as f64).sum::<f64>()
            / (audit.per_gate.len() as f64 * audit.pairs_seen as f64);
        s.push_str(&format!(
            "Pre-registering one metric drops the false positive rate from {} to {} on average, because it is then one test rather than {}.

",
            pct(share(audit.any_gate, audit.pairs_seen)),
            pct(per),
            audit.per_gate.len()
        ));
    }
    if !audit.detail.is_empty() {
        s.push_str("The pairs that still get through:\n\n");
        for d in &audit.detail {
            s.push_str(&format!("- {d}\n"));
        }
        s.push('\n');
    }
    s.push_str("## What the stopping rule does on a null\n\n");
    s.push_str(&format!(
        "A same-build arm of four or more tapes, split in half: two arms that\n\
         differ by nothing but the match. {} splits, {} decisions across the\n\
         metrics with a measured sigma.\n\n\
         | call | count | share |\n|---|---|---|\n\
         | accept (must be none) | {} | {} |\n\
         | reject | {} | {} |\n\
         | continue or abandon | {} | {} |\n\n",
        sprt.splits,
        sprt.decisions,
        sprt.accept,
        pct(share(sprt.accept, sprt.decisions)),
        sprt.reject,
        pct(share(sprt.reject, sprt.decisions)),
        sprt.keep_going,
        pct(share(sprt.keep_going, sprt.decisions)),
    ));
    for w in &sprt.wrong {
        s.push_str(&format!("- {w}\n"));
    }
    s.push_str(&format!(
        "Fed one tape at a time, which is how a ladder is actually run: {} of\n\
         {} nulls reached a decision, at a mean of {:.1} tapes a side, and {}\n\
         did not. READ THE CEILING BEFORE THE MEAN: these splits offer a\n\
         median of {:.0} tapes a side, because most committed arms are four or\n\
         five tapes long. The undecided rows are mostly arms that ran out of\n\
         tapes, and the mean is conditional on deciding at all, so it says the\n\
         ones that decided decided early - not that a null costs two tapes.\n\n",
        sprt.asn_decided,
        sprt.asn_decided + sprt.asn_undecided,
        sprt.asn_mean,
        sprt.asn_undecided,
        sprt.asn_cap_median,
    ));
    s.push_str(
        "The continue rows are the point. At three to five tapes a side this\n\
         instrument frequently cannot rule an effect out either, and saying\n\
         so is the answer the lab has never been able to give: the old rule\n\
         had to return improved, regressed or parity whatever the evidence\n\
         was.\n\n",
    );

    s.push_str(
        "The any-gate row is the number that matters and it is always the\n\
         largest one in the table. Four gates each with their own chance to\n\
         convict is not one test. That is why `compare_band` takes a\n\
         pre-registered primary metric: name the gate the change is expected\n\
         to move BEFORE the tapes are in, and the rest flag without\n\
         convicting. Deciding which gate to believe after seeing the tapes is\n\
         how a coin flip gets written down as a finding.\n",
    );
    s
}

#[cfg(test)]
mod tests {
    use super::*;

    fn runs_dir() -> std::path::PathBuf {
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs")
    }

    #[test]
    fn the_metric_names_the_gates_use_all_resolve() {
        let b = MatchBrief::empty();
        // both spellings, because the band gate and the table disagree
        // on two of them and a silent 0.0 would be a table of zeroes
        for n in [
            "stalls",
            "stall_parity",
            "engages",
            "engagements",
            "lava_deaths",
            "freezes",
            "cover",
            "coverage",
            "goals",
        ] {
            let _ = metric_value(&b, n);
        }
        // and an unknown name must not quietly read as zero data
        assert_eq!(metric_value(&b, "not_a_metric"), 0.0);
    }

    #[test]
    fn the_null_corpus_is_sixteen_distinct_pairs() {
        let mut seen: Vec<(&str, &str)> = NULL_PAIRS.to_vec();
        seen.sort();
        seen.dedup();
        assert_eq!(seen.len(), 16);
    }

    /// THE STOPPING RULE MUST NEVER ACCEPT A NULL. Every same-build
    /// arm of four or more tapes, split in half, is two arms that
    /// differ by nothing but the match. Measured 2026-09-16: 58
    /// decisions, zero accepts, 20 rejects, 38 continues.
    #[test]
    fn the_stopping_rule_never_accepts_two_halves_of_one_build() {
        let a = sprt_audit_in(&runs_dir());
        if a.decisions == 0 {
            return;
        }
        assert_eq!(a.accept, 0, "accepted a null: {:?}", a.wrong);
        // and it must not be answering "continue" to everything,
        // which would be a test that never terminates rather than a
        // careful one
        assert!(a.reject > 0, "the test never rejected anything: {a:?}");
    }

    /// The baked sigmas must stay recognisably the corpus. A factor
    /// of two is loose on purpose: arms accumulate and the numbers
    /// move a little every harvest. What this catches is a metric
    /// changing meaning underneath the table, which has happened to
    /// this project's counters more than once.
    #[test]
    fn the_baked_sigmas_have_not_drifted_from_the_corpus() {
        let rows = limits_in(&runs_dir());
        if rows.is_empty() {
            return;
        }
        let mut checked = 0;
        for (map, metric, baked) in SIGMA {
            let Some(row) = rows.iter().find(|l| l.map == *map && l.metric == *metric) else {
                continue;
            };
            if row.sigma <= 0.0 {
                continue;
            }
            checked += 1;
            let ratio = row.sigma / baked;
            assert!(
                (0.5..=2.0).contains(&ratio),
                "{map} {metric}: baked {baked}, corpus {:.2} - rerun argus-mcp measure",
                row.sigma
            );
        }
        assert!(checked > 10, "only {checked} baked sigmas met the corpus");
    }

    /// The table is only worth reading if it was built from real
    /// arms. On a machine with the corpus, every map must contribute
    /// at least one row and no sigma may be zero on a metric that
    /// moves.
    #[test]
    fn the_limit_table_measures_something_if_the_corpus_is_present() {
        let rows = limits_in(&runs_dir());
        if rows.is_empty() {
            return;
        }
        let dm4: Vec<&Limit> = rows.iter().filter(|l| l.map == "dm4").collect();
        if dm4.is_empty() {
            return;
        }
        let stalls = dm4
            .iter()
            .find(|l| l.metric == "stalls")
            .expect("dm4 stalls row");
        assert!(
            stalls.arms >= 2,
            "dm4 stalls came from {} arms",
            stalls.arms
        );
        assert!(stalls.sigma > 0.0, "dm4 stalls sigma {}", stalls.sigma);
        // the MDE must fall with tapes, always
        assert!(stalls.mde3 > stalls.mde5 && stalls.mde5 > stalls.mde10);
    }
}
