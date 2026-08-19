//! Vanilla BSP29 reader. Enough for the cartographer: entities and world bounds.

use std::path::Path;

const HEADER: usize = 4 + 15 * 8;
const MODEL_SIZE: usize = 64;

pub const CONTENTS_EMPTY: i32 = -1;
pub const CONTENTS_SOLID: i32 = -2;
pub const CONTENTS_WATER: i32 = -3;
pub const CONTENTS_SLIME: i32 = -4;
pub const CONTENTS_LAVA: i32 = -5;

/// Render hull (hull 0). Leaves keep real contents, so this is the
/// classifier for lava / slime / water. Clip hulls collapse liquids
/// to empty, which is why dm2's trench was invisible to hull 1.
#[derive(Debug, Clone)]
pub struct Hull0 {
    planes: Vec<([f32; 3], f32)>,
    nodes: Vec<(i32, i32, i32)>,
    leaves: Vec<i32>,
    head: i32,
}

impl Hull0 {
    pub fn contents_at(&self, p: [f32; 3]) -> i32 {
        let mut n = self.head;
        let mut guard = 0;
        while n >= 0 && guard < 4096 {
            guard += 1;
            let idx = n as usize;
            if idx >= self.nodes.len() {
                return CONTENTS_SOLID;
            }
            let (pi, c0, c1) = self.nodes[idx];
            let Some((normal, dist)) = self.planes.get(pi as usize).copied() else {
                return CONTENTS_SOLID;
            };
            let d = normal[0] * p[0] + normal[1] * p[1] + normal[2] * p[2] - dist;
            n = if d >= 0.0 { c0 } else { c1 };
        }
        if n >= 0 {
            return CONTENTS_SOLID;
        }
        let leaf = (-1 - n) as usize;
        self.leaves.get(leaf).copied().unwrap_or(CONTENTS_SOLID)
    }

    pub fn is_hazard(&self, p: [f32; 3]) -> bool {
        matches!(self.contents_at(p), CONTENTS_LAVA | CONTENTS_SLIME)
    }
}

/// Classify a death origin. Probe the point and one step below
/// (the victim origin sits above the surface). No hull: z < -300,
/// the old dm4-shaped rule, used only when the BSP is missing.
pub fn death_is_lava(hull: Option<&Hull0>, x: f64, y: f64, z: f64) -> bool {
    match hull {
        Some(h) => {
            let p = [x as f32, y as f32, z as f32];
            h.is_hazard(p) || h.is_hazard([p[0], p[1], p[2] - 24.0])
        }
        None => z < -300.0,
    }
}

/// Player clip hull (hull 1). Liquids collapse to empty here; use it
/// for solid walls, not for lava/water classification.
#[derive(Debug, Clone)]
pub struct ClipHull {
    planes: Vec<([f32; 3], f32)>,
    nodes: Vec<(i32, i16, i16)>,
    head: i32,
}

impl ClipHull {
    pub fn contents_at(&self, p: [f32; 3]) -> i32 {
        let mut n = self.head;
        let mut guard = 0;
        while n >= 0 && guard < 4096 {
            guard += 1;
            let idx = n as usize;
            if idx >= self.nodes.len() {
                return CONTENTS_SOLID;
            }
            let (pi, c0, c1) = self.nodes[idx];
            let Some((normal, dist)) = self.planes.get(pi as usize).copied() else {
                return CONTENTS_SOLID;
            };
            let d = normal[0] * p[0] + normal[1] * p[1] + normal[2] * p[2] - dist;
            n = if d >= 0.0 { c0 as i32 } else { c1 as i32 };
        }
        n
    }

    /// Stepped point sample. Good enough for item-to-node snaps.
    pub fn line_clear(&self, a: [f32; 3], b: [f32; 3]) -> bool {
        const STEPS: i32 = 20;
        for i in 0..=STEPS {
            let t = i as f32 / STEPS as f32;
            let p = [
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t,
            ];
            if self.contents_at(p) == CONTENTS_SOLID {
                return false;
            }
        }
        true
    }
}

#[derive(Debug, Clone)]
pub struct Bsp29 {
    pub version: i32,
    pub entities: String,
    pub mins: [f32; 3],
    pub maxs: [f32; 3],
    pub models: Vec<BModel>,
    pub clip: Option<ClipHull>,
    pub hull0: Option<Hull0>,
}

#[derive(Debug, Clone)]
pub struct BModel {
    pub mins: [f32; 3],
    pub maxs: [f32; 3],
}

pub fn read_bsp29(path: &Path) -> Result<Bsp29, String> {
    let data = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    parse_bsp29(&data)
}

pub fn parse_bsp29(data: &[u8]) -> Result<Bsp29, String> {
    if data.len() < HEADER {
        return Err("BSP too short for a BSP29 header".into());
    }
    let version = i32::from_le_bytes(data[0..4].try_into().unwrap());
    if version != 29 {
        return Err(format!("not BSP29 (version {version})"));
    }
    let lumps: Vec<(u32, u32)> = (0..15)
        .map(|i| {
            let o = 4 + i * 8;
            (
                u32::from_le_bytes(data[o..o + 4].try_into().unwrap()),
                u32::from_le_bytes(data[o + 4..o + 8].try_into().unwrap()),
            )
        })
        .collect();

    let (eo, el) = lumps[0];
    let ent_bytes = lump(data, eo, el)?;
    let end = ent_bytes.iter().position(|&b| b == 0).unwrap_or(ent_bytes.len());
    let entities = String::from_utf8_lossy(&ent_bytes[..end]).into_owned();

    let (mo, ml) = lumps[14];
    let md = lump(data, mo, ml)?;
    let mut models = Vec::new();
    let mut i = 0;
    while i + MODEL_SIZE <= md.len() {
        let mins = [
            f32_le(md, i),
            f32_le(md, i + 4),
            f32_le(md, i + 8),
        ];
        let maxs = [
            f32_le(md, i + 12),
            f32_le(md, i + 16),
            f32_le(md, i + 20),
        ];
        models.push(BModel { mins, maxs });
        i += MODEL_SIZE;
    }
    let (mins, maxs) = models
        .first()
        .map(|m| (m.mins, m.maxs))
        .unwrap_or(([0.0; 3], [0.0; 3]));

    let clip = parse_clip_hull(data, &lumps, md);
    let hull0 = parse_hull0(data, &lumps, md);

    Ok(Bsp29 {
        version,
        entities,
        mins,
        maxs,
        models,
        clip,
        hull0,
    })
}

fn parse_clip_hull(data: &[u8], lumps: &[(u32, u32)], md: &[u8]) -> Option<ClipHull> {
    if md.len() < 44 {
        return None;
    }
    // dmodel_t: 9 floats then headnode[4]; headnode[1] is the player hull
    let head = i32::from_le_bytes(md[40..44].try_into().ok()?);
    let (po, pl) = lumps[1];
    let planes_raw = lump(data, po, pl).ok()?;
    if planes_raw.len() < 20 {
        return None;
    }
    let mut planes = Vec::new();
    let mut i = 0;
    while i + 20 <= planes_raw.len() {
        planes.push((
            [
                f32_le(planes_raw, i),
                f32_le(planes_raw, i + 4),
                f32_le(planes_raw, i + 8),
            ],
            f32_le(planes_raw, i + 12),
        ));
        i += 20;
    }
    let (co, cl) = lumps[9];
    let clip_raw = lump(data, co, cl).ok()?;
    if clip_raw.len() < 8 {
        return None;
    }
    let mut nodes = Vec::new();
    let mut i = 0;
    while i + 8 <= clip_raw.len() {
        let planenum = i32::from_le_bytes(clip_raw[i..i + 4].try_into().ok()?);
        let c0 = i16::from_le_bytes(clip_raw[i + 4..i + 6].try_into().ok()?);
        let c1 = i16::from_le_bytes(clip_raw[i + 6..i + 8].try_into().ok()?);
        nodes.push((planenum, c0, c1));
        i += 8;
    }
    if nodes.is_empty() || planes.is_empty() {
        return None;
    }
    Some(ClipHull {
        planes,
        nodes,
        head,
    })
}

fn parse_hull0(data: &[u8], lumps: &[(u32, u32)], md: &[u8]) -> Option<Hull0> {
    if md.len() < 40 {
        return None;
    }
    // dmodel_t: 9 floats then headnode[4]; headnode[0] is the render hull
    let head = i32::from_le_bytes(md[36..40].try_into().ok()?);
    let (po, pl) = lumps[1];
    let planes_raw = lump(data, po, pl).ok()?;
    if planes_raw.len() < 20 {
        return None;
    }
    let mut planes = Vec::new();
    let mut i = 0;
    while i + 20 <= planes_raw.len() {
        planes.push((
            [
                f32_le(planes_raw, i),
                f32_le(planes_raw, i + 4),
                f32_le(planes_raw, i + 8),
            ],
            f32_le(planes_raw, i + 12),
        ));
        i += 20;
    }
    let (no, nl) = lumps[5];
    let nodes_raw = lump(data, no, nl).ok()?;
    if nodes_raw.len() < 24 {
        return None;
    }
    let mut nodes = Vec::new();
    let mut i = 0;
    while i + 24 <= nodes_raw.len() {
        let planenum = i32::from_le_bytes(nodes_raw[i..i + 4].try_into().ok()?);
        let c0 = i16::from_le_bytes(nodes_raw[i + 4..i + 6].try_into().ok()?) as i32;
        let c1 = i16::from_le_bytes(nodes_raw[i + 6..i + 8].try_into().ok()?) as i32;
        nodes.push((planenum, c0, c1));
        i += 24;
    }
    let (lo, ll) = lumps[10];
    let leaves_raw = lump(data, lo, ll).ok()?;
    if leaves_raw.len() < 28 {
        return None;
    }
    let mut leaves = Vec::new();
    let mut i = 0;
    while i + 28 <= leaves_raw.len() {
        leaves.push(i32::from_le_bytes(leaves_raw[i..i + 4].try_into().ok()?));
        i += 28;
    }
    if nodes.is_empty() || planes.is_empty() || leaves.is_empty() {
        return None;
    }
    Some(Hull0 {
        planes,
        nodes,
        leaves,
        head,
    })
}

fn lump(data: &[u8], off: u32, len: u32) -> Result<&[u8], String> {
    let start = off as usize;
    let end = start.saturating_add(len as usize);
    if end > data.len() {
        return Err(format!("lump out of range ({start}..{end} of {})", data.len()));
    }
    Ok(&data[start..end])
}

fn f32_le(data: &[u8], off: usize) -> f32 {
    f32::from_le_bytes(data[off..off + 4].try_into().unwrap())
}

/// Minimal PACK reader: find a file by basename (case-insensitive).
pub fn pak_find(pak: &Path, basename: &str) -> Result<Option<Vec<u8>>, String> {
    let data = std::fs::read(pak).map_err(|e| format!("{}: {e}", pak.display()))?;
    if data.len() < 12 || &data[0..4] != b"PACK" {
        return Err(format!("{}: not a PAK", pak.display()));
    }
    let dir_ofs = i32::from_le_bytes(data[4..8].try_into().unwrap()) as usize;
    let dir_len = i32::from_le_bytes(data[8..12].try_into().unwrap()) as usize;
    let want = basename.to_ascii_lowercase();
    let mut found = None;
    let mut i = dir_ofs;
    let end = dir_ofs.saturating_add(dir_len);
    while i + 64 <= end.min(data.len()) {
        let raw = &data[i..i + 56];
        let nlen = raw.iter().position(|&b| b == 0).unwrap_or(56);
        let name = String::from_utf8_lossy(&raw[..nlen]).replace('\\', "/");
        let ofs = i32::from_le_bytes(data[i + 56..i + 60].try_into().unwrap()) as usize;
        let length = i32::from_le_bytes(data[i + 60..i + 64].try_into().unwrap()) as usize;
        let base = name.rsplit('/').next().unwrap_or(&name).to_ascii_lowercase();
        if base == want {
            if ofs + length <= data.len() {
                found = Some(data[ofs..ofs + length].to_vec());
            }
        }
        i += 64;
    }
    Ok(found)
}

pub fn pak_list_maps(pak: &Path) -> Result<Vec<String>, String> {
    let data = std::fs::read(pak).map_err(|e| format!("{}: {e}", pak.display()))?;
    if data.len() < 12 || &data[0..4] != b"PACK" {
        return Err(format!("{}: not a PAK", pak.display()));
    }
    let dir_ofs = i32::from_le_bytes(data[4..8].try_into().unwrap()) as usize;
    let dir_len = i32::from_le_bytes(data[8..12].try_into().unwrap()) as usize;
    let mut maps = Vec::new();
    let mut i = dir_ofs;
    let end = dir_ofs.saturating_add(dir_len);
    while i + 64 <= end.min(data.len()) {
        let raw = &data[i..i + 56];
        let nlen = raw.iter().position(|&b| b == 0).unwrap_or(56);
        let name = String::from_utf8_lossy(&raw[..nlen]).replace('\\', "/");
        let base = name.rsplit('/').next().unwrap_or(&name).to_string();
        if base.to_ascii_lowercase().ends_with(".bsp") {
            maps.push(base);
        }
        i += 64;
    }
    maps.sort();
    maps.dedup();
    Ok(maps)
}

#[cfg(test)]
pub fn write_mini_bsp(ents: &str, mins: [f32; 3], maxs: [f32; 3]) -> Vec<u8> {
    let mut ents = ents.as_bytes().to_vec();
    if !ents.ends_with(&[0]) {
        ents.push(0);
    }
    let mut model = vec![0u8; MODEL_SIZE];
    model[0..4].copy_from_slice(&mins[0].to_le_bytes());
    model[4..8].copy_from_slice(&mins[1].to_le_bytes());
    model[8..12].copy_from_slice(&mins[2].to_le_bytes());
    model[12..16].copy_from_slice(&maxs[0].to_le_bytes());
    model[16..20].copy_from_slice(&maxs[1].to_le_bytes());
    model[20..24].copy_from_slice(&maxs[2].to_le_bytes());

    let ent_off = HEADER as u32;
    let ent_len = ents.len() as u32;
    let mod_off = ent_off + ent_len;
    let mod_len = MODEL_SIZE as u32;

    let mut out = vec![0u8; HEADER];
    out[0..4].copy_from_slice(&29i32.to_le_bytes());
    // lump 0 entities
    out[4..8].copy_from_slice(&ent_off.to_le_bytes());
    out[8..12].copy_from_slice(&ent_len.to_le_bytes());
    // lump 14 models
    let lo = 4 + 14 * 8;
    out[lo..lo + 4].copy_from_slice(&mod_off.to_le_bytes());
    out[lo + 4..lo + 8].copy_from_slice(&mod_len.to_le_bytes());
    out.extend_from_slice(&ents);
    out.extend_from_slice(&model);
    out
}

/// Test BSP: hull 0 is a z=0 plane, empty above, lava below.
#[cfg(test)]
pub fn write_halfspace_bsp() -> Vec<u8> {
    let mut planes = vec![0u8; 20];
    planes[8..12].copy_from_slice(&1.0f32.to_le_bytes()); // normal z
    let mut node = vec![0u8; 24];
    node[4..6].copy_from_slice(&(-1i16).to_le_bytes()); // leaf 0 (empty)
    node[6..8].copy_from_slice(&(-2i16).to_le_bytes()); // leaf 1 (lava)
    let mut leaf_empty = vec![0u8; 28];
    leaf_empty[0..4].copy_from_slice(&CONTENTS_EMPTY.to_le_bytes());
    let mut leaf_lava = vec![0u8; 28];
    leaf_lava[0..4].copy_from_slice(&CONTENTS_LAVA.to_le_bytes());
    let mut model = vec![0u8; MODEL_SIZE];
    // headnode[0] = 0 at offset 36
    model[36..40].copy_from_slice(&0i32.to_le_bytes());

    let plane_off = HEADER as u32;
    let node_off = plane_off + 20;
    let leaf_off = node_off + 24;
    let mod_off = leaf_off + 56;

    let mut out = vec![0u8; HEADER];
    out[0..4].copy_from_slice(&29i32.to_le_bytes());
    set_lump(&mut out, 1, plane_off, 20);
    set_lump(&mut out, 5, node_off, 24);
    set_lump(&mut out, 10, leaf_off, 56);
    set_lump(&mut out, 14, mod_off, MODEL_SIZE as u32);
    out.extend_from_slice(&planes);
    out.extend_from_slice(&node);
    out.extend_from_slice(&leaf_empty);
    out.extend_from_slice(&leaf_lava);
    out.extend_from_slice(&model);
    out
}

#[cfg(test)]
fn set_lump(hdr: &mut [u8], i: usize, off: u32, len: u32) {
    let o = 4 + i * 8;
    hdr[o..o + 4].copy_from_slice(&off.to_le_bytes());
    hdr[o + 4..o + 8].copy_from_slice(&len.to_le_bytes());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mini_bsp_roundtrip() {
        let ents = "{\n\"classname\" \"worldspawn\"\n\"message\" \"The Pit\"\n}\n";
        let raw = write_mini_bsp(ents, [-128.0, -64.0, -32.0], [128.0, 64.0, 32.0]);
        let bsp = parse_bsp29(&raw).unwrap();
        assert_eq!(bsp.version, 29);
        assert!(bsp.entities.contains("The Pit"));
        assert!((bsp.mins[0] + 128.0).abs() < 0.01);
        assert!((bsp.maxs[2] - 32.0).abs() < 0.01);
        assert!(bsp.hull0.is_none());
    }

    #[test]
    fn hull0_classifies_lava_below_the_plane() {
        let raw = write_halfspace_bsp();
        let bsp = parse_bsp29(&raw).unwrap();
        let h = bsp.hull0.expect("hull0");
        assert_eq!(h.contents_at([0.0, 0.0, 16.0]), CONTENTS_EMPTY);
        assert_eq!(h.contents_at([0.0, 0.0, -16.0]), CONTENTS_LAVA);
        assert!(death_is_lava(Some(&h), 0.0, 0.0, -8.0));
        assert!(!death_is_lava(Some(&h), 0.0, 0.0, 40.0));
        // no hull: only the dm4-shaped z rule
        assert!(death_is_lava(None, 0.0, 0.0, -360.0));
        assert!(!death_is_lava(None, 0.0, 0.0, -35.0));
    }
}
