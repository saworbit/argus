//! NetQuake .dem reader (protocol 15) - the microscope beside the
//! ARGLOG tape. A demo carries what telemetry cannot: full-rate
//! positions for every entity (the 1 Hz ARGLOG misses anything under
//! a second - dodges, rocket-jump arcs, sprint run-ups), projectiles
//! in flight, view angles, and the human's exact movement. Demos are
//! recorded by the CLIENT (`+record <name> <map>` in the launch
//! command; a headless dedicated match cannot record), harvested into
//! runs/demos/, and read here as pure offline tooling - the charter
//! is untouched.
//!
//! Bots identify themselves in the stream for free: v3.15 gave every
//! bot `skin = ar_slot + 1` on the player model, and svc_updatename
//! carries the roster, so a player-model entity's skin byte IS its
//! scoreboard row. Real clients are entities 1..maxclients with skin
//! 0. No position correlation needed.

use serde::Serialize;
use std::collections::BTreeMap;
use std::path::PathBuf;

use crate::config::Config;

// svc_* opcodes, protocol 15
const SVC_NOP: u8 = 1;
const SVC_DISCONNECT: u8 = 2;
const SVC_UPDATESTAT: u8 = 3;
const SVC_VERSION: u8 = 4;
const SVC_SETVIEW: u8 = 5;
const SVC_SOUND: u8 = 6;
const SVC_TIME: u8 = 7;
const SVC_PRINT: u8 = 8;
const SVC_STUFFTEXT: u8 = 9;
const SVC_SETANGLE: u8 = 10;
const SVC_SERVERINFO: u8 = 11;
const SVC_LIGHTSTYLE: u8 = 12;
const SVC_UPDATENAME: u8 = 13;
const SVC_UPDATEFRAGS: u8 = 14;
const SVC_CLIENTDATA: u8 = 15;
const SVC_STOPSOUND: u8 = 16;
const SVC_UPDATECOLORS: u8 = 17;
const SVC_PARTICLE: u8 = 18;
const SVC_DAMAGE: u8 = 19;
const SVC_SPAWNSTATIC: u8 = 20;
const SVC_SPAWNBASELINE: u8 = 22;
const SVC_TEMP_ENTITY: u8 = 23;
const SVC_SETPAUSE: u8 = 24;
const SVC_SIGNONNUM: u8 = 25;
const SVC_CENTERPRINT: u8 = 26;
const SVC_KILLEDMONSTER: u8 = 27;
const SVC_FOUNDSECRET: u8 = 28;
const SVC_SPAWNSTATICSOUND: u8 = 29;
const SVC_INTERMISSION: u8 = 30;
const SVC_FINALE: u8 = 31;
const SVC_CDTRACK: u8 = 32;
const SVC_SELLSCREEN: u8 = 33;
const SVC_CUTSCENE: u8 = 34;

// fast-update U_* bits
const U_MOREBITS: u16 = 1;
const U_ORIGIN1: u16 = 1 << 1;
const U_ORIGIN2: u16 = 1 << 2;
const U_ORIGIN3: u16 = 1 << 3;
const U_ANGLE2: u16 = 1 << 4;
const U_FRAME: u16 = 1 << 6;
const U_ANGLE1: u16 = 1 << 8;
const U_ANGLE3: u16 = 1 << 9;
const U_MODEL: u16 = 1 << 10;
const U_COLORMAP: u16 = 1 << 11;
const U_SKIN: u16 = 1 << 12;
const U_EFFECTS: u16 = 1 << 13;
const U_LONGENTITY: u16 = 1 << 14;

// svc_clientdata SU_* bits
const SU_VIEWHEIGHT: u16 = 1;
const SU_IDEALPITCH: u16 = 1 << 1;
const SU_PUNCH1: u16 = 1 << 2;
const SU_VELOCITY1: u16 = 1 << 5;
const SU_WEAPONFRAME: u16 = 1 << 12;
const SU_ARMOR: u16 = 1 << 13;
const SU_WEAPON: u16 = 1 << 14;

#[derive(Debug, Clone, Serialize)]
pub struct DemoBrief {
    pub file: String,
    pub protocol: i32,
    pub level: String,
    pub maxclients: u8,
    pub duration_sec: f64,
    pub blocks: usize,
    /// true when the file ends mid-block (a killed engine instead of
    /// a `stop`); everything up to the tear still counts
    pub truncated: bool,
    /// scoreboard slot -> netname (svc_updatename)
    pub names: BTreeMap<u8, String>,
    pub tracks: Vec<TrackBrief>,
    /// last console prints in the stream (obituaries, chat)
    pub prints_tail: Vec<String>,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct TrackBrief {
    pub entity: u16,
    /// resolved player identity: skin byte -> roster slot for bots,
    /// entity number -> client slot for humans
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    pub kind: String,
    pub samples: usize,
    pub hz: f64,
    pub first: [f32; 3],
    pub last: [f32; 3],
    pub dist: f64,
}

/// Full-rate positions for one entity, for analysis callers.
#[derive(Debug, Clone, Serialize)]
pub struct Track {
    pub entity: u16,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    pub kind: String,
    pub t: Vec<f64>,
    pub pos: Vec<[f32; 3]>,
}

struct Reader<'a> {
    d: &'a [u8],
    p: usize,
}

impl<'a> Reader<'a> {
    fn new(d: &'a [u8]) -> Self {
        Reader { d, p: 0 }
    }
    fn left(&self) -> usize {
        self.d.len().saturating_sub(self.p)
    }
    fn u8(&mut self) -> Option<u8> {
        let v = *self.d.get(self.p)?;
        self.p += 1;
        Some(v)
    }
    fn i8(&mut self) -> Option<i8> {
        Some(self.u8()? as i8)
    }
    fn i16(&mut self) -> Option<i16> {
        if self.left() < 2 {
            return None;
        }
        let v = i16::from_le_bytes([self.d[self.p], self.d[self.p + 1]]);
        self.p += 2;
        Some(v)
    }
    fn i32(&mut self) -> Option<i32> {
        if self.left() < 4 {
            return None;
        }
        let v = i32::from_le_bytes(self.d[self.p..self.p + 4].try_into().ok()?);
        self.p += 4;
        Some(v)
    }
    fn f32(&mut self) -> Option<f32> {
        Some(f32::from_bits(self.i32()? as u32))
    }
    /// protocol 15 coord: 13.3 fixed point
    fn coord(&mut self) -> Option<f32> {
        Some(self.i16()? as f32 / 8.0)
    }
    fn angle(&mut self) -> Option<f32> {
        Some(self.i8()? as f32 * (360.0 / 256.0))
    }
    fn string(&mut self) -> Option<String> {
        let start = self.p;
        while *self.d.get(self.p)? != 0 {
            self.p += 1;
        }
        let s = String::from_utf8_lossy(&self.d[start..self.p]).into_owned();
        self.p += 1;
        Some(s)
    }
}

#[derive(Default, Clone)]
struct EntState {
    model: u16,
    skin: u8,
    pos: [f32; 3],
    base_pos: [f32; 3],
    base_model: u16,
    base_skin: u8,
    /// classification is by history, not final state: a bot that
    /// ends the demo gibbed wears head.mdl at the cut and would
    /// otherwise vanish from the track list
    was_player: bool,
    was_projectile: bool,
    /// last nonzero skin seen while wearing the player model - the
    /// bot identity survives the skin-0 gib/ring states
    player_skin: u8,
}

pub struct Demo {
    pub brief: DemoBrief,
    pub tracks: Vec<Track>,
}

pub fn resolve_demo(cfg: &Config, name: &str) -> Result<PathBuf, String> {
    let base = name.trim().trim_end_matches(".dem");
    let cands = [
        cfg.runs.join("demos").join(format!("{base}.dem")),
        cfg.basedir.join(&cfg.game).join(format!("{base}.dem")),
    ];
    for c in &cands {
        if c.exists() {
            return Ok(c.clone());
        }
    }
    Err(format!(
        "no demo '{base}.dem' in runs/demos or {}/{} - record with '+record {base} <map>' in the launch command",
        cfg.basedir.display(),
        cfg.game
    ))
}

pub fn read_demo(path: &PathBuf) -> Result<Demo, String> {
    let data = std::fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
    // header: cd-track line terminated by \n
    let hdr_end = data
        .iter()
        .take(16)
        .position(|b| *b == b'\n')
        .ok_or("not a .dem: no cd-track header line")?;
    let mut p = hdr_end + 1;

    let mut protocol = 0i32;
    let mut level = String::new();
    let mut maxclients = 0u8;
    let mut models: Vec<String> = Vec::new();
    let mut names: BTreeMap<u8, String> = BTreeMap::new();
    let mut prints: Vec<String> = Vec::new();
    let mut notes: Vec<String> = Vec::new();
    let mut ents: BTreeMap<u16, EntState> = BTreeMap::new();
    let mut samples: BTreeMap<u16, (Vec<f64>, Vec<[f32; 3]>)> = BTreeMap::new();
    let mut player_m: Option<u16> = None;
    let mut missile_m: Option<u16> = None;
    let mut grenade_m: Option<u16> = None;
    let mut cur_time = 0f64;
    let mut first_time: Option<f64> = None;
    let mut blocks = 0usize;
    let mut truncated = false;
    let mut done = false;

    'blocks: while !done {
        if data.len() - p < 16 {
            truncated = data.len() - p != 0;
            break;
        }
        let len = i32::from_le_bytes(data[p..p + 4].try_into().unwrap());
        p += 4;
        if !(0..=640_000).contains(&len) {
            notes.push(format!("corrupt block length {len} at byte {p}"));
            truncated = true;
            break;
        }
        p += 12; // POV view angles, 3 x f32
        let len = len as usize;
        if data.len() - p < len {
            truncated = true;
            break;
        }
        let mut r = Reader::new(&data[p..p + len]);
        p += len;
        blocks += 1;

        macro_rules! need {
            ($e:expr) => {
                match $e {
                    Some(v) => v,
                    None => {
                        truncated = true;
                        break 'blocks;
                    }
                }
            };
        }

        while r.left() > 0 {
            let cmd = need!(r.u8());
            if cmd & 0x80 != 0 {
                let mut bits = (cmd & 0x7f) as u16;
                if bits & U_MOREBITS != 0 {
                    bits |= (need!(r.u8()) as u16) << 8;
                }
                let ent = if bits & U_LONGENTITY != 0 {
                    need!(r.i16()) as u16
                } else {
                    need!(r.u8()) as u16
                };
                let st = ents.entry(ent).or_default();
                // a fresh server frame resets absent fields to the
                // baseline; we track absolute state per update
                let mut pos = st.base_pos;
                let mut model = st.base_model;
                let mut skin = st.base_skin;
                if bits & U_MODEL != 0 {
                    model = need!(r.u8()) as u16;
                }
                if bits & U_FRAME != 0 {
                    need!(r.u8());
                }
                if bits & U_COLORMAP != 0 {
                    need!(r.u8());
                }
                if bits & U_SKIN != 0 {
                    skin = need!(r.u8());
                }
                if bits & U_EFFECTS != 0 {
                    need!(r.u8());
                }
                if bits & U_ORIGIN1 != 0 {
                    pos[0] = need!(r.coord());
                }
                if bits & U_ANGLE1 != 0 {
                    need!(r.angle());
                }
                if bits & U_ORIGIN2 != 0 {
                    pos[1] = need!(r.coord());
                }
                if bits & U_ANGLE2 != 0 {
                    need!(r.angle());
                }
                if bits & U_ORIGIN3 != 0 {
                    pos[2] = need!(r.coord());
                }
                if bits & U_ANGLE3 != 0 {
                    need!(r.angle());
                }
                st.model = model;
                st.skin = skin;
                st.pos = pos;
                if Some(model) == player_m && player_m.is_some() {
                    st.was_player = true;
                    if skin > 0 {
                        st.player_skin = skin;
                    }
                } else if (Some(model) == missile_m || Some(model) == grenade_m)
                    && model != 0
                {
                    st.was_projectile = true;
                }
                let rec = samples.entry(ent).or_default();
                rec.0.push(cur_time);
                rec.1.push(pos);
                continue;
            }
            match cmd {
                SVC_NOP | SVC_KILLEDMONSTER | SVC_FOUNDSECRET | SVC_INTERMISSION
                | SVC_SELLSCREEN => {}
                SVC_DISCONNECT => {
                    done = true;
                    break;
                }
                SVC_UPDATESTAT => {
                    need!(r.u8());
                    need!(r.i32());
                }
                SVC_VERSION => {
                    protocol = need!(r.i32());
                }
                SVC_SETVIEW => {
                    need!(r.i16());
                }
                SVC_SOUND => {
                    let mask = need!(r.u8());
                    if mask & 1 != 0 {
                        need!(r.u8());
                    }
                    if mask & 2 != 0 {
                        need!(r.u8());
                    }
                    need!(r.i16());
                    need!(r.u8());
                    for _ in 0..3 {
                        need!(r.coord());
                    }
                }
                SVC_TIME => {
                    cur_time = need!(r.f32()) as f64;
                    first_time.get_or_insert(cur_time);
                }
                SVC_PRINT | SVC_CENTERPRINT => {
                    let s = need!(r.string());
                    let s = s.trim().to_string();
                    if !s.is_empty() {
                        prints.push(s);
                        if prints.len() > 200 {
                            prints.remove(0);
                        }
                    }
                }
                SVC_STUFFTEXT | SVC_FINALE | SVC_CUTSCENE => {
                    need!(r.string());
                }
                SVC_SETANGLE => {
                    for _ in 0..3 {
                        need!(r.angle());
                    }
                }
                SVC_SERVERINFO => {
                    protocol = need!(r.i32());
                    maxclients = need!(r.u8());
                    need!(r.u8()); // gametype
                    level = need!(r.string());
                    models.clear();
                    loop {
                        let m = need!(r.string());
                        if m.is_empty() {
                            break;
                        }
                        models.push(m);
                    }
                    loop {
                        let s = need!(r.string());
                        if s.is_empty() {
                            break;
                        }
                    }
                    let idx = |suffix: &str| {
                        models
                            .iter()
                            .position(|m| m.ends_with(suffix))
                            .map(|i| i as u16 + 1)
                    };
                    player_m = idx("player.mdl");
                    missile_m = idx("missile.mdl");
                    grenade_m = idx("grenade.mdl");
                }
                SVC_LIGHTSTYLE => {
                    need!(r.u8());
                    need!(r.string());
                }
                SVC_UPDATENAME => {
                    let slot = need!(r.u8());
                    let name = need!(r.string());
                    if name.is_empty() {
                        names.remove(&slot);
                    } else {
                        names.insert(slot, name);
                    }
                }
                SVC_UPDATEFRAGS => {
                    need!(r.u8());
                    need!(r.i16());
                }
                SVC_CLIENTDATA => {
                    let bits = need!(r.i16()) as u16;
                    if bits & SU_VIEWHEIGHT != 0 {
                        need!(r.i8());
                    }
                    if bits & SU_IDEALPITCH != 0 {
                        need!(r.i8());
                    }
                    for i in 0..3 {
                        if bits & (SU_PUNCH1 << i) != 0 {
                            need!(r.i8());
                        }
                        if bits & (SU_VELOCITY1 << i) != 0 {
                            need!(r.i8());
                        }
                    }
                    need!(r.i32()); // items, always present
                    if bits & SU_WEAPONFRAME != 0 {
                        need!(r.u8());
                    }
                    if bits & SU_ARMOR != 0 {
                        need!(r.u8());
                    }
                    if bits & SU_WEAPON != 0 {
                        need!(r.u8());
                    }
                    need!(r.i16()); // health
                    for _ in 0..5 {
                        need!(r.u8()); // ammo, shells, nails, rockets, cells
                    }
                    need!(r.u8()); // active weapon
                }
                SVC_STOPSOUND => {
                    need!(r.i16());
                }
                SVC_UPDATECOLORS => {
                    need!(r.u8());
                    need!(r.u8());
                }
                SVC_PARTICLE => {
                    for _ in 0..3 {
                        need!(r.coord());
                    }
                    for _ in 0..3 {
                        need!(r.i8());
                    }
                    need!(r.u8());
                    need!(r.u8());
                }
                SVC_DAMAGE => {
                    need!(r.u8());
                    need!(r.u8());
                    for _ in 0..3 {
                        need!(r.coord());
                    }
                }
                SVC_SPAWNSTATIC => {
                    need!(r.u8());
                    need!(r.u8());
                    need!(r.u8());
                    need!(r.u8());
                    for _ in 0..3 {
                        need!(r.coord());
                        need!(r.angle());
                    }
                }
                SVC_SPAWNBASELINE => {
                    let ent = need!(r.i16()) as u16;
                    let model = need!(r.u8()) as u16;
                    need!(r.u8()); // frame
                    need!(r.u8()); // colormap
                    let skin = need!(r.u8());
                    let mut pos = [0f32; 3];
                    for (i, item) in pos.iter_mut().enumerate() {
                        *item = need!(r.coord());
                        need!(r.angle());
                        let _ = i;
                    }
                    let st = ents.entry(ent).or_default();
                    st.base_model = model;
                    st.base_skin = skin;
                    st.base_pos = pos;
                    st.model = model;
                    st.skin = skin;
                    st.pos = pos;
                }
                SVC_TEMP_ENTITY => {
                    let t = need!(r.u8());
                    match t {
                        5 | 6 | 9 | 13 => {
                            // lightning beams / grapple: ent + two points
                            need!(r.i16());
                            for _ in 0..6 {
                                need!(r.coord());
                            }
                        }
                        12 => {
                            // TE_EXPLOSION2: point + colour start/len
                            for _ in 0..3 {
                                need!(r.coord());
                            }
                            need!(r.u8());
                            need!(r.u8());
                        }
                        _ => {
                            for _ in 0..3 {
                                need!(r.coord());
                            }
                        }
                    }
                }
                SVC_SETPAUSE | SVC_SIGNONNUM => {
                    need!(r.u8());
                }
                SVC_SPAWNSTATICSOUND => {
                    for _ in 0..3 {
                        need!(r.coord());
                    }
                    need!(r.u8());
                    need!(r.u8());
                    need!(r.u8());
                }
                SVC_CDTRACK => {
                    need!(r.u8());
                    need!(r.u8());
                }
                other => {
                    notes.push(format!("unknown svc {other} in block {blocks}; block skipped"));
                    break;
                }
            }
        }
    }

    let duration = cur_time - first_time.unwrap_or(cur_time);
    let mut tracks: Vec<Track> = Vec::new();
    for (ent, (t, pos)) in &samples {
        let st = ents.get(ent).cloned().unwrap_or_default();
        let kind = if st.was_player {
            "player"
        } else if st.was_projectile {
            "projectile"
        } else {
            continue; // gibs, packs, doors: not tracked in v1
        };
        // identity: a real client is entity 1..maxclients and its
        // scoreboard row is entity-1; a bot's skin byte is its ROSTER
        // slot + 1 (v3.15) and its scoreboard row counts down from
        // the top (v3.1: ar_clientno = maxclients - 1 - spawncount)
        let name = if kind == "player" {
            if *ent >= 1 && *ent <= maxclients as u16 {
                names.get(&(*ent as u8 - 1)).cloned()
            } else if st.player_skin > 0 && maxclients as u16 >= st.player_skin as u16 {
                names.get(&(maxclients - st.player_skin)).cloned()
            } else {
                None
            }
        } else {
            None
        };
        tracks.push(Track {
            entity: *ent,
            name,
            kind: kind.into(),
            t: t.clone(),
            pos: pos.clone(),
        });
    }
    tracks.sort_by_key(|t| (t.kind.clone(), std::cmp::Reverse(t.t.len())));

    let track_briefs = tracks
        .iter()
        .map(|tr| {
            let n = tr.t.len();
            let span = if n > 1 { tr.t[n - 1] - tr.t[0] } else { 0.0 };
            let mut dist = 0f64;
            for w in tr.pos.windows(2) {
                let dx = (w[1][0] - w[0][0]) as f64;
                let dy = (w[1][1] - w[0][1]) as f64;
                let dz = (w[1][2] - w[0][2]) as f64;
                dist += (dx * dx + dy * dy + dz * dz).sqrt();
            }
            TrackBrief {
                entity: tr.entity,
                name: tr.name.clone(),
                kind: tr.kind.clone(),
                samples: n,
                hz: if span > 0.0 { n as f64 / span } else { 0.0 },
                first: tr.pos.first().copied().unwrap_or_default(),
                last: tr.pos.last().copied().unwrap_or_default(),
                dist,
            }
        })
        .collect();

    let brief = DemoBrief {
        file: path.display().to_string(),
        protocol,
        level,
        maxclients,
        duration_sec: duration,
        blocks,
        truncated,
        names,
        tracks: track_briefs,
        prints_tail: prints.iter().rev().take(20).rev().cloned().collect(),
        notes,
    };
    Ok(Demo { brief, tracks })
}

pub fn demo_brief(cfg: &Config, name: &str) -> Result<DemoBrief, String> {
    let path = resolve_demo(cfg, name)?;
    Ok(read_demo(&path)?.brief)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn real_labtest_demo_if_present() {
        // captured 2026-08-27 by the automated recorder (windowed
        // engine, `+record labtest dm4`, killed after 45 s): protocol
        // 15, the homage roster identified by skin byte, full-rate
        // tracks. Machine-local like the BSPs.
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../runs/demos/labtest.dem");
        if !path.exists() {
            return;
        }
        let demo = read_demo(&path).unwrap();
        let b = &demo.brief;
        println!(
            "labtest: proto {} level '{}' dur {:.1} blocks {} truncated {} notes {:?} names {:?}",
            b.protocol, b.level, b.duration_sec, b.blocks, b.truncated, b.notes, b.names
        );
        for t in &b.tracks {
            println!("  e{} {:?} {} n={} hz={:.1} dist={:.0}", t.entity, t.name, t.kind, t.samples, t.hz, t.dist);
        }
        assert_eq!(b.protocol, 15, "lab matches are protocol 15");
        // a killed engine usually tears mid-block, but a tear exactly
        // on a block boundary is legal - truncation is reported, not
        // asserted
        assert!(b.duration_sec > 20.0, "duration {}", b.duration_sec);
        assert!(b.names.values().any(|n| n == "Carmack"), "roster: {:?}", b.names);
        let players: Vec<_> = b.tracks.iter().filter(|t| t.kind == "player").collect();
        assert!(players.len() >= 3, "player tracks: {:?}", b.tracks);
        let named = players.iter().filter(|t| t.name.is_some()).count();
        assert!(named >= 3, "skin byte must resolve bot names: {players:?}");
        let bot = players.iter().find(|t| t.name.is_some()).unwrap();
        assert!(
            bot.hz > 5.0,
            "full-rate tracks are the whole point: {} Hz",
            bot.hz
        );
        assert!(bot.dist > 500.0, "bots move: {}", bot.dist);
    }
}
