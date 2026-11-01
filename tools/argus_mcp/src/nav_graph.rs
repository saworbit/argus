//! Waypoint graph from navgen JSON: links, jumps, teles, BFS routes.

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

#[derive(Debug, Clone, Default)]
pub struct NavGraph {
    pub family_counts: BTreeMap<String, usize>,
    pub map: String,
    pub nodes: Vec<[f32; 3]>,
    pub adj: Vec<Vec<NavEdge>>,
    pub cam_nodes: Vec<CamNode>,
    pub exposure: Vec<u32>,
    pub cover_targets: Vec<Option<(u32, u32)>>,
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
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub train: u32,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub sprint: u32,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub door: u32,
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
    let map = crate::paths::map_name(map)?;
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
    let v: serde_json::Value = serde_json::from_str(&text).map_err(|e| format!("nav json: {e}"))?;
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

/// navgen writes the third element of a `links` entry as reciprocity
/// (1 when the reverse link also exists), not as a kind. Reading it as
/// walk-or-drop briefed every one-way link as a drop: the 7f escape
/// stitches, one-direction knit walks, trace-mined walks and every
/// reverse the slot clamp evicted. dm4 alone carries 81 one-way links
/// at the same level. Derive the kind from node height with the
/// runtime's own step rule instead.
pub(crate) const NAV_STEP: f64 = 18.0;

pub(crate) const LINK_FAMILIES: &[(&str, Option<&str>)] = &[
    ("links", None),
    ("jlinks", Some("jump")),
    ("teles", Some("tele")),
    ("rjlinks", Some("rocket")),
    ("liftlinks", Some("lift")),
    ("swimlinks", Some("swim")),
    ("doorlinks", Some("door")),
    ("trainlinks", Some("train")),
    ("sprintlinks", Some("sprint")),
];

fn link_kind(from: [f32; 3], to: [f32; 3]) -> &'static str {
    if from[2] - to[2] > NAV_STEP as f32 {
        "drop"
    } else {
        "walk"
    }
}

pub(crate) fn parse_graph(map: &str, v: &serde_json::Value) -> Result<NavGraph, String> {
    let nodes_v = v
        .get("nodes")
        .and_then(|n| n.as_array())
        .ok_or("nav json missing nodes")?;
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
            if from < n && to < n {
                let kind = link_kind(nodes[from], nodes[to]);
                push_edge(&mut adj[from], to as u32, kind);
            }
        }
    }
    for &(key, kind) in &LINK_FAMILIES[1..] {
        let error = match key {
            "jlinks" => "bad jlink",
            "teles" => "bad tele",
            _ => "bad typed link",
        };
        if let Some(list) = v.get(key).and_then(|x| x.as_array()) {
            for link in list {
                let a = link.as_array().ok_or(error)?;
                let from = a.first().and_then(|x| x.as_u64()).ok_or(error)? as usize;
                let to = a.get(1).and_then(|x| x.as_u64()).ok_or(error)? as usize;
                if from < n && to < n {
                    set_kind(&mut adj[from], to as u32, kind.expect("typed family"));
                }
            }
        }
    }
    let exposure = v
        .get("exposure")
        .and_then(|x| x.as_array())
        .map(|rows| {
            (0..n)
                .map(|i| rows.get(i).and_then(|x| x.as_u64()).unwrap_or(0) as u32)
                .collect()
        })
        .unwrap_or_else(|| vec![0; n]);
    let cover_targets = v
        .get("cover_targets")
        .and_then(|x| x.as_array())
        .map(|rows| {
            (0..n)
                .map(|i| {
                    let row = rows.get(i)?.as_array()?;
                    let target = row.first()?.as_i64()?;
                    let hop = row.get(1)?.as_i64()?;
                    if target >= 0 && hop >= 0 && target < n as i64 && hop < n as i64 {
                        Some((target as u32, hop as u32))
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_else(|| vec![None; n]);
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
        family_counts: LINK_FAMILIES
            .iter()
            .map(|(key, _)| {
                (
                    (*key).into(),
                    v.get(*key)
                        .and_then(|rows| rows.as_array())
                        .map_or(0, Vec::len),
                )
            })
            .collect(),
        map: map.to_string(),
        nodes,
        adj,
        cam_nodes,
        exposure,
        cover_targets,
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
            train: 0,
            sprint: 0,
            door: 0,
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
            train: 0,
            sprint: 0,
            door: 0,
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
            train: 0,
            sprint: 0,
            door: 0,
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
    let mut train = 0;
    let mut sprint = 0;
    let mut door = 0;
    for (node, kind) in chain {
        // the loader types these three (nav_graph.rs load, "doorlinks" /
        // "trainlinks" / "sprintlinks"); without their own arms a train
        // ride read as a plain walk in every route summary.
        match kind.as_str() {
            "drop" => drop += 1,
            "jump" => jump += 1,
            "tele" => tele += 1,
            "rocket" => rocket += 1,
            "lift" => lift += 1,
            "swim" => swim += 1,
            "train" => train += 1,
            "sprint" => sprint += 1,
            "door" => door += 1,
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
        train,
        sprint,
        door,
        path,
        ok: true,
        note: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;

    fn graph_with_bridge(family: Option<&str>) -> NavGraph {
        let mut value = serde_json::json!({
            "nodes": [[0,0,0],[100,0,0],[200,0,0],[300,0,0]],
            "links": [[0,1,1],[2,3,1]]
        });
        if let Some("links") = family {
            value["links"]
                .as_array_mut()
                .unwrap()
                .push(serde_json::json!([1, 2, 0]));
        } else if let Some(key) = family {
            value[key] = serde_json::json!([[1, 2]]);
        }
        parse_graph("metamorphic", &value).unwrap()
    }

    fn reachable_sets(graph: &NavGraph) -> Vec<BTreeSet<u32>> {
        (0..graph.nodes.len() as u32)
            .map(|from| {
                (0..graph.nodes.len() as u32)
                    .filter(|to| route_nodes(graph, from, *to).ok)
                    .collect()
            })
            .collect()
    }

    fn assert_reach_subset(before: &[BTreeSet<u32>], after: &[BTreeSet<u32>], context: &str) {
        assert_eq!(before.len(), after.len());
        for (node, (old, new)) in before.iter().zip(after).enumerate() {
            assert!(
                old.is_subset(new),
                "{context}: n{node} lost destinations {old:?} -> {new:?}"
            );
        }
    }

    // #218: element 2 of a links entry is reciprocity. Reading it as a
    // kind briefed all 206 of dm4's one-way links as drops, 81 of them
    // at the same height.
    #[test]
    fn one_way_level_link_is_a_walk_not_a_drop() {
        let v: serde_json::Value = serde_json::from_str(
            r#"{"nodes":[[0,0,24],[100,0,24],[200,0,-120]],
                "links":[[0,1,0],[1,2,0],[2,1,1],[1,2,1]]}"#,
        )
        .unwrap();
        let g = parse_graph("t", &v).unwrap();
        let kind = |from: usize, to: u32| {
            g.adj[from]
                .iter()
                .find(|e| e.to == to)
                .map(|e| e.kind.clone())
                .unwrap()
        };
        // one-way, same height: a walk, whatever the reciprocity flag says
        assert_eq!(kind(0, 1), "walk");
        // 144 below: a real drop, and its reverse is still a walk (a climb
        // the graph believes in, not a drop)
        assert_eq!(kind(1, 2), "drop");
        assert_eq!(kind(2, 1), "walk");
    }

    // The shipped dm4 graph: 206 one-way links, 81 of them level. Before
    // the fix every one of the 206 briefed as a drop.
    #[test]
    fn shipped_dm4_level_one_way_links_are_walks() {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../src/argus_nav_dm4.qc.json");
        let text = std::fs::read_to_string(&p).expect("shipped dm4 nav json is tracked");
        let v: serde_json::Value = serde_json::from_str(&text).unwrap();
        let g = parse_graph("dm4", &v).unwrap();
        let mut level_walks = 0;
        for (from, edges) in g.adj.iter().enumerate() {
            for e in edges {
                let dz = g.nodes[from][2] - g.nodes[e.to as usize][2];
                // typed hops (jump, lift, swim, rocket, ...) legitimately
                // overwrite the kind afterwards; a plain link at the same
                // height must never read as a drop
                if dz.abs() <= NAV_STEP as f32 {
                    assert_ne!(
                        e.kind, "drop",
                        "level link {from}->{} briefed as a drop",
                        e.to
                    );
                    if e.kind == "walk" {
                        level_walks += 1;
                    }
                }
            }
        }
        assert!(
            level_walks > 100,
            "expected the bulk of dm4 to be level walks"
        );
    }

    #[test]
    fn bfs_finds_short_path() {
        let g = NavGraph {
            family_counts: BTreeMap::new(),
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
            exposure: vec![0; 3],
            cover_targets: vec![None; 3],
        };
        let r = route_nodes(&g, 0, 2);
        assert!(r.ok);
        assert_eq!(r.hops, 2);
        assert_eq!(r.jump, 1);
        assert_eq!(r.walk, 1);
    }

    #[test]
    fn every_link_family_obeys_per_node_reach_monotonicity() {
        let base = graph_with_bridge(None);
        let base_reach = reachable_sets(&base);
        for (family, expected_kind) in [
            ("links", "walk"),
            ("jlinks", "jump"),
            ("teles", "tele"),
            ("rjlinks", "rocket"),
            ("liftlinks", "lift"),
            ("swimlinks", "swim"),
            ("doorlinks", "door"),
            ("trainlinks", "train"),
            ("sprintlinks", "sprint"),
        ] {
            let added = graph_with_bridge(Some(family));
            let added_reach = reachable_sets(&added);
            let removed = graph_with_bridge(None);
            let removed_reach = reachable_sets(&removed);

            // Adding an engine-verified edge cannot remove any destination
            // from any source node. Removing it is the same relation read in
            // reverse: the reduced graph cannot invent a destination.
            assert_reach_subset(&base_reach, &added_reach, family);
            assert_reach_subset(&removed_reach, &added_reach, &format!("remove {family}"));
            assert!(
                base_reach
                    .iter()
                    .zip(&added_reach)
                    .any(|(old, new)| old != new),
                "{family} fixture did not change reach"
            );
            let bridge = added.adj[1]
                .iter()
                .find(|edge| edge.to == 2)
                .expect("parsed bridge edge");
            assert_eq!(bridge.kind, expected_kind, "{family}");
        }
    }

    #[test]
    fn equal_aggregate_reach_can_hide_different_stranded_nodes() {
        let left = parse_graph(
            "left",
            &serde_json::json!({"nodes": [[0,0,0],[1,0,0],[2,0,0]], "links": [[0,1,0]]}),
        )
        .unwrap();
        let right = parse_graph(
            "right",
            &serde_json::json!({"nodes": [[0,0,0],[1,0,0],[2,0,0]], "links": [[1,2,0]]}),
        )
        .unwrap();
        let left_reach = reachable_sets(&left);
        let right_reach = reachable_sets(&right);
        let total = |sets: &[BTreeSet<u32>]| sets.iter().map(BTreeSet::len).sum::<usize>();

        assert_eq!(total(&left_reach), total(&right_reach));
        assert_ne!(left_reach, right_reach);
        assert_eq!(left_reach[0], BTreeSet::from([0, 1]));
        assert_eq!(right_reach[0], BTreeSet::from([0]));
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

    #[test]
    fn parses_tactical_node_annotations() {
        let v = serde_json::json!({
            "nodes": [[0,0,0],[100,0,0]],
            "links": [[0,1,1]],
            "exposure": [1, 0],
            "cover_targets": [[1,1],[-1,-1]]
        });
        let g = parse_graph("dm4", &v).unwrap();
        assert_eq!(g.exposure, vec![1, 0]);
        assert_eq!(g.cover_targets, vec![Some((1, 1)), None]);
    }

    #[test]
    fn typed_hops_are_not_counted_as_walks() {
        // #39: train / sprint / door edges fell through `_ => walk`, so
        // a dm2 east-deck ride briefed as a plain walk.
        let g = NavGraph {
            family_counts: BTreeMap::new(),
            map: "t".into(),
            nodes: vec![[0.0; 3], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0], [3.0, 0.0, 0.0]],
            adj: vec![
                vec![NavEdge {
                    to: 1,
                    kind: "train".into(),
                }],
                vec![NavEdge {
                    to: 2,
                    kind: "sprint".into(),
                }],
                vec![NavEdge {
                    to: 3,
                    kind: "door".into(),
                }],
                vec![],
            ],
            cam_nodes: vec![],
            exposure: vec![0; 4],
            cover_targets: vec![None; 4],
        };
        let r = route_nodes(&g, 0, 3);
        assert!(r.ok);
        assert_eq!((r.train, r.sprint, r.door), (1, 1, 1));
        assert_eq!(r.walk, 0, "typed hops leaked into the walk tally");
    }
}
