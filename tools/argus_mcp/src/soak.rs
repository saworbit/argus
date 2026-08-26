//! Unattended lab shifts, built to sit idle.
//!
//! `argus-mcp soak` runs matches in a loop while nobody watches -
//! gates every tape against the shipped baseline and writes a
//! morning report. `argus-mcp cycle` closes the offline learning
//! loop once, with a guard: learn hotspots, regen the nav, compile,
//! probe, and ADOPT only if the gates improve (otherwise everything
//! is restored byte for byte).
//!
//! Neither is scheduled by anything. They exist for the Saturday
//! night the operator feels like it. Guardrails are hard limits,
//! not suggestions:
//!   - wall clock cap (default 4 h, max 12)
//!   - match count cap (default 60)
//!   - bytes-written cap (default 200 MB; a whole night of tapes is
//!     under 10 MB in practice - the cap is there for the fear, and
//!     for any future artefact that grows)
//!   - stop file: create runs/soak.stop and the loop ends after the
//!     current match
//!   - Ctrl+C stops the child engine cleanly (MatchCtrl shutdown)

use crate::config::Config;
use crate::intel::{compare_runs_scaled, Verdict};
use crate::match_ctrl::MatchCtrl;
use std::io::Write;
use std::path::PathBuf;
use std::time::{Duration, Instant};

pub struct SoakOpts {
    pub maps: Vec<String>,
    pub hours: f64,
    pub matches: u32,
    pub duration_sec: u32,
    pub skill: u32,
    pub max_mb: u64,
    pub learn: bool,
}

impl Default for SoakOpts {
    fn default() -> Self {
        SoakOpts {
            maps: vec!["dm4".into(), "dm2".into(), "dm6".into()],
            hours: 4.0,
            matches: 60,
            duration_sec: 185,
            skill: 2,
            max_mb: 200,
            learn: false,
        }
    }
}

pub fn parse_soak_args(
    mut args: impl Iterator<Item = String>,
) -> Result<SoakOpts, String> {
    let mut o = SoakOpts::default();
    while let Some(a) = args.next() {
        let mut val = |what: &str| -> Result<String, String> {
            args.next().ok_or(format!("{what} needs a value"))
        };
        match a.as_str() {
            "--maps" => o.maps = val("--maps")?.split(',').map(|s| s.trim().to_string()).collect(),
            "--hours" => o.hours = val("--hours")?.parse().map_err(|e| format!("--hours: {e}"))?,
            "--matches" => {
                o.matches = val("--matches")?.parse().map_err(|e| format!("--matches: {e}"))?
            }
            "--duration" => {
                o.duration_sec =
                    val("--duration")?.parse().map_err(|e| format!("--duration: {e}"))?
            }
            "--skill" => o.skill = val("--skill")?.parse().map_err(|e| format!("--skill: {e}"))?,
            "--max-mb" => {
                o.max_mb = val("--max-mb")?.parse().map_err(|e| format!("--max-mb: {e}"))?
            }
            "--learn" => o.learn = true,
            other => return Err(format!("unknown soak flag {other:?}")),
        }
    }
    o.hours = o.hours.clamp(0.1, 12.0);
    o.matches = o.matches.clamp(1, 500);
    o.duration_sec = o.duration_sec.clamp(60, 600);
    Ok(o)
}

pub async fn run_soak(opts: SoakOpts) -> Result<(), String> {
    let cfg = Config::load().map_err(|e| format!("{e:?}"))?;
    let stamp = chrono_lite_stamp();
    let report_path = cfg.runs.join(format!("soak_{stamp}.md"));
    let stop_file = cfg.runs.join("soak.stop");
    let _ = std::fs::remove_file(&stop_file);

    let deadline = Instant::now() + Duration::from_secs_f64(opts.hours * 3600.0);
    let mut written: u64 = 0;
    let mut ctrl = MatchCtrl::default();
    let mut report = std::fs::File::create(&report_path)
        .map_err(|e| format!("{}: {e}", report_path.display()))?;
    let mut w = |line: &str| {
        println!("{line}");
        let _ = writeln!(report, "{line}");
    };
    w(&format!(
        "# Soak {stamp}\n\nmaps {:?}, skill {}, {} s/match; caps: {:.1} h, {} matches, {} MB.\nStop early: create {}\n",
        opts.maps, opts.skill, opts.duration_sec, opts.hours, opts.matches, opts.max_mb,
        stop_file.display()
    ));

    let mut counts = std::collections::BTreeMap::<String, [u32; 3]>::new();
    let mut n = 0u32;
    'outer: loop {
        for map in &opts.maps {
            if n >= opts.matches {
                w("\nmatch cap reached.");
                break 'outer;
            }
            if Instant::now() >= deadline {
                w("\nwall clock cap reached.");
                break 'outer;
            }
            if stop_file.exists() {
                w("\nsoak.stop found - stopping.");
                let _ = std::fs::remove_file(&stop_file);
                break 'outer;
            }
            if written > opts.max_mb * 1024 * 1024 {
                w(&format!("\nbytes-written cap reached ({} MB).", opts.max_mb));
                break 'outer;
            }
            n += 1;
            let run_name = format!("soak_{stamp}_{n:03}_{map}");
            let res = ctrl
                .run(&cfg, map, opts.duration_sec, Some(&run_name), None, Some(opts.skill))
                .await;
            match res {
                Ok(r) => {
                    written += std::fs::metadata(&r.log_path).map(|m| m.len()).unwrap_or(0);
                    let verdict = match compare_runs_scaled(&cfg, "baseline", &run_name, Some(map))
                    {
                        Ok(rep) => {
                            let slot = counts.entry(map.clone()).or_default();
                            match rep.verdict {
                                Verdict::Improved | Verdict::Parity => slot[0] += 1,
                                Verdict::Mixed => slot[1] += 1,
                                Verdict::Regressed => slot[2] += 1,
                            }
                            format!("{:?}: {}", rep.verdict, rep.headline)
                        }
                        Err(e) => format!("compare failed: {e}"),
                    };
                    w(&format!("- {n:03} {map}: {} | {verdict}", r.brief.headline));
                    for f in r.brief.flags.iter().take(3) {
                        w(&format!("    - {f}"));
                    }
                }
                Err(e) => {
                    w(&format!("- {n:03} {map}: MATCH FAILED: {e}"));
                }
            }
        }
    }
    ctrl.shutdown().await;

    w("\n## Verdict counts (ok / mixed / regressed)");
    for (map, c) in &counts {
        w(&format!("- {map}: {} / {} / {}", c[0], c[1], c[2]));
    }
    if opts.learn {
        w("\n## Hotspot folding (--learn)");
        for map in &opts.maps {
            match crate::learn::learn_hotspots(&cfg, map, 8) {
                Ok(rep) => w(&format!(
                    "- {map}: {} cell(s), wrote {:?} - a future nav regen inflates them",
                    rep.cells.len(),
                    rep.wrote
                )),
                Err(e) => w(&format!("- {map}: learn failed: {e}")),
            }
        }
    }
    w(&format!(
        "\n{} matches, {:.1} MB written. Report: {}",
        n,
        written as f64 / (1024.0 * 1024.0),
        report_path.display()
    ));
    Ok(())
}

/// One guarded learning cycle for one map: learn -> regen -> compile
/// and install the CANDIDATE (the probe engine reads the install) ->
/// probe -> judge. Adopt keeps the learned costs and regenerated
/// graph in src/ with the installs matching. Reject restores nav,
/// costs AND every installed progs.dat byte for byte from the
/// snapshot (never by recompiling - fteqcc is not byte-stable and a
/// recompile would silently drift the recorded ship MD5).
pub async fn run_cycle(map: &str) -> Result<(), String> {
    let cfg = Config::load().map_err(|e| format!("{e:?}"))?;
    let stamp = chrono_lite_stamp();
    let snap = cfg.runs.join(format!("cycle_{stamp}_{map}_snapshot"));
    std::fs::create_dir_all(&snap).map_err(|e| e.to_string())?;

    // 1. snapshot everything the cycle may change: nav sources plus
    // every installed progs.dat
    let nav_qc = cfg.src.join(format!("argus_nav_{map}.qc"));
    let nav_json = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let costs = cfg.src.join(format!("argus_nav_{map}.costs.json"));
    let mut saved: Vec<(PathBuf, PathBuf, bool)> = Vec::new(); // (orig, copy, existed)
    for (i, p) in [nav_qc.clone(), nav_json.clone(), costs.clone()]
        .into_iter()
        .chain(cfg.install_paths())
        .enumerate()
    {
        let dst = snap.join(format!(
            "{i}_{}",
            p.file_name().map(|f| f.to_string_lossy().into_owned()).unwrap_or_default()
        ));
        let existed = p.exists();
        if existed {
            std::fs::copy(&p, &dst).map_err(|e| format!("snapshot {}: {e}", p.display()))?;
        }
        saved.push((p, dst, existed));
    }
    let restore = |saved: &[(PathBuf, PathBuf, bool)]| {
        for (orig, copy, existed) in saved {
            if *existed {
                let _ = std::fs::copy(copy, orig);
            } else {
                let _ = std::fs::remove_file(orig);
            }
        }
    };

    // 2. learn
    let rep = crate::learn::learn_hotspots(&cfg, map, 8)?;
    println!("learned {} cell(s) for {map} ({:?})", rep.cells.len(), rep.wrote);
    if rep.wrote.is_none() {
        println!("nothing learned - cycle is a no-op, snapshot kept at {}", snap.display());
        return Ok(());
    }

    // 3. regen (the costs file inflates the learned cells)
    let bsp = format!("{map}.bsp");
    let gen = crate::navgen::nav_generate(&cfg, &bsp, map, None, None, false)?;
    if !gen.ok {
        restore(&saved);
        return Err(format!("navgen failed, snapshot restored: {:?}", gen.stdout_tail));
    }
    for line in &gen.stdout_tail {
        if line.contains("directed reach") || line.contains("WARNING") {
            println!("{line}");
        }
    }

    // 4. compile and install the CANDIDATE - the probe engine reads
    // the install; reject restores the snapshot bytes, never a
    // recompile
    let comp = crate::compile::compile_qc(&cfg, true);
    if !comp.ok {
        restore(&saved);
        return Err("compile failed, snapshot restored".into());
    }

    // 5. probe and judge
    let run_name = format!("cycle_{stamp}_{map}");
    let mut ctrl = MatchCtrl::default();
    let probe = ctrl.run(&cfg, map, 185, Some(&run_name), None, Some(2)).await;
    ctrl.shutdown().await;
    let probe = match probe {
        Ok(p) => p,
        Err(e) => {
            restore(&saved);
            return Err(format!("probe failed, snapshot restored: {e}"));
        }
    };
    let repcmp = compare_runs_scaled(&cfg, "baseline", &run_name, Some(map))?;
    println!("probe: {}", probe.brief.headline);
    println!("verdict: {:?}: {}", repcmp.verdict, repcmp.headline);

    // 6. adopt or restore
    match repcmp.verdict {
        Verdict::Improved => {
            println!(
                "ADOPTED: learned costs + regenerated {map} nav stay in src/, installs carry the adopted build (record its MD5 in the handoff). Snapshot: {}",
                snap.display()
            );
        }
        v => {
            restore(&saved);
            println!(
                "REJECTED ({v:?}): nav, costs and every installed progs.dat restored byte for byte. Tape kept: {}",
                probe.log_path
            );
        }
    }
    Ok(())
}

/// yyyy-mm-dd_hhmm without a chrono dependency.
fn chrono_lite_stamp() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    let days = secs / 86400;
    let (mut y, mut rem) = (1970i64, days as i64);
    loop {
        let len = if y % 4 == 0 && (y % 100 != 0 || y % 400 == 0) { 366 } else { 365 };
        if rem < len {
            break;
        }
        rem -= len;
        y += 1;
    }
    let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    let ml = [31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    let mut m = 0usize;
    while rem >= ml[m] {
        rem -= ml[m];
        m += 1;
    }
    let tod = secs % 86400;
    format!("{y}-{:02}-{:02}_{:02}{:02}", m + 1, rem + 1, tod / 3600, (tod % 3600) / 60)
}
