//! Localhost deploy wizard. `argus-mcp gui` opens this page.

use crate::backup::{list_backups, restore_backup, take_backup};
use crate::bsp::parse_bsp29;
use crate::cartograph::{atlas_brief, cartograph, list_maps};
use crate::compile::compile_qc;
use crate::config::Config;
use crate::nav_graph::load_nav;
use crate::navgen::nav_generate;

use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

const PAGE: &str = include_str!("gui.html");
const DEFAULT_PORT: u16 = 7420;

pub struct GuiOpts {
    pub port: u16,
    pub open_browser: bool,
}

impl Default for GuiOpts {
    fn default() -> Self {
        Self {
            port: DEFAULT_PORT,
            open_browser: true,
        }
    }
}

pub fn parse_gui_args<I, S>(args: I) -> GuiOpts
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut opts = GuiOpts::default();
    let mut it = args.into_iter();
    while let Some(a) = it.next() {
        match a.as_ref() {
            "--port" => {
                if let Some(p) = it.next() {
                    if let Ok(n) = p.as_ref().parse() {
                        opts.port = n;
                    }
                }
            }
            "--no-open" => opts.open_browser = false,
            _ => {}
        }
    }
    opts
}

/// The port actually bound, so the POST guard can check the Host header
/// against it. serve_gui falls back to an ephemeral port when the
/// requested one is busy, so opts.port is not it.
static GUI_PORT: std::sync::atomic::AtomicU16 = std::sync::atomic::AtomicU16::new(0);

/// Bind 127.0.0.1 and serve until `stop` is set (or forever if None).
pub fn serve_gui(opts: GuiOpts, stop: Option<Arc<AtomicBool>>) -> Result<u16, String> {
    let addr = format!("127.0.0.1:{}", opts.port);
    let listener = TcpListener::bind(&addr)
        .or_else(|_| TcpListener::bind("127.0.0.1:0"))
        .map_err(|e| format!("bind: {e}"))?;
    listener
        .set_nonblocking(true)
        .map_err(|e| format!("nonblocking: {e}"))?;
    let port = listener
        .local_addr()
        .map_err(|e| format!("local_addr: {e}"))?
        .port();
    GUI_PORT.store(port, std::sync::atomic::Ordering::Relaxed);
    let url = format!("http://127.0.0.1:{port}/");
    eprintln!("Argus lab GUI on {url} (localhost only)");
    if opts.open_browser {
        open_browser(&url);
    }
    loop {
        if stop.as_ref().is_some_and(|s| s.load(Ordering::Relaxed)) {
            break;
        }
        match listener.accept() {
            Ok((stream, _)) => {
                thread::spawn(move || {
                    if let Err(e) = handle_conn(stream) {
                        eprintln!("gui conn: {e}");
                    }
                });
            }
            Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(40));
            }
            Err(e) => return Err(format!("accept: {e}")),
        }
    }
    Ok(port)
}

pub fn run_gui(opts: GuiOpts) -> Result<(), String> {
    serve_gui(opts, None).map(|_| ())
}

fn open_browser(url: &str) {
    let _ = if cfg!(windows) {
        std::process::Command::new("cmd")
            .args(["/C", "start", "", url])
            .spawn()
    } else {
        std::process::Command::new("xdg-open").arg(url).spawn()
    };
}

struct Request {
    method: String,
    path: String,
    query: HashMap<String, String>,
    body: Vec<u8>,
    headers: HashMap<String, String>,
}

fn handle_conn(mut stream: TcpStream) -> Result<(), String> {
    let _ = stream.set_read_timeout(Some(Duration::from_secs(120)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(120)));
    let req = read_request(&mut stream)?;
    let resp = route(&req);
    write_response(&mut stream, &resp)
}

fn read_request(stream: &mut TcpStream) -> Result<Request, String> {
    let mut buf = Vec::new();
    let mut tmp = [0u8; 4096];
    let header_end;
    loop {
        let n = stream.read(&mut tmp).map_err(|e| e.to_string())?;
        if n == 0 {
            return Err("client closed".into());
        }
        buf.extend_from_slice(&tmp[..n]);
        if let Some(i) = find_double_crlf(&buf) {
            header_end = i;
            break;
        }
        if buf.len() > 64 * 1024 {
            return Err("headers too large".into());
        }
    }
    let header = std::str::from_utf8(&buf[..header_end]).map_err(|e| e.to_string())?;
    let mut lines = header.split("\r\n");
    let start = lines.next().unwrap_or("");
    let mut parts = start.split_whitespace();
    let method = parts.next().unwrap_or("GET").to_string();
    let raw_path = parts.next().unwrap_or("/").to_string();
    let mut headers = HashMap::new();
    for line in lines {
        if let Some((k, v)) = line.split_once(':') {
            headers.insert(k.trim().to_ascii_lowercase(), v.trim().to_string());
        }
    }
    let (path, query) = split_query(&raw_path);
    let want = headers
        .get("content-length")
        .and_then(|s| s.parse::<usize>().ok())
        .unwrap_or(0);
    if want > 32 * 1024 * 1024 {
        return Err("body too large".into());
    }
    let mut body = buf[header_end + 4..].to_vec();
    while body.len() < want {
        let n = stream.read(&mut tmp).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        body.extend_from_slice(&tmp[..n]);
    }
    body.truncate(want);
    Ok(Request {
        method,
        path,
        query,
        body,
        headers,
    })
}

fn find_double_crlf(buf: &[u8]) -> Option<usize> {
    buf.windows(4).position(|w| w == b"\r\n\r\n")
}

fn split_query(raw: &str) -> (String, HashMap<String, String>) {
    match raw.split_once('?') {
        Some((p, q)) => {
            let mut m = HashMap::new();
            for pair in q.split('&') {
                if let Some((k, v)) = pair.split_once('=') {
                    m.insert(url_decode(k), url_decode(v));
                }
            }
            (p.to_string(), m)
        }
        None => (raw.to_string(), HashMap::new()),
    }
}

fn url_decode(s: &str) -> String {
    let mut out = Vec::new();
    let b = s.as_bytes();
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            // slice by BYTE index only when those two bytes really are
            // hex digits: a percent followed by a multibyte character
            // used to slice mid-codepoint and panic the connection
            // thread
            b'%' if i + 2 < b.len()
                && b[i + 1].is_ascii_hexdigit()
                && b[i + 2].is_ascii_hexdigit() =>
            {
                let hi = (b[i + 1] as char).to_digit(16).unwrap_or(0) as u8;
                let lo = (b[i + 2] as char).to_digit(16).unwrap_or(0) as u8;
                out.push(hi * 16 + lo);
                i += 3;
            }
            c => {
                out.push(c);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

struct Response {
    status: u16,
    content_type: &'static str,
    body: Vec<u8>,
}

fn text(status: u16, body: &str) -> Response {
    Response {
        status,
        content_type: "text/plain; charset=utf-8",
        body: body.as_bytes().to_vec(),
    }
}

fn html(body: &str) -> Response {
    Response {
        status: 200,
        content_type: "text/html; charset=utf-8",
        body: body.as_bytes().to_vec(),
    }
}

fn json_ok(v: &impl serde::Serialize) -> Response {
    let body = serde_json::to_vec_pretty(v).unwrap_or_else(|_| b"{}".to_vec());
    Response {
        status: 200,
        content_type: "application/json",
        body,
    }
}

fn png_bytes(data: Vec<u8>) -> Response {
    Response {
        status: 200,
        content_type: "image/png",
        body: data,
    }
}

fn write_response(stream: &mut TcpStream, resp: &Response) -> Result<(), String> {
    let reason = match resp.status {
        200 => "OK",
        400 => "Bad Request",
        404 => "Not Found",
        405 => "Method Not Allowed",
        _ => "Error",
    };
    let head = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n",
        resp.status,
        reason,
        resp.content_type,
        resp.body.len()
    );
    stream.write_all(head.as_bytes()).map_err(|e| e.to_string())?;
    stream.write_all(&resp.body).map_err(|e| e.to_string())?;
    Ok(())
}

/// The wizard is meant to be left running while the user browses, and
/// these POST endpoints rewrite the source tree and every installed
/// progs.dat. A page on any other origin could reach them as a simple
/// cross-site request: text/plain body, no preflight, no token. Require
/// a same-origin Host, no cross-origin Origin, and real JSON.
fn post_allowed(req: &Request) -> Result<(), Response> {
    let port = GUI_PORT.load(std::sync::atomic::Ordering::Relaxed);
    let host = req.headers.get("host").map(|s| s.as_str()).unwrap_or("");
    let want_a = format!("127.0.0.1:{port}");
    let want_b = format!("localhost:{port}");
    if host != want_a && host != want_b {
        return Err(text(403, "bad Host header"));
    }
    if let Some(origin) = req.headers.get("origin") {
        let o = origin.trim_end_matches('/');
        if o != format!("http://{want_a}") && o != format!("http://{want_b}") {
            return Err(text(403, "cross-origin request refused"));
        }
    }
    let ctype = req
        .headers
        .get("content-type")
        .map(|s| s.as_str())
        .unwrap_or("");
    // a simple cross-site fetch can only send text/plain,
    // x-www-form-urlencoded or multipart/form-data; anything else needs
    // a preflight, which the Origin check above then refuses. /api/attach
    // uploads a BSP as octet-stream.
    if !ctype.starts_with("application/json")
        && !ctype.starts_with("application/octet-stream")
    {
        return Err(text(
            415,
            "POST needs Content-Type: application/json or application/octet-stream",
        ));
    }
    Ok(())
}

fn route(req: &Request) -> Response {
    if req.method == "POST" {
        if let Err(r) = post_allowed(req) {
            return r;
        }
    }
    match (req.method.as_str(), req.path.as_str()) {
        ("GET", "/") => html(PAGE),
        ("GET", "/api/status") => json_ok(&status_payload()),
        (m, p) if m == "GET" && p.starts_with("/api/nav/") => map_nav_graph(&p["/api/nav/".len()..]),
        (m, p) if m == "GET" && p.starts_with("/api/map/") => map_brief(&p["/api/map/".len()..]),
        (m, p) if m == "GET" && p.starts_with("/api/png/") => map_png(&p["/api/png/".len()..]),
        ("POST", "/api/config") => set_config(&req.body),
        ("POST", "/api/attach") => attach_bsp(req),
        ("POST", "/api/backup") => do_backup(),
        ("POST", "/api/generate") => do_generate(&req.body),
        ("POST", "/api/compile") => do_compile(),
        ("POST", "/api/compare") => do_compare(&req.body),
        ("POST", "/api/restore") => do_restore(&req.body),
        ("GET", _) => text(404, "not found"),
        _ => text(405, "method not allowed"),
    }
}

/// Overrides the wizard has been given, held here rather than pushed
/// into the process environment. set_var from a connection thread while
/// other request threads walk std::env::vars() is the unsynchronised
/// setenv race, and it mutated the whole process for every other caller
/// besides.
static OVERRIDES: std::sync::Mutex<Option<HashMap<String, String>>> =
    std::sync::Mutex::new(None);

fn set_override(key: &str, value: String) {
    let mut g = OVERRIDES.lock().unwrap_or_else(|e| e.into_inner());
    g.get_or_insert_with(HashMap::new).insert(key.into(), value);
}

fn merged_env() -> HashMap<String, String> {
    let mut env: HashMap<String, String> = std::env::vars().collect();
    if let Ok(g) = OVERRIDES.lock() {
        if let Some(over) = g.as_ref() {
            for (k, v) in over {
                env.insert(k.clone(), v.clone());
            }
        }
    }
    env
}

fn cfg_read() -> Result<Config, String> {
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    crate::config::load_for_reads_from(&merged_env(), &cwd).map_err(|e| e.to_string())
}

fn cfg_full() -> Result<Config, String> {
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    crate::config::load_from(&merged_env(), &cwd).map_err(|e| e.to_string())
}

fn status_payload() -> serde_json::Value {
    let cwd = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    let report = crate::config::report_from(&merged_env(), &cwd);
    let cfg = cfg_read().ok();
    let maps = cfg
        .as_ref()
        .and_then(|c| list_maps(c).ok())
        .unwrap_or_default()
        .into_iter()
        .map(|m| {
            let dispatcher = cfg
                .as_ref()
                .map(|c| dispatcher_knows(c, &m.name))
                .unwrap_or(false);
            json!({
                "name": m.name,
                "source": m.source,
                "has_bsp": m.path.is_some(),
                "has_nav": m.has_nav,
                "dispatcher": dispatcher,
            })
        })
        .collect::<Vec<_>>();
    let backups = cfg.as_ref().map(list_backups).unwrap_or_default();
    let installs = cfg
        .as_ref()
        .map(|c| {
            c.install_paths()
                .into_iter()
                .map(|p| p.display().to_string())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    json!({
        "ready": report.complete,
        "root": cfg.as_ref().map(|c| c.root.display().to_string()),
        "basedir": cfg.as_ref().map(|c| c.basedir.display().to_string()),
        "game": cfg.as_ref().map(|c| c.game.clone()),
        "config": report,
        "maps": maps,
        "backups": backups,
        "installs": installs,
    })
}

fn dispatcher_knows(cfg: &Config, map: &str) -> bool {
    let path = cfg.src.join("argus_nav_dispatch.qc");
    std::fs::read_to_string(path)
        .map(|t| t.contains(&format!("mapname == \"{map}\"")))
        .unwrap_or(false)
}

fn map_brief(name: &str) -> Response {
    let Some(map) = safe_map_name(name) else {
        return text(400, "bad map name");
    };
    let Ok(cfg) = cfg_read() else {
        return text(400, "ARGUS_ROOT missing");
    };
    match cartograph(&cfg, &map) {
        Ok(atlas) => json_ok(&atlas_brief(&atlas)),
        Err(e) => json_ok(&json!({"ok": false, "error": e})),
    }
}

#[derive(Deserialize, Default)]
struct ProbeJson {
    #[serde(default)]
    failed: Vec<[[f32; 3]; 2]>,
}

#[derive(Deserialize, Default)]
struct CostsJson {
    #[serde(default)]
    cells: Vec<CostCellJson>,
}

#[derive(Deserialize, Serialize, Clone)]
struct CostCellJson {
    kind: String,
    x: f32,
    y: f32,
    z: f32,
    count: u32,
    radius: f32,
    cost: f32,
}

fn map_nav_graph(name: &str) -> Response {
    let Some(map) = safe_map_name(name) else {
        return text(400, "bad map name");
    };
    let Ok(cfg) = cfg_read() else {
        return text(400, "ARGUS_ROOT missing");
    };
    match load_nav(&cfg, &map) {
        Ok(g) => {
            let probe_path = cfg.src.join(format!("argus_nav_{map}.probe.json"));
            let probe_data: ProbeJson = std::fs::read_to_string(&probe_path)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or_default();

            let cost_path = crate::learn::cost_path(&cfg, &map);
            let cost_data: CostsJson = std::fs::read_to_string(&cost_path)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
                .unwrap_or_default();

            let atlas = cartograph(&cfg, &map).ok();
            let mut in_edges: Vec<Vec<serde_json::Value>> = vec![Vec::new(); g.nodes.len()];
            for (from, edges) in g.adj.iter().enumerate() {
                for e in edges {
                    if (e.to as usize) < in_edges.len() {
                        in_edges[e.to as usize].push(json!({
                            "from": from,
                            "kind": e.kind,
                        }));
                    }
                }
            }

            let mut min_x = f32::MAX;
            let mut min_y = f32::MAX;
            let mut min_z = f32::MAX;
            let mut max_x = f32::MIN;
            let mut max_y = f32::MIN;
            let mut max_z = f32::MIN;

            for pos in &g.nodes {
                min_x = min_x.min(pos[0]);
                min_y = min_y.min(pos[1]);
                min_z = min_z.min(pos[2]);
                max_x = max_x.max(pos[0]);
                max_y = max_y.max(pos[1]);
                max_z = max_z.max(pos[2]);
            }

            let mut all_links = Vec::new();
            for (from, edges) in g.adj.iter().enumerate() {
                for e in edges {
                    all_links.push(json!({
                        "from": from,
                        "to": e.to,
                        "kind": e.kind,
                    }));
                }
            }

            let nodes = g
                .nodes
                .iter()
                .enumerate()
                .map(|(id, pos)| {
                    let mut refusals = 0;
                    for pair in &probe_data.failed {
                        let d1 = (pair[0][0] - pos[0])
                            .hypot(pair[0][1] - pos[1])
                            .hypot(pair[0][2] - pos[2]);
                        let d2 = (pair[1][0] - pos[0])
                            .hypot(pair[1][1] - pos[1])
                            .hypot(pair[1][2] - pos[2]);
                        if d1 < 32.0 || d2 < 32.0 {
                            refusals += 1;
                        }
                    }

                    let mut cost_mult: f32 = 1.0;
                    let mut cost_kind: Option<String> = None;
                    for c in &cost_data.cells {
                        let d = (c.x - pos[0]).hypot(c.y - pos[1]).hypot(c.z - pos[2]);
                        if d <= c.radius && c.cost > cost_mult {
                            cost_mult = c.cost;
                            cost_kind = Some(c.kind.clone());
                        }
                    }

                    let nearby: Vec<String> = atlas
                        .as_ref()
                        .map(|a| {
                            a.control
                                .iter()
                                .filter(|c| c.nearest_node == Some(id as u32))
                                .map(|c| format!("{} ({})", c.classname, c.reach))
                                .collect()
                        })
                        .unwrap_or_default();

                    let out = g.adj[id]
                        .iter()
                        .map(|e| {
                            json!({
                                "to": e.to,
                                "kind": e.kind,
                            })
                        })
                        .collect::<Vec<_>>();

                    json!({
                        "id": id,
                        "pos": pos,
                        "band": crate::cartograph::band_label(&map, pos[2]),
                        "nearby_control": nearby,
                        "out": out,
                        "inn": &in_edges[id],
                        "refusals": refusals,
                        "cost_mult": cost_mult,
                        "cost_kind": cost_kind,
                    })
                })
                .collect::<Vec<_>>();

            let refusals_list = probe_data
                .failed
                .iter()
                .map(|pair| {
                    json!({
                        "from": pair[0],
                        "to": pair[1],
                    })
                })
                .collect::<Vec<_>>();

            let hotspots_list = cost_data
                .cells
                .iter()
                .map(|c| {
                    json!({
                        "kind": c.kind,
                        "x": c.x,
                        "y": c.y,
                        "z": c.z,
                        "count": c.count,
                        "radius": c.radius,
                        "cost": c.cost,
                    })
                })
                .collect::<Vec<_>>();

            json_ok(&json!({
                "ok": true,
                "map": map,
                "bounds": {
                    "min_x": min_x,
                    "min_y": min_y,
                    "min_z": min_z,
                    "max_x": max_x,
                    "max_y": max_y,
                    "max_z": max_z,
                },
                "nodes": nodes,
                "links": all_links,
                "refusals": refusals_list,
                "hotspots": hotspots_list,
            }))
        }
        Err(e) => json_ok(&json!({"ok": false, "error": e})),
    }
}

fn map_png(name: &str) -> Response {
    let Some(map) = safe_map_name(name) else {
        return text(400, "bad map name");
    };
    let Ok(cfg) = cfg_read() else {
        return text(400, "ARGUS_ROOT missing");
    };
    for cand in [
        cfg.runs.join(format!("nav_{map}.png")),
        cfg.src.join(format!("argus_nav_{map}.png")),
    ] {
        if cand.is_file() {
            if let Ok(bytes) = std::fs::read(&cand) {
                return png_bytes(bytes);
            }
        }
    }
    text(404, "no nav png yet")
}

#[derive(Deserialize)]
struct PathBody {
    root: Option<String>,
    basedir: Option<String>,
    game: Option<String>,
}

fn set_config(body: &[u8]) -> Response {
    let parsed: PathBody = match serde_json::from_slice(body) {
        Ok(v) => v,
        Err(e) => return json_ok(&json!({"ok": false, "error": e.to_string()})),
    };
    if let Some(r) = parsed.root.filter(|s| !s.is_empty()) {
        if !Path::new(&r).is_dir() {
            return json_ok(&json!({"ok": false, "error": "root is not a directory"}));
        }
        set_override("ARGUS_ROOT", r);
    }
    if let Some(b) = parsed.basedir.filter(|s| !s.is_empty()) {
        if !Path::new(&b).is_dir() {
            return json_ok(&json!({"ok": false, "error": "basedir is not a directory"}));
        }
        set_override("ARGUS_BASEDIR", b);
    }
    if let Some(g) = parsed.game.filter(|s| !s.is_empty()) {
        if safe_map_name(&g).is_none() {
            return json_ok(&json!({"ok": false, "error": "bad game name"}));
        }
        set_override("ARGUS_GAME", g);
    }
    json_ok(&json!({"ok": true, "status": status_payload()}))
}

fn attach_bsp(req: &Request) -> Response {
    let raw_name = req
        .query
        .get("name")
        .cloned()
        .unwrap_or_else(|| "map.bsp".into());
    let Some(map) = safe_map_name(&raw_name) else {
        return json_ok(&json!({"ok": false, "error": "filename must be a simple .bsp name"}));
    };
    if req.body.len() < 4 {
        return json_ok(&json!({"ok": false, "error": "file too small"}));
    }
    if parse_bsp29(&req.body).is_err() {
        return json_ok(&json!({"ok": false, "error": "not a BSP29 file"}));
    }
    let Ok(cfg) = cfg_read() else {
        return json_ok(&json!({"ok": false, "error": "ARGUS_ROOT missing"}));
    };
    if let Err(e) = std::fs::create_dir_all(&cfg.maps) {
        return json_ok(&json!({"ok": false, "error": e.to_string()}));
    }
    let dest = cfg.maps.join(format!("{map}.bsp"));
    if let Err(e) = std::fs::write(&dest, &req.body) {
        return json_ok(&json!({"ok": false, "error": e.to_string()}));
    }
    json_ok(&json!({
        "ok": true,
        "map": map,
        "path": dest.display().to_string(),
        "bytes": req.body.len(),
    }))
}

fn do_backup() -> Response {
    let Ok(cfg) = cfg_read() else {
        return json_ok(&json!({"ok": false, "error": "ARGUS_ROOT missing"}));
    };
    json_ok(&take_backup(&cfg))
}

#[derive(Deserialize)]
struct MapBody {
    map: Option<String>,
}

fn do_generate(body: &[u8]) -> Response {
    let parsed: MapBody = serde_json::from_slice(body).unwrap_or(MapBody { map: None });
    let Some(map) = parsed.map.as_deref().and_then(safe_map_name) else {
        return json_ok(&json!({"ok": false, "error": "map required"}));
    };
    let Ok(cfg) = cfg_full() else {
        return json_ok(&json!({"ok": false, "error": "lab paths incomplete; set ARGUS_*"}));
    };
    match nav_generate(&cfg, &format!("{map}.bsp"), &map, None, None, true) {
        Ok(r) => json_ok(&r),
        Err(e) => json_ok(&json!({"ok": false, "error": e})),
    }
}

fn do_compile() -> Response {
    let Ok(cfg) = cfg_full() else {
        return json_ok(&json!({"ok": false, "error": "lab paths incomplete; set ARGUS_*"}));
    };
    let bak = take_backup(&cfg);
    if !bak.ok {
        return json_ok(&json!({"ok": false, "error": bak.error, "backup": bak}));
    }
    let mut result = compile_qc(&cfg, true);
    let extra = json!({
        "ok": result.ok,
        "backup": bak,
        "success_line": result.success_line,
        "progs_bytes": result.progs_bytes,
        "installed_to": result.installed_to,
        "new_errors": result.new_errors,
        "raw_tail": result.raw_tail,
        "error": if result.ok { None } else { result.raw_tail.pop() },
    });
    json_ok(&extra)
}

#[derive(Deserialize)]
struct CompareBody {
    map: Option<String>,
    log_a: Option<String>,
    log_b: Option<String>,
}

fn do_compare(body: &[u8]) -> Response {
    let parsed: CompareBody = match serde_json::from_slice(body) {
        Ok(v) => v,
        Err(_) => CompareBody {
            map: None,
            log_a: None,
            log_b: None,
        },
    };
    let Ok(cfg) = cfg_read() else {
        return json_ok(&json!({"ok": false, "error": "lab paths incomplete"}));
    };
    let log_a = parsed.log_a.as_deref().unwrap_or("baseline");
    let log_b = parsed.log_b.as_deref().unwrap_or("latest");
    let map = parsed.map.as_deref();
    match crate::intel::compare_runs_scaled(&cfg, log_a, log_b, map) {
        Ok(report) => {
            let lite = crate::intel::compare_lite(&report);
            json_ok(&json!({
                "ok": true,
                "gate_card": report.gate_card,
                "verdict": report.verdict,
                "headline": report.headline,
                "compare": lite,
            }))
        }
        Err(e) => json_ok(&json!({"ok": false, "error": e})),
    }
}

#[derive(Deserialize)]
struct RestoreBody {
    id: String,
}

fn do_restore(body: &[u8]) -> Response {
    let parsed: RestoreBody = match serde_json::from_slice(body) {
        Ok(v) => v,
        Err(e) => return json_ok(&json!({"ok": false, "error": e.to_string()})),
    };
    let Ok(cfg) = cfg_read() else {
        return json_ok(&json!({"ok": false, "error": "ARGUS_ROOT missing"}));
    };
    match restore_backup(&cfg, &parsed.id) {
        Ok(r) => json_ok(&r),
        Err(e) => json_ok(&json!({"ok": false, "error": e})),
    }
}

pub fn safe_map_name(s: &str) -> Option<String> {
    let s = s.trim();
    if s.contains("..") || s.contains('/') || s.contains('\\') {
        return None;
    }
    let stem = Path::new(s)
        .file_stem()
        .and_then(|x| x.to_str())
        .unwrap_or(s);
    if stem.is_empty() || stem.len() > 32 {
        return None;
    }
    if !stem
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return None;
    }
    Some(stem.to_ascii_lowercase())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_unsafe_map_names() {
        assert_eq!(safe_map_name("dm4.bsp"), Some("dm4".into()));
        assert_eq!(safe_map_name("My-Map_2"), Some("my-map_2".into()));
        assert!(safe_map_name("../evil").is_none());
        assert!(safe_map_name("foo.bar.bsp").is_none());
        assert_eq!(safe_map_name("x.exe"), Some("x".into()));
        assert!(safe_map_name("").is_none());
    }

    fn post(path: &str, headers: &[(&str, &str)]) -> Response {
        let mut h = HashMap::new();
        for (k, v) in headers {
            h.insert(k.to_string(), v.to_string());
        }
        route(&Request {
            method: "POST".into(),
            path: path.into(),
            query: HashMap::new(),
            body: b"{}".to_vec(),
            headers: h,
        })
    }

    // #214: these endpoints rewrite the source tree and every installed
    // progs.dat. A page on any other origin could reach them as a simple
    // cross-site request: text/plain body, no preflight, no token.
    #[test]
    fn post_endpoints_refuse_other_origins() {
        GUI_PORT.store(7420, std::sync::atomic::Ordering::Relaxed);
        let ok_headers = [
            ("host", "127.0.0.1:7420"),
            ("content-type", "application/json"),
        ];
        assert_eq!(
            post(
                "/api/restore",
                &[("host", "127.0.0.1:7420"), ("content-type", "text/plain")]
            )
            .status,
            415
        );
        assert_eq!(
            post(
                "/api/restore",
                &[
                    ("host", "127.0.0.1:7420"),
                    ("content-type", "application/json"),
                    ("origin", "http://evil.example"),
                ],
            )
            .status,
            403
        );
        // DNS rebinding: resolves to us, but the Host says someone else
        assert_eq!(
            post(
                "/api/restore",
                &[("host", "evil.example"), ("content-type", "application/json")]
            )
            .status,
            403
        );
        // and the wizard's own request is not blocked by the guard
        assert_ne!(post("/api/restore", &ok_headers).status, 403);
        assert_ne!(post("/api/restore", &ok_headers).status, 415);
    }

    // #214: a percent escape followed by a multibyte character used to
    // slice mid-codepoint and panic the connection thread
    #[test]
    fn url_decode_survives_a_bad_escape() {
        assert_eq!(url_decode("dm%34"), "dm4");
        assert_eq!(url_decode("%\u{e9}x"), "%\u{e9}x");
        assert_eq!(url_decode("a%zz"), "a%zz");
        assert_eq!(url_decode("%"), "%");
    }

    #[test]
    fn homepage_and_status_route() {
        let req = Request {
            method: "GET".into(),
            path: "/".into(),
            query: HashMap::new(),
            body: Vec::new(),
            headers: HashMap::new(),
        };
        let r = route(&req);
        assert_eq!(r.status, 200);
        let page = String::from_utf8_lossy(&r.body);
        assert!(page.contains("Argus lab"));
        assert!(page.contains("Drop a .bsp"));
    }

    #[test]
    fn gui_page_has_compare_gate_elements() {
        let req = Request {
            method: "GET".into(),
            path: "/".into(),
            query: HashMap::new(),
            body: Vec::new(),
            headers: HashMap::new(),
        };
        let r = route(&req);
        let page = String::from_utf8_lossy(&r.body);
        assert!(page.contains("A/B quality gates"));
        assert!(page.contains("id=\"gatecard\""));
    }

    #[test]
    fn gui_binds_localhost() {
        let stop = Arc::new(AtomicBool::new(false));
        let stop2 = stop.clone();
        let handle = thread::spawn(move || {
            serve_gui(
                GuiOpts {
                    port: 0,
                    open_browser: false,
                },
                Some(stop2),
            )
        });
        thread::sleep(Duration::from_millis(80));
        stop.store(true, Ordering::Relaxed);
        let port = handle.join().unwrap().unwrap();
        assert!(port > 0);
    }

    #[test]
    fn nav_route_for_dm4() {
        let req = Request {
            method: "GET".into(),
            path: "/api/nav/dm4".into(),
            query: HashMap::new(),
            body: Vec::new(),
            headers: HashMap::new(),
        };
        let r = route(&req);
        assert_eq!(r.status, 200);
        let val: serde_json::Value = serde_json::from_slice(&r.body).unwrap();
        assert_eq!(val["ok"], true);
        assert_eq!(val["map"], "dm4");
        assert!(val["nodes"].as_array().unwrap().len() > 100);
        assert!(val["links"].as_array().unwrap().len() > 100);
        assert!(val["bounds"]["min_x"].is_number());
    }

    #[test]
    fn nav_route_bad_map_name() {
        let req = Request {
            method: "GET".into(),
            path: "/api/nav/../bad".into(),
            query: HashMap::new(),
            body: Vec::new(),
            headers: HashMap::new(),
        };
        let r = route(&req);
        assert_eq!(r.status, 400);
    }

    #[test]
    fn gui_page_has_interactive_canvas_and_inspector() {
        let req = Request {
            method: "GET".into(),
            path: "/".into(),
            query: HashMap::new(),
            body: Vec::new(),
            headers: HashMap::new(),
        };
        let r = route(&req);
        let page = String::from_utf8_lossy(&r.body);
        assert!(page.contains("id=\"navcanvas\""));
        assert!(page.contains("id=\"inspector-card\""));
        assert!(page.contains("id=\"tog-hotspots\""));
        assert!(page.contains("id=\"tog-refusals\""));
    }
}
