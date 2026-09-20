use argus_mcp::gui::{parse_gui_args, run_gui};
use argus_mcp::server::Argus;
use rmcp::{transport::stdio, ServiceExt};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let mut args = std::env::args().skip(1);
    match args.next().as_deref() {
        Some("gui") => {
            let opts = parse_gui_args(args);
            run_gui(opts).map_err(|e| anyhow::anyhow!(e))?;
            Ok(())
        }
        Some("soak") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args
                .iter()
                .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                print_soak_help();
                return Ok(());
            }
            let opts = argus_mcp::soak::parse_soak_args(sub_args.into_iter())
                .map_err(|e| anyhow::anyhow!(e))?;
            argus_mcp::soak::run_soak(opts)
                .await
                .map_err(|e| anyhow::anyhow!(e))
        }
        Some("cycle") => {
            let map = args
                .next()
                .ok_or_else(|| anyhow::anyhow!("usage: argus-mcp cycle <map>"))?;
            if map == "-h" || map == "--help" || map == "help" {
                println!("usage: argus-mcp cycle <map>\n\nOne guarded learning cycle: learn -> regen -> compile -> probe.");
                return Ok(());
            }
            argus_mcp::engine::validate_map(&map).map_err(|e| anyhow::anyhow!(e))?;
            argus_mcp::soak::run_cycle(&map)
                .await
                .map_err(|e| anyhow::anyhow!(e))
        }
        Some("demo") => {
            // CLI face of see what=demo, so demos read without an MCP
            // client (append :export to also write <stem>.tracks.json)
            let name = args
                .next()
                .ok_or_else(|| anyhow::anyhow!("usage: argus-mcp demo <stem>[:export]"))?;
            if name == "-h" || name == "--help" || name == "help" {
                println!("usage: argus-mcp demo <stem>[:export]\n\nParse a harvested .dem (append :export to also write <stem>.tracks.json).");
                return Ok(());
            }
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let brief = argus_mcp::demo::demo_brief(&cfg, &name).map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&brief)?);
            Ok(())
        }
        Some("probelinks") => {
            // empirical link verification: the puppet walks the graph
            //   argus-mcp probelinks <map> [limit] [skip] [--coop] [--jumps]
            // The mode is part of the verdict (#310): deathmatch
            // strips every spawnflags 2048 entity, doors included, so
            // a link verified there can still be a lie in co-op.
            let rest: Vec<String> = args.collect();
            let coop = rest.iter().any(|a| a == "--coop");
            let jumps_only = rest.iter().any(|a| a == "--jumps");
            let mut pos = rest.iter().filter(|a| !a.starts_with("--"));
            let map = pos.next().cloned().ok_or_else(|| {
                anyhow::anyhow!(
                    "usage: argus-mcp probelinks <map> [limit] [skip] [--coop] [--jumps]"
                )
            })?;
            if map == "-h" || map == "--help" || map == "help" {
                println!("usage: argus-mcp probelinks <map> [limit] [skip] [--coop] [--jumps]\n\nEmpirical link verification: puppet walks navigation graph links.\n--coop runs the server in co-op, where spawnflags 2048 entities are NOT stripped.\n--jumps verifies generated jump links instead of ordinary walk/drop links.");
                return Ok(());
            }
            argus_mcp::engine::validate_map(&map).map_err(|e| anyhow::anyhow!(e))?;
            let limit: usize = pos.next().and_then(|s| s.parse().ok()).unwrap_or(30);
            let skip: usize = pos.next().and_then(|s| s.parse().ok()).unwrap_or(0);
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let report =
                argus_mcp::netclient::probe_links(&cfg, &map, limit, skip, coop, jumps_only)
                    .await
                    .map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            Ok(())
        }
        Some("match") => {
            // One named lab match, without an MCP client. Every ladder
            // in the recovery plan needs dozens of named tapes and the
            // running server's exe is locked on Windows, so the loop
            // cannot wait for a client restart:
            //   argus-mcp match <map> [duration_sec] [run_name] [--skill N] [--coop] [--slots N]
            let rest: Vec<String> = args.collect();
            if rest
                .iter()
                .any(|a| a == "-h" || a == "--help" || a == "help")
                || rest.is_empty()
            {
                println!("usage: argus-mcp match <map> [duration_sec] [run_name] [--skill N] [--slots N] [--port N] [--coop]

Run one named match and print its brief as JSON. The tape lands in runs/<run_name>.log.");
                return Ok(());
            }
            let flag = |name: &str| -> Option<String> {
                rest.iter()
                    .position(|a| a == name)
                    .and_then(|i| rest.get(i + 1).cloned())
            };
            let coop = rest.iter().any(|a| a == "--coop");
            let skill: Option<u32> = flag("--skill").and_then(|s| s.parse().ok());
            let slots: Option<u32> = flag("--slots").and_then(|s| s.parse().ok());
            let flagged: std::collections::HashSet<usize> = rest
                .iter()
                .enumerate()
                .filter(|(_, a)| a.starts_with("--"))
                .flat_map(|(i, a)| {
                    if a == "--coop" {
                        vec![i]
                    } else {
                        vec![i, i + 1]
                    }
                })
                .collect();
            let pos: Vec<&String> = rest
                .iter()
                .enumerate()
                .filter(|(i, _)| !flagged.contains(i))
                .map(|(_, a)| a)
                .collect();
            let map = pos
                .first()
                .cloned()
                .ok_or_else(|| {
                    anyhow::anyhow!("usage: argus-mcp match <map> [duration_sec] [run_name]")
                })?
                .clone();
            argus_mcp::engine::validate_map(&map).map_err(|e| anyhow::anyhow!(e))?;
            let duration: u32 = pos.get(1).and_then(|s| s.parse().ok()).unwrap_or(185);
            let run_name = pos.get(2).map(|s| s.to_string());
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            // a second engine on its own port halves a ladder's wall
            // clock; check the tapes still read the listen tick class
            // before trusting a parallel run, because a loaded box
            // drops the dedicated loop into the slow regime
            let port: Option<u32> = flag("--port").and_then(|s| s.parse().ok());
            let mut ctrl = match port {
                Some(p) => argus_mcp::match_ctrl::MatchCtrl::on_port(p),
                None => argus_mcp::match_ctrl::MatchCtrl::default(),
            };
            let res = ctrl
                .run(
                    &cfg,
                    &map,
                    duration,
                    run_name.as_deref(),
                    slots,
                    skill,
                    Some(coop),
                )
                .await
                .map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&res)?);
            Ok(())
        }
        Some("corpus") => {
            // Ask the whole corpus a question instead of briefing one
            // tape at a time. Read-only.
            let rest: Vec<String> = args.collect();
            if rest.iter().any(|a| a == "-h" || a == "--help") {
                print_corpus_help();
                return Ok(());
            }
            let opt = |name: &str| -> Option<String> {
                rest.iter()
                    .position(|a| a == name)
                    .and_then(|i| rest.get(i + 1))
                    .cloned()
            };
            let flag = |name: &str| rest.iter().any(|a| a == name);
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let runs = cfg.runs.clone();

            if flag("--cells") {
                let rows = argus_mcp::corpus::cells(&runs, opt("--map").as_deref());
                println!("run,map,started,kind,x,y,z,count,cause");
                let lim = opt("--limit")
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(usize::MAX);
                for c in rows.iter().take(lim) {
                    println!(
                        "{},{},{},{},{:.0},{:.0},{:.0},{:.0},{}",
                        c.run, c.map, c.started, c.kind, c.x, c.y, c.z, c.count, c.cause
                    );
                }
                return Ok(());
            }

            let (rows, st) = argus_mcp::corpus::index(&runs, flag("--rebuild"));
            if flag("--write") || flag("--rebuild") {
                let p = argus_mcp::corpus::write_index(&runs, &rows)?;
                eprintln!(
                    "{} tapes indexed ({} cached, {} parsed, {} unreadable) -> {}",
                    st.rows,
                    st.from_cache,
                    st.parsed,
                    st.dropped,
                    p.display()
                );
            }
            let q = argus_mcp::corpus::Query {
                map: opt("--map"),
                kind: opt("--kind"),
                tick_class: opt("--tick"),
                run_like: opt("--run"),
                since: opt("--since"),
                until: opt("--until"),
                metric: opt("--metric"),
                group_by: opt("--group-by"),
                limit: opt("--limit").and_then(|v| v.parse().ok()),
            };
            match argus_mcp::corpus::query(&rows, &q) {
                Ok(a) => print!("{}", argus_mcp::corpus::to_csv(&a)),
                Err(e) => return Err(anyhow::anyhow!(e)),
            }
            Ok(())
        }
        Some("history") => {
            // Change points over the corpus, and probabilistic
            // bisection to localise one. Read-only.
            let rest: Vec<String> = args.collect();
            if rest.iter().any(|a| a == "-h" || a == "--help") {
                print_history_help();
                return Ok(());
            }
            let opt = |name: &str| -> Option<String> {
                rest.iter()
                    .position(|a| a == name)
                    .and_then(|i| rest.get(i + 1))
                    .cloned()
            };
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let (rows, _) = argus_mcp::corpus::index(&cfg.runs, false);
            let kind = opt("--kind").unwrap_or_else(|| "bot".into());
            // one class at a time is how to be certain a step is not
            // the server frame rate wearing a regression costume
            let tick = opt("--tick");
            // A bisect assumes ONE step. A series with three cannot
            // be localised and says so; the composition the issues
            // describe is to run the detector first and then point
            // the bisect at one segment between two of its steps.
            let since = opt("--since");
            let until = opt("--until");
            let metrics: Vec<String> = match opt("--metric") {
                Some(m) => vec![m],
                None => ["stalls", "engages", "lava_deaths", "cover", "goals"]
                    .iter()
                    .map(|s| s.to_string())
                    .collect(),
            };
            let maps: Vec<String> = match opt("--map") {
                Some(m) => vec![m],
                None => {
                    let mut m: Vec<String> = rows
                        .iter()
                        .filter(|r| r.kind == kind)
                        .map(|r| r.map.clone())
                        .filter(|m| !m.is_empty())
                        .collect();
                    m.sort();
                    m.dedup();
                    m
                }
            };
            let series = |map: &str| -> Vec<argus_mcp::corpus::TapeRow> {
                let mut v: Vec<argus_mcp::corpus::TapeRow> = rows
                    .iter()
                    .filter(|r| {
                        r.map.eq_ignore_ascii_case(map)
                            && r.kind == kind
                            && !r.started.is_empty()
                            && r.duration_sec > 0.0
                            && tick.as_ref().map(|t| &r.tick_class == t).unwrap_or(true)
                            && since.as_ref().map(|d| r.started >= *d).unwrap_or(true)
                            && until.as_ref().map(|d| r.started <= *d).unwrap_or(true)
                    })
                    .cloned()
                    .collect();
                v.sort_by(|a, b| a.started.cmp(&b.started));
                v
            };

            if let Some(m) = opt("--bisect") {
                let map = maps.first().cloned().unwrap_or_else(|| "dm2".into());
                let v = series(&map);
                let win = opt("--window").and_then(|v| v.parse().ok()).unwrap_or(10);
                let out = argus_mcp::history::bisect(&v, &m, &map, win);
                println!("map,metric,queries,at,date,run,lo,hi,width,settled");
                println!(
                    "{},{},{},{},{},{},{},{},{},{}",
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
                );
                for n in &out.notes {
                    println!("# {n}");
                }
                return Ok(());
            }

            println!("map,metric,date,run,n_before,n_after,before,after,p,tick_before,tick_after");
            for map in &maps {
                let v = series(map);
                for metric in &metrics {
                    for st in argus_mcp::history::change_points(&v, metric) {
                        println!(
                            "{},{},{},{},{},{},{:.1},{:.1},{:.3},{},{}",
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
                        );
                    }
                }
            }
            Ok(())
        }
        Some("measure") => {
            // What this instrument can see, over the tapes already
            // committed. Read-only: no engine, no QC.
            //   argus-mcp measure [--write <path>]
            let rest: Vec<String> = args.collect();
            if rest.iter().any(|a| a == "-h" || a == "--help") {
                println!(
                    "usage: argus-mcp measure [--write <path>]

The detection limit per map and metric, from every committed same-build arm,
and what running four gates costs measured over the null corpus. Read-only.
--write puts the table in a file instead of stdout."
                );
                return Ok(());
            }
            let out = rest
                .iter()
                .position(|a| a == "--write")
                .and_then(|i| rest.get(i + 1))
                .cloned();
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let limits = argus_mcp::measure::limits(&cfg);
            if limits.is_empty() {
                return Err(anyhow::anyhow!(
                    "no same-build arms found under ARGUS_RUNS; nothing to measure"
                ));
            }
            let audit = argus_mcp::measure::gate_audit(&cfg);
            let sprt = argus_mcp::measure::sprt_audit(&cfg);
            let stamp = chrono::Local::now().format("%Y-%m-%d").to_string();
            let text = argus_mcp::measure::render(&limits, &audit, &sprt, &stamp);
            match out {
                Some(path) => {
                    std::fs::write(&path, &text)?;
                    println!("wrote {path}");
                }
                None => println!("{text}"),
            }
            Ok(())
        }

        Some("compare") => {
            // Judge a band from the CLI, so a ladder can be decided
            // without an MCP client:
            //   argus-mcp compare <cand,cand,...> [<ctrl,ctrl,...>]
            // With no controls the map's baseline band is used.
            let rest: Vec<String> = args.collect();
            if rest.is_empty() || rest.iter().any(|a| a == "-h" || a == "--help") {
                println!("usage: argus-mcp compare <candidate[,candidate...]> [control[,control...]] [--primary <metric>]

Judge candidate tapes against control tapes as bands. With no controls, the map's baseline band from runs/baselines.json is used.
--primary names the metric the change was predicted to move: only that gate convicts, the rest flag.
  stall_parity | engagements | lava_deaths | freezes");
                return Ok(());
            }
            let split = |s: &str| -> Vec<String> {
                s.split(',')
                    .map(|x| x.trim().to_string())
                    .filter(|x| !x.is_empty())
                    .collect()
            };
            // the metric this change was pre-registered to move: with
            // it, only that gate convicts and the rest flag (#377)
            let primary = rest
                .iter()
                .position(|a| a == "--primary")
                .and_then(|i| rest.get(i + 1))
                .cloned();
            let positional: Vec<String> = {
                let mut v = Vec::new();
                let mut it = rest.iter();
                while let Some(a) = it.next() {
                    if a == "--primary" {
                        it.next();
                        continue;
                    }
                    v.push(a.clone());
                }
                v
            };
            if positional.is_empty() {
                return Err(anyhow::anyhow!(
                    "usage: argus-mcp compare <cand,...> [<ctrl,...>] [--primary <metric>]"
                ));
            }
            let cands = split(&positional[0]);
            let ctrls = positional.get(1).map(|s| split(s)).unwrap_or_default();
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let report = if ctrls.is_empty() {
                argus_mcp::intel::compare_runs_band(&cfg, &cands, None, primary.as_deref())
                    .map_err(|e| anyhow::anyhow!(e))?
            } else {
                let mut cb = Vec::new();
                for c in &cands {
                    cb.push(
                        argus_mcp::intel::brief_run(&cfg, c, None)
                            .map_err(|e| anyhow::anyhow!(e))?,
                    );
                }
                let map = cb[0].map.clone();
                let mut kb = Vec::new();
                for c in &ctrls {
                    kb.push(
                        argus_mcp::intel::brief_run(&cfg, c, map.as_deref())
                            .map_err(|e| anyhow::anyhow!(e))?,
                    );
                }
                argus_mcp::intel::compare_band_primary(&cb, &kb, primary.as_deref())
            };
            println!("{}", report.gate_card);
            println!("{}", report.headline);
            for f in &report.findings {
                println!("  - {f}");
            }
            Ok(())
        }
        Some("client") => {
            // the lab as a real NetQuake client (see netclient.rs):
            //   argus-mcp client observe [secs] [host] [port]
            //   argus-mcp client walk <x> <y> <z> [secs] [host] [port]
            let sub = args.next().unwrap_or_else(|| "observe".into());
            if sub == "-h" || sub == "--help" || sub == "help" {
                print_client_help();
                return Ok(());
            }
            let rest: Vec<String> = args.collect();
            let res = tokio::task::spawn_blocking(move || match sub.as_str() {
                "observe" => {
                    let secs: f32 = rest.first().and_then(|s| s.parse().ok()).unwrap_or(6.0);
                    let host = rest.get(1).cloned().unwrap_or_else(|| "127.0.0.1".into());
                    let port: u16 =
                        rest.get(2).and_then(|s| s.parse().ok()).unwrap_or(26000);
                    argus_mcp::netclient::observe(&host, port, secs, "labprobe")
                        .and_then(|r| serde_json::to_string_pretty(&r).map_err(|e| e.to_string()))
                }
                "walk" => {
                    if rest.len() < 3 {
                        return Err("usage: argus-mcp client walk <x> <y> <z> [secs]".into());
                    }
                    let tgt = [
                        rest[0].parse::<f32>().map_err(|e| e.to_string())?,
                        rest[1].parse::<f32>().map_err(|e| e.to_string())?,
                        rest[2].parse::<f32>().map_err(|e| e.to_string())?,
                    ];
                    let secs: f32 = rest.get(3).and_then(|s| s.parse().ok()).unwrap_or(15.0);
                    let host = rest.get(4).cloned().unwrap_or_else(|| "127.0.0.1".into());
                    let port: u16 =
                        rest.get(5).and_then(|s| s.parse().ok()).unwrap_or(26000);
                    let mut c = argus_mcp::netclient::NetClient::connect(
                        &host, port, "labprobe",
                    )?;
                    c.pump(std::time::Duration::from_secs(3));
                    let start = c.my_pos();
                    let out = c.walk_toward(tgt, secs);
                    c.disconnect();
                    serde_json::to_string_pretty(&serde_json::json!({
                        "start": start,
                        "target": tgt,
                        "reached": out.reached,
                        "closest": out.closest,
                        "final_pos": out.final_pos,
                        "samples": out.track.len(),
                    }))
                    .map_err(|e| e.to_string())
                }
                "walkrel" => {
                    // walk a relative offset from wherever we spawn -
                    // the quickest live proof that the puppet moves
                    let dx: f32 = rest.first().and_then(|s| s.parse().ok()).unwrap_or(200.0);
                    let dy: f32 = rest.get(1).and_then(|s| s.parse().ok()).unwrap_or(0.0);
                    let secs: f32 = rest.get(2).and_then(|s| s.parse().ok()).unwrap_or(8.0);
                    let mut c = argus_mcp::netclient::NetClient::connect(
                        "127.0.0.1",
                        26000,
                        "labprobe",
                    )?;
                    c.pump(std::time::Duration::from_secs(3));
                    let Some(start) = c.my_pos() else {
                        return Err("no spawn position observed".into());
                    };
                    let tgt = [start[0] + dx, start[1] + dy, start[2]];
                    let out = c.walk_toward(tgt, secs);
                    c.disconnect();
                    serde_json::to_string_pretty(&serde_json::json!({
                        "start": start,
                        "target": tgt,
                        "reached": out.reached,
                        "closest": out.closest,
                        "final_pos": out.final_pos,
                        "samples": out.track.len(),
                    }))
                    .map_err(|e| e.to_string())
                }
                "attack" => {
                    // FIRE FROM THE PUPPET'S SEAT (#259). clc_move
                    // already carries the button bits and set_move
                    // already takes pitch and yaw, so the protocol
                    // work was done; what was missing was a seat that
                    // a bot will react to and a verb to drive it.
                    //
                    // The name IS the opt-in. Argus_CanSee refuses the
                    // exact netname "labprobe" so the link-probe
                    // puppet stays an instrument rather than a target,
                    // which is right for a sweep and wrong for this.
                    // Connecting as "labfoe" is visible to every bot
                    // and needs no QC change at all.
                    //
                    // This is what unblocks "the bot takes damage from
                    // a player": Argus_Pain retaliation, the vendetta
                    // ledger, retreat entry, the pain flinch on aim,
                    // knockback response and the shove economy were
                    // none of them exercisable headless before.
                    let secs: f32 = rest.first().and_then(|s| s.parse().ok()).unwrap_or(6.0);
                    let yaw: f32 = rest.get(1).and_then(|s| s.parse().ok()).unwrap_or(0.0);
                    let pitch: f32 = rest.get(2).and_then(|s| s.parse().ok()).unwrap_or(0.0);
                    let host = rest.get(3).cloned().unwrap_or_else(|| "127.0.0.1".into());
                    let port: u16 = rest.get(4).and_then(|s| s.parse().ok()).unwrap_or(26000);
                    let mut c =
                        argus_mcp::netclient::NetClient::connect(&host, port, "labfoe")?;
                    c.pump(std::time::Duration::from_secs(3));
                    let start = c.my_pos();
                    // BUTTON_ATTACK is bit 1; bit 2 is jump, which the
                    // walk auto-hop already uses. With no yaw given we
                    // TRACK the nearest player instead of firing down
                    // a fixed heading, because a stray shot exercises
                    // nothing: every case worth testing starts with a
                    // bot actually taking damage.
                    let (ticks, tracked) = if rest.len() > 1 {
                        c.set_move(pitch, yaw, 0, 0, 1);
                        c.pump(std::time::Duration::from_secs_f32(secs.max(0.5)));
                        c.set_move(pitch, yaw, 0, 0, 0);
                        c.pump(std::time::Duration::from_secs_f32(0.5));
                        (0, 0)
                    } else {
                        c.attack_nearest(secs.max(0.5))
                    };
                    let end = c.my_pos();
                    let report = c.snapshot();
                    c.disconnect();
                    serde_json::to_string_pretty(&serde_json::json!({
                        "name": "labfoe",
                        "note": "visible to bots: Argus_CanSee only refuses \"labprobe\"",
                        "held_attack_secs": secs,
                        "aim": if rest.len() > 1 {
                            serde_json::json!({ "mode": "fixed", "yaw": yaw, "pitch": pitch })
                        } else {
                            serde_json::json!({
                                "mode": "track nearest player",
                                "ticks": ticks,
                                "ticks_with_a_target": tracked,
                            })
                        },
                        "start_pos": start,
                        "final_pos": end,
                        "level": report.level,
                        "roster": report.names,
                        "last_prints": report.last_prints,
                    }))
                    .map_err(|e| e.to_string())
                }
                "impulse" => {
                    // fire a player impulse from the puppet's seat -
                    // the roster interface (101 add bot / 102 remove / 100 menu)
                    // and the dev teleport (216) all become drivable
                    // headless. GitHub #2's 4-player measurement was
                    // the first customer.
                    // a comma list fires several from ONE seat, which is
                    // what a toggle needs: two separate invocations are
                    // two different players. "impulse 210,210" is the
                    // spectator camera round trip.
                    let imps: Vec<u8> = rest
                        .first()
                        .map(|s| s.split(',').filter_map(|t| t.trim().parse().ok()).collect())
                        .unwrap_or_default();
                    if imps.is_empty() {
                        return Err("usage: argus-mcp client impulse <n>[,<n>...] [secs]".into());
                    }
                    let secs: f32 = rest.get(1).and_then(|s| s.parse().ok()).unwrap_or(2.0);
                    let host = rest.get(2).cloned().unwrap_or_else(|| "127.0.0.1".into());
                    let port: u16 =
                        rest.get(3).and_then(|s| s.parse().ok()).unwrap_or(26000);
                    let mut c = argus_mcp::netclient::NetClient::connect(
                        &host, port, "labprobe",
                    )?;
                    c.pump(std::time::Duration::from_secs(3));
                    for imp in &imps {
                        c.set_impulse(*imp);
                        c.pump(std::time::Duration::from_secs_f32(secs.max(0.5)));
                    }
                    c.disconnect();
                    serde_json::to_string_pretty(&serde_json::json!({
                        "impulses": imps,
                        "sent": true,
                    }))
                    .map_err(|e| e.to_string())
                }
                other => Err(format!(
                    "unknown client subcommand {other:?}; try: observe, walk, walkrel, impulse, attack"
                )),
            })
            .await?;
            println!("{}", res.map_err(|e| anyhow::anyhow!(e))?);
            Ok(())
        }
        Some("compile") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args
                .iter()
                .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp compile [options]\n\
                     \n\
                     Compile QuakeC progs.dat with fteqcc, with timestamp verification.\n\
                     \n\
                     Options:\n\
                       --install       Install progs.dat to basedir/game and lq1\n\
                       --backup        Create backup snapshot before compiling"
                );
                return Ok(());
            }
            let install = sub_args.iter().any(|a| a == "--install" || a == "-i");
            let backup = sub_args.iter().any(|a| a == "--backup" || a == "-b");
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            if backup {
                let snap = argus_mcp::backup::take_backup(&cfg);
                if snap.ok {
                    println!("Backup written to: {}", snap.path);
                } else {
                    eprintln!("Warning: backup failed: {:?}", snap.error);
                }
            }
            let res = argus_mcp::compile::compile_qc(&cfg, install);
            if res.ok {
                println!(
                    "Compile OK! (progs.dat: {} bytes)",
                    res.progs_bytes.unwrap_or(0)
                );
                for p in &res.installed_to {
                    println!("  Installed to: {p}");
                }
                if res.new_warnings > 0 {
                    println!("  Warnings: {}", res.new_warnings);
                }
                Ok(())
            } else {
                eprintln!("Compile FAILED ({} errors):", res.new_errors);
                for line in &res.raw_tail {
                    eprintln!("  {line}");
                }
                std::process::exit(1);
            }
        }
        Some("nav") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args.is_empty()
                || sub_args
                    .iter()
                    .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp nav <map> [options]\n\
                     \n\
                     Generate navigation graph for a BSP map.\n\
                     \n\
                     Options:\n\
                       --register     Register only after current reach and mill evidence pass\n\
                       --no-register  Generate nav without registering dispatcher"
                );
                return Ok(());
            }
            let map = &sub_args[0];
            argus_mcp::engine::validate_map(map).map_err(|e| anyhow::anyhow!(e))?;
            let register = !sub_args.iter().any(|a| a == "--no-register");
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let res = argus_mcp::navgen::nav_generate(&cfg, map, map, None, None, register)
                .map_err(|e| anyhow::anyhow!(e))?;
            if res.ok {
                println!("Nav generation OK for {map}!");
                if let Some(budget) = &res.edict_budget {
                    println!("  {budget}");
                }
                if let Some(gate) = &res.playability_gate {
                    println!("  {gate}");
                }
                println!("  QC:  {}", res.out_qc);
                println!("  PNG: {}", res.out_png);
                Ok(())
            } else {
                eprintln!("Nav generation failed for {map}:");
                for line in &res.stdout_tail {
                    eprintln!("  {line}");
                }
                std::process::exit(1);
            }
        }
        Some("analyze") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args.is_empty()
                || sub_args
                    .iter()
                    .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp analyze <log_path> [options]\n\
                     \n\
                     Analyze match telemetry log and generate brief/charts."
                );
                return Ok(());
            }
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            run_python_script(&cfg, "tools/analyze_match.py", &sub_args)
        }
        Some("harvest") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args
                .iter()
                .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp harvest [options]\n\
                     \n\
                     Harvest human listen server session and demos into runs/.\n\
                     \n\
                     Options:\n\
                       --tag <name>   Tag label for the harvested run (e.g. v398)\n\
                       --dry-run      Inspect session without moving files"
                );
                return Ok(());
            }
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            run_python_script(&cfg, "tools/harvest_session.py", &sub_args)
        }
        Some("reach") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args
                .iter()
                .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp reach [map]\n\
                     \n\
                     Inspect directed item reachability for shipped navigation graphs."
                );
                return Ok(());
            }
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            run_python_script(&cfg, "tools/argus_reach.py", &sub_args)
        }
        Some("campaign") => {
            let sub_args: Vec<String> = args.collect();
            if sub_args.is_empty()
                || sub_args
                    .iter()
                    .any(|a| a == "-h" || a == "--help" || a == "help")
            {
                println!(
                    "usage: argus-mcp campaign <map> [options]\n\
                     \n\
                     Run campaign/co-op experiment and evaluate against win/checkpoint triggers and fail taxonomy.\n\
                     \n\
                     Options:\n\
                       --seat <solo|companion>  Seat mode (default: solo)\n\
                       --duration <sec>         Wall-clock seconds (default: 60, 10..=300)\n\
                       --skill <0..3>           Bot skill (default: 2)\n\
                       --no-compile             Skip QuakeC compilation\n\
                       --json                   Output only JSON report"
                );
                return Ok(());
            }
            let map = &sub_args[0];
            argus_mcp::engine::validate_map(map).map_err(|e| anyhow::anyhow!(e))?;
            let mut seat = "solo".to_string();
            let mut duration: u32 = 60;
            let mut skill: Option<u32> = None;
            let mut compile = true;
            let mut json_only = false;

            let mut idx = 1;
            while idx < sub_args.len() {
                match sub_args[idx].as_str() {
                    "--seat" => {
                        idx += 1;
                        if idx < sub_args.len() {
                            seat = sub_args[idx].clone();
                        }
                    }
                    "--duration" => {
                        idx += 1;
                        if idx < sub_args.len() {
                            duration = sub_args[idx].parse().unwrap_or(60);
                        }
                    }
                    "--skill" => {
                        idx += 1;
                        if idx < sub_args.len() {
                            skill = sub_args[idx].parse().ok();
                        }
                    }
                    "--no-compile" => {
                        compile = false;
                    }
                    "--json" => {
                        json_only = true;
                    }
                    _ => {}
                }
                idx += 1;
            }

            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            if compile {
                println!("Compiling QuakeC progs.dat...");
                let cres = argus_mcp::compile::compile_qc(&cfg, true);
                if !cres.ok {
                    eprintln!("QuakeC compilation failed!");
                    std::process::exit(1);
                }
            }

            println!("Running campaign match on {map} (seat={seat}, duration={duration}s)...");
            let mut mc = argus_mcp::match_ctrl::MatchCtrl::default();
            let run_name = format!("campaign_{}_{}", map, seat);

            let stop_puppet = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
            let puppet_thread = if seat == "companion" {
                let stop_clone = std::sync::Arc::clone(&stop_puppet);
                Some(std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(1500));
                    if let Ok(mut puppet) =
                        argus_mcp::netclient::NetClient::connect("127.0.0.1", 26000, "puppet")
                    {
                        while !stop_clone.load(std::sync::atomic::Ordering::Relaxed) {
                            puppet.pump(std::time::Duration::from_millis(100));
                        }
                        puppet.disconnect();
                    }
                }))
            } else {
                None
            };

            let ran = mc
                .run(
                    &cfg,
                    map,
                    duration,
                    Some(&run_name),
                    None,
                    skill,
                    Some(true),
                )
                .await;

            if let Some(th) = puppet_thread {
                stop_puppet.store(true, std::sync::atomic::Ordering::Relaxed);
                let _ = th.join();
            }

            let ran = ran.map_err(|e| anyhow::anyhow!(e))?;

            let log_text = std::fs::read_to_string(&ran.log_path)
                .map_err(|e| anyhow::anyhow!("failed to read log {}: {}", ran.log_path, e))?;
            let report = argus_mcp::campaign::evaluate_campaign_log(
                &log_text,
                map,
                &seat,
                &ran.log_path,
                ran.elapsed_sec,
                argus_mcp::intel::hull0_for_map(&cfg, map).as_ref(),
            );

            if json_only {
                println!("{}", serde_json::to_string_pretty(&report)?);
            } else {
                println!("{}", report.summary_line);
                println!("{}", serde_json::to_string_pretty(&report)?);
            }
            if !report.ok {
                std::process::exit(1);
            }
            Ok(())
        }
        Some("-h" | "--help" | "help") => {
            print_help();
            Ok(())
        }
        Some(other) => {
            anyhow::bail!("unknown command {other:?}; try argus-mcp --help");
        }
        None => run_stdio().await,
    }
}

fn run_python_script(
    cfg: &argus_mcp::config::Config,
    script_rel: &str,
    args: &[String],
) -> anyhow::Result<()> {
    let script = cfg.root.join(script_rel);
    if !script.exists() {
        anyhow::bail!("Script not found: {}", script.display());
    }
    let status = std::process::Command::new(&cfg.python)
        .arg(&script)
        .args(args)
        .current_dir(&cfg.root)
        .status()
        .map_err(|e| anyhow::anyhow!("Failed to execute python: {e}"))?;
    if !status.success() {
        std::process::exit(status.code().unwrap_or(1));
    }
    Ok(())
}

fn print_history_help() {
    println!(
        "usage: argus-mcp history [--map M] [--metric M] [--kind bot|human]
       argus-mcp history --bisect <metric> --map <map>

Change points over the tape corpus: every dated step in every metric on every
map, with a permutation p. Read-only, CSV out.

--bisect localises one step with a noisy oracle (probabilistic bisection) and
names the date to spend the next tapes at when it cannot settle.

examples
  argus-mcp history --map dm2 --metric stalls
  argus-mcp history --kind human
  argus-mcp history --map dm2 --tick listen
  argus-mcp history --bisect stalls --map dm2 --since 2026-08-20",
    );
}

fn print_corpus_help() {
    println!(
        "usage: argus-mcp corpus [filters] [--metric M [--group-by G]] [--write|--rebuild]

Ask the whole tape corpus a question. Read-only, CSV out.

filters   --map dm4  --kind bot|human  --tick listen|dedicated_fast
          --run <substring of the run name>  --since YYYY-MM-DD  --until YYYY-MM-DD
aggregate --metric stalls|engages|lava_deaths|world_deaths|freezes|freeze_underfire|
                   cover|goals|frags|deaths|routefails|hazards|grabs|weapons|boards|
                   kd_spread|avg_speed|duration_sec
          --group-by map|month|day|tick_class|kind|run
other     --limit N   --cells (hotspot cells instead of tapes)
          --write (persist the index)  --rebuild (re-parse every tape, then write)

Without --metric it returns the matching tapes. With one it returns n, IQM,
median, mean, sd, CV, min and max per group.

examples
  argus-mcp corpus --map dm2 --kind bot --metric stalls --group-by month
  argus-mcp corpus --run ab_dm4_leadclip --metric engages",
    );
}

fn print_soak_help() {
    println!(
        "usage: argus-mcp soak [options]\n\
         \n\
         Unattended match loop with gated verdicts.\n\
         \n\
         Options:\n\
           --maps <list>      Comma-separated map list (default: dm4,dm2,dm6)\n\
           --hours <n>        Wall clock cap in hours (default: 4.0, max: 12.0)\n\
           --matches <n>      Match cap (default: 60, max: 500)\n\
           --duration <sec>   Seconds per match (default: 185, 60..=600)\n\
           --skill <0..3>     Bot skill (default: 2)\n\
           --max-mb <n>       Max bytes written (default: 200)\n\
           --parallel <1|2>   Run one or two engine workers (default: 1)\n\
           --learn            Fold learned hotspots into costs.json\n\
           (Stop early any time by creating runs/soak.stop)"
    );
}

fn print_client_help() {
    println!(
        "usage: argus-mcp client <subcommand> [args...]\n\
         \n\
         Puppet NetQuake client commands:\n\
           observe [secs] [host] [port]           Observe world and print state\n\
           walk <x> <y> <z> [secs] [host] [port]  Walk puppet toward target coords\n\
           walkrel <dx> <dy> [secs]               Walk puppet relative to spawn\n\
           impulse <n> [secs] [host] [port]       Fire impulse (101=add bot, 100=menu, 210=cam)"
    );
}

async fn run_stdio() -> anyhow::Result<()> {
    // swap a newer staged build into place for the NEXT restart and
    // arm the session-wide staleness banner (see stale.rs)
    let _ = argus_mcp::stale::detect_and_swap();
    let server = Argus::new();
    let running = server.clone().serve(stdio()).await?;
    let _ = running.waiting().await;
    server.shutdown().await;
    Ok(())
}

fn print_help() {
    eprintln!(
        "Argus lab\n\
         \n\
         argus-mcp              stdio MCP server (default)\n\
         argus-mcp gui          localhost deploy wizard (127.0.0.1:7420)\n\
         argus-mcp gui --port N\n\
         argus-mcp gui --no-open\n\
         argus-mcp soak         unattended match loop with gated verdicts\n\
           --maps dm4,dm2,dm6   round-robin map list\n\
           --hours 4            wall clock cap (max 12)\n\
           --matches 60         match cap (max 500)\n\
           --duration 185       seconds per match\n\
           --skill 2\n\
           --max-mb 200         bytes-written cap (a night is <10 MB)\n\
           --parallel 2         run two engines (ports default+26011)\n\
           --learn              fold hotspots into costs.json at the end\n\
           (stop early any time: create runs/soak.stop)\n\
         argus-mcp cycle <map>  one guarded learning cycle: learn ->\n\
                                regen -> compile -> probe; adopts only\n\
                                on an improved verdict, else restores\n\
                                the snapshot byte for byte\n\
         argus-mcp demo <stem>[:export]\n\
                                parse a harvested .dem (append :export\n\
                                to also write <stem>.tracks.json)\n\
         argus-mcp probelinks <map> [limit] [skip] [--coop] [--jumps]\n\
                                empirical link verification: puppet walks\n\
                                navigation graph links in the real engine\n\
         argus-mcp client observe [secs] [host] [port]\n\
                                connect as a real NetQuake client and\n\
                                report the live world (default\n\
                                127.0.0.1:26000)\n\
         argus-mcp client walk <x> <y> <z> [secs]\n\
                                puppet walk toward a point; reports\n\
                                closest approach\n\
         argus-mcp client walkrel <dx> <dy> [secs]\n\
         argus-mcp client attack [secs] [yaw] [pitch]\n\
              connects as labfoe, which bots CAN see, and holds fire\n\
                                puppet walk relative to current spawn\n\
         argus-mcp client impulse <n> [secs]\n\
                                fire an impulse from puppet client (e.g. 101=bot, 100=menu, 210=cam)\n\
         argus-mcp compile [--install] [--backup]\n\
                                compile QuakeC progs.dat with fteqcc\n\
         argus-mcp nav <map> [--register]\n\
                                generate navigation graph; first registration\n\
                                needs current reach and mill evidence\n\
         argus-mcp analyze <log_path> [options]\n\
                                analyze match telemetry log and generate brief\n\
         argus-mcp harvest [--tag <name>]\n\
                                harvest listen server session and demos\n\
         argus-mcp reach [map]\n\
                                verify directed reach of shipped graphs\n\
         argus-mcp campaign <map> [options]\n\
                                run campaign lab experiment and evaluate against win/checkpoint triggers and fail taxonomy\n"
    );
}
