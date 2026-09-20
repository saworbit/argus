//! The measurement layer: how large an effect this lab can see, how to
//! aggregate a handful of noisy tapes into one number, and when to stop
//! running them.
//!
//! Everything here is arithmetic over tapes that are already committed.
//! It runs no engine and changes no bot. It exists because the verdict
//! rule was fitted to sixteen pairs of byte-identical builds and then
//! read as though it were an oracle, and because "three tapes is not
//! enough on dm2 and four is barely" is folklore with a number behind
//! it that nobody had written down.
//!
//! Three pieces, and they feed each other:
//!
//!   - `pooled_sd` over same-build arms gives sigma per map per metric,
//!   - `mde` turns a sigma and a tape count into the smallest effect
//!     worth claiming,
//!   - `sprt` uses that effect as its alternative hypothesis, so the
//!     stopping rule and the detection limit are the same number
//!     rather than two independent guesses.
//!
//! The estimators are the ones the reinforcement-learning literature
//! settled on for exactly this regime (a handful of high-variance runs
//! per arm): interquartile mean rather than median or mean, a
//! stratified bootstrap interval rather than a min-max range, and a
//! probability of improvement rather than a three-way label.

use serde::Serialize;

// ---------------------------------------------------------------- basics

/// Sample mean. Empty is 0, because every caller here would otherwise
/// have to special-case an arm it already knows is non-empty.
pub fn mean(v: &[f64]) -> f64 {
    if v.is_empty() {
        return 0.0;
    }
    v.iter().sum::<f64>() / v.len() as f64
}

/// Sample standard deviation, Bessel-corrected. Fewer than two
/// observations carries no information about spread and returns 0.
pub fn sd(v: &[f64]) -> f64 {
    if v.len() < 2 {
        return 0.0;
    }
    let m = mean(v);
    let ss: f64 = v.iter().map(|x| (x - m) * (x - m)).sum();
    (ss / (v.len() as f64 - 1.0)).sqrt()
}

/// Interquartile mean: sort, drop the outer quartiles, average what is
/// left.
///
/// This is the aggregate to quote. The median throws away most of the
/// sample, and on three or four tapes that is nearly all of it; the
/// mean is at the mercy of the one tape where a bot fell in the pit.
/// IQM keeps the middle half, which is both robust to the outlier that
/// has repeatedly flipped conclusions in this project and far more
/// efficient than the median at these sample sizes.
///
/// Below four observations there is no middle half to take, so it
/// falls back to the median, which is what "trim 25 per cent from each
/// end" degenerates to anyway.
pub fn iqm(vals: &[f64]) -> f64 {
    if vals.is_empty() {
        return 0.0;
    }
    let mut v = vals.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let n = v.len();
    if n < 4 {
        return median_sorted(&v);
    }
    let drop = n / 4;
    mean(&v[drop..n - drop])
}

fn median_sorted(v: &[f64]) -> f64 {
    let n = v.len();
    if n == 0 {
        return 0.0;
    }
    if n % 2 == 1 {
        v[n / 2]
    } else {
        (v[n / 2 - 1] + v[n / 2]) / 2.0
    }
}

/// The median, for the places that still quote one.
pub fn median(vals: &[f64]) -> f64 {
    let mut v = vals.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    median_sorted(&v)
}

/// Pooled within-arm standard deviation across several same-build arms.
///
/// Each arm is a set of tapes from ONE build on ONE map, so its spread
/// is the instrument's noise and nothing else. Pooling by degrees of
/// freedom uses every arm's evidence instead of averaging their sds,
/// which would over-weight a two-tape arm against a five-tape one.
pub fn pooled_sd(arms: &[Vec<f64>]) -> f64 {
    let mut num = 0.0;
    let mut den = 0.0;
    for a in arms {
        if a.len() < 2 {
            continue;
        }
        let s = sd(a);
        num += (a.len() as f64 - 1.0) * s * s;
        den += a.len() as f64 - 1.0;
    }
    if den <= 0.0 {
        return 0.0;
    }
    (num / den).sqrt()
}

// ---------------------------------------------------------------- MDE

/// z at 0.975: the two-sided 5 per cent significance point.
const Z_ALPHA: f64 = 1.959_964;
/// z at 0.80: the conventional power point.
const Z_POWER: f64 = 0.841_621;

/// The smallest difference in arm means this instrument could detect,
/// at n tapes a side, with 5 per cent false positives and 80 per cent
/// power.
///
/// `mde = (z_alpha + z_power) * sigma * sqrt(2 / n)`
///
/// It is the standard two-sample expression and it is the whole answer
/// to "how many tapes does this need": the count enters as a square
/// root, so halving the detectable effect costs four times the tapes.
pub fn mde(sigma: f64, n_per_arm: usize) -> f64 {
    if n_per_arm == 0 || sigma <= 0.0 {
        return 0.0;
    }
    (Z_ALPHA + Z_POWER) * sigma * (2.0 / n_per_arm as f64).sqrt()
}

// ---------------------------------------------------------------- bootstrap

/// A tape's value for one metric, tagged with the stratum it belongs
/// to. The stratum here is the MAP: resampling within strata keeps
/// every map represented in every resample, which is the structure the
/// lab has and currently handles by judging each map separately and
/// then arguing about which map to believe.
#[derive(Debug, Clone)]
pub struct Sample {
    pub stratum: String,
    pub value: f64,
}

impl Sample {
    pub fn new(stratum: &str, value: f64) -> Sample {
        Sample {
            stratum: stratum.to_string(),
            value,
        }
    }
}

/// A closed interval estimate.
#[derive(Debug, Clone, Copy, Serialize)]
pub struct Interval {
    pub lo: f64,
    pub hi: f64,
}

/// xorshift64*, so a bootstrap is reproducible from its seed.
///
/// A confidence interval that moves when you run the tool twice is
/// worse than no interval at all, and this lab has already spent a
/// session on an instrument that would not hold still. No crate: the
/// generator is eight lines and a dependency here buys nothing.
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
    fn below(&mut self, n: usize) -> usize {
        if n == 0 {
            return 0;
        }
        (self.next_u64() % n as u64) as usize
    }
}

/// How many resamples. 2000 is enough for a 95 per cent interval to be
/// stable to about a per cent, and the whole corpus is small.
const BOOT_ITERS: usize = 2000;
/// Fixed seed: see `Rng`.
const BOOT_SEED: u64 = 0x4152_4755_5300_0001;

fn strata_of(s: &[Sample]) -> Vec<Vec<f64>> {
    let mut keys: Vec<String> = s.iter().map(|x| x.stratum.clone()).collect();
    keys.sort();
    keys.dedup();
    keys.iter()
        .map(|k| {
            s.iter()
                .filter(|x| &x.stratum == k)
                .map(|x| x.value)
                .collect()
        })
        .collect()
}

fn resample(groups: &[Vec<f64>], rng: &mut Rng) -> Vec<f64> {
    let mut out = Vec::new();
    for g in groups {
        for _ in 0..g.len() {
            out.push(g[rng.below(g.len())]);
        }
    }
    out
}

/// Stratified bootstrap interval on IQM(candidate) minus IQM(control).
///
/// This is the number the band could never produce. A min-max range is
/// not an interval estimate: it does not narrow as tapes accumulate,
/// and at one tape a side its lower edge is whatever the single worst
/// tape did, which is why "improved" was unreachable. An interval
/// entirely on one side of zero is what an improvement actually is.
///
/// `lower_is_better` flips the sign so the interval always reads in
/// the good direction: positive means the candidate is better.
/// `None` when a stratum holds fewer than two tapes. Resampling one
/// observation with replacement draws that observation every time,
/// so the interval would collapse onto the difference itself and
/// print as a confidence interval of width zero. That is not a
/// narrow interval, it is no interval, and this lab has already
/// been bitten once by a band whose floor was structurally
/// unreachable at one tape a side.
pub fn bootstrap_diff_ci(
    cand: &[Sample],
    ctl: &[Sample],
    lower_is_better: bool,
    alpha: f64,
) -> Option<Interval> {
    if cand.is_empty() || ctl.is_empty() {
        return None;
    }
    let cg = strata_of(cand);
    let kg = strata_of(ctl);
    if cg.iter().chain(kg.iter()).any(|g| g.len() < 2) {
        return None;
    }
    let mut rng = Rng::new(BOOT_SEED);
    let mut diffs = Vec::with_capacity(BOOT_ITERS);
    for _ in 0..BOOT_ITERS {
        let c = iqm(&resample(&cg, &mut rng));
        let k = iqm(&resample(&kg, &mut rng));
        diffs.push(if lower_is_better { k - c } else { c - k });
    }
    diffs.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let lo_i = ((alpha / 2.0) * BOOT_ITERS as f64).floor() as usize;
    let hi_i = (((1.0 - alpha / 2.0) * BOOT_ITERS as f64).ceil() as usize).min(BOOT_ITERS - 1);
    Some(Interval {
        lo: diffs[lo_i],
        hi: diffs[hi_i],
    })
}

/// Probability that a candidate tape drawn at random beats a control
/// tape drawn at random. Ties count a half.
///
/// A number with a direction, which a three-way label is not. 0.5 is
/// "no difference"; 0.8 says four times in five the candidate wins.
/// It is the Mann-Whitney statistic, so it makes no assumption about
/// the shape of the distribution, which matters on a metric whose
/// same-build ratio has run 0.18 to 11.0.
pub fn prob_improvement(cand: &[f64], ctl: &[f64], lower_is_better: bool) -> f64 {
    if cand.is_empty() || ctl.is_empty() {
        return 0.5;
    }
    let mut wins = 0.0;
    for c in cand {
        for k in ctl {
            let better = if lower_is_better { *c < *k } else { *c > *k };
            let tie = (c - k).abs() < 1e-9;
            if tie {
                wins += 0.5;
            } else if better {
                wins += 1.0;
            }
        }
    }
    wins / (cand.len() as f64 * ctl.len() as f64)
}

// ---------------------------------------------------------------- SPRT

/// What a sequential test says after the tapes it has seen.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum SprtCall {
    /// The effect is real and at least as large as the bound.
    Accept,
    /// There is no effect worth shipping.
    Reject,
    /// Neither boundary crossed. Run another tape a side.
    Continue,
    /// Neither boundary crossed and the cap is spent. Abandon it.
    Abandon,
}

#[derive(Debug, Clone, Serialize)]
pub struct SprtOut {
    pub metric: String,
    pub call: SprtCall,
    /// log-likelihood ratio, in favour of "the effect is real"
    pub llr: f64,
    /// the boundaries the llr is being compared against
    pub accept_at: f64,
    pub reject_at: f64,
    /// the effect size the test is powered for, in the metric's units
    pub bound: f64,
    /// observed difference, positive meaning the candidate is better
    pub effect: f64,
    /// the sigma used, and where it came from
    pub sigma: f64,
    pub sigma_source: String,
    pub note: String,
}

/// alpha and beta both 5 per cent, so the boundaries are symmetric at
/// +-log(0.95/0.05).
const SPRT_A: f64 = 2.944_439;

/// The tape cap. A marginal change gets abandoned rather than ground
/// out forever, which is the other half of what a sequential test is
/// for. Ten a side is also the last column of the MDE table, so the
/// cap and the detection limit agree.
pub const SPRT_CAP: usize = 10;

/// Sequential probability ratio test on the difference of arm means.
///
/// The structure is Fishtest's, translated: instead of a game result
/// the per-trial outcome is a tape's metric, and instead of elo the
/// bound is an effect in the metric's own units. H0 is "no effect",
/// H1 is "an effect of at least `bound`". After each tape the
/// log-likelihood ratio moves, and the moment it crosses a boundary
/// the test stops.
///
/// The reason this matters here and not only in theory: looking after
/// every tape and deciding whether to run another is peeking, and a
/// fixed-horizon test read that way has a badly inflated false
/// positive rate. The lab peeks constantly. A sequential test is built
/// to be peeked at.
///
/// `sigma` is supplied by the caller rather than estimated from the
/// arms, because three tapes estimate a standard deviation terribly
/// and this test's whole job is to not be fooled by a small sample.
/// The corpus sigma for that map and metric is the right input; the
/// caller falls back to the pooled arm sd and says so.
pub fn sprt(
    metric: &str,
    cand: &[f64],
    ctl: &[f64],
    lower_is_better: bool,
    bound: f64,
    sigma: f64,
    sigma_source: &str,
) -> SprtOut {
    let n_c = cand.len();
    let n_k = ctl.len();
    let raw = mean(cand) - mean(ctl);
    let effect = if lower_is_better { -raw } else { raw };
    let mut out = SprtOut {
        metric: metric.to_string(),
        call: SprtCall::Continue,
        llr: 0.0,
        accept_at: SPRT_A,
        reject_at: -SPRT_A,
        bound,
        effect,
        sigma,
        sigma_source: sigma_source.to_string(),
        note: String::new(),
    };
    if n_c == 0 || n_k == 0 || sigma <= 0.0 || bound <= 0.0 {
        out.note = "no variance estimate for this metric; the test cannot run".into();
        return out;
    }
    // standard error of the difference of means
    let se2 = sigma * sigma * (1.0 / n_c as f64 + 1.0 / n_k as f64);
    // For d ~ N(delta, se^2), log f(d | bound) - log f(d | 0).
    out.llr = bound * (effect - bound / 2.0) / se2;
    let spent = n_c.min(n_k);
    out.call = if out.llr >= SPRT_A {
        SprtCall::Accept
    } else if out.llr <= -SPRT_A {
        SprtCall::Reject
    } else if spent >= SPRT_CAP {
        SprtCall::Abandon
    } else {
        SprtCall::Continue
    };
    out.note = match out.call {
        SprtCall::Accept => format!(
            "the effect is real and at least {bound:.1}: {n_c} against {n_k} tapes were enough"
        ),
        SprtCall::Reject => format!("no effect of {bound:.1} or more; stop running tapes"),
        SprtCall::Continue => format!(
            "neither boundary crossed at {spent} tapes a side; run another (cap {SPRT_CAP})"
        ),
        SprtCall::Abandon => format!(
            "still undecided at the {SPRT_CAP} tape cap; the effect is smaller than {bound:.1} \
             or this metric cannot see it"
        ),
    };
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn iqm_drops_the_outer_quartiles() {
        // the middle half of 1..8 is 3,4,5,6
        let v: Vec<f64> = (1..=8).map(|x| x as f64).collect();
        assert!((iqm(&v) - 4.5).abs() < 1e-9);
        // and the tape where a bot fell in the pit does not move it
        let mut w = v.clone();
        w[7] = 900.0;
        assert!((iqm(&w) - 4.5).abs() < 1e-9);
        // where the mean would have moved by more than a hundred
        assert!(mean(&w) - mean(&v) > 100.0);
    }

    #[test]
    fn iqm_below_four_is_the_median() {
        assert!((iqm(&[5.0, 1.0, 3.0]) - 3.0).abs() < 1e-9);
        assert!((iqm(&[4.0]) - 4.0).abs() < 1e-9);
        assert_eq!(iqm(&[]), 0.0);
    }

    #[test]
    fn pooled_sd_weights_by_degrees_of_freedom() {
        // one tight arm of five, one wide arm of two: the five-tape
        // arm must dominate, which an average of sds would not do
        let tight = vec![10.0, 10.0, 11.0, 9.0, 10.0];
        let wide = vec![0.0, 40.0];
        let p = pooled_sd(&[tight.clone(), wide.clone()]);
        assert!(p < (sd(&tight) + sd(&wide)) / 2.0, "pooled {p}");
        assert!(p > sd(&tight), "pooled {p}");
        // an arm of one carries no spread and must not divide by zero
        assert_eq!(pooled_sd(&[vec![3.0]]), 0.0);
    }

    #[test]
    fn mde_falls_as_the_square_root_of_the_tapes() {
        let s = 10.0;
        let a = mde(s, 3);
        let b = mde(s, 12);
        // four times the tapes, half the detectable effect
        assert!((a / b - 2.0).abs() < 1e-6, "{a} {b}");
        assert_eq!(mde(s, 0), 0.0);
    }

    #[test]
    fn a_bootstrap_interval_covers_zero_on_identical_arms() {
        let a: Vec<Sample> = [12.0, 15.0, 9.0, 20.0, 11.0]
            .iter()
            .map(|v| Sample::new("dm2", *v))
            .collect();
        let ci = bootstrap_diff_ci(&a, &a, true, 0.05).expect("five tapes a side");
        assert!(ci.lo <= 0.0 && ci.hi >= 0.0, "{ci:?}");
    }

    #[test]
    fn a_bootstrap_interval_clears_zero_on_a_real_separation() {
        let cand: Vec<Sample> = [3.0, 4.0, 2.0, 5.0, 3.0]
            .iter()
            .map(|v| Sample::new("dm2", *v))
            .collect();
        let ctl: Vec<Sample> = [40.0, 44.0, 38.0, 46.0, 41.0]
            .iter()
            .map(|v| Sample::new("dm2", *v))
            .collect();
        // lower is better, so the candidate wins and the interval is
        // entirely positive
        let ci = bootstrap_diff_ci(&cand, &ctl, true, 0.05).expect("five tapes a side");
        assert!(ci.lo > 0.0, "{ci:?}");
    }

    #[test]
    fn a_bootstrap_is_reproducible() {
        let a: Vec<Sample> = [12.0, 15.0, 9.0, 20.0]
            .iter()
            .map(|v| Sample::new("dm4", *v))
            .collect();
        let b: Vec<Sample> = [8.0, 11.0, 7.0, 14.0]
            .iter()
            .map(|v| Sample::new("dm4", *v))
            .collect();
        let one = bootstrap_diff_ci(&a, &b, false, 0.05).unwrap();
        let two = bootstrap_diff_ci(&a, &b, false, 0.05).unwrap();
        assert_eq!(one.lo, two.lo);
        assert_eq!(one.hi, two.hi);

        // and one tape a side has no interval to give
        let single = vec![Sample::new("dm4", 12.0)];
        assert!(bootstrap_diff_ci(&single, &single, false, 0.05).is_none());
    }

    #[test]
    fn stratification_keeps_every_map_in_every_resample() {
        // one map with many tapes and one with few: an unstratified
        // bootstrap would sometimes draw no e1m6 tape at all
        let mixed: Vec<Sample> = vec![
            Sample::new("dm2", 10.0),
            Sample::new("dm2", 12.0),
            Sample::new("dm2", 11.0),
            Sample::new("e1m6", 90.0),
        ];
        let groups = strata_of(&mixed);
        assert_eq!(groups.len(), 2);
        let mut rng = Rng::new(7);
        for _ in 0..50 {
            let r = resample(&groups, &mut rng);
            assert_eq!(r.len(), 4);
            assert!(
                r.iter().any(|v| *v > 50.0),
                "e1m6 dropped out of a resample"
            );
        }
    }

    #[test]
    fn probability_of_improvement_reads_in_the_right_direction() {
        let better = [1.0, 2.0, 3.0];
        let worse = [10.0, 11.0, 12.0];
        assert!((prob_improvement(&better, &worse, true) - 1.0).abs() < 1e-9);
        assert!((prob_improvement(&worse, &better, true) - 0.0).abs() < 1e-9);
        // identical arms sit at a coin flip
        assert!((prob_improvement(&better, &better, true) - 0.5).abs() < 1e-9);
    }

    #[test]
    fn sprt_accepts_a_large_effect_and_rejects_a_null() {
        // stalls, lower is better, bound 10, sigma 8
        let big = sprt(
            "stalls",
            &[2.0, 3.0, 1.0, 2.0],
            &[40.0, 44.0, 38.0, 42.0],
            true,
            10.0,
            8.0,
            "test",
        );
        assert_eq!(big.call, SprtCall::Accept, "{big:?}");

        // A NULL COSTS MORE TAPES THAN AN EFFECT DOES, and the
        // arithmetic says how many. To reject "an effect of 10 or
        // more" on a zero difference the llr must reach -2.944, which
        // needs bound^2 / (2 * se^2) >= 2.944, so with sigma 8 that is
        // se^2 <= 17 and n >= 8 a side. Four is not enough and the
        // test correctly says continue rather than guessing.
        let flat = [40.0, 41.0, 39.0, 40.0];
        let short = sprt("stalls", &flat, &flat, true, 10.0, 8.0, "test");
        assert_eq!(short.call, SprtCall::Continue, "{short:?}");
        let long: Vec<f64> = (0..8).map(|i| 39.0 + (i % 3) as f64).collect();
        let null = sprt("stalls", &long, &long, true, 10.0, 8.0, "test");
        assert_eq!(null.call, SprtCall::Reject, "{null:?}");
    }

    #[test]
    fn sprt_says_continue_before_it_says_anything_else() {
        // a half-sized effect on two tapes a side is exactly the case
        // the lab currently answers with a verdict and should not
        let marginal = sprt(
            "stalls",
            &[35.0, 36.0],
            &[40.0, 41.0],
            true,
            10.0,
            12.0,
            "test",
        );
        assert_eq!(marginal.call, SprtCall::Continue, "{marginal:?}");
        assert!(marginal.note.contains("run another"));
    }

    #[test]
    fn sprt_abandons_at_the_cap() {
        let flat: Vec<f64> = (0..SPRT_CAP).map(|i| 40.0 + (i % 3) as f64).collect();
        let near: Vec<f64> = (0..SPRT_CAP).map(|i| 38.0 + (i % 3) as f64).collect();
        // a 2 unit effect against a 40 unit bound and a wide sigma
        // cannot cross either boundary
        let out = sprt("stalls", &near, &flat, true, 40.0, 60.0, "test");
        assert_eq!(out.call, SprtCall::Abandon, "{out:?}");
    }

    #[test]
    fn sprt_without_a_variance_estimate_refuses_to_answer() {
        let out = sprt("stalls", &[1.0], &[2.0], true, 5.0, 0.0, "none");
        assert_eq!(out.call, SprtCall::Continue);
        assert!(out.note.contains("cannot run"));
    }
}
