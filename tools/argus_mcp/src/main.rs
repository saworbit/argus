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
            if sub_args.iter().any(|a| a == "-h" || a == "--help" || a == "help") {
                print_soak_help();
                return Ok(());
            }
            let opts = argus_mcp::soak::parse_soak_args(sub_args.into_iter()).map_err(|e| anyhow::anyhow!(e))?;
            argus_mcp::soak::run_soak(opts).await.map_err(|e| anyhow::anyhow!(e))
        }
        Some("cycle") => {
            let map = args.next().ok_or_else(|| anyhow::anyhow!("usage: argus-mcp cycle <map>"))?;
            if map == "-h" || map == "--help" || map == "help" {
                println!("usage: argus-mcp cycle <map>\n\nOne guarded learning cycle: learn -> regen -> compile -> probe.");
                return Ok(());
            }
            argus_mcp::engine::validate_map(&map).map_err(|e| anyhow::anyhow!(e))?;
            argus_mcp::soak::run_cycle(&map).await.map_err(|e| anyhow::anyhow!(e))
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
            let brief =
                argus_mcp::demo::demo_brief(&cfg, &name).map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&brief)?);
            Ok(())
        }
        Some("probelinks") => {
            // empirical link verification: the puppet walks the graph
            //   argus-mcp probelinks <map> [limit] [skip]
            let map = args
                .next()
                .ok_or_else(|| anyhow::anyhow!("usage: argus-mcp probelinks <map> [limit] [skip]"))?;
            if map == "-h" || map == "--help" || map == "help" {
                println!("usage: argus-mcp probelinks <map> [limit] [skip]\n\nEmpirical link verification: puppet walks navigation graph links.");
                return Ok(());
            }
            argus_mcp::engine::validate_map(&map).map_err(|e| anyhow::anyhow!(e))?;
            let limit: usize = args.next().and_then(|s| s.parse().ok()).unwrap_or(30);
            let skip: usize = args.next().and_then(|s| s.parse().ok()).unwrap_or(0);
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let report = argus_mcp::netclient::probe_links(&cfg, &map, limit, skip)
                .await
                .map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&report)?);
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
                "impulse" => {
                    // fire a player impulse from the puppet's seat -
                    // the roster interface (100 add bot / 102 remove)
                    // and the dev teleport (216) all become drivable
                    // headless. GitHub #2's 4-player measurement was
                    // the first customer.
                    let imp: u8 = rest
                        .first()
                        .and_then(|s| s.parse().ok())
                        .ok_or("usage: argus-mcp client impulse <n> [secs]")?;
                    let secs: f32 = rest.get(1).and_then(|s| s.parse().ok()).unwrap_or(2.0);
                    let host = rest.get(2).cloned().unwrap_or_else(|| "127.0.0.1".into());
                    let port: u16 =
                        rest.get(3).and_then(|s| s.parse().ok()).unwrap_or(26000);
                    let mut c = argus_mcp::netclient::NetClient::connect(
                        &host, port, "labprobe",
                    )?;
                    c.pump(std::time::Duration::from_secs(3));
                    c.set_impulse(imp);
                    c.pump(std::time::Duration::from_secs_f32(secs.max(0.5)));
                    c.disconnect();
                    serde_json::to_string_pretty(&serde_json::json!({
                        "impulse": imp,
                        "sent": true,
                    }))
                    .map_err(|e| e.to_string())
                }
                other => Err(format!(
                    "unknown client subcommand {other:?}; try: observe, walk, walkrel, impulse"
                )),
            })
            .await?;
            println!("{}", res.map_err(|e| anyhow::anyhow!(e))?);
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
           impulse <n> [secs] [host] [port]       Fire impulse (100=add bot, 210=cam)"
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
         argus-mcp probelinks <map> [limit] [skip]\n\
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
                                puppet walk relative to current spawn\n\
         argus-mcp client impulse <n> [secs]\n\
                                fire an impulse from puppet client (e.g. 100=bot, 210=cam)\n"
    );
}
