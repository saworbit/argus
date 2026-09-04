//! Map cartographer: ingest a BSP and return a structured atlas.

use crate::bsp::{pak_find, pak_list_maps, read_bsp29, Bsp29, ClipHull};
use crate::config::Config;
use crate::paths::resolve_input;
use regex::Regex;
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::SystemTime;

/// Quake skill/DM filter bit. item_health spawnflags 2 is mega, not this.
const SPAWNFLAG_NOT_DEATHMATCH: u32 = 2048;

#[derive(Debug, Clone, Serialize)]
pub struct AtlasItem {
    pub classname: String,
    pub kind: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub origin: Option<[f32; 3]>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub target: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub targetname: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(default, skip_serializing_if = "is_zero_u32")]
    pub spawnflags: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub health: Option<String>,
}

fn is_zero_u32(v: &u32) -> bool {
    *v == 0
}

#[derive(Debug, Clone, Serialize)]
pub struct Teleport {
    pub target: String,
    pub dest_origin: Option<[f32; 3]>,
    pub dest_name: String,
    pub trigger_center: Option<[f32; 3]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CausalLink {
    pub from_class: String,
    pub from_target: String,
    pub to_class: String,
    pub to_name: String,
    pub actuator: String,
    #[serde(default)]
    pub hops: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub via: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NavOverlay {
    pub json_path: String,
    pub nodes: usize,
    pub links: usize,
    pub jump_links: usize,
    pub tele_links: usize,
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub rocket_links: usize,
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub lift_links: usize,
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub swim_links: usize,
    /// sprint-only trick jumps: arcs that close only at full run
    /// speed, skill 3+ at runtime (Shane: "the cartographer should
    /// show that")
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub sprint_links: usize,
    /// horizontal mover rides (dm2's east-deck train)
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub train_links: usize,
    /// walk links a door brush stands in
    #[serde(default, skip_serializing_if = "is_zero_usize")]
    pub door_links: usize,
}

fn is_zero_usize(v: &usize) -> bool {
    *v == 0
}

#[derive(Debug, Clone, Serialize)]
pub struct MapAtlas {
    pub map: String,
    pub bsp_path: String,
    pub ingested_from: String,
    pub version: i32,
    pub mins: [f32; 3],
    pub maxs: [f32; 3],
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    pub counts: BTreeMap<String, usize>,
    pub items: Vec<AtlasItem>,
    pub teleports: Vec<Teleport>,
    pub causality: Vec<CausalLink>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nav: Option<NavOverlay>,
    pub notes: Vec<String>,
    pub headline: String,
    pub control: Vec<ControlItem>,
    pub implications: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recommended_baseline: Option<String>,
    pub recommended_duration_sec: u32,
    pub dispatcher_known: bool,
    pub height_bands: Vec<HeightBand>,
    pub recipe: String,
    pub edicts_est: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edicts_note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub graph_cuts: Option<GraphCuts>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub door_cuts: Vec<DoorCut>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub corridor_misses: Vec<CorridorMiss>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub plats: Vec<PlatBrief>,
    /// Brush AABBs for the tape-side cause tagger; never serialized
    /// (the human-facing brief stays lean, the in-memory cache keeps
    /// them).
    #[serde(skip)]
    pub door_aabbs: Vec<([f32; 3], [f32; 3])>,
    #[serde(skip)]
    pub plat_aabbs: Vec<([f32; 3], [f32; 3])>,
}

/// Boardability analysis per func_plat (the dm2 *31 forensics turned
/// into a static check: an unboardable plat or a ledge inside the
/// swept column costs a runtime session to diagnose; the cartographer
/// can say it up front).
#[derive(Debug, Clone, Serialize)]
pub struct PlatBrief {
    pub model: String,
    pub travel: f32,
    pub seated_face_z: f32,
    pub raised_face_z: f32,
    pub centre: [f32; 2],
    pub boardable: bool,
    /// A lift link in the shipped graph lands on this plat: navgen has
    /// already seated it (ordinary pad or 5b virtual pad) and the
    /// runtime rides it. Static hull 0 alone cannot see that.
    #[serde(default)]
    pub nav_served: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct GraphCuts {
    pub weak: usize,
    pub strong: usize,
    pub largest_weak: usize,
    pub islands: Vec<IslandBrief>,
}

#[derive(Debug, Clone, Serialize)]
pub struct IslandBrief {
    pub id: u32,
    pub nodes: usize,
    pub control: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sample: Option<[f32; 3]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct DoorCut {
    pub door: String,
    pub classname: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub targetname: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub button: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub actuator: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub key: Option<String>,
    pub walk_links: u32,
    pub sample: Vec<[u32; 2]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CorridorMiss {
    pub x: f32,
    pub y: f32,
    pub z: f32,
    pub why: String,
}

/// Compact atlas for LLM context. Default cartograph / see-map output.
#[derive(Debug, Clone, Serialize)]
pub struct AtlasBrief {
    pub map: String,
    pub headline: String,
    pub recipe: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    pub counts: BTreeMap<String, usize>,
    pub control: Vec<ControlItem>,
    pub height_bands: Vec<HeightBand>,
    pub teleports: usize,
    pub tele_list: Vec<TeleportBrief>,
    pub implications: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recommended_baseline: Option<String>,
    pub recommended_duration_sec: u32,
    pub dispatcher_known: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nav: Option<NavOverlay>,
    pub notes: Vec<String>,
    pub edicts_est: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub edicts_note: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub graph_cuts: Option<GraphCuts>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub door_cuts: Vec<DoorCut>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub corridor_misses: Vec<CorridorMiss>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HeightBand {
    pub z: f32,
    pub nodes: usize,
    pub label: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ControlItem {
    pub classname: String,
    pub value: u8,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub origin: Option<[f32; 3]>,
    pub elevated: bool,
    pub why: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub nearest_node: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub node_dist: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub node_dz: Option<f32>,
    pub reach: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub band: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub island: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TeleportBrief {
    pub target: String,
    pub dest_name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dest_origin: Option<[f32; 3]>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NodeView {
    pub map: String,
    pub node: u32,
    pub origin: [f32; 3],
    pub band: String,
    pub nearby_control: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapSource {
    pub name: String,
    pub path: Option<String>,
    pub source: String,
    pub has_nav: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct EntityInspect {
    pub map: String,
    pub bsp_path: String,
    pub filter: Option<String>,
    pub counts: BTreeMap<String, usize>,
    pub items: Vec<AtlasItem>,
    pub teleports: Vec<Teleport>,
    pub causality: Vec<CausalLink>,
}

/// Spec tool `bsp_inspect_entities`: lump 0 connectivity, optional classname filter.
pub fn inspect_entities(
    cfg: &Config,
    map_name: &str,
    filter_classname: Option<&str>,
) -> Result<EntityInspect, String> {
    let atlas = cartograph(cfg, map_name)?;
    let filt = filter_classname
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());
    let items: Vec<AtlasItem> = match &filt {
        Some(f) => {
            let fl = f.to_ascii_lowercase();
            atlas
                .items
                .into_iter()
                .filter(|i| i.classname.to_ascii_lowercase().contains(&fl))
                .collect()
        }
        None => atlas.items,
    };
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for i in &items {
        *counts.entry(i.kind.clone()).or_insert(0) += 1;
        *counts.entry("entities".into()).or_insert(0) += 1;
    }
    let causality = if let Some(f) = &filt {
        let fl = f.to_ascii_lowercase();
        atlas
            .causality
            .into_iter()
            .filter(|c| {
                c.from_class.to_ascii_lowercase().contains(&fl)
                    || c.to_class.to_ascii_lowercase().contains(&fl)
            })
            .collect()
    } else {
        atlas.causality
    };
    Ok(EntityInspect {
        map: atlas.map,
        bsp_path: atlas.bsp_path,
        filter: filt,
        counts,
        items,
        teleports: atlas.teleports,
        causality,
    })
}

pub fn cartograph(cfg: &Config, bsp: &str) -> Result<MapAtlas, String> {
    let key = bsp.trim().to_ascii_lowercase();
    let (path, ingested_from) = ingest_bsp(cfg, bsp)?;
    let raw = read_bsp29(&path)?;
    let map = path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_ascii_lowercase();
    let nav_path = cfg.src.join(format!("argus_nav_{map}.qc.json"));
    let stamps = vec![file_stamp(&path), file_stamp(&nav_path)];
    if let Ok(cache) = ATLAS_CACHE.lock() {
        if let Some(hit) = cache.get(&key).or_else(|| cache.get(&map)) {
            if stamps_fresh(&hit.stamps, &stamps) {
                return Ok(hit.atlas.clone());
            }
        }
    }
    let atlas = atlas_from_bsp(&map, &path, &ingested_from, &raw, cfg);
    if let Ok(mut cache) = ATLAS_CACHE.lock() {
        let entry = CachedAtlas {
            atlas: atlas.clone(),
            stamps,
        };
        cache.insert(key, entry.clone());
        cache.insert(map, entry);
    }
    Ok(atlas)
}

#[derive(Clone)]
struct CachedAtlas {
    atlas: MapAtlas,
    stamps: Vec<(PathBuf, Option<SystemTime>)>,
}

static ATLAS_CACHE: Mutex<BTreeMap<String, CachedAtlas>> = Mutex::new(BTreeMap::new());

fn file_stamp(path: &Path) -> (PathBuf, Option<SystemTime>) {
    (
        path.to_path_buf(),
        std::fs::metadata(path).and_then(|m| m.modified()).ok(),
    )
}

fn stamps_fresh(cached: &[(PathBuf, Option<SystemTime>)], now: &[(PathBuf, Option<SystemTime>)]) -> bool {
    if cached.len() != now.len() {
        return false;
    }
    cached.iter().zip(now.iter()).all(|(a, b)| a == b)
}

pub fn lookup_node(cfg: &Config, map: &str, node: u32) -> Result<NodeView, String> {
    let atlas = cartograph(cfg, map)?;
    let path = cfg.src.join(format!("argus_nav_{}.qc.json", atlas.map));
    let text = std::fs::read_to_string(&path)
        .map_err(|_| format!("no nav JSON for {}", atlas.map))?;
    let v: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("nav json: {e}"))?;
    let nodes = v
        .get("nodes")
        .and_then(|n| n.as_array())
        .ok_or("nav json missing nodes")?;
    let n = nodes
        .get(node as usize)
        .and_then(|a| a.as_array())
        .ok_or_else(|| format!("node {node} out of range (0..{})", nodes.len()))?;
    let origin = [
        n.first().and_then(|x| x.as_f64()).unwrap_or(0.0) as f32,
        n.get(1).and_then(|x| x.as_f64()).unwrap_or(0.0) as f32,
        n.get(2).and_then(|x| x.as_f64()).unwrap_or(0.0) as f32,
    ];
    let nearby_control = atlas
        .control
        .iter()
        .filter(|c| c.nearest_node == Some(node))
        .map(|c| format!("{} ({})", c.classname, c.reach))
        .collect();
    Ok(NodeView {
        map: atlas.map.clone(),
        node,
        origin,
        band: band_label(&atlas.map, origin[2]),
        nearby_control,
    })
}

pub fn atlas_brief(atlas: &MapAtlas) -> AtlasBrief {
    AtlasBrief {
        map: atlas.map.clone(),
        headline: atlas.headline.clone(),
        recipe: atlas.recipe.clone(),
        message: atlas.message.clone(),
        counts: atlas.counts.clone(),
        control: atlas.control.clone(),
        height_bands: atlas.height_bands.clone(),
        teleports: atlas.teleports.len(),
        tele_list: atlas
            .teleports
            .iter()
            .map(|t| TeleportBrief {
                target: t.target.clone(),
                dest_name: t.dest_name.clone(),
                dest_origin: t.dest_origin,
            })
            .collect(),
        implications: atlas.implications.clone(),
        recommended_baseline: atlas.recommended_baseline.clone(),
        recommended_duration_sec: atlas.recommended_duration_sec,
        dispatcher_known: atlas.dispatcher_known,
        nav: atlas.nav.clone(),
        notes: atlas.notes.clone(),
        edicts_est: atlas.edicts_est,
        edicts_note: atlas.edicts_note.clone(),
        graph_cuts: atlas.graph_cuts.clone(),
        door_cuts: atlas.door_cuts.clone(),
        corridor_misses: atlas.corridor_misses.iter().take(8).cloned().collect(),
    }
}

/// Ingest point: existing path / maps_local / short name, else extract from id1 PAKs.
pub fn ingest_bsp(cfg: &Config, given: &str) -> Result<(PathBuf, String), String> {
    if let Ok(p) = resolve_input(cfg, given) {
        return Ok((p, "filesystem".into()));
    }
    let base = Path::new(given)
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(given);
    let want = if base.to_ascii_lowercase().ends_with(".bsp") {
        base.to_string()
    } else {
        format!("{base}.bsp")
    };
    let dest = cfg.maps.join(&want);
    if dest.is_file() {
        return Ok((dest, "filesystem".into()));
    }
    for pak in candidate_paks(cfg) {
        if let Ok(Some(bytes)) = pak_find(&pak, &want) {
            if let Some(parent) = dest.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            std::fs::write(&dest, &bytes)
                .map_err(|e| format!("write extracted {}: {e}", dest.display()))?;
            return Ok((dest, format!("pak:{}", pak.display())));
        }
    }
    Err(format!(
        "BSP not found: {given} (tried ARGUS_MAPS and id1 PAK0/PAK1)"
    ))
}

pub fn list_maps(cfg: &Config) -> Result<Vec<MapSource>, String> {
    let mut out = Vec::new();
    if cfg.maps.is_dir() {
        if let Ok(rd) = std::fs::read_dir(&cfg.maps) {
            for ent in rd.flatten() {
                let p = ent.path();
                if p.extension().and_then(|s| s.to_str()).map(|s| s.eq_ignore_ascii_case("bsp")) != Some(true)
                {
                    continue;
                }
                let name = p
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or_default()
                    .to_string();
                let has_nav = cfg.src.join(format!("argus_nav_{name}.qc.json")).is_file();
                out.push(MapSource {
                    name,
                    path: Some(p.display().to_string()),
                    source: "maps_local".into(),
                    has_nav,
                });
            }
        }
    }
    for pak in candidate_paks(cfg) {
        if let Ok(maps) = pak_list_maps(&pak) {
            for base in maps {
                let name = base.trim_end_matches(".bsp").trim_end_matches(".BSP").to_string();
                if out.iter().any(|m| m.name.eq_ignore_ascii_case(&name)) {
                    continue;
                }
                let has_nav = cfg.src.join(format!("argus_nav_{name}.qc.json")).is_file();
                out.push(MapSource {
                    name,
                    path: None,
                    source: format!("pak:{}", pak.display()),
                    has_nav,
                });
            }
        }
    }
    out.sort_by(|a, b| a.name.cmp(&b.name));
    Ok(out)
}

fn candidate_paks(cfg: &Config) -> Vec<PathBuf> {
    let mut p = Vec::new();
    let roots = [
        cfg.basedir.join("id1"),
        cfg.root.join("engine").join("id1"),
        cfg.root.join("id1"),
    ];
    for dir in roots {
        for name in ["pak0.pak", "pak1.pak", "PAK0.PAK", "PAK1.PAK"] {
            let cand = dir.join(name);
            if cand.is_file() && !p.contains(&cand) {
                p.push(cand);
            }
        }
    }
    p
}

pub fn parse_entities(text: &str) -> Vec<BTreeMap<String, String>> {
    let block_re = block_re();
    let kv_re = kv_re();
    let mut out = Vec::new();
    for caps in block_re.captures_iter(text) {
        let mut kv = BTreeMap::new();
        for pair in kv_re.captures_iter(&caps[1]) {
            kv.insert(pair[1].to_string(), pair[2].to_string());
        }
        if !kv.is_empty() {
            out.push(kv);
        }
    }
    out
}

pub fn classify(classname: &str) -> &'static str {
    if classname.starts_with("info_player") {
        "spawn"
    } else if classname.starts_with("weapon_") {
        "weapon"
    } else if classname.starts_with("item_armor") {
        "armor"
    } else if classname == "item_health" || classname == "item_artifact_super_health" {
        "health"
    } else if classname.starts_with("item_artifact_") {
        "powerup"
    } else if matches!(
        classname,
        "item_shells" | "item_spikes" | "item_rockets" | "item_cells"
    ) {
        "ammo"
    } else if classname == "trigger_teleport" || classname == "info_teleport_destination" {
        "teleport"
    } else if classname == "func_button" {
        "button"
    } else if classname.starts_with("func_door") {
        "door"
    } else if classname == "func_plat" {
        "plat"
    } else if classname == "func_train" {
        "train"
    } else if classname.starts_with("trigger_") {
        "trigger"
    } else if classname == "worldspawn" {
        "world"
    } else {
        "other"
    }
}

fn atlas_from_bsp(
    map: &str,
    path: &Path,
    ingested_from: &str,
    bsp: &Bsp29,
    cfg: &Config,
) -> MapAtlas {
    let ents = parse_entities(&bsp.entities);
    let mut items = Vec::new();
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    let mut message = None;
    let mut dests: BTreeMap<String, ([f32; 3], String)> = BTreeMap::new();

    for e in &ents {
        let classname = e.get("classname").cloned().unwrap_or_else(|| "?".into());
        if classname == "worldspawn" {
            message = e.get("message").cloned();
        }
        let kind = classify(&classname).to_string();
        let spawnflags = e
            .get("spawnflags")
            .and_then(|s| s.parse().ok())
            .unwrap_or(0);
        let dm_hidden = spawnflags & SPAWNFLAG_NOT_DEATHMATCH != 0
            && matches!(
                kind.as_str(),
                "weapon" | "health" | "ammo" | "armor" | "powerup"
            );
        if !dm_hidden {
            *counts.entry(kind.clone()).or_insert(0) += 1;
        }
        *counts.entry("entities".into()).or_insert(0) += 1;
        let origin = parse_origin(e.get("origin").map(|s| s.as_str()));
        if classname == "info_teleport_destination" {
            if let (Some(name), Some(o)) = (e.get("targetname"), origin) {
                dests.insert(name.clone(), (o, name.clone()));
            }
        }
        items.push(AtlasItem {
            classname,
            kind,
            origin,
            target: e.get("target").cloned(),
            targetname: e.get("targetname").cloned(),
            model: e.get("model").cloned(),
            spawnflags,
            health: e.get("health").cloned(),
        });
    }

    let mut teleports = Vec::new();
    for e in &ents {
        if e.get("classname").map(|s| s.as_str()) != Some("trigger_teleport") {
            continue;
        }
        let Some(target) = e.get("target") else {
            continue;
        };
        let dest = dests.get(target);
        let trigger_center = e
            .get("model")
            .and_then(|m| m.strip_prefix('*'))
            .and_then(|s| s.parse::<usize>().ok())
            .and_then(|i| bsp.models.get(i))
            .map(|m| {
                [
                    (m.mins[0] + m.maxs[0]) / 2.0,
                    (m.mins[1] + m.maxs[1]) / 2.0,
                    (m.mins[2] + m.maxs[2]) / 2.0,
                ]
            });
        teleports.push(Teleport {
            target: target.clone(),
            dest_origin: dest.map(|d| d.0),
            dest_name: dest.map(|d| d.1.clone()).unwrap_or_default(),
            trigger_center,
        });
    }

    let mut by_name: BTreeMap<String, Vec<&BTreeMap<String, String>>> = BTreeMap::new();
    for e in &ents {
        if let Some(n) = e.get("targetname") {
            by_name.entry(n.clone()).or_default().push(e);
        }
    }
    let causality = build_causality(&ents, &by_name);

    let graph = load_nav_graph(cfg, map);
    let nav = graph.as_ref().map(|g| g.overlay.clone());
    let height_bands = graph
        .as_ref()
        .map(|g| height_bands(map, &g.nodes))
        .unwrap_or_default();
    let mut notes = Vec::new();
    if counts.get("spawn").copied().unwrap_or(0) == 0 {
        notes.push("no info_player* spawn points in the entity lump".into());
    }
    if items.iter().any(|i| i.classname == "item_artifact_super_damage") {
        notes.push(
            "quad is on this map; hold it via prize-only rocket-jump pads when navgen emitted them (dm4: 150->149, 151->149, 152->99, 153->99)"
                .into(),
        );
    }
    if nav.is_none() {
        notes.push(format!(
            "no nav JSON at src/argus_nav_{map}.qc.json; run nav_generate or cartograph with generate_nav"
        ));
    }
    if teleports.iter().any(|t| t.dest_origin.is_none()) {
        notes.push("a trigger_teleport has no matching info_teleport_destination".into());
    }

    // Drop worldspawn from the item list to keep the atlas readable.
    items.retain(|i| i.classname != "worldspawn");

    let spawn_z = median_spawn_z(&items);
    let doors = model_aabbs(bsp, &items, "door");
    let plats = model_aabbs(bsp, &items, "plat");
    // kept on the atlas for the tape-side cause tagger (intel):
    // "stall at x y z" becomes "stall at a door / in a plat column"
    let door_aabbs = doors.clone();
    let plat_aabbs = plats.clone();
    let mut control: Vec<ControlItem> = items
        .iter()
        .filter_map(|i| {
            if i.spawnflags & SPAWNFLAG_NOT_DEATHMATCH != 0 {
                return None;
            }
            let (value, why) = item_value(&i.classname, i.spawnflags)?;
            let elevated = match (i.origin, spawn_z) {
                (Some(o), Some(sz)) => o[2] - sz >= 80.0,
                _ => false,
            };
            let (snap, reach) = i.origin.map(|o| {
                snap_reach(
                    graph.as_ref().map(|g| g.nodes.as_slice()).unwrap_or(&[]),
                    o,
                    elevated,
                    bsp.clip.as_ref(),
                    &doors,
                    &plats,
                )
            }).unzip();
            let band = i.origin.map(|o| band_label(map, o[2]));
            Some(ControlItem {
                classname: i.classname.clone(),
                value,
                origin: i.origin,
                elevated,
                why: if elevated {
                    format!("{why}; origin is well above spawn height (likely a jump or rocket-jump item)")
                } else {
                    why.to_string()
                },
                nearest_node: snap.as_ref().map(|s| s.node),
                node_dist: snap.as_ref().map(|s| s.dist),
                node_dz: snap.as_ref().map(|s| s.dz),
                reach: reach.unwrap_or_else(|| "unknown".into()),
                band,
                island: None,
            })
        })
        .collect();
    control.sort_by(|a, b| b.value.cmp(&a.value));
    control.truncate(12);

    let dispatcher_known = dispatcher_knows(cfg, map);
    let baseline_override = crate::intel::baseline_override_for(cfg, map);
    let recommended_baseline: Option<&str> = baseline_override
        .as_deref()
        .or_else(|| recommended_baseline_for(map));
    let mut implications = map_implications(map);
    if !dispatcher_known {
        implications.push(
            "dispatcher has no branch for this map; bots degrade to line-of-sight seeking".into(),
        );
    }
    if nav.is_none() {
        implications.push("no compiled nav graph; cartograph with generate_nav=true".into());
    }
    if control.iter().any(|c| c.reach == "rocket_jump") {
        implications.push(
            "a prize item is beyond a normal jump from its nearest nav node (rocket-jump or shelve)".into(),
        );
    }
    if control.iter().any(|c| c.reach == "off_graph") {
        implications.push("a control item is off the waypoint graph; bots will routefail or LOS-seek it".into());
    }
    if causality.iter().any(|c| c.actuator == "shoot") {
        implications.push("shootable button on this map; bots need a weapon and a purpose to fire it".into());
    }

    let (graph_cuts, node_island) = graph
        .as_ref()
        .map(|g| graph_cuts(g, &control))
        .map(|(c, m)| (Some(c), m))
        .unwrap_or((None, Vec::new()));
    if !node_island.is_empty() {
        for c in &mut control {
            if let Some(n) = c.nearest_node {
                c.island = node_island.get(n as usize).copied();
            }
        }
    }
    if let Some(cuts) = &graph_cuts {
        if cuts.weak > 1 {
            implications.push(format!(
                "{} walk-islands (largest {}); control on a small island will routefail or LOS-seek",
                cuts.weak, cuts.largest_weak
            ));
        }
        if cuts.strong > cuts.weak {
            implications.push(format!(
                "{} strongly-connected components (one-way drops/hops split return paths)",
                cuts.strong
            ));
        }
    }

    let door_meta: Vec<DoorMeta> = items
        .iter()
        .filter(|i| i.kind == "door")
        .filter_map(|i| {
            let raw = i.model.as_deref()?.strip_prefix('*')?;
            let idx: usize = raw.parse().ok()?;
            let m = bsp.models.get(idx)?;
            let mut door_items = 0u32;
            if i.spawnflags & 16 != 0 {
                door_items |= 131072; // IT_KEY1: silver key (DOOR_SILVER_KEY = 16)
            }
            if i.spawnflags & 8 != 0 {
                door_items |= 262144; // IT_KEY2: gold key (DOOR_GOLD_KEY = 8)
            }
            Some(DoorMeta {
                door: i.model.clone().unwrap_or_default(),
                classname: i.classname.clone(),
                targetname: i.targetname.clone(),
                items: door_items,
                mins: m.mins,
                maxs: m.maxs,
            })
        })
        .collect();
    let door_cuts = graph
        .as_ref()
        .map(|g| find_door_cuts(g, &door_meta, &causality))
        .unwrap_or_default();
    if !door_cuts.is_empty() {
        let n: u32 = door_cuts.iter().map(|d| d.walk_links).sum();
        implications.push(format!(
            "{} door(s) cut {} walk link(s); bots pin on a closed door until the button fires",
            door_cuts.len(),
            n
        ));
        let keyed_cuts: Vec<_> = door_cuts.iter().filter_map(|d| d.key.as_deref()).collect();
        if !keyed_cuts.is_empty() {
            implications.push(format!(
                "{} keyed door cut(s) ({}); bots commit to fetch key before traversing",
                keyed_cuts.len(),
                keyed_cuts.join(", ")
            ));
        }
    }

    let corridor_misses = graph
        .as_ref()
        .and_then(|g| {
            let hull = bsp.clip.as_ref()?;
            Some(find_corridor_misses(g, hull, &doors))
        })
        .unwrap_or_default();
    if !corridor_misses.is_empty() {
        implications.push(format!(
            "{} pinch cell(s) the 32u sampler never stood in; try navgen --grid 16",
            corridor_misses.len()
        ));
    }

    let plats = analyze_plats(&items, bsp, graph.as_ref());
    for p in &plats {
        for w in &p.warnings {
            implications.push(format!("plat {}: {w}", p.model));
        }
    }

    let headline = atlas_headline(
        map,
        &counts,
        &control,
        dispatcher_known,
        nav.as_ref(),
        graph_cuts.as_ref(),
    );
    let duration = if map == "dm4" { 185 } else { 120 };
    let recipe = format!(
        "cartograph bsp={map} (brief); match_run map={map} duration_sec={duration} skill=2; compare_runs log_a={} log_b=latest",
        recommended_baseline.unwrap_or("baseline")
    );
    let wp = graph.as_ref().map(|g| g.nodes.len() as u32).unwrap_or(0);
    let ents = counts.get("entities").copied().unwrap_or(0) as u32;
    let edicts_est = ents + wp;
    let edicts_note = if edicts_est > 500 {
        Some(format!(
            "edict estimate {edicts_est} (entities {ents} + waypoints {wp}); vanilla max_edicts is 600, keep a margin"
        ))
    } else {
        None
    };
    if let Some(n) = &edicts_note {
        notes.push(n.clone());
    }

    MapAtlas {
        map: map.to_string(),
        bsp_path: path.display().to_string(),
        ingested_from: ingested_from.to_string(),
        version: bsp.version,
        mins: bsp.mins,
        maxs: bsp.maxs,
        message,
        counts,
        items,
        teleports,
        causality,
        nav,
        notes,
        headline,
        control,
        implications,
        recommended_baseline: recommended_baseline.map(|s| s.to_string()),
        recommended_duration_sec: duration,
        dispatcher_known,
        height_bands,
        recipe,
        edicts_est,
        edicts_note,
        graph_cuts,
        door_cuts,
        corridor_misses,
        plats,
        door_aabbs,
        plat_aabbs,
    }
}

/// Static plat boardability: seated-face height, a boarding-floor ring
/// probe outside the footprint, and a ledge-inside-the-swept-column
/// probe (the *31 statue class, found the hard way on 2026-08-19).

/// True when the shipped graph carries a lift link with an endpoint over
/// this plat's footprint. navgen seats boarding pads outside the swept
/// column (v3.56) and rest-top virtual pads inside it (v3.84), so check
/// a generous xy margin and ignore z: the two ends of a lift link are by
/// definition the two heights the slab serves.
fn plat_has_lift_link(g: &NavGraph, mins: [f32; 3], maxs: [f32; 3]) -> bool {
    const MARGIN: f32 = 96.0;
    let over = |n: &[f32; 3]| {
        n[0] >= mins[0] - MARGIN
            && n[0] <= maxs[0] + MARGIN
            && n[1] >= mins[1] - MARGIN
            && n[1] <= maxs[1] + MARGIN
    };
    for (from, edges) in g.adj.iter().enumerate() {
        for (to, kind) in edges {
            if kind != "lift" {
                continue;
            }
            let (Some(a), Some(b)) = (g.nodes.get(from), g.nodes.get(*to as usize)) else {
                continue;
            };
            if over(a) || over(b) {
                return true;
            }
        }
    }
    false
}

fn analyze_plats(items: &[AtlasItem], bsp: &Bsp29, graph: Option<&NavGraph>) -> Vec<PlatBrief> {
    let Some(hull) = bsp.hull0.as_ref() else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for i in items.iter().filter(|i| i.kind == "plat") {
        let Some(raw) = i.model.as_deref().and_then(|m| m.strip_prefix('*')) else {
            continue;
        };
        let Ok(idx) = raw.parse::<usize>() else {
            continue;
        };
        let Some(m) = bsp.models.get(idx) else {
            continue;
        };
        // plats are compiled at the extended position; travel is the
        // height key (not retained in the lump we keep) or size_z - 8
        let travel = (m.maxs[2] - m.mins[2] - 8.0).max(8.0);
        let seated = m.maxs[2] - travel;
        let cx = (m.mins[0] + m.maxs[0]) / 2.0;
        let cy = (m.mins[1] + m.maxs[1]) / 2.0;

        let ring = [
            (m.mins[0] - 24.0, cy),
            (m.maxs[0] + 24.0, cy),
            (cx, m.mins[1] - 24.0),
            (cx, m.maxs[1] + 24.0),
            (m.mins[0] - 24.0, m.mins[1] - 24.0),
            (m.maxs[0] + 24.0, m.mins[1] - 24.0),
            (m.mins[0] - 24.0, m.maxs[1] + 24.0),
            (m.maxs[0] + 24.0, m.maxs[1] + 24.0),
        ];
        let mut boardable = false;
        for (x, y) in ring {
            let open =
                hull.contents_at([x, y, seated + 30.0]) != crate::bsp::CONTENTS_SOLID;
            let floor =
                hull.contents_at([x, y, seated - 6.0]) == crate::bsp::CONTENTS_SOLID;
            if open && floor {
                boardable = true;
                break;
            }
        }

        // A lift link whose endpoints straddle this footprint is navgen
        // saying it already seated the plat - dm3 rides its three plats
        // every tape while hull 0 alone still called them unboardable.
        let nav_served = graph
            .map(|g| plat_has_lift_link(g, m.mins, m.maxs))
            .unwrap_or(false);

        let mut warnings = Vec::new();
        if !boardable && !nav_served {
            warnings.push(format!(
                "no static floor within a step of the seated face (z {seated:.0}) beside the footprint - the runtime cannot walk aboard; needs a virtual pad on the slab rest-top (navgen 5b gap)"
            ));
        }

        // 5x5 interior grid: narrow ledge strips (the *31 corridor is
        // one 30u band of a 94u footprint) slip through a 3x3
        let xs = [
            m.mins[0] + 12.0,
            (m.mins[0] + cx) / 2.0,
            cx,
            (cx + m.maxs[0]) / 2.0,
            m.maxs[0] - 12.0,
        ];
        let ys = [
            m.mins[1] + 12.0,
            (m.mins[1] + cy) / 2.0,
            cy,
            (cy + m.maxs[1]) / 2.0,
            m.maxs[1] - 12.0,
        ];
        // a ledge is a STANDABLE static point inside the footprint:
        // solid floor with headroom, at any height a waiting bot could
        // occupy while the slab sweeps through. The slab itself is a
        // moving bmodel and lives in no static hull, so it cannot
        // false-positive here. (*31's ledge floors sit at 160-199
        // around a seated face of 169 - probe below it as well as
        // above.)
        let mut ledge = false;
        for x in xs {
            for y in ys {
                for dz in [-16.0f32, 8.0, 40.0, 80.0] {
                    let h = seated + dz;
                    if h + 56.0 > m.maxs[2] {
                        continue;
                    }
                    let floor =
                        hull.contents_at([x, y, h - 6.0]) == crate::bsp::CONTENTS_SOLID;
                    let room =
                        hull.contents_at([x, y, h + 30.0]) != crate::bsp::CONTENTS_SOLID;
                    if floor && room {
                        ledge = true;
                    }
                }
            }
        }
        if ledge {
            warnings.push(
                "static ledge inside the swept column: a bot waiting on it stands in the slab's path and its touches postpone the cycle (the *31 statue class); boarding pads must sit outside the footprint".into(),
            );
        }

        out.push(PlatBrief {
            model: i.model.clone().unwrap_or_default(),
            travel,
            seated_face_z: seated,
            raised_face_z: m.maxs[2],
            centre: [cx, cy],
            boardable,
            nav_served,
            warnings,
        });
    }
    out
}

struct NavGraph {
    overlay: NavOverlay,
    nodes: Vec<[f32; 3]>,
    /// Directed edges (kind, to). Walk/drop/jump/tele/rocket/lift/swim.
    adj: Vec<Vec<(u32, String)>>,
}

struct NodeSnap {
    node: u32,
    dist: f32,
    dz: f32,
}

fn load_nav_graph(cfg: &Config, map: &str) -> Option<NavGraph> {
    load_nav_graph_at(&cfg.src.join(format!("argus_nav_{map}.qc.json")))
}

fn load_nav_graph_at(path: &std::path::Path) -> Option<NavGraph> {
    let text = std::fs::read_to_string(path).ok()?;
    let v: serde_json::Value = serde_json::from_str(&text).ok()?;
    let nodes: Vec<[f32; 3]> = v
        .get("nodes")?
        .as_array()?
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
        return None;
    }
    let n = nodes.len();
    let mut adj: Vec<Vec<(u32, String)>> = vec![Vec::new(); n];
    if let Some(links) = v.get("links").and_then(|x| x.as_array()) {
        for link in links {
            let Some(a) = link.as_array() else { continue };
            let Some(from) = a.first().and_then(|x| x.as_u64()).map(|x| x as usize) else {
                continue;
            };
            let Some(to) = a.get(1).and_then(|x| x.as_u64()).map(|x| x as usize) else {
                continue;
            };
            let walk = a.get(2).and_then(|x| x.as_u64()).unwrap_or(1);
            if from < n && to < n {
                let kind = if walk == 0 { "drop" } else { "walk" };
                if !adj[from].iter().any(|(t, _)| *t == to as u32) {
                    adj[from].push((to as u32, kind.into()));
                }
            }
        }
    }
    for (key, kind) in [
        ("jlinks", "jump"),
        ("teles", "tele"),
        ("rjlinks", "rocket"),
        ("liftlinks", "lift"),
        ("swimlinks", "swim"),
        ("doorlinks", "door"),
        ("trainlinks", "train"),
        ("sprintlinks", "sprint"),
    ] {
        if let Some(list) = v.get(key).and_then(|x| x.as_array()) {
            for link in list {
                let Some(a) = link.as_array() else { continue };
                let Some(from) = a.first().and_then(|x| x.as_u64()).map(|x| x as usize) else {
                    continue;
                };
                let Some(to) = a.get(1).and_then(|x| x.as_u64()).map(|x| x as usize) else {
                    continue;
                };
                if from < n && to < n {
                    if let Some(e) = adj[from].iter_mut().find(|(t, _)| *t == to as u32) {
                        e.1 = kind.into();
                    } else {
                        adj[from].push((to as u32, kind.into()));
                    }
                }
            }
        }
    }
    Some(NavGraph {
        overlay: NavOverlay {
            json_path: path.display().to_string(),
            nodes: nodes.len(),
            links: v.get("links").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            jump_links: v.get("jlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            tele_links: v.get("teles").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            rocket_links: v.get("rjlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            lift_links: v.get("liftlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            swim_links: v.get("swimlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            sprint_links: v.get("sprintlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            train_links: v.get("trainlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
            door_links: v.get("doorlinks").and_then(|n| n.as_array()).map(|a| a.len()).unwrap_or(0),
        },
        nodes,
        adj,
    })
}

fn snap_reach(
    nodes: &[[f32; 3]],
    origin: [f32; 3],
    elevated: bool,
    hull: Option<&ClipHull>,
    doors: &[([f32; 3], [f32; 3])],
    plats: &[([f32; 3], [f32; 3])],
) -> (NodeSnap, String) {
    if nodes.is_empty() {
        return (
            NodeSnap {
                node: 0,
                dist: f32::MAX,
                dz: 0.0,
            },
            "unknown".into(),
        );
    }
    let mut ranked: Vec<(f32, usize)> = nodes
        .iter()
        .enumerate()
        .map(|(i, n)| {
            let dx = origin[0] - n[0];
            let dy = origin[1] - n[1];
            let dz = origin[2] - n[2];
            ((dx * dx + dy * dy + dz * dz).sqrt(), i)
        })
        .collect();
    ranked.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));

    let pick = if let Some(hull) = hull {
        ranked
            .iter()
            .take(8)
            .find(|(_, i)| {
                let n = nodes[*i];
                hull.line_clear([n[0], n[1], n[2] + 22.0], item_eye(origin, n[2]))
            })
            .copied()
            .or_else(|| ranked.first().copied())
    } else {
        ranked.first().copied()
    };
    let (dist, i) = pick.unwrap_or((f32::MAX, 0));
    let n = nodes.get(i).copied().unwrap_or([0.0; 3]);
    let snap = NodeSnap {
        node: i as u32,
        dist,
        dz: origin[2] - n[2],
    };
    let reach = reach_label_full(&snap, n, origin, elevated, hull, doors, plats);
    (snap, reach)
}

// Entity-lump item origins sit ON the floor while nav nodes sit at
// player-origin height (floor + 24). In the clip hull everything
// below floor + 24 is solid, so an eye-trace endpoint at a
// floor-seated item's origin + 22 starts 2u INSIDE the floor and the
// trace can never clear - the 2026-08-26 dm4 audit found eleven of
// twelve control items labelled off_graph, every one with node_dz
// exactly -24, on a map whose tapes route 57% of the time. Lift a
// below-node origin to node height before tracing; a floating or
// above-node origin (the dm4 quad, jump/RJ prizes) keeps its own
// height so the elevation labels still see the true dz.
fn item_eye(origin: [f32; 3], node_z: f32) -> [f32; 3] {
    let z = if node_z - origin[2] >= 16.0 {
        node_z + 22.0
    } else {
        origin[2] + 22.0
    };
    [origin[0], origin[1], z]
}

fn reach_label_full(
    s: &NodeSnap,
    node: [f32; 3],
    origin: [f32; 3],
    elevated: bool,
    hull: Option<&ClipHull>,
    doors: &[([f32; 3], [f32; 3])],
    plats: &[([f32; 3], [f32; 3])],
) -> String {
    if s.dist > 192.0 {
        return "off_graph".into();
    }
    if doors.iter().any(|(mn, mx)| segment_hits_aabb(*mn, *mx, node, origin)) {
        return "blocked_by_door".into();
    }
    if s.dz > 40.0
        && plats.iter().any(|(mn, mx)| {
            point_near_aabb(node, *mn, *mx, 80.0) || point_near_aabb(origin, *mn, *mx, 80.0)
        })
    {
        return "elevator".into();
    }
    if let Some(hull) = hull {
        if !hull.line_clear([node[0], node[1], node[2] + 22.0], item_eye(origin, node[2]))
            && s.dz <= 45.0
        {
            return "off_graph".into();
        }
    }
    if s.dz > 80.0 || elevated && s.dz > 45.0 {
        return "rocket_jump".into();
    }
    if s.dz > 45.0 {
        return "jump".into();
    }
    "walk".into()
}

fn segment_hits_aabb(mins: [f32; 3], maxs: [f32; 3], a: [f32; 3], b: [f32; 3]) -> bool {
    let mins = [mins[0] - 8.0, mins[1] - 8.0, mins[2] - 8.0];
    let maxs = [maxs[0] + 8.0, maxs[1] + 8.0, maxs[2] + 8.0];
    for i in 0..=8 {
        let t = i as f32 / 8.0;
        let p = [
            a[0] + (b[0] - a[0]) * t,
            a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t,
        ];
        if p[0] >= mins[0]
            && p[0] <= maxs[0]
            && p[1] >= mins[1]
            && p[1] <= maxs[1]
            && p[2] >= mins[2]
            && p[2] <= maxs[2]
        {
            return true;
        }
    }
    false
}

fn point_near_aabb(p: [f32; 3], mins: [f32; 3], maxs: [f32; 3], pad: f32) -> bool {
    p[0] >= mins[0] - pad
        && p[0] <= maxs[0] + pad
        && p[1] >= mins[1] - pad
        && p[1] <= maxs[1] + pad
        && p[2] >= mins[2] - pad
        && p[2] <= maxs[2] + pad
}

fn model_aabbs(bsp: &Bsp29, items: &[AtlasItem], kind: &str) -> Vec<([f32; 3], [f32; 3])> {
    items
        .iter()
        .filter(|i| i.kind == kind)
        .filter_map(|i| {
            let raw = i.model.as_deref()?.strip_prefix('*')?;
            let idx: usize = raw.parse().ok()?;
            let m = bsp.models.get(idx)?;
            Some((m.mins, m.maxs))
        })
        .collect()
}

fn actuator_of(classname: &str, health: Option<&str>) -> &'static str {
    if classname == "func_button" {
        if health.map(|h| h != "0").unwrap_or(false) {
            "shoot"
        } else {
            "touch"
        }
    } else if classname == "func_door_secret" {
        "secret"
    } else if classname.starts_with("trigger_") {
        "touch"
    } else {
        "target"
    }
}

fn is_relay(classname: &str) -> bool {
    matches!(
        classname,
        "trigger_relay" | "trigger_once" | "trigger_multiple" | "trigger_counter"
    )
}

fn build_causality(
    ents: &[BTreeMap<String, String>],
    by_name: &BTreeMap<String, Vec<&BTreeMap<String, String>>>,
) -> Vec<CausalLink> {
    let mut out = Vec::new();
    for e in ents {
        let Some(target) = e.get("target") else {
            continue;
        };
        let from_class = e.get("classname").cloned().unwrap_or_default();
        if from_class == "path_corner" || from_class == "func_train" {
            continue;
        }
        let actuator = actuator_of(&from_class, e.get("health").map(|s| s.as_str()));
        let Some(victims) = by_name.get(target) else {
            continue;
        };
        for v in victims {
            let to_class = v.get("classname").cloned().unwrap_or_default();
            let to_name = v.get("targetname").cloned().unwrap_or_default();
            out.push(CausalLink {
                from_class: from_class.clone(),
                from_target: target.clone(),
                to_class: to_class.clone(),
                to_name: to_name.clone(),
                actuator: actuator.into(),
                hops: 1,
                via: None,
            });
            // one extra hop through relays so dm2-style chains show up
            if is_relay(&to_class) {
                if let Some(next) = v.get("target") {
                    if let Some(second) = by_name.get(next) {
                        for w in second {
                            out.push(CausalLink {
                                from_class: from_class.clone(),
                                from_target: next.clone(),
                                to_class: w.get("classname").cloned().unwrap_or_default(),
                                to_name: w.get("targetname").cloned().unwrap_or_default(),
                                actuator: actuator.into(),
                                hops: 2,
                                via: Some(to_class.clone()),
                            });
                        }
                    }
                }
            }
        }
    }
    out
}

fn height_bands(map: &str, nodes: &[[f32; 3]]) -> Vec<HeightBand> {
    let mut buckets: BTreeMap<i32, usize> = BTreeMap::new();
    for n in nodes {
        let key = (n[2] / 64.0).round() as i32;
        *buckets.entry(key).or_insert(0) += 1;
    }
    let mut bands: Vec<HeightBand> = buckets
        .into_iter()
        .map(|(k, nodes)| {
            let z = k as f32 * 64.0;
            HeightBand {
                label: band_label(map, z),
                z,
                nodes,
            }
        })
        .collect();
    bands.sort_by(|a, b| b.nodes.cmp(&a.nodes));
    bands
}

pub fn band_label(map: &str, z: f32) -> String {
    if map == "dm4" {
        if z >= 0.0 {
            return "upper walkway".into();
        }
        if z >= -80.0 {
            return "mid ledge".into();
        }
        if z >= -160.0 {
            return "stair / tele floor".into();
        }
        if z >= -320.0 {
            return "pit".into();
        }
        return "deep / lava".into();
    }
    format!("z≈{z:.0}")
}

/// `item_health` with spawnflags bit 1 (value 2) is MegaHealth on id maps.
pub fn item_value(classname: &str, spawnflags: u32) -> Option<(u8, &'static str)> {
    if classname == "item_health" && (spawnflags & 2) != 0 {
        return Some((80, "megahealth"));
    }
    Some(match classname {
        "weapon_lightning" => (100, "lightning gun; wins close/mid if dry feet"),
        "weapon_rocketlauncher" => (95, "rocket launcher; map control"),
        "item_artifact_super_damage" => (90, "quad; spawn-control prize"),
        "item_artifact_invulnerability" => (88, "pentagram"),
        "item_artifact_invisibility" => (82, "ring"),
        "item_artifact_super_health" => (80, "megahealth"),
        "item_armorInv" => (78, "red armour"),
        "item_armor2" => (70, "yellow armour"),
        "weapon_grenadelauncher" => (62, "grenade launcher"),
        "weapon_supernailgun" => (58, "super nailgun"),
        "item_armor1" => (50, "green armour"),
        "weapon_nailgun" => (45, "nailgun"),
        "weapon_supershotgun" => (40, "super shotgun"),
        _ => return None,
    })
}

pub fn recommended_baseline_for(map: &str) -> Option<&'static str> {
    match map {
        "dm4" => Some("ab_dm4_water"),
        "dm2" => Some("ab_dm2_lava"),
        "dm3" => Some("ab_dm3_water"),
        "dm6" => Some("ab_dm6_first"),
        "lqdm2" => Some("match_v3"),
        _ => None,
    }
}

fn map_implications(map: &str) -> Vec<String> {
    // Frozen campaign notes that do not go stale when the graph
    // heals. Live island / door / plat / off_graph lines are pushed
    // by the atlas walk above - do not bake counts or era verdicts
    // here (dm2's "31 lava-side waypoints" outlived the lava-graph
    // slice by ten versions).
    match map {
        "dm4" => vec![
            "lava pit under the walkways; hull-0 contents classify lava deaths (z below -300 is the no-BSP fallback)".into(),
            "quad ledge is a rocket-jump item; prize-only pads are in the nav".into(),
        ],
        "dm2" => vec![
            "closed button-only doors stall at runtime until the button fires".into(),
            "one shootable button (*30 health 1) opens t18".into(),
            "liquid is lava (train-side z around -40), not water".into(),
        ],
        "dm3" => vec![
            "lifts and swim-exit links are compiled in; remaining reach gap is directed (one-way drops), not dry islands".into(),
        ],
        "dm6" => vec![
            "one shootable secret door plus teleporters; no plats".into(),
        ],
        "lqdm2" => vec!["LibreQuake stand-in used for the original headless lab matches".into()],
        _ => Vec::new(),
    }
}

fn dispatcher_knows(cfg: &Config, map: &str) -> bool {
    let path = cfg.src.join("argus_nav_dispatch.qc");
    let Ok(text) = std::fs::read_to_string(path) else {
        return false;
    };
    text.contains(&format!("mapname == \"{map}\""))
}

fn median_spawn_z(items: &[AtlasItem]) -> Option<f32> {
    let mut zs: Vec<f32> = items
        .iter()
        .filter(|i| i.kind == "spawn")
        .filter_map(|i| i.origin.map(|o| o[2]))
        .collect();
    if zs.is_empty() {
        return None;
    }
    zs.sort_by(|a, b| a.partial_cmp(b).unwrap());
    Some(zs[zs.len() / 2])
}

fn atlas_headline(
    map: &str,
    counts: &BTreeMap<String, usize>,
    control: &[ControlItem],
    dispatcher: bool,
    nav: Option<&NavOverlay>,
    cuts: Option<&GraphCuts>,
) -> String {
    let top = control
        .first()
        .map(|c| c.classname.as_str())
        .unwrap_or("no major item");
    let nav_s = match nav {
        Some(n) => format!("{} nodes", n.nodes),
        None => "no nav".into(),
    };
    let islands = cuts
        .map(|c| format!(", {} islands", c.weak))
        .unwrap_or_default();
    let disp = if dispatcher {
        "dispatcher yes"
    } else {
        "dispatcher no (LOS seeking)"
    };
    format!(
        "{map}: {} spawns, {} weapons, top control {top}, {nav_s}{islands}, {disp}",
        counts.get("spawn").copied().unwrap_or(0),
        counts.get("weapon").copied().unwrap_or(0),
    )
}

struct DoorMeta {
    door: String,
    classname: String,
    targetname: Option<String>,
    items: u32,
    mins: [f32; 3],
    maxs: [f32; 3],
}

fn undirected(g: &NavGraph) -> Vec<Vec<u32>> {
    let n = g.nodes.len();
    let mut u = vec![Vec::new(); n];
    for (i, edges) in g.adj.iter().enumerate() {
        for (to, _) in edges {
            let j = *to as usize;
            if j < n {
                if !u[i].contains(&(*to)) {
                    u[i].push(*to);
                }
                if !u[j].contains(&(i as u32)) {
                    u[j].push(i as u32);
                }
            }
        }
    }
    u
}

fn flood(adj: &[Vec<u32>]) -> Vec<Vec<u32>> {
    let n = adj.len();
    let mut seen = vec![false; n];
    let mut out = Vec::new();
    for start in 0..n {
        if seen[start] {
            continue;
        }
        let mut stack = vec![start];
        let mut comp = Vec::new();
        seen[start] = true;
        while let Some(i) = stack.pop() {
            comp.push(i as u32);
            for &j in &adj[i] {
                let ju = j as usize;
                if ju < n && !seen[ju] {
                    seen[ju] = true;
                    stack.push(ju);
                }
            }
        }
        out.push(comp);
    }
    out.sort_by_key(|c| std::cmp::Reverse(c.len()));
    out
}

fn kosaraju(g: &NavGraph) -> Vec<Vec<u32>> {
    let n = g.nodes.len();
    let mut seen = vec![false; n];
    let mut order = Vec::new();
    fn visit(i: usize, g: &NavGraph, seen: &mut [bool], order: &mut Vec<usize>) {
        if seen[i] {
            return;
        }
        seen[i] = true;
        for (to, _) in &g.adj[i] {
            visit(*to as usize, g, seen, order);
        }
        order.push(i);
    }
    for i in 0..n {
        visit(i, g, &mut seen, &mut order);
    }
    let mut rev = vec![Vec::new(); n];
    for (i, edges) in g.adj.iter().enumerate() {
        for (to, _) in edges {
            let j = *to as usize;
            if j < n {
                rev[j].push(i as u32);
            }
        }
    }
    let mut seen = vec![false; n];
    let mut out = Vec::new();
    for &i in order.iter().rev() {
        if seen[i] {
            continue;
        }
        let mut stack = vec![i];
        let mut comp = Vec::new();
        seen[i] = true;
        while let Some(u) = stack.pop() {
            comp.push(u as u32);
            for &v in &rev[u] {
                let vu = v as usize;
                if vu < n && !seen[vu] {
                    seen[vu] = true;
                    stack.push(vu);
                }
            }
        }
        out.push(comp);
    }
    out.sort_by_key(|c| std::cmp::Reverse(c.len()));
    out
}

fn graph_cuts(g: &NavGraph, control: &[ControlItem]) -> (GraphCuts, Vec<u32>) {
    let weak = flood(&undirected(g));
    let strong = kosaraju(g);
    let mut node_island = vec![0u32; g.nodes.len()];
    for (id, comp) in weak.iter().enumerate() {
        for n in comp {
            if (*n as usize) < node_island.len() {
                node_island[*n as usize] = id as u32;
            }
        }
    }
    let islands: Vec<IslandBrief> = weak
        .iter()
        .enumerate()
        .take(8)
        .map(|(id, comp)| {
            let ctrl: Vec<String> = control
                .iter()
                .filter(|c| {
                    c.nearest_node
                        .and_then(|n| node_island.get(n as usize).copied())
                        == Some(id as u32)
                })
                .map(|c| c.classname.clone())
                .collect();
            let sample = comp
                .first()
                .and_then(|n| g.nodes.get(*n as usize))
                .copied();
            IslandBrief {
                id: id as u32,
                nodes: comp.len(),
                control: ctrl,
                sample,
            }
        })
        .collect();
    (
        GraphCuts {
            weak: weak.len(),
            strong: strong.len(),
            largest_weak: weak.first().map(|c| c.len()).unwrap_or(0),
            islands,
        },
        node_island,
    )
}

fn find_door_cuts(g: &NavGraph, doors: &[DoorMeta], causality: &[CausalLink]) -> Vec<DoorCut> {
    let mut out = Vec::new();
    for d in doors {
        let mut sample = Vec::new();
        let mut walk_links = 0u32;
        for (from, edges) in g.adj.iter().enumerate() {
            for (to, kind) in edges {
                if kind != "walk" && kind != "drop" && kind != "door" {
                    continue;
                }
                let a = g.nodes[from];
                let Some(b) = g.nodes.get(*to as usize).copied() else {
                    continue;
                };
                if segment_hits_aabb(d.mins, d.maxs, a, b) {
                    walk_links += 1;
                    if sample.len() < 3 {
                        sample.push([from as u32, *to]);
                    }
                }
            }
        }
        if walk_links == 0 {
            continue;
        }
        let (button, actuator) = d
            .targetname
            .as_deref()
            .and_then(|tn| {
                causality.iter().find(|c| c.to_name == tn).map(|c| {
                    (
                        Some(c.from_target.clone()),
                        Some(c.actuator.clone()),
                    )
                })
            })
            .unwrap_or((None, None));
        let key = if (d.items & 131072 != 0) || (d.items & 16 != 0) {
            Some("silver".to_string())
        } else if (d.items & 262144 != 0) || (d.items & 8 != 0) {
            Some("gold".to_string())
        } else {
            None
        };
        out.push(DoorCut {
            door: d.door.clone(),
            classname: d.classname.clone(),
            targetname: d.targetname.clone(),
            button,
            actuator,
            key,
            walk_links,
            sample,
        });
    }
    out.sort_by_key(|d| std::cmp::Reverse(d.walk_links));
    out.truncate(12);
    out
}

fn find_corridor_misses(
    g: &NavGraph,
    hull: &ClipHull,
    doors: &[([f32; 3], [f32; 3])],
) -> Vec<CorridorMiss> {
    const DIRS: [(f32, f32); 8] = [
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (1.0, 1.0),
        (1.0, -1.0),
        (-1.0, 1.0),
        (-1.0, -1.0),
    ];
    let mut out = Vec::new();
    for n in &g.nodes {
        for (dx, dy) in DIRS {
            let len = (dx * dx + dy * dy).sqrt();
            let p = [n[0] + 16.0 * dx / len, n[1] + 16.0 * dy / len, n[2]];
            let torso = [p[0], p[1], p[2] + 24.0];
            if hull.contents_at(torso) == crate::bsp::CONTENTS_SOLID {
                continue;
            }
            let floor = [p[0], p[1], p[2] - 36.0];
            if hull.contents_at(floor) != crate::bsp::CONTENTS_SOLID {
                continue;
            }
            if doors.iter().any(|(mn, mx)| point_near_aabb(p, *mn, *mx, 8.0)) {
                continue;
            }
            let near = g.nodes.iter().any(|o| {
                let d = (o[0] - p[0]).hypot(o[1] - p[1]).hypot(o[2] - p[2]);
                d < 48.0
            });
            if near {
                continue;
            }
            out.push(CorridorMiss {
                x: p[0],
                y: p[1],
                z: p[2],
                why: "16u standable, no waypoint within 48u".into(),
            });
            if out.len() >= 16 {
                return out;
            }
        }
    }
    out
}

fn parse_origin(s: Option<&str>) -> Option<[f32; 3]> {
    let parts: Vec<f32> = s?
        .split_whitespace()
        .filter_map(|t| t.parse().ok())
        .collect();
    if parts.len() == 3 {
        Some([parts[0], parts[1], parts[2]])
    } else {
        None
    }
}

fn block_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?s)\{(.*?)\}").expect("block"))
}

fn kv_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r#""([^"]+)"\s+"([^"]*)""#).expect("kv"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::bsp::write_mini_bsp;
    use crate::config::load_for_reads_from;
    use std::collections::HashMap;
    use std::fs;

    /// Machine-local regression: on the real dm2 (licensed data, so
    /// this silently passes where the BSP is absent), plat *31 must be
    /// flagged for its static ledge inside the swept column - the
    /// geometry behind the 2026-08-19/20 statue forensics.
    #[test]
    fn dm2_plat_31_flags_the_ledge_in_its_column() {
        let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../maps_local/dm2.bsp");
        if !p.exists() {
            return;
        }
        let bsp = crate::bsp::read_bsp29(&p).unwrap();
        let ents = parse_entities(&bsp.entities);
        let items: Vec<AtlasItem> = ents
            .iter()
            .filter(|e| e.get("classname").map(|c| c.as_str()) == Some("func_plat"))
            .map(|e| AtlasItem {
                classname: "func_plat".into(),
                kind: "plat".into(),
                origin: None,
                target: e.get("target").cloned(),
                targetname: e.get("targetname").cloned(),
                model: e.get("model").cloned(),
                spawnflags: 0,
                health: None,
            })
            .collect();
        assert_eq!(items.len(), 2, "dm2 carries two plats");
        let plats = analyze_plats(&items, &bsp, None);
        assert_eq!(plats.len(), 2);
        let p31 = plats.iter().find(|p| p.model == "*31").expect("*31 analyzed");
        assert!(
            p31.warnings.iter().any(|w| w.contains("swept column")),
            "*31 must be flagged for the ledge in its column, got {:?}",
            p31.warnings
        );
    }

    fn ents() -> &'static str {
        r#"
{
"classname" "worldspawn"
"message" "The Bad Place"
}
{
"classname" "info_player_deathmatch"
"origin" "0 0 24"
}
{
"classname" "weapon_rocketlauncher"
"origin" "200 -100 24"
}
{
"classname" "item_health"
"origin" "50 50 24"
"spawnflags" "2"
}
{
"classname" "item_health"
"origin" "60 60 24"
}
{
"classname" "item_artifact_super_damage"
"origin" "400 0 200"
}
{
"classname" "func_button"
"target" "bridge"
"health" "1"
}
{
"classname" "func_door"
"targetname" "bridge"
}
{
"classname" "func_button"
"target" "relay1"
}
{
"classname" "trigger_relay"
"targetname" "relay1"
"target" "secret1"
}
{
"classname" "func_door_secret"
"targetname" "secret1"
}
{
"classname" "weapon_supershotgun"
"origin" "1 1 24"
"spawnflags" "2048"
}
{
"classname" "trigger_teleport"
"target" "t1"
"model" "*1"
}
{
"classname" "info_teleport_destination"
"targetname" "t1"
"origin" "10 20 30"
}
"#
    }

    #[test]
    fn classifies_and_links() {
        let parsed = parse_entities(ents());
        assert!(parsed.iter().any(|e| e["classname"] == "weapon_rocketlauncher"));
        assert_eq!(classify("weapon_lightning"), "weapon");
        assert_eq!(classify("info_player_deathmatch"), "spawn");
        assert_eq!(classify("item_artifact_invulnerability"), "powerup");
        let mega = parsed.iter().find(|e| e.get("spawnflags").map(|s| s.as_str()) == Some("2"));
        assert!(mega.is_some());
        assert_eq!(item_value("item_health", 2).unwrap().1, "megahealth");
        assert!(item_value("item_health", 0).is_none());
    }

    #[test]
    fn ingest_mini_bsp_builds_atlas() {
        let root = std::env::temp_dir().join(format!("argus-carto-{}", std::process::id()));
        let maps = root.join("maps_local");
        fs::create_dir_all(&maps).unwrap();
        let raw = write_mini_bsp(ents(), [-256.0, -256.0, -64.0], [256.0, 256.0, 128.0]);
        let bsp_path = maps.join("dmtest.bsp");
        fs::write(&bsp_path, raw).unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, &root).unwrap();
        let atlas = cartograph(&cfg, "dmtest").unwrap();
        assert_eq!(atlas.map, "dmtest");
        assert_eq!(atlas.ingested_from, "filesystem");
        assert_eq!(atlas.message.as_deref(), Some("The Bad Place"));
        assert_eq!(atlas.counts.get("weapon"), Some(&1));
        assert_eq!(atlas.counts.get("spawn"), Some(&1));
        assert_eq!(atlas.teleports.len(), 1);
        assert_eq!(atlas.teleports[0].dest_origin, Some([10.0, 20.0, 30.0]));
        assert!(atlas
            .causality
            .iter()
            .any(|c| c.actuator == "shoot" && c.to_class == "func_door"));
        assert!(
            atlas
                .causality
                .iter()
                .any(|c| c.hops == 2 && c.to_class == "func_door_secret"),
            "relay hop: {:?}",
            atlas.causality
        );
        assert!(
            atlas
                .control
                .iter()
                .all(|c| c.classname != "weapon_supershotgun"),
            "2048 not-in-deathmatch should not be control"
        );
        assert!(atlas.items.iter().any(|i| i.classname == "item_artifact_super_damage"));
        assert!(
            atlas
                .control
                .iter()
                .any(|c| c.classname == "item_artifact_super_damage" && c.elevated),
            "control: {:?}",
            atlas.control
        );
        assert!(atlas.headline.contains("dmtest"));
        assert!(atlas.recipe.contains("match_run"));
        let brief = atlas_brief(&atlas);
        assert!(brief.control.iter().any(|c| c.reach == "rocket_jump" || c.elevated));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn real_dm4_if_present() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../maps_local/dm4.bsp");
        if !path.exists() {
            return;
        }
        let root = path.parent().unwrap().parent().unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, root).unwrap();
        let atlas = cartograph(&cfg, "dm4").unwrap();
        assert_eq!(atlas.version, 29);
        assert!(atlas.counts.get("spawn").copied().unwrap_or(0) >= 4);
        assert!(atlas.items.iter().any(|i| i.classname.starts_with("weapon_")));
        assert!(!atlas.teleports.is_empty());
        assert!(atlas.nav.is_some(), "dm4 nav JSON should exist in this tree");
        assert!(atlas.dispatcher_known);
        assert!(atlas.headline.contains("dm4"));
        assert!(atlas
            .control
            .iter()
            .any(|c| c.classname == "weapon_rocketlauncher"));
        assert!(!atlas.height_bands.is_empty());
        assert!(atlas.control.iter().any(|c| c.nearest_node.is_some()));
        assert!(
            atlas.control.iter().any(|c| c.reach == "walk"),
            "expected an on-graph prize, got {:?}",
            atlas.control
        );
        // floor-seated origins must not read off_graph (the item_eye
        // fix): dm4 routes its whole control set at runtime, so a
        // majority-off_graph label set means the classifier is wrong,
        // not the map. The pit RL and the LG are the sentinels - both
        // are floor-seated (lump origin 24 below their node) and both
        // were mislabelled before the fix.
        let off = atlas.control.iter().filter(|c| c.reach == "off_graph").count();
        assert!(
            off * 2 < atlas.control.len(),
            "majority of dm4 control off_graph: {:?}",
            atlas
                .control
                .iter()
                .map(|c| (c.classname.clone(), c.reach.clone()))
                .collect::<Vec<_>>()
        );
        assert!(
            atlas
                .control
                .iter()
                .filter(|c| c.classname == "weapon_lightning"
                    || c.classname == "weapon_rocketlauncher")
                .all(|c| c.reach == "walk"),
            "floor-seated prizes must snap walk: {:?}",
            atlas.control
        );
        let node = lookup_node(&cfg, "dm4", 56).unwrap();
        assert_eq!(node.node, 56);
        assert!(!node.band.is_empty());
        let insp = inspect_entities(&cfg, "dm4", Some("weapon_rocket")).unwrap();
        assert!(insp.items.iter().all(|i| i.classname.contains("rocket")));
        assert!(!insp.items.is_empty());
        let cuts = atlas.graph_cuts.expect("dm4 nav should yield graph_cuts");
        assert!(cuts.weak >= 1);
        assert_eq!(cuts.largest_weak, cuts.islands.first().map(|i| i.nodes).unwrap_or(0));
        assert!(atlas.headline.contains("islands"));
    }

    #[test]
    fn real_dm2_if_present_reports_door_cuts() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../maps_local/dm2.bsp");
        if !path.exists() {
            return;
        }
        let root = path.parent().unwrap().parent().unwrap();
        let mut env = HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let cfg = load_for_reads_from(&env, root).unwrap();
        let atlas = cartograph(&cfg, "dm2").unwrap();
        // the recommendation is the baselines.json override when the
        // live runs dir carries one, else the era default
        let expect = crate::intel::baseline_override_for(&cfg, "dm2")
            .unwrap_or_else(|| "ab_dm2_lava".to_string());
        assert_eq!(atlas.recommended_baseline.as_deref(), Some(expect.as_str()));
        assert!(
            !atlas.door_cuts.is_empty(),
            "dm2 button-doors should cut walk links: {:?}",
            atlas.door_cuts
        );
        let cuts = atlas.graph_cuts.expect("dm2 nav");
        assert!(cuts.weak >= 1);
    }

    fn dummy_overlay(n: usize) -> NavOverlay {
        NavOverlay {
            json_path: String::new(),
            nodes: n,
            links: 0,
            jump_links: 0,
            tele_links: 0,
            rocket_links: 0,
            lift_links: 0,
            swim_links: 0,
            sprint_links: 0,
            train_links: 0,
            door_links: 0,
        }
    }

    #[test]
    fn two_islands_from_a_disconnected_node() {
        let g = NavGraph {
            overlay: dummy_overlay(3),
            nodes: vec![[0.0, 0.0, 0.0], [32.0, 0.0, 0.0], [400.0, 0.0, 0.0]],
            adj: vec![
                vec![(1, "walk".into())],
                vec![(0, "walk".into())],
                vec![],
            ],
        };
        let (cuts, map) = graph_cuts(&g, &[]);
        assert_eq!(cuts.weak, 2);
        assert_eq!(map[2], 1);
        assert_eq!(cuts.largest_weak, 2);
    }

    #[test]
    fn door_aabb_cuts_a_walk_link() {
        let g = NavGraph {
            overlay: dummy_overlay(2),
            nodes: vec![[0.0, 0.0, 0.0], [64.0, 0.0, 0.0]],
            adj: vec![vec![(1, "walk".into())], vec![]],
        };
        let doors = [DoorMeta {
            door: "*12".into(),
            classname: "func_door".into(),
            targetname: Some("t6".into()),
            items: 0,
            mins: [20.0, -16.0, -16.0],
            maxs: [40.0, 16.0, 16.0],
        }];
        let causality = [CausalLink {
            from_class: "func_button".into(),
            from_target: "*15".into(),
            to_class: "func_door".into(),
            to_name: "t6".into(),
            actuator: "touch".into(),
            hops: 1,
            via: None,
        }];
        let cuts = find_door_cuts(&g, &doors, &causality);
        assert_eq!(cuts.len(), 1);
        assert_eq!(cuts[0].walk_links, 1);
        assert_eq!(cuts[0].button.as_deref(), Some("*15"));
        assert_eq!(cuts[0].key, None);
        assert_eq!(cuts[0].sample, vec![[0, 1]]);
    }

    #[test]
    fn door_keyed_cut_records_key_requirement() {
        let g = NavGraph {
            overlay: dummy_overlay(2),
            nodes: vec![[0.0, 0.0, 0.0], [64.0, 0.0, 0.0]],
            adj: vec![vec![(1, "walk".into())], vec![]],
        };
        let doors = [DoorMeta {
            door: "*13".into(),
            classname: "func_door".into(),
            targetname: None,
            items: 131072, // IT_KEY1: silver key
            mins: [20.0, -16.0, -16.0],
            maxs: [40.0, 16.0, 16.0],
        }];
        let cuts = find_door_cuts(&g, &doors, &[]);
        assert_eq!(cuts.len(), 1);
        assert_eq!(cuts[0].key.as_deref(), Some("silver"));
    }

    #[test]
    fn map_implications_do_not_bake_era_counts() {
        let dm2 = map_implications("dm2");
        assert!(
            dm2.iter().all(|s| !s.contains("31 lava")),
            "frozen lava-waypoint count leaked: {dm2:?}"
        );
        let dm3 = map_implications("dm3");
        assert!(
            dm3.iter().all(|s| !s.contains("dry corridors")),
            "stale dry-island note leaked: {dm3:?}"
        );
        let dm6 = map_implications("dm6");
        assert!(
            dm6.iter().all(|s| !s.contains("debut botmatch")),
            "stale debut verdict leaked: {dm6:?}"
        );
    }

    /// #29: dm3 rides its three plats in every tape (liftlinks are in
    /// the shipped graph), yet static hull 0 alone briefed two of them
    /// as "the runtime cannot walk aboard". Machine-local like its
    /// dm2 neighbour above.
    #[test]
    fn dm3_nav_served_plats_stop_warning_unboardable() {
        let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../maps_local/dm3.bsp");
        let jf = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../src/argus_nav_dm3.qc.json");
        if !p.exists() || !jf.exists() {
            return;
        }
        let bsp = crate::bsp::read_bsp29(&p).unwrap();
        let ents = parse_entities(&bsp.entities);
        let items: Vec<AtlasItem> = ents
            .iter()
            .filter(|e| e.get("classname").map(|c| c.as_str()) == Some("func_plat"))
            .map(|e| AtlasItem {
                classname: "func_plat".into(),
                kind: "plat".into(),
                origin: None,
                target: e.get("target").cloned(),
                targetname: e.get("targetname").cloned(),
                model: e.get("model").cloned(),
                spawnflags: 0,
                health: None,
            })
            .collect();
        let bare = analyze_plats(&items, &bsp, None);
        assert!(
            bare.iter()
                .any(|p| p.warnings.iter().any(|w| w.contains("cannot walk aboard"))),
            "expected the pre-fix false warning on raw geometry"
        );
        let g = load_nav_graph_at(&jf).expect("dm3 nav graph");
        assert!(g.overlay.lift_links >= 1, "dm3 ships lift links");
        let served = analyze_plats(&items, &bsp, Some(&g));
        for pl in &served {
            assert!(
                !pl.warnings.iter().any(|w| w.contains("cannot walk aboard")),
                "plat {} still briefed unboardable with lift links present",
                pl.model
            );
        }
        assert!(served.iter().any(|pl| pl.nav_served));
    }
}
