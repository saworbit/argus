//! Isolated tactical trials, sequenced by engine acknowledgements.
use crate::{config::Config, match_ctrl::MatchCtrl, netclient::NetClient};
use serde::Serialize;
use std::time::{Duration, Instant};

pub const REVIEW_CASES: &[u32] = &[0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

#[derive(Debug, Default)]
struct Ack {
    header: bool,
    begun: bool,
    ended: bool,
    done: bool,
    busy: usize,
}

impl Ack {
    fn read(&mut self, line: &str, id: u32, case: u32) -> Result<(), String> {
        let Some(line) = line.strip_prefix("TACFIX ") else {
            return Ok(());
        };
        let words: Vec<_> = line.split_whitespace().collect();
        match words.first().copied() {
            Some("begin") => {
                if self.header
                    || words.len() != 4
                    || words[2] != "case"
                    || words[3] != case.to_string()
                {
                    return Err(format!("wrong or overlapping fixture begin: {line}"));
                }
                self.header = true;
            }
            Some("trial") => {
                if words != ["trial", &id.to_string(), "case", &case.to_string()]
                    || !self.header
                    || self.begun
                {
                    return Err(format!("wrong or duplicate trial acknowledgement: {line}"));
                }
                self.begun = true;
            }
            Some("end") => {
                if !self.begun || self.ended {
                    return Err("missing begin or duplicate end".into());
                }
                self.ended = true;
            }
            Some("done") => {
                if !self.ended || self.done || words != ["done", &id.to_string()] {
                    return Err(format!(
                        "wrong or premature cleanup acknowledgement: {line}"
                    ));
                }
                self.done = true;
            }
            Some("busy") => {
                if !self.begun
                    || words != ["busy", "id", &id.to_string(), "requested", &id.to_string()]
                {
                    return Err(format!("unexpected overlap acknowledgement: {line}"));
                }
                self.busy += 1;
                if self.busy > 1 {
                    return Err("duplicate busy acknowledgement".into());
                }
            }
            _ => {}
        }
        Ok(())
    }
}

#[derive(Serialize)]
pub struct SuiteReport {
    pub demo_path: Option<String>,
    pub observer_restored: bool,
    pub map: String,
    pub log_path: String,
    pub cases: Vec<u32>,
    pub step: f32,
    pub deathmatch: u32,
    pub overlap_refused: bool,
    pub source_md5: String,
    pub binary_md5: String,
    pub nav_md5: String,
}

fn digest(path: &std::path::Path) -> Result<String, String> {
    std::fs::read(path)
        .map(|b| format!("{:x}", md5::compute(b)))
        .map_err(|e| e.to_string())
}

fn source_digest(dir: &std::path::Path) -> Result<String, String> {
    fn collect(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) -> Result<(), String> {
        for entry in std::fs::read_dir(dir).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            if path.is_dir() {
                collect(&path, out)?;
            } else if path.extension().is_some_and(|e| e == "qc" || e == "src") {
                out.push(path);
            }
        }
        Ok(())
    }
    let mut paths = Vec::new();
    collect(dir, &mut paths)?;
    paths.sort();
    let mut hash = md5::Context::new();
    for path in paths {
        hash.consume(
            path.strip_prefix(dir)
                .map_err(|e| e.to_string())?
                .to_string_lossy()
                .replace('\\', "/"),
        );
        hash.consume([0]);
        hash.consume(std::fs::read(path).map_err(|e| e.to_string())?);
    }
    Ok(format!("{:x}", hash.finalize()))
}

pub fn validate(map: &str, name: &str, cases: &[u32], step: f32, dm: u32) -> Result<(), String> {
    if !crate::paths::valid_run_name(name)
        || !["dm4", "dm2"].contains(&map)
        || cases.is_empty()
        || cases.len() > 25
        || cases.iter().any(|c| *c > 14)
        || !step.is_finite()
        || !(0.01..=0.1).contains(&step)
        || ![1, 4].contains(&dm)
    {
        return Err("tactic suite needs dm4/dm2, 1..25 cases in 0..14, step 0.01..0.1 and deathmatch 1 or 4".into());
    }
    Ok(())
}

pub async fn run(
    cfg: &Config,
    map: &str,
    name: &str,
    cases: &[u32],
    step: f32,
    dm: u32,
) -> Result<SuiteReport, String> {
    run_recorded(cfg, map, name, cases, step, dm, false).await
}

// Retain the existing run signature for callers; recording adds one opt-in.
#[allow(clippy::too_many_arguments)]
pub async fn run_recorded(
    cfg: &Config,
    map: &str,
    name: &str,
    cases: &[u32],
    step: f32,
    dm: u32,
    record: bool,
) -> Result<SuiteReport, String> {
    validate(map, name, cases, step, dm)?;
    // Pin the inspected source and installed binary independently.
    let source_md5 = source_digest(&cfg.src)?;
    let binary_md5 = digest(&cfg.basedir.join(&cfg.game).join("progs.dat"))?;
    let nav_md5 = digest(&cfg.src.join(format!("argus_nav_{map}.qc.json")))?;
    let mut ctrl = MatchCtrl::default();
    ctrl.begin(cfg, map, 600, Some(name), Some(8), Some(1), Some(false))
        .await?;
    let result = async {
        let initial_offset = ctrl.log_text().unwrap_or_default().len();
        // Keep setup in one console submission. Back-to-back Windows console
        // injections can otherwise join an unfinished input line.
        ctrl.command(&format!("deathmatch {dm}; map {map}; sys_ticrate {step}; developer 1; scratch1 197; echo TACFIX server_ready")).await?;
        let setup_deadline = Instant::now() + Duration::from_secs(8);
        loop {
            let text = ctrl.log_text().ok_or("fixture tape unavailable")?;
            if text.get(initial_offset..).unwrap_or("").lines().any(|l| l.trim() == "TACFIX server_ready") { break; }
            if Instant::now() >= setup_deadline { return Err("missing server setup acknowledgement".into()); }
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        let mut client = NetClient::connect("127.0.0.1", 26000, "labprobe")?;
        if record {
            let demos = cfg.runs.join("demos");
            std::fs::create_dir_all(&demos).map_err(|e| e.to_string())?;
            client.start_recording(&demos.join(format!("{name}.dem")))?;
        }
        let signon_deadline = Instant::now() + Duration::from_secs(8);
        while client.world.signon < 3 && Instant::now() < signon_deadline {
            client.pump(Duration::from_millis(50));
        }
        if client.world.signon < 3 {
            return Err("fixture client did not sign on".into());
        }
        let own_entity = client.world.my_ent;
        let mut overlap_refused = false;
        for (index, &case) in cases.iter().enumerate() {
            let id = index as u32 + 1;
            let mut offset = ctrl.log_text().unwrap_or_default().len();
            let mut pending = String::new();
            let mut ack = Ack::default();
            let mut overlap_sent = false;
            let ready = format!("TACFIX ready {id} case {case}");
            ctrl.command(&format!("scratch2 {case}; scratch3 {id}; scratch4 {}; echo {ready}", if record {517} else {0}))
                .await?;
            // The console echo proves the case/id writes were processed. A
            // completed injection alone is not a server acknowledgement.
            let ready_deadline = Instant::now() + Duration::from_secs(5);
            loop {
                client.pump(Duration::from_millis(50));
                let text = ctrl.log_text().ok_or("fixture tape unavailable")?;
                if text.get(offset..).ok_or("fixture tape was truncated")?.lines().any(|line| line.trim() == ready) {
                    break;
                }
                if Instant::now() >= ready_deadline {
                    return Err(format!(
                        "trial {id} case {case}: missing console-ready acknowledgement"
                    ));
                }
            }
            client.set_impulse(217);
            let deadline = Instant::now() + Duration::from_secs(15);
            loop {
                client.pump(Duration::from_millis(50));
                let text = ctrl.log_text().ok_or("fixture tape unavailable")?;
                if text.len() < offset {
                    return Err("fixture tape was truncated".into());
                }
                pending.push_str(&text[offset..]);
                offset = text.len();
                while let Some(nl) = pending.find('\n') {
                    let line = pending[..nl].trim_end_matches('\r');
                    if line.starts_with("TACFIX begin ") && line != format!("TACFIX begin {map} case {case}") {
                        return Err(format!("wrong map or case: {line}"));
                    }
                    ack.read(line, id, case)?;
                    pending.drain(..=nl);
                }
                if ack.begun && case == 9 && !overlap_sent {
                    client.set_impulse(217);
                    overlap_sent = true;
                }
                if ack.done {
                    break;
                }
                if Instant::now() >= deadline {
                    return Err(format!(
                        "trial {id} case {case}: timed out; begin={}, end={}, cleanup={}",
                        ack.begun, ack.ended, ack.done
                    ));
                }
                if !ctrl.poll().0 || client.world.disconnected {
                    return Err(format!("trial {id} case {case}: engine/client stopped"));
                }
            }
            if case == 9 {
                if ack.busy != 1 {
                    return Err("overlapping trial was not refused exactly once".into());
                }
                overlap_refused = true;
            } else if ack.busy != 0 {
                return Err("unrequested overlapping trial".into());
            }
            if record {
                let restore_deadline = Instant::now() + Duration::from_secs(2);
                while client.world.my_ent != own_entity && Instant::now() < restore_deadline {
                    client.pump(Duration::from_millis(50));
                }
                if client.world.my_ent != own_entity { return Err("fixture observer view entity was not restored".into()); }
            }
            eprintln!("{map}: trial {id} case {case} acknowledged and cleaned up");
        }
        let demo_path = client.finish_recording()?;
        client.disconnect();
        if binary_md5 != digest(&cfg.basedir.join(&cfg.game).join("progs.dat"))?
            || source_md5 != source_digest(&cfg.src)?
            || nav_md5 != digest(&cfg.src.join(format!("argus_nav_{map}.qc.json")))?
        {
            return Err("source, binary or navigation changed during suite".into());
        }
        Ok((overlap_refused, demo_path))
    }
    .await;
    // This driver owns its match. A bad/missing acknowledgement stops the entire
    // isolated engine, including frozen bots and temporary pickup changes.
    let stopped = ctrl.stop(Duration::from_secs(3)).await;
    let status = stopped.map_err(|e| format!("fixture engine cleanup failed: {e}"))?;
    let (overlap_refused, demo_path) = result?;
    Ok(SuiteReport {
        demo_path,
        observer_restored: record,
        map: map.into(),
        log_path: status.log_path.ok_or("no harvested fixture tape")?,
        cases: cases.to_vec(),
        step,
        deathmatch: dm,
        overlap_refused,
        source_md5,
        binary_md5,
        nav_md5,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_suite_is_refused_before_any_launch_or_compile() {
        assert!(validate("dm4", "test", REVIEW_CASES, 0.1, 4).is_ok());
        assert!(validate("dm3", "test", REVIEW_CASES, 0.1, 1).is_err());
        assert!(validate("dm4", "../bad", REVIEW_CASES, 0.1, 1).is_err());
        assert!(validate("dm4", "test", &[], 0.1, 1).is_err());
        assert!(validate("dm4", "test", &[99], 0.1, 1).is_err());
        assert!(validate("dm4", "test", REVIEW_CASES, f32::NAN, 1).is_err());
        assert!(validate("dm4", "test", REVIEW_CASES, 0.1, 2).is_err());
    }
    #[test]
    fn trial_ids_distinguish_repeated_cases_and_require_cleanup() {
        let mut a = Ack::default();
        a.read("TACFIX begin dm4 case 0", 2, 0).unwrap();
        assert!(a.read("TACFIX trial 1 case 0", 2, 0).is_err());
        a.read("TACFIX trial 2 case 0", 2, 0).unwrap();
        assert!(!a.done);
        assert!(a.read("TACFIX done 2", 2, 0).is_err());
        a.read("TACFIX end frames 430 seconds 6.01", 2, 0).unwrap();
        a.read("TACFIX done 2", 2, 0).unwrap();
        assert!(a.done);
        assert!(a.read("TACFIX done 2", 2, 0).is_err());
    }
    #[test]
    fn duplicate_wrong_missing_and_overlapping_trials_fail() {
        let mut a = Ack::default();
        assert!(a.read("TACFIX end frames 10 seconds 6", 1, 5).is_err());
        a.read("TACFIX begin dm4 case 5", 1, 5).unwrap();
        assert!(a.read("TACFIX trial 1 case 6", 1, 5).is_err());
        a.read("TACFIX trial 1 case 5", 1, 5).unwrap();
        assert!(a.read("TACFIX trial 1 case 5", 1, 5).is_err());
        assert!(a.read("TACFIX begin dm4 case 5", 1, 5).is_err());
        a.read("TACFIX busy id 1 requested 1", 1, 5).unwrap();
        assert!(a.read("TACFIX busy id 1 requested 1", 1, 5).is_err());
    }
}
