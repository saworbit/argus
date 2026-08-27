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
            let opts = argus_mcp::soak::parse_soak_args(args).map_err(|e| anyhow::anyhow!(e))?;
            argus_mcp::soak::run_soak(opts).await.map_err(|e| anyhow::anyhow!(e))
        }
        Some("cycle") => {
            let map = args.next().ok_or_else(|| anyhow::anyhow!("usage: argus-mcp cycle <map>"))?;
            argus_mcp::soak::run_cycle(&map).await.map_err(|e| anyhow::anyhow!(e))
        }
        Some("demo") => {
            // CLI face of see what=demo, so demos read without an MCP
            // client (append :export to also write <stem>.tracks.json)
            let name = args
                .next()
                .ok_or_else(|| anyhow::anyhow!("usage: argus-mcp demo <stem>[:export]"))?;
            let cfg = argus_mcp::config::Config::load().map_err(|e| anyhow::anyhow!("{e:?}"))?;
            let brief =
                argus_mcp::demo::demo_brief(&cfg, &name).map_err(|e| anyhow::anyhow!(e))?;
            println!("{}", serde_json::to_string_pretty(&brief)?);
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

async fn run_stdio() -> anyhow::Result<()> {
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
           --learn              fold hotspots into costs.json at the end\n\
           (stop early any time: create runs/soak.stop)\n\
         argus-mcp cycle <map>  one guarded learning cycle: learn ->\n\
                                regen -> compile -> probe; adopts only\n\
                                on an improved verdict, else restores\n\
                                the snapshot byte for byte\n\
         argus-mcp demo <stem>[:export]\n\
                                parse a harvested .dem (append :export\n\
                                to also write <stem>.tracks.json)\n"
    );
}
