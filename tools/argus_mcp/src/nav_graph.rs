//! Waypoint graph from navgen JSON: links, jumps, teles, BFS routes.

use crate::cartograph::{cartograph, item_value, band_label, ControlItem};
use crate::config::Config;
use serde::Serialize;
use std::collections::{BTreeMap, VecDeque};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::SystemTime;

#[derive(Debug, Clone, Serialize)]
pub struct NavEdge {
    pub to: u32,
    pub kind: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct CamNode {
    pub pos: [f32; 3],
    pub ang: [f32; 3],
    pub tag: String,
}

#[derive(Debug, Clone)]
pub struct NavGraph {
    pub map: String,
    pub nodes: Vec<[f32; 3]>,
    pub adj: Vec<Vec<NavEdge>>,
    pub cam_nodes: Vec<CamNode>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NodeDeep {
    pub map: String,
    pub node: u32,
    pub origin: [f32; 3],
    pub band: String,
    pub nearby_control: Vec<String>,
    pub out: Vec<NavEdge>,
    pub inn: Vec<NavEdge>,
    pub degree: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct RouteHop {
    pub node: u32,
    pub origin: [f32; 3],
    pub via: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct Route {
    pub map: String,
    pub from: u32,
    pub to: u32,
    pub from_label: String,
    pub to_label: String,
    pub hops: usize,
    pub walk: u32,
    pub drop: u32,
    pub jump: u32,
    pub tele: u32,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub rocket: u32,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub lift: u32,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub swim: u32,
    pub path: Vec<RouteHop>,
    pub ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

fn is_zero_u32(v: &u32) -> bool {
    *v == 0
}

struct CachedGraph {
    graph: NavGraph,
    path: PathBuf,
    mtime: Option<SystemTime>,
}

static GRAPH_CACHE: Mutex<BTreeMap<String, CachedGraph>> = Mutex::new(BTreeMap::new());

pub fn load_nav(cfg: &Config, map: &str) -> Result<NavGraph, String> {
    let map = map.trim().to_ascii_lowercase();
    let path = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let mtime = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
    if let Ok(c) = GRAPH_CACHE.lock() {
        if let Some(hit) = c.get(&map) {
            if hit.path == path && hit.mtime == mtime {
                return Ok(hit.graph.clone());
            }
        }
    }
    let text = std::fs::read_to_string(&path)
        .map_err(|_| format!("no nav JSON for {map} ({})", path.display()))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("nav json: {e}"))?;
    let graph = parse_graph(&map, &v)?;
    if let Ok(mut c) = GRAPH_CACHE.lock() {
        c.insert(
            map,
            CachedGraph {
                graph: graph.clone(),
                path,
                mtime,
            },
        );
    }
    Ok(graph)
}

fn parse_graph(map: &str, v: &serde_json::Value) -> Result<NavGraph, String> {
    let nodes_v = v.get("nodes").and_then(|n| n.as_array()).ok_or("nav json missing nodes")?;
    let nodes: Vec<[f32; 3]> = nodes_v
        .iter()
        .filter_map(|n| {
            let a = n.as_array()?;
            Some([
                a.first()?.as_f64()? as f32,
                a.get(1)?.as_f64()? as f32,
                a.get(2)?.as_f64()? as f32,
            ])
        })
        .collect();
    if nodes.is_empty() {
        return Err("nav json has no nodes".into());
    }
    let n = nodes.len();
    let mut adj: Vec<Vec<NavEdge>> = vec![Vec::new(); n];
    if let Some(links) = v.get("links").and_then(|x| x.as_array()) {
        for link in links {
            let a = link.as_array().ok_or("bad link")?;
            let from = a.first().and_then(|x| x.as_u64()).ok_or("bad link from")? as usize;
            let to = a.get(1).and_then(|x| x.as_u64()).ok_or("bad link to")? as usize;
            let walk = a.get(2).and_then(|x| x.as_u64()).unwrap_or(1);
            if from < n && to < n {
                let kind = if walk == 0 { "drop" } else { "walk" };
                push_edge(&mut adj[from], to as u32, kind);
            }
        }
    }
    if let Some(jlinks) = v.get("jlinks").and_then(|x| x.as_array()) {
        for link in jlinks {
            let a = link.as_array().ok_or("bad jlink")?;
            let from = a.first().and_then(|x| x.as_u64()).ok_or("bad jlink")? as usize;
            let to = a.get(1).and_then(|x| x.as_u64()).ok_or("bad jlink")? as usize;
            if from < n && to < n {
                set_kind(&mut adj[from], to as u32, "jump");
            }
        }
    }
    if let Some(teles) = v.get("teles").and_then(|x| x.as_array()) {
        for link in teles {
            let a = link.as_array().ok_or("bad tele")?;
            let from = a.first().and_then(|x| x.as_u64()).ok_or("bad tele")? as usize;
            let to = a.get(1).and_then(|x| x.as_u64()).ok_or("bad tele")? as usize;
            if from < n && to < n {
                set_kind(&mut adj[from], to as u32, "tele");
            }
        }
    }
    // typed hop edges live outside the walk-link list: without these
    // the inspect BFS reported "no walk route" to targets that QC
    // routes over Argus_NavLinkRocket/Lift/Swim (Shane's drift list)
    for (key, kind) in [
        ("rjlinks", "rocket"),
        ("liftlinks", "lift"),
        ("swimlinks", "swim"),
        ("doorlinks", "door"),
    ] {
        if let Some(list) = v.get(key).and_then(|x| x.as_array()) {
            for link in list {
                let a = link.as_array().ok_or("bad typed link")?;
                let from = a.first().and_then(|x| x.as_u64()).ok_or("bad typed link")? as usize;
                let to = a.get(1).and_then(|x| x.as_u64()).ok_or("bad typed link")? as usize;
                if from < n && to < n {
                    set_kind(&mut adj[from], to as u32, kind);
                }
            }
        }
    }
    let mut cam_nodes = Vec::new();
    if let Some(cams) = v.get("cam_nodes").and_then(|x| x.as_array()) {
        for cam in cams {
            if let (Some(pos), Some(ang), Some(tag)) = (
                cam.get("pos").and_then(|p| p.as_array()),
                cam.get("ang").and_then(|a| a.as_array()),
                cam.get("tag").and_then(|t| t.as_str()),
            ) {
                if pos.len() == 3 && ang.len() == 3 {
                    cam_nodes.push(CamNode {
                        pos: [
                            pos[0].as_f64().unwrap_or(0.0) as f32,
                            pos[1].as_f64().unwrap_or(0.0) as f32,
                            pos[2].as_f64().unwrap_or(0.0) as f32,
                        ],
                        ang: [
                            ang[0].as_f64().unwrap_or(0.0) as f32,
                            ang[1].as_f64().unwrap_or(0.0) as f32,
                            ang[2].as_f64().unwrap_or(0.0) as f32,
                        ],
                        tag: tag.to_string(),
                    });
                }
            }
        }
    }
    Ok(NavGraph {
        map: map.to_string(),
        nodes,
        adj,
        cam_nodes,
    })
}

fn push_edge(edges: &mut Vec<NavEdge>, to: u32, kind: &str) {
    if !edges.iter().any(|e| e.to == to) {
        edges.push(NavEdge {
            to,
            kind: kind.into(),
        });
    }
}

fn set_kind(edges: &mut Vec<NavEdge>, to: u32, kind: &str) {
    if let Some(e) = edges.iter_mut().find(|e| e.to == to) {
        e.kind = kind.into();
    } else {
        edges.push(NavEdge {
            to,
            kind: kind.into(),
        });
    }
}

pub fn nearest_node(g: &NavGraph, x: f32, y: f32, z: f32) -> (u32, f32) {
    let mut best = (0u32, f32::MAX);
    for (i, p) in g.nodes.iter().enumerate() {
        let d = (p[0] - x).hypot(p[1] - y).hypot(p[2] - z);
        if d < best.1 {
            best = (i as u32, d);
        }
    }
    best
}

pub fn node_deep(cfg: &Config, map: &str, id: u32) -> Result<NodeDeep, String> {
    let g = load_nav(cfg, map)?;
    let i = id as usize;
    if i >= g.nodes.len() {
        return Err(format!("node {id} out of range (0..{})", g.nodes.len()));
    }
    let origin = g.nodes[i];
    let mut inn = Vec::new();
    for (from, edges) in g.adj.iter().enumerate() {
        for e in edges {
            if e.to == id {
                inn.push(NavEdge {
                    to: from as u32,
                    kind: e.kind.clone(),
                });
            }
        }
    }
    let nearby = nearby_control(cfg, map, id);
    Ok(NodeDeep {
        map: g.map,
        node: id,
        origin,
        band: band_label(map, origin[2]),
        nearby_control: nearby,
        out: g.adj[i].clone(),
        inn,
        degree: g.adj[i].len(),
    })
}

fn nearby_control(cfg: &Config, map: &str, id: u32) -> Vec<String> {
    cartograph(cfg, map)
        .map(|a| {
            a.control
                .iter()
                .filter(|c| c.nearest_node == Some(id))
                .map(|c| format!("{} ({})", c.classname, c.reach))
                .collect()
        })
        .unwrap_or_default()
}

pub fn route_nodes(g: &NavGraph, from: u32, to: u32) -> Route {
    let n = g.nodes.len();
    if from as usize >= n || to as usize >= n {
        return Route {
            map: g.map.clone(),
            from,
            to,
            from_label: format!("n{from}"),
            to_label: format!("n{to}"),
            hops: 0,
            walk: 0,
            drop: 0,
            jump: 0,
            tele: 0,
            rocket: 0,
            lift: 0,
            swim: 0,
            path: Vec::new(),
            ok: false,
            note: Some("node out of range".into()),
        };
    }
    if from == to {
        return Route {
            map: g.map.clone(),
            from,
            to,
            from_label: format!("n{from}"),
            to_label: format!("n{to}"),
            hops: 0,
            walk: 0,
            drop: 0,
            jump: 0,
            tele: 0,
            rocket: 0,
            lift: 0,
            swim: 0,
            path: vec![RouteHop {
                node: from,
                origin: g.nodes[from as usize],
                via: "start".into(),
            }],
            ok: true,
            note: None,
        };
    }
    let mut prev: Vec<Option<(u32, String)>> = vec![None; n];
    let mut seen = vec![false; n];
    let mut q = VecDeque::new();
    q.push_back(from);
    seen[from as usize] = true;
    while let Some(cur) = q.pop_front() {
        if cur == to {
            break;
        }
        for e in &g.adj[cur as usize] {
            if !seen[e.to as usize] {
                seen[e.to as usize] = true;
                prev[e.to as usize] = Some((cur, e.kind.clone()));
                q.push_back(e.to);
            }
        }
    }
    if !seen[to as usize] {
        return Route {
            map: g.map.clone(),
            from,
            to,
            from_label: format!("n{from}"),
            to_label: format!("n{to}"),
            hops: 0,
            walk: 0,
            drop: 0,
            jump: 0,
            tele: 0,
            rocket: 0,
            lift: 0,
            swim: 0,
            path: Vec::new(),
            ok: false,
            note: Some("no route on the waypoint graph".into()),
        };
    }
    let mut chain = Vec::new();
    let mut cur = to;
    while cur != from {
        let (p, kind) = prev[cur as usize].clone().unwrap();
        chain.push((cur, kind));
        cur = p;
    }
    chain.reverse();
    let mut path = vec![RouteHop {
        node: from,
        origin: g.nodes[from as usize],
        via: "start".into(),
    }];
    let mut walk = 0;
    let mut drop = 0;
    let mut jump = 0;
    let mut tele = 0;
    let mut rocket = 0;
    let mut lift = 0;
    let mut swim = 0;
    for (node, kind) in chain {
        match kind.as_str() {
            "drop" => drop += 1,
            "jump" => jump += 1,
            "tele" => tele += 1,
            "rocket" => rocket += 1,
            "lift" => lift += 1,
            "swim" => swim += 1,
            _ => walk += 1,
        }
        path.push(RouteHop {
            origin: g.nodes[node as usize],
            node,
            via: kind,
        });
    }
    Route {
        map: g.map.clone(),
        from,
        to,
        from_label: format!("n{from}"),
        to_label: format!("n{to}"),
        hops: path.len().saturating_sub(1),
        walk,
        drop,
        jump,
        tele,
        rocket,
        lift,
        swim,
        path,
        ok: true,
        note: None,
    }
}

pub fn route_ref(cfg: &Config, raw: &str) -> Result<Route, String> {
    let spec = parse_path_ref(raw).ok_or_else(|| {
        "name=dm4:56-72 or dm4:56->72 or dm4:quad->lg".to_string()
    })?;
    let g = load_nav(cfg, &spec.map)?;
    let atlas = cartograph(cfg, &spec.map).ok();
    let from = resolve_end(&g, atlas.as_ref().map(|a| a.control.as_slice()), &spec.from)?;
    let to = resolve_end(&g, atlas.as_ref().map(|a| a.control.as_slice()), &spec.to)?;
    let mut r = route_nodes(&g, from.id, to.id);
    r.from_label = from.label;
    r.to_label = to.label;
    Ok(r)
}

struct PathSpec {
    map: String,
    from: End,
    to: End,
}

enum End {
    Node(u32),
    Item(String),
}

struct Resolved {
    id: u32,
    label: String,
}

fn resolve_end(g: &NavGraph, control: Option<&[ControlItem]>, end: &End) -> Result<Resolved, String> {
    match end {
        End::Node(id) => {
            if *id as usize >= g.nodes.len() {
                return Err(format!("node {id} out of range (0..{})", g.nodes.len()));
            }
            Ok(Resolved {
                id: *id,
                label: format!("n{id}"),
            })
        }
        End::Item(token) => {
            let control = control.ok_or("no atlas to resolve item")?;
            let item = resolve_item(control, token)
                .ok_or_else(|| format!("no control item matching {token}"))?;
            let id = item.nearest_node.ok_or_else(|| {
                format!("{} is off-graph ({})", item.classname, item.reach)
            })?;
            Ok(Resolved {
                id,
                label: format!("{}@n{id}", item.classname),
            })
        }
    }
}

pub fn resolve_item<'a>(control: &'a [ControlItem], token: &str) -> Option<&'a ControlItem> {
    let t = token.to_ascii_lowercase();
    let class = match t.as_str() {
        "quad" => "item_artifact_super_damage",
        "lg" | "lightning" => "weapon_lightning",
        "rl" | "rocket" => "weapon_rocketlauncher",
        "gl" | "grenade" => "weapon_grenadelauncher",
        "ssg" => "weapon_supershotgun",
        "sng" => "weapon_supernailgun",
        "ng" | "nails" => "weapon_nailgun",
        "sg" | "shotgun" => "weapon_shotgun",
        "pent" => "item_artifact_invulnerability",
        "ring" => "item_artifact_invisibility",
        "mega" | "mh" => "item_health",
        "ya" | "yellow" => "item_armor2",
        "ra" | "red" => "item_armorInv",
        other => other,
    };
    control
        .iter()
        .find(|c| c.classname.eq_ignore_ascii_case(class))
        .or_else(|| {
            control.iter().find(|c| {
                c.classname.to_ascii_lowercase().contains(&t)
                    || item_value(&c.classname, 0)
                        .map(|(_, why)| why.to_ascii_lowercase().contains(&t))
                        .unwrap_or(false)
                    || c.why.to_ascii_lowercase().contains(&t)
            })
        })
}

pub fn around_point(cfg: &Config, raw: &str) -> Result<serde_json::Value, String> {
    let (map, coords) = raw.split_once(':').unwrap_or(("dm4", raw));
    let parts: Vec<&str> = coords
        .split(|c: char| c == ',' || c.is_whitespace())
        .filter(|s| !s.is_empty())
        .collect();
    if parts.len() < 3 {
        return Err("name=dm4:200,-900,24".into());
    }
    let x: f32 = parts[0].parse().map_err(|_| "bad x")?;
    let y: f32 = parts[1].parse().map_err(|_| "bad y")?;
    let z: f32 = parts[2].parse().map_err(|_| "bad z")?;
    let g = load_nav(cfg, map)?;
    let (id, dist) = nearest_node(&g, x, y, z);
    let node = node_deep(cfg, map, id)?;
    let atlas = cartograph(cfg, map).ok();
    let near_items: Vec<String> = atlas
        .as_ref()
        .map(|a| {
            let mut items: Vec<(f32, String)> = a
                .control
                .iter()
                .filter_map(|c| {
                    let o = c.origin?;
                    let d = (o[0] - x).hypot(o[1] - y).hypot(o[2] - z);
                    Some((d, format!("{} {} @ {:.0}", c.classname, c.reach, d)))
                })
                .collect();
            items.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
            items.into_iter().take(5).map(|(_, s)| s).collect()
        })
        .unwrap_or_default();
    Ok(serde_json::json!({
        "map": map,
        "at": [x, y, z],
        "nearest_node": id,
        "dist": dist,
        "node": node,
        "nearby_items": near_items,
    }))
}

pub fn item_view(cfg: &Config, raw: &str) -> Result<serde_json::Value, String> {
    let (map, token) = raw.split_once(':').unwrap_or(("dm4", raw));
    let atlas = cartograph(cfg, map)?;
    let item = resolve_item(&atlas.control, token)
        .cloned()
        .ok_or_else(|| format!("no control item matching {token} on {map}"))?;
    let node = item.nearest_node.and_then(|id| node_deep(cfg, map, id).ok());
    Ok(serde_json::json!({
        "map": atlas.map,
        "item": item,
        "node": node,
    }))
}

/// `dm4:56-72`, `dm4:56->72`, `dm4:quad->lg`
fn parse_path_ref(raw: &str) -> Option<PathSpec> {
    let raw = raw.trim();
    let (map, rest) = raw.split_once(':')?;
    if map.is_empty() || rest.is_empty() {
        return None;
    }
    let rest = rest.replace("->", "-").replace(" to ", "-");
    let (a, b) = rest.split_once('-')?;
    Some(PathSpec {
        map: map.to_ascii_lowercase(),
        from: parse_end(a.trim())?,
        to: parse_end(b.trim())?,
    })
}

fn parse_end(s: &str) -> Option<End> {
    if s.is_empty() {
        return None;
    }
    if let Ok(n) = s.parse::<u32>() {
        return Some(End::Node(n));
    }
    Some(End::Item(s.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_node_and_item_paths() {
        let a = parse_path_ref("dm4:56-72").unwrap();
        assert_eq!(a.map, "dm4");
        let b = parse_path_ref("dm4:quad->lg").unwrap();
        assert!(matches!(b.from, End::Item(_)));
        assert!(parse_path_ref("56-72").is_none());
    }

    #[test]
    fn bfs_finds_short_path() {
        let g = NavGraph {
            map: "t".into(),
            nodes: vec![[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            adj: vec![
                vec![NavEdge {
                    to: 1,
                    kind: "walk".into(),
                }],
                vec![NavEdge {
                    to: 2,
                    kind: "jump".into(),
                }],
                vec![],
            ],
            cam_nodes: vec![],
        };
        let r = route_nodes(&g, 0, 2);
        assert!(r.ok);
        assert_eq!(r.hops, 2);
        assert_eq!(r.jump, 1);
        assert_eq!(r.walk, 1);
    }

    #[test]
    fn parse_typed_hops() {
        let v = serde_json::json!({
            "nodes": [[0,0,0],[1,0,0],[2,0,80]],
            "links": [[0,1,1]],
            "rjlinks": [[1,2]],
            "liftlinks": [],
            "swimlinks": []
        });
        let g = parse_graph("t", &v).unwrap();
        assert_eq!(g.adj[1][0].kind, "rocket");
        let r = route_nodes(&g, 0, 2);
        assert!(r.ok);
        assert_eq!(r.rocket, 1);
    }

    #[test]
    fn parse_cam_nodes_vantage() {
        let v = serde_json::json!({
            "nodes": [[0,0,0],[100,0,0]],
            "links": [[0,1,1]],
            "cam_nodes": [
                {
                    "pos": [200.0, -900.0, 140.0],
                    "ang": [-15.0, 85.0, 0.0],
                    "tag": "arena_quad"
                }
            ]
        });
        let g = parse_graph("dm4", &v).unwrap();
        assert_eq!(g.cam_nodes.len(), 1);
        assert_eq!(g.cam_nodes[0].tag, "arena_quad");
        assert_eq!(g.cam_nodes[0].pos[2], 140.0);
    }
}
