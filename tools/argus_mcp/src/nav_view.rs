//! Graph views enriched with optional map items. The graph parser stays a leaf.
use crate::cartograph::{band_label, cartograph, item_value, ControlItem};
use crate::config::Config;
use crate::nav_graph::{load_nav, nearest_node, route_nodes, NavEdge, NavGraph, Route};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct NodeDeep {
    pub map: String,
    pub node: u32,
    pub origin: [f32; 3],
    pub band: String,
    pub nearby_control: Vec<String>,
    pub atlas: String,
    pub out: Vec<NavEdge>,
    pub inn: Vec<NavEdge>,
    pub degree: usize,
    pub exposure: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cover_target: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cover_hop: Option<u32>,
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
    let (nearby, atlas) = nearby_control(cfg, map, id);
    let band = band_label(&g.map, origin[2]);
    Ok(NodeDeep {
        map: g.map,
        node: id,
        origin,
        band,
        nearby_control: nearby,
        atlas,
        out: g.adj[i].clone(),
        inn,
        degree: g.adj[i].len(),
        exposure: g.exposure.get(i).copied().unwrap_or(0),
        cover_target: g.cover_targets.get(i).and_then(|v| v.map(|x| x.0)),
        cover_hop: g.cover_targets.get(i).and_then(|v| v.map(|x| x.1)),
    })
}

fn nearby_control(cfg: &Config, map: &str, id: u32) -> (Vec<String>, String) {
    match cartograph(cfg, map) {
        Ok(atlas) => (
            atlas
                .control
                .iter()
                .filter(|c| c.nearest_node == Some(id))
                .map(|c| format!("{} ({})", c.classname, c.reach))
                .collect(),
            "available".into(),
        ),
        Err(error) => (Vec::new(), format!("unavailable: {error}")),
    }
}

pub fn route_ref(cfg: &Config, raw: &str) -> Result<Route, String> {
    route_checked(cfg, raw).map_err(|e| e.to_string())
}

pub fn route_checked(cfg: &Config, raw: &str) -> Result<Route, crate::inspection_error::Failure> {
    use crate::inspection_error::Failure;
    let spec = parse_path_ref(raw)
        .ok_or_else(|| Failure::bad("name=dm4:56-72 or dm4:56->72 or dm4:quad->lg"))?;
    match std::fs::metadata(cfg.src.join(format!("argus_nav_{}.qc.json", spec.map))) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return Err(Failure::missing(format!("no nav graph for {}", spec.map)))
        }
        Err(e) => return Err(e.to_string().into()),
        Ok(_) => {}
    }
    let g = load_nav(cfg, &spec.map)?;
    let atlas = if matches!(&spec.from, End::Item(_)) || matches!(&spec.to, End::Item(_)) {
        Some(cartograph(cfg, &spec.map).map_err(|e| format!("atlas unavailable: {e}"))?)
    } else {
        None
    };
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

fn resolve_end(
    g: &NavGraph,
    control: Option<&[ControlItem]>,
    end: &End,
) -> Result<Resolved, crate::inspection_error::Failure> {
    use crate::inspection_error::Failure;
    match end {
        End::Node(id) => {
            if *id as usize >= g.nodes.len() {
                return Err(Failure::bad(format!(
                    "node {id} out of range (0..{})",
                    g.nodes.len()
                )));
            }
            Ok(Resolved {
                id: *id,
                label: format!("n{id}"),
            })
        }
        End::Item(token) => {
            let control = control.ok_or("no atlas to resolve item")?;
            let item = resolve_item(control, token)
                .ok_or_else(|| Failure::bad(format!("no control item matching {token}")))?;
            let id = item
                .nearest_node
                .ok_or_else(|| format!("{} is off-graph ({})", item.classname, item.reach))?;
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
    let normalized = crate::paths::map_name(map)?;
    let map = normalized.as_str();
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
    let atlas = cartograph(cfg, map);
    let atlas_state = match &atlas {
        Ok(_) => "available".to_string(),
        Err(error) => format!("unavailable: {error}"),
    };
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
        "atlas": atlas_state,
    }))
}

pub fn item_view(cfg: &Config, raw: &str) -> Result<serde_json::Value, String> {
    let (map, token) = raw.split_once(':').unwrap_or(("dm4", raw));
    let normalized = crate::paths::map_name(map)?;
    let map = normalized.as_str();
    let atlas = cartograph(cfg, map).map_err(|e| format!("atlas unavailable: {e}"))?;
    let item = resolve_item(&atlas.control, token)
        .cloned()
        .ok_or_else(|| format!("no control item matching {token} on {map}"))?;
    let node = item
        .nearest_node
        .map(|id| node_deep(cfg, map, id))
        .transpose()?;
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
        map: crate::paths::map_name(map).ok()?,
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
    fn graph_query_exposes_missing_atlas_instead_of_an_empty_area() {
        let dir = crate::test_support::TestDir::new("graph-without-bsp").unwrap();
        let cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([(
                "ARGUS_ROOT".into(),
                dir.path().display().to_string(),
            )]),
            dir.path(),
        )
        .unwrap();
        std::fs::create_dir_all(&cfg.src).unwrap();
        std::fs::write(
            cfg.src.join("argus_nav_dm4.qc.json"),
            r#"{"nodes":[[0,0,0],[100,0,0]],"links":[[0,1,0]]}"#,
        )
        .unwrap();
        let node = serde_json::to_value(node_deep(&cfg, "dm4", 0).unwrap()).unwrap();
        assert!(
            node["atlas"]
                .as_str()
                .is_some_and(|s| s.starts_with("unavailable:")),
            "{node}"
        );
        let error = route_ref(&cfg, "dm4:quad->lg").unwrap_err();
        assert!(error.contains("atlas unavailable:"), "{error}");
        assert!(route_ref(&cfg, "dm4:0->1").unwrap().ok);
        let area = around_point(&cfg, "DM4:0,0,0").unwrap();
        assert_eq!(area["map"], "dm4");
        assert!(area["atlas"].as_str().unwrap().starts_with("unavailable:"));
        assert!(item_view(&cfg, "dm4:quad")
            .unwrap_err()
            .contains("atlas unavailable:"));
    }

    #[test]
    fn parses_node_and_item_paths() {
        let a = parse_path_ref("dm4:56-72").unwrap();
        assert_eq!(a.map, "dm4");
        let b = parse_path_ref("dm4:quad->lg").unwrap();
        assert!(matches!(b.from, End::Item(_)));
        assert!(parse_path_ref("56-72").is_none());
    }
}
