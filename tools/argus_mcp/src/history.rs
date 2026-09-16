//! A regression is a change in a series, not a difference between two
//! samples.
//!
//! Pairwise comparison throws away every other tape ever recorded, and
//! this project has 752 of them, each stamped with a date, on a small
//! set of maps, measuring the same metrics. That is a time series per
//! map per metric with a couple of hundred points on it, and nobody had
//! ever run a detector over it. The observations that motivated the
//! whole recovery plan are exactly what such a detector outputs:
//! dm2 human stalls a minute stepping 6 to 9 and then to 21.6 and 32.5;
//! the September dm2 ladder mean at 52 against late August's 36,
//! recorded as "not bisected"; dm4 bot kills on Shane falling from 4.2
//! a minute to 2.2. Each is a suspected step, eyeballed.
//!
//! Two things live here, and the issues say to run them in that order.
//!
//! 1. `change_points` finds however many steps a series has and dates
//!    them. It does not assume there is one.
//! 2. `bisect` localises a single step with a NOISY oracle, which is
//!    the situation a rebuild-and-ladder bisect is actually in.
//!
//! Both are read-only over the committed corpus.

use crate::corpus::TapeRow;
use crate::stats;
use serde::Serialize;

// ------------------------------------------------- change point detection

/// The shortest run of tapes that may be called a level. Below this a
/// single unlucky tape is a "change point", and on dm2 at 75 per cent
/// CV there is an unlucky tape in every arm.
const MIN_SEG: usize = 5;
/// Permutations for the significance test. The statistic is the MAX
/// over every split, so permuting it calibrates the threshold across
/// all split positions at once: no separate multiplicity correction is
/// needed, which is the same problem the gate set has and does not
/// solve this way.
const PERMS: usize = 999;
/// Reject above this and the detector is finding noise.
const ALPHA: f64 = 0.01;

/// One step in a series.
#[derive(Debug, Clone, Serialize)]
pub struct Step {
    /// index into the series, first point of the AFTER segment
    pub at: usize,
    /// the date of that tape, which is the answer anyone wants
    pub date: String,
    pub run: String,
    pub before_n: usize,
    pub after_n: usize,
    pub before: f64,
    pub after: f64,
    /// permutation p of the max statistic
    pub p: f64,
    /// The commonest tick class either side. A step where these
    /// DIFFER is a rate change before it is a regression: the
    /// server frame rate is itself a step in most series, and
    /// reading one as the other is the mistake this column exists
    /// to prevent. Filter the series to one class to be sure.
    pub before_tick: String,
    pub after_tick: String,
}

struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Rng {
        Rng(seed | 1)
    }
    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }
}

/// The largest standardised mean shift over every legal split, and
/// where it is.
///
/// E-Divisive is the named prior art (MongoDB, and Hunter which is now
/// Apache Otava) and this is its STRUCTURE - scan every split, keep the
/// best, calibrate by permutation, recurse - with a cheaper statistic.
/// The energy distance E-Divisive maximises is O(n^2) per split, which
/// is O(n^3) per permutation on a 321 point series, and it buys
/// sensitivity to distributional change beyond the mean. The question
/// this corpus is asked is "did the level step", so a standardised mean
/// shift answers it directly and runs in one pass with prefix sums.
/// Recorded because it is a deliberate substitution, not an oversight.
fn best_split(v: &[f64]) -> Option<(usize, f64)> {
    let n = v.len();
    if n < 2 * MIN_SEG {
        return None;
    }
    let mut pre = vec![0.0; n + 1];
    let mut pre2 = vec![0.0; n + 1];
    for i in 0..n {
        pre[i + 1] = pre[i] + v[i];
        pre2[i + 1] = pre2[i] + v[i] * v[i];
    }
    let mut best = None;
    for k in MIN_SEG..=(n - MIN_SEG) {
        let (a, b) = (k as f64, (n - k) as f64);
        let ma = pre[k] / a;
        let mb = (pre[n] - pre[k]) / b;
        let ssa = pre2[k] - a * ma * ma;
        let ssb = (pre2[n] - pre2[k]) - b * mb * mb;
        let pooled = ((ssa + ssb) / (n as f64 - 2.0)).max(1e-12).sqrt();
        let t = (mb - ma).abs() / (pooled * (1.0 / a + 1.0 / b).sqrt());
        if best.map(|(_, bt)| t > bt).unwrap_or(true) {
            best = Some((k, t));
        }
    }
    best
}

fn permutation_p(v: &[f64], observed: f64, seed: u64) -> f64 {
    let mut rng = Rng::new(seed);
    let mut w = v.to_vec();
    let mut worse = 0usize;
    for _ in 0..PERMS {
        // Fisher-Yates, so every ordering is equally likely and the
        // null being tested really is "the order carries nothing"
        for i in (1..w.len()).rev() {
            let j = (rng.next_u64() % (i as u64 + 1)) as usize;
            w.swap(i, j);
        }
        if let Some((_, t)) = best_split(&w) {
            if t >= observed {
                worse += 1;
            }
        }
    }
    (worse as f64 + 1.0) / (PERMS as f64 + 1.0)
}

fn segment(v: &[f64], offset: usize, out: &mut Vec<(usize, f64, f64, f64, usize, usize)>) {
    let Some((k, t)) = best_split(v) else { return };
    let p = permutation_p(v, t, 0x5EED_0000 + offset as u64);
    if p > ALPHA {
        return;
    }
    let before = stats::iqm(&v[..k]);
    let after = stats::iqm(&v[k..]);
    out.push((offset + k, before, after, p, k, v.len() - k));
    segment(&v[..k], offset, out);
    segment(&v[k..], offset + k, out);
}

/// The tick class most of a window ran at, for the column that
/// stops a rate change being read as a regression.
fn commonest_tick(rows: &[TapeRow]) -> String {
    let mut counts: std::collections::BTreeMap<&str, usize> = Default::default();
    for r in rows {
        *counts.entry(r.tick_class.as_str()).or_insert(0) += 1;
    }
    counts
        .into_iter()
        .max_by_key(|(_, n)| *n)
        .map(|(k, _)| k.to_string())
        .unwrap_or_default()
}

/// Every step in one series, dated, with a permutation p.
///
/// `rows` must already be filtered to one map and one kind and sorted
/// by date: a series that mixes maps is not a series, and one that
/// mixes bot and human tapes steps every time the human sat down.
pub fn change_points(rows: &[TapeRow], metric: &str) -> Vec<Step> {
    let v: Vec<f64> = rows.iter().filter_map(|r| r.metric(metric)).collect();
    if v.len() != rows.len() || v.len() < 2 * MIN_SEG {
        return Vec::new();
    }
    let mut raw = Vec::new();
    segment(&v, 0, &mut raw);
    let mut steps: Vec<Step> = raw
        .into_iter()
        .map(|(at, before, after, p, bn, an)| Step {
            at,
            date: rows[at].started.clone(),
            run: rows[at].run.clone(),
            before_n: bn,
            after_n: an,
            before,
            after,
            p,
            before_tick: commonest_tick(&rows[at.saturating_sub(bn)..at]),
            after_tick: commonest_tick(&rows[at..(at + an).min(rows.len())]),
        })
        .collect();
    steps.sort_by_key(|s| s.at);
    steps
}

// ------------------------------------------------- probabilistic bisection

/// Horstein's probabilistic bisection, posed in 1963 for exactly this:
/// bisection when the oracle is only right with probability p.
///
/// `git bisect` assumes an oracle. Each answer permanently discards
/// half the range, so one unlucky tape sends the search into the wrong
/// half and it never comes back - and with dm2 stalls at 75 per cent
/// CV, unlucky tapes are the common case. Phase 1 came three tapes away
/// from convicting the wrong arm, which is this failure mode caught
/// only by luck.
///
/// Instead of discarding, keep a posterior over WHERE the change is,
/// update it with each noisy answer, and sample next at the posterior
/// median. Sampling at the median is provably the optimal query and the
/// posterior concentrates exponentially. A single bad tape shifts the
/// posterior rather than cutting off the truth.
#[derive(Debug, Clone, Serialize)]
pub struct Pba {
    /// probability mass per candidate position
    pub mass: Vec<f64>,
    pub queries: usize,
}

impl Pba {
    /// Flat prior: the change is equally likely anywhere.
    pub fn new(n: usize) -> Pba {
        let m = if n == 0 { 1 } else { n };
        Pba { mass: vec![1.0 / m as f64; m], queries: 0 }
    }

    /// Fold in one noisy answer.
    ///
    /// `after` is true when the query at `pos` said the change is at or
    /// after it, false when it said before. `reliability` is how often
    /// that answer is right, in (0.5, 1); 0.5 carries no information
    /// and is refused rather than silently flattening the posterior.
    pub fn update(&mut self, pos: usize, after: bool, reliability: f64) {
        let p = reliability.clamp(0.500_001, 0.999_999);
        let n = self.mass.len();
        let pos = pos.min(n.saturating_sub(1));
        for (i, m) in self.mass.iter_mut().enumerate() {
            let consistent = if after { i >= pos } else { i < pos };
            *m *= if consistent { p } else { 1.0 - p };
        }
        let total: f64 = self.mass.iter().sum();
        if total > 0.0 {
            for m in self.mass.iter_mut() {
                *m /= total;
            }
        } else {
            // every hypothesis killed means the answers contradict each
            // other harder than the reliability allows. Reset to flat
            // rather than return a posterior of NaNs.
            let flat = 1.0 / n as f64;
            self.mass.iter_mut().for_each(|m| *m = flat);
        }
        self.queries += 1;
    }

    /// Where to spend the next tape: the posterior median, which is the
    /// optimal query and is the question that actually costs time in a
    /// bisect.
    pub fn next_query(&self) -> usize {
        self.quantile(0.5)
    }

    pub fn quantile(&self, q: f64) -> usize {
        let mut acc = 0.0;
        for (i, m) in self.mass.iter().enumerate() {
            acc += m;
            if acc >= q {
                return i;
            }
        }
        self.mass.len().saturating_sub(1)
    }

    /// The credible interval, so "localised to within two builds" is a
    /// statement with a confidence on it rather than a judgement call.
    pub fn interval(&self, mass: f64) -> (usize, usize) {
        let tail = (1.0 - mass) / 2.0;
        (self.quantile(tail), self.quantile(1.0 - tail))
    }

    /// The stopping rule: the interval is narrow enough to act on.
    pub fn settled(&self, mass: f64, width: usize) -> bool {
        let (lo, hi) = self.interval(mass);
        hi.saturating_sub(lo) <= width
    }
}

/// The nearest position to `want` that has not been queried, within
/// the legal range. None when every legal position is spent.
fn nearest_unasked(want: usize, lo: usize, hi: usize, asked: &[usize]) -> Option<usize> {
    if hi < lo {
        return None;
    }
    for d in 0..=(hi - lo) {
        for cand in [want.saturating_add(d), want.saturating_sub(d)] {
            if cand >= lo && cand <= hi && !asked.contains(&cand) {
                return Some(cand);
            }
        }
    }
    None
}

/// What a bisection run concluded.
#[derive(Debug, Clone, Serialize)]
pub struct BisectOut {
    pub metric: String,
    pub map: String,
    pub queries: usize,
    /// the posterior median, as an index into the series
    pub at: usize,
    pub date: String,
    pub run: String,
    pub lo_date: String,
    pub hi_date: String,
    pub interval_width: usize,
    pub settled: bool,
    /// where to spend the next tape if it is not settled
    pub next_date: String,
    pub notes: Vec<String>,
}

/// Localise one step by probabilistic bisection, answering each query
/// from the corpus.
///
/// The corpus is the oracle here: a query at position i compares the
/// window of tapes before it against the window after, and answers
/// "the change is at or after i" when the level on the right is closer
/// to the known-later level. The answer's RELIABILITY is where the
/// noise is admitted: it comes from the probability that a tape on one
/// side beats a tape on the other, which is exactly what this lab has
/// been pretending was certainty.
///
/// This composes with the sequential test as the issue describes. When
/// a position has no tapes, the run stops and names the date to spend
/// the next ones at, which is the whole point.
pub fn bisect(rows: &[TapeRow], metric: &str, map: &str, window: usize) -> BisectOut {
    let n = rows.len();
    let mut out = BisectOut {
        metric: metric.to_string(),
        map: map.to_string(),
        queries: 0,
        at: 0,
        date: String::new(),
        run: String::new(),
        lo_date: String::new(),
        hi_date: String::new(),
        interval_width: 0,
        settled: false,
        next_date: String::new(),
        notes: Vec::new(),
    };
    if n < 2 * window {
        out.notes.push(format!(
            "only {n} tapes on {map}; a bisect needs at least {} for a window of {window}",
            2 * window
        ));
        return out;
    }
    let v: Vec<f64> = rows.iter().filter_map(|r| r.metric(metric)).collect();
    if v.len() != n {
        out.notes.push(format!("no metric called '{metric}'"));
        return out;
    }
    // which end is "after the change": the later level, taken as the
    // last window. The bisect is localising a step toward it.
    let late = stats::iqm(&v[n - window..]);
    let early = stats::iqm(&v[..window]);
    if (late - early).abs() < 1e-9 {
        out.notes.push("the two ends are level; there is nothing to localise".into());
        return out;
    }

    let mut pba = Pba::new(n);
    let mut asked: Vec<usize> = Vec::new();
    // A POSITION IS ASKED AT MOST ONCE. Horstein re-queries the
    // posterior median, and doing that here would feed the same
    // tapes in twice and manufacture confidence out of nothing:
    // the corpus has exactly one answer per position. When the
    // median lands somewhere already asked, move to the nearest
    // position that is not, which spends the evidence that exists
    // and then stops. Running fresh tapes is what a re-query
    // means, and the report names where.
    let budget = (n / 2).clamp(8, 40);
    for _ in 0..budget {
        let want = pba.next_query().clamp(window, n - window);
        let Some(q) = nearest_unasked(want, window, n - window, &asked) else {
            break;
        };
        asked.push(q);
        let left = &v[q - window..q];
        let right = &v[q..(q + window).min(n)];
        // The oracle answers "does the window starting here already
        // look like the LATE level?". Mind the direction: if it does,
        // the change has already happened, so the change point is at
        // or before q and the posterior must be boosted BELOW q. The
        // two readings are opposites and getting them the wrong way
        // round walks the median away from the truth while looking
        // perfectly healthy, which is how the first cut of this
        // localised a planted step at 53 of 60.
        let lr = stats::iqm(right);
        let looks_late = (lr - late).abs() < (lr - early).abs();
        // reliability from the separation the tapes actually show, not
        // from a constant. Bounded well away from 1 because a window of
        // a few noisy tapes is never that sure.
        let lower_is_better = late > early;
        let sep = stats::prob_improvement(right, left, !lower_is_better);
        let rel = (0.5 + (sep - 0.5).abs()).clamp(0.55, 0.85);
        pba.update(q + 1, !looks_late, rel);
        out.queries += 1;
        if pba.settled(0.9, 2) {
            break;
        }
    }
    let at = pba.next_query();
    let (lo, hi) = pba.interval(0.9);
    out.at = at;
    out.date = rows[at].started.clone();
    out.run = rows[at].run.clone();
    out.lo_date = rows[lo].started.clone();
    out.hi_date = rows[hi].started.clone();
    out.interval_width = hi - lo;
    out.settled = pba.settled(0.9, 2);
    out.next_date = rows[at].started.clone();
    if !out.settled {
        out.notes.push(format!(
            "not localised: the 90 per cent interval still spans {} tapes. \
             Run tapes at {} and feed the answer back.",
            out.interval_width, out.date
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn series(map: &str, vals: &[f64]) -> Vec<TapeRow> {
        vals.iter()
            .enumerate()
            .map(|(i, v)| TapeRow {
                run: format!("t{i:03}"),
                map: map.into(),
                started: format!("2026-08-{:02} 10:00:00", (i % 28) + 1),
                kind: "bot".into(),
                tick_class: "listen".into(),
                duration_sec: 185.0,
                stalls: *v,
                ..Default::default()
            })
            .collect()
    }

    #[test]
    fn a_flat_series_has_no_change_points() {
        // noisy but level: the detector must find nothing, which is the
        // property that matters most. A detector that fires on noise is
        // the old OR rule with extra steps.
        let v: Vec<f64> = (0..60).map(|i| 40.0 + ((i * 7) % 11) as f64).collect();
        let steps = change_points(&series("dm2", &v), "stalls");
        assert!(steps.is_empty(), "{steps:?}");
    }

    #[test]
    fn a_real_step_is_found_and_dated() {
        let mut v: Vec<f64> = (0..30).map(|i| 10.0 + ((i * 3) % 5) as f64).collect();
        v.extend((0..30).map(|i| 40.0 + ((i * 3) % 5) as f64));
        let rows = series("dm2", &v);
        let steps = change_points(&rows, "stalls");
        assert_eq!(steps.len(), 1, "{steps:?}");
        assert!((steps[0].at as i64 - 30).abs() <= 2, "found at {}", steps[0].at);
        assert!(steps[0].before < 15.0 && steps[0].after > 38.0, "{steps:?}");
        assert!(steps[0].p <= ALPHA, "p {}", steps[0].p);
        assert_eq!(steps[0].run, rows[steps[0].at].run);
    }

    #[test]
    fn two_steps_are_both_found() {
        let mut v: Vec<f64> = (0..25).map(|i| 10.0 + (i % 3) as f64).collect();
        v.extend((0..25).map(|i| 50.0 + (i % 3) as f64));
        v.extend((0..25).map(|i| 12.0 + (i % 3) as f64));
        let steps = change_points(&series("dm2", &v), "stalls");
        assert_eq!(steps.len(), 2, "{steps:?}");
        assert!((steps[0].at as i64 - 25).abs() <= 2);
        assert!((steps[1].at as i64 - 50).abs() <= 2);
    }

    #[test]
    fn one_outlier_is_not_a_change_point() {
        let mut v: Vec<f64> = (0..40).map(|i| 20.0 + (i % 4) as f64).collect();
        v[19] = 300.0;
        let steps = change_points(&series("dm2", &v), "stalls");
        assert!(steps.is_empty(), "an outlier became a step: {steps:?}");
    }

    #[test]
    fn a_posterior_survives_one_wrong_answer() {
        // the whole reason not to use git bisect. Nine answers pointing
        // at 30 and one liar pointing the other way.
        let mut p = Pba::new(60);
        for _ in 0..9 {
            p.update(30, true, 0.75);
            p.update(30, false, 0.75);
        }
        // ten honest answers that the change is at or after 30
        let mut q = Pba::new(60);
        for _ in 0..10 {
            q.update(30, true, 0.8);
        }
        q.update(30, false, 0.8); // the liar
        assert!(q.next_query() >= 30, "one bad answer moved the median below the truth");
        // and a hard bisect would have discarded the truth outright
        assert!(q.mass[35] > 0.0);
    }

    #[test]
    fn the_posterior_concentrates_and_the_interval_narrows() {
        let mut p = Pba::new(100);
        let (lo0, hi0) = p.interval(0.9);
        for _ in 0..25 {
            // everything below 40 says "after", everything above says
            // "before", so the truth is 40
            p.update(20, true, 0.8);
            p.update(60, false, 0.8);
        }
        let (lo, hi) = p.interval(0.9);
        assert!(hi - lo < hi0 - lo0, "the interval did not narrow");
        assert!(p.next_query() >= 20 && p.next_query() <= 60, "{}", p.next_query());
    }

    #[test]
    fn a_reliability_of_a_coin_flip_is_refused() {
        let mut p = Pba::new(20);
        let before = p.mass.clone();
        p.update(10, true, 0.5);
        // 0.5 is clamped just above, so the posterior tilts by a hair
        // rather than staying identical or collapsing
        assert!(p.mass != before);
        assert!(p.mass.iter().all(|m| m.is_finite() && *m > 0.0));
        let sum: f64 = p.mass.iter().sum();
        assert!((sum - 1.0).abs() < 1e-9);
    }

    #[test]
    fn bisect_localises_a_planted_step() {
        let mut v: Vec<f64> = (0..30).map(|i| 10.0 + (i % 3) as f64).collect();
        v.extend((0..30).map(|i| 45.0 + (i % 3) as f64));
        let rows = series("dm2", &v);
        let out = bisect(&rows, "stalls", "dm2", 5);
        assert!(out.queries > 0, "{out:?}");
        assert!((out.at as i64 - 30).abs() <= 6, "localised at {} of 60", out.at);
    }

    #[test]
    fn bisect_says_what_it_needs_rather_than_guessing() {
        let rows = series("dm2", &[10.0, 11.0, 12.0]);
        let out = bisect(&rows, "stalls", "dm2", 5);
        assert!(out.notes[0].contains("needs at least"), "{out:?}");
        let flat: Vec<f64> = vec![20.0; 40];
        let out = bisect(&series("dm2", &flat), "stalls", "dm2", 5);
        assert!(out.notes[0].contains("level"), "{out:?}");
    }
}
