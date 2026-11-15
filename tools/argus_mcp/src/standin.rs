//! The stand-in human: a puppet client that plays a deathmatch the way a
//! person does, so the lab can estimate "how often do the bots kill the
//! human" without one.
//!
//! The objective's threat goal (tools/lab_objective.json, tier 3) is measured
//! only in human sessions, and those are the scarcest thing the lab has. The
//! stand-in is a cheaper, repeatable referee for the same question. It is NOT
//! a substitute for a person: it earns a place in the evidence ladder only by
//! calibration (docs/specs/2026-11-15-stand-in-calibration.md), and every
//! number it produces is labelled as a stand-in number.
//!
//! What it does, each 50 ms tick:
//!
//! - Moves along a route a human actually ran: the recording player's
//!   full-rate path from the session demo's track export
//!   (`runs/demos/<stem>.tracks.json`, about 70 samples a second), or the
//!   tape's 2 Hz human samples when there is no export. The 2 Hz route cuts
//!   corners: points up to 160 units apart joined by straight lines ran the
//!   first smoke test into dm4's pit lava twice and onto a walkway step.
//!   Knocked off the route, stuck, or respawned, it re-anchors.
//! - Finds its way back to the route over the bots' own nav graph
//!   (`src/argus_nav_<map>.qc.json`, walk and jump links) when it is stuck or
//!   loses sight of the route. A straight line to the nearest visible route
//!   point is not a way there: dm4 spawns a player in a walkway box whose
//!   nearest route points sit over a 48-unit step it cannot climb.
//! - Will not step into lava or slime: a move whose ground 32 or 64 units
//!   ahead is a liquid hazard (hull 0) falls back to the route's own heading,
//!   which is where the human walked, and stops if that is hazardous too.
//! - Sees a bot only along a clear hull-0 line from its eye, within
//!   `sight_range`, and only fires once a target has stayed in sight for
//!   `reaction` seconds - a person's visual reaction time.
//! - Aims with a turn-rate cap and a gain per tick, plus a held aim offset
//!   re-rolled every 0.3 to 0.6 s, the way a hand settles between saccades.
//! - Strafes while fighting, reversing every 1.6 to 3.4 s: a mean of about 24
//!   reversals a moving minute, inside the 18 to 26 measured for the human
//!   in six dm4 session demos (#697).
//! - Chooses a weapon from its real inventory (svc_clientdata), keeping the
//!   rocket launcher out of point-blank range.
//! - Respawns by pressing fire, as a player does.

use crate::bsp::Hull0;
use crate::netclient::NetClient;
use serde::Serialize;
use std::time::{Duration, Instant};

pub const NAME: &str = "standin";
const TICK: Duration = Duration::from_millis(50);
const EYE: f32 = 22.0;
const RUN: f32 = 320.0;

// Quake item bits (defs.qc)
const IT_SHOTGUN: i32 = 1;
const IT_SUPER_SHOTGUN: i32 = 2;
const IT_NAILGUN: i32 = 4;
const IT_SUPER_NAILGUN: i32 = 8;
const IT_ROCKET_LAUNCHER: i32 = 32;
const IT_LIGHTNING: i32 = 64;

#[derive(Debug, Clone, Serialize)]
pub struct Profile {
    /// Seconds a target must stay in sight before the stand-in fires at it.
    pub reaction: f32,
    /// Hard cap on how fast the view turns, degrees a second.
    pub max_turn_dps: f32,
    /// Fraction of the remaining aim error closed each tick.
    pub turn_gain: f32,
    /// Standard deviation of the held aim offset, degrees.
    pub aim_sigma_deg: f32,
    /// Fire only when the view is within this many degrees of the target.
    pub fire_cone_deg: f32,
    /// Seconds between strafe reversals while fighting, drawn uniformly.
    pub strafe_period: (f32, f32),
    pub sight_range: f32,
}

impl Default for Profile {
    fn default() -> Self {
        Profile {
            reaction: 0.25,
            max_turn_dps: 540.0,
            turn_gain: 0.45,
            aim_sigma_deg: 2.5,
            fire_cone_deg: 7.0,
            strafe_period: (1.6, 3.4),
            sight_range: 1800.0,
        }
    }
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct StandInReport {
    pub seconds: f64,
    pub ticks: u32,
    /// Ticks with a bot in sight, and ticks spent firing.
    pub sight_ticks: u32,
    pub fire_ticks: u32,
    /// Ticks spent dead (waiting to respawn).
    pub dead_ticks: u32,
    pub deaths_seen: u32,
    pub waypoints_reached: u32,
    pub reanchors: u32,
    pub route_points: usize,
    pub weapon_switches: u32,
    pub strafe_reversals: u32,
    /// Ticks the lava and slime guard turned a move back to the route.
    pub hazard_refusals: u32,
    /// Detours planned over the nav graph back to the route.
    pub detours: u32,
}

/// A small deterministic generator, so a stand-in run can be repeated.
#[derive(Debug, Clone)]
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }

    pub fn next_f32(&mut self) -> f32 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }

    pub fn range(&mut self, lo: f32, hi: f32) -> f32 {
        lo + (hi - lo) * self.next_f32()
    }

    /// Approximately normal, mean 0 and the given deviation (Irwin-Hall).
    pub fn normal(&mut self, sigma: f32) -> f32 {
        let s: f32 = (0..12).map(|_| self.next_f32()).sum::<f32>() - 6.0;
        s * sigma
    }
}

/// Consecutive route points further apart than this are a respawn or a
/// teleporter, not a path: the stand-in never walks that line.
pub const ROUTE_GAP: f32 = 160.0;

/// The recording player's full-rate path from a demo track export, thinned to
/// points `spacing` apart. The recorder is the real client on entity 1.
pub fn route_from_tracks(path: &std::path::Path, spacing: f32) -> Result<Vec<[f32; 3]>, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let doc: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
    let track = doc["tracks"]
        .as_array()
        .and_then(|tracks| {
            tracks
                .iter()
                .find(|t| t["entity"].as_u64() == Some(1) && t["kind"].as_str() == Some("player"))
        })
        .ok_or_else(|| format!("{}: no recording player track", path.display()))?;
    let mut out: Vec<[f32; 3]> = Vec::new();
    for p in track["pos"].as_array().into_iter().flatten() {
        let Some(xyz) = p.as_array() else { continue };
        if xyz.len() < 3 {
            continue;
        }
        let q = [
            xyz[0].as_f64().unwrap_or(0.0) as f32,
            xyz[1].as_f64().unwrap_or(0.0) as f32,
            xyz[2].as_f64().unwrap_or(0.0) as f32,
        ];
        if out.last().is_none_or(|last| dist(*last, q) >= spacing) {
            out.push(q);
        }
    }
    if out.len() < 4 {
        return Err(format!(
            "{}: the recorded track is too short to follow",
            path.display()
        ));
    }
    Ok(out)
}

/// The best route for a session tape: its demo's full-rate export when one
/// sits beside it under runs/demos/, else the tape's own human samples.
pub fn route_for(tape: &std::path::Path) -> Result<(Vec<[f32; 3]>, String), String> {
    let stem = tape
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or_default();
    if let Some(runs) = tape.parent() {
        let tracks = runs.join("demos").join(format!("{stem}.tracks.json"));
        if tracks.is_file() {
            return route_from_tracks(&tracks, 32.0).map(|r| (r, tracks.display().to_string()));
        }
    }
    route_from_tape(tape, 64.0).map(|r| (r, tape.display().to_string()))
}

/// A route a human ran: points at least `spacing` apart, split into
/// segments wherever the human jumped further than a run could carry them
/// (a death and respawn, or a teleporter).
pub fn route_from_tape(path: &std::path::Path, spacing: f32) -> Result<Vec<[f32; 3]>, String> {
    let tape = crate::parse_arglog::parse_tape_path(path)
        .map_err(|e| format!("{}: {e}", path.display()))?;
    let human = tape
        .human_names()
        .into_iter()
        .max_by_key(|n| tape.samples.get(n).map_or(0, Vec::len))
        .ok_or_else(|| format!("{} holds no human track to follow", path.display()))?;
    let mut out: Vec<[f32; 3]> = Vec::new();
    for s in &tape.samples[&human] {
        let p = [s.pos.x as f32, s.pos.y as f32, s.pos.z as f32];
        if out.last().is_none_or(|q| dist(*q, p) >= spacing) {
            out.push(p);
        }
    }
    if out.len() < 4 {
        return Err(format!(
            "{}: the human track is too short to follow",
            path.display()
        ));
    }
    Ok(out)
}

fn dist(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
}

fn flat(a: [f32; 3], b: [f32; 3]) -> f32 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt()
}

/// Signed smallest difference b - a in degrees, in -180..180.
pub fn angle_diff(a: f32, b: f32) -> f32 {
    (b - a + 540.0).rem_euclid(360.0) - 180.0
}

/// Whether stepping `ahead` units along `yaw` from `me` would put the player
/// over lava or slime: the first non-empty contents below that point, down to
/// 320 units, is a liquid hazard. A point inside a wall is not a hazard (the
/// move simply will not happen).
pub fn hazard_ahead(hull: &Hull0, me: [f32; 3], yaw: f32, ahead: f32) -> bool {
    use crate::bsp::{CONTENTS_EMPTY, CONTENTS_LAVA, CONTENTS_SLIME};
    let r = yaw.to_radians();
    let (x, y) = (me[0] + ahead * r.cos(), me[1] + ahead * r.sin());
    let mut z = me[2];
    while z > me[2] - 320.0 {
        match hull.contents_at([x, y, z]) {
            CONTENTS_EMPTY => z -= 16.0,
            CONTENTS_LAVA | CONTENTS_SLIME => return true,
            _ => return false,
        }
    }
    false
}

/// The route point to (re)join from `p`: the nearest one in clear sight
/// (hull 0, eye to the point's eye), skipping `skip` (the stretch just
/// walked) and anything nearer than `min_dist`, and the nearest at all when
/// none is in sight. The plain nearest point can sit behind a thin wall: the
/// second smoke test spent forty seconds pressed into dm4's walkway wall at
/// x 720, steering at a route point on its far side. `min_dist` serves the
/// stuck case, where the visible points close by are the ones that cannot be
/// reached (a step face, a ledge above).
pub fn join_point(
    route: &[[f32; 3]],
    p: [f32; 3],
    hull: Option<&Hull0>,
    skip: Option<(usize, usize)>,
    min_dist: f32,
) -> usize {
    let n = route.len();
    let skipped = |k: usize| {
        skip.is_some_and(|(walked_to, behind)| (walked_to + n - k) % n <= behind)
            || dist(route[k], p) < min_dist
    };
    let mut order: Vec<usize> = (0..n).filter(|&k| !skipped(k)).collect();
    order.sort_by(|&a, &b| dist(route[a], p).total_cmp(&dist(route[b], p)));
    let eye = [p[0], p[1], p[2] + EYE];
    if let Some(h) = hull {
        // the nearest sixty-four in sight is plenty: a farther one is not a rejoin
        if let Some(&k) = order.iter().take(64).find(|&&k| {
            let q = route[k];
            h.line_clear(eye, [q[0], q[1], q[2] + EYE])
        }) {
            return k;
        }
    }
    order.first().copied().unwrap_or(0)
}

/// The bots' waypoint graph, walk and jump links only: enough to walk from
/// anywhere to anywhere a bot can, without lifts, trains or rocket jumps.
#[derive(Debug, Clone, Default)]
pub struct NavGraph {
    pub nodes: Vec<[f32; 3]>,
    pub next: Vec<Vec<usize>>,
}

impl NavGraph {
    pub fn load(path: &std::path::Path) -> Result<NavGraph, String> {
        let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let doc: serde_json::Value =
            serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
        let nodes: Vec<[f32; 3]> = doc["nodes"]
            .as_array()
            .ok_or("nav json has no nodes")?
            .iter()
            .map(|n| {
                let a = n.as_array().cloned().unwrap_or_default();
                let f = |i: usize| a.get(i).and_then(|v| v.as_f64()).unwrap_or(0.0) as f32;
                [f(0), f(1), f(2)]
            })
            .collect();
        let mut next = vec![Vec::new(); nodes.len()];
        for key in ["links", "jlinks"] {
            for link in doc[key].as_array().into_iter().flatten() {
                let a = link.as_array().cloned().unwrap_or_default();
                let (Some(u), Some(v)) = (
                    a.first().and_then(|x| x.as_u64()),
                    a.get(1).and_then(|x| x.as_u64()),
                ) else {
                    continue;
                };
                let (u, v) = (u as usize, v as usize);
                if u < nodes.len() && v < nodes.len() && !next[u].contains(&v) {
                    next[u].push(v);
                }
            }
        }
        Ok(NavGraph { nodes, next })
    }

    /// The nearest node to `p` in clear sight, else the nearest at all.
    pub fn nearest(&self, p: [f32; 3], hull: Option<&Hull0>) -> Option<usize> {
        let mut order: Vec<usize> = (0..self.nodes.len()).collect();
        order.sort_by(|&a, &b| dist(self.nodes[a], p).total_cmp(&dist(self.nodes[b], p)));
        let eye = [p[0], p[1], p[2] + EYE];
        if let Some(h) = hull {
            if let Some(&k) = order.iter().take(16).find(|&&k| {
                let q = self.nodes[k];
                h.line_clear(eye, [q[0], q[1], q[2] + EYE])
            }) {
                return Some(k);
            }
        }
        order.first().copied()
    }

    /// The node path from `from` to `to`, breadth first, both ends included.
    pub fn path(&self, from: usize, to: usize) -> Option<Vec<usize>> {
        let mut prev = vec![usize::MAX; self.nodes.len()];
        let mut queue = std::collections::VecDeque::from([from]);
        prev[from] = from;
        while let Some(u) = queue.pop_front() {
            if u == to {
                let mut out = vec![to];
                let mut k = to;
                while k != from {
                    k = prev[k];
                    out.push(k);
                }
                out.reverse();
                return Some(out);
            }
            for &v in &self.next[u] {
                if prev[v] == usize::MAX {
                    prev[v] = u;
                    queue.push_back(v);
                }
            }
        }
        None
    }
}

/// The weapon impulse a player would want at range `d`, from what it holds.
pub fn choose_weapon(items: i32, ammo: [u8; 4], d: f32) -> u8 {
    let [shells, nails, rockets, cells] = ammo;
    let has = |bit: i32| items & bit != 0;
    if has(IT_ROCKET_LAUNCHER) && rockets > 0 && d > 180.0 {
        7
    } else if has(IT_LIGHTNING) && cells > 0 && d < 600.0 {
        8
    } else if has(IT_SUPER_NAILGUN) && nails > 1 {
        5
    } else if has(IT_SUPER_SHOTGUN) && shells > 1 {
        3
    } else if has(IT_NAILGUN) && nails > 0 {
        4
    } else if has(IT_SHOTGUN) && shells > 0 {
        2
    } else {
        1
    }
}

/// The item bit the active-weapon byte carries for a weapon impulse.
fn weapon_bit(impulse: u8) -> u8 {
    match impulse {
        2 => IT_SHOTGUN as u8,
        3 => IT_SUPER_SHOTGUN as u8,
        4 => IT_NAILGUN as u8,
        5 => IT_SUPER_NAILGUN as u8,
        7 => IT_ROCKET_LAUNCHER as u8,
        8 => IT_LIGHTNING as u8,
        _ => 0,
    }
}

/// Forward and side moves (Quake's sign convention: side positive is right)
/// that carry the player toward world heading `want` while it faces `view`.
pub fn move_relative(view: f32, want: f32, speed: f32) -> (i16, i16) {
    let rel = (want - view).to_radians();
    ((speed * rel.cos()) as i16, (-speed * rel.sin()) as i16)
}

struct Target {
    ent: u16,
    since: Instant,
}

/// Play for `secs` seconds of wall time on an already connected client.
#[allow(clippy::too_many_arguments)]
pub fn play(
    client: &mut NetClient,
    route: &[[f32; 3]],
    hull: Option<&Hull0>,
    graph: Option<&NavGraph>,
    profile: &Profile,
    seed: u64,
    secs: f32,
) -> StandInReport {
    let mut rng = Rng::new(seed);
    let mut rep = StandInReport {
        route_points: route.len(),
        ..Default::default()
    };
    let start = Instant::now();
    let end = start + Duration::from_secs_f32(secs);
    let dt = TICK.as_secs_f32();
    let (mut yaw, mut pitch) = (client.yaw, client.pitch);
    let mut idx = 0usize;
    let mut last_pos: Option<[f32; 3]> = None;
    let mut stuck = 0u32;
    let mut lost = 0u32;
    // a detour over the nav graph back to the route, nearest node first
    let mut detour: Vec<[f32; 3]> = Vec::new();
    let mut target: Option<Target> = None;
    let mut aim_off = (0.0f32, 0.0f32);
    let mut aim_until = start;
    let mut strafe = 1.0f32;
    let mut strafe_until = start;
    let mut last_switch = start;
    let mut was_dead = false;
    let mut press = false;
    let mut anchored = false;
    while Instant::now() < end && !client.world.disconnected {
        rep.ticks += 1;
        let now = Instant::now();
        let Some(me) = client.my_pos() else {
            client.pump(TICK);
            continue;
        };
        let dead = client.world.stats_seen && client.world.health <= 0;
        if dead {
            if !was_dead {
                rep.deaths_seen += 1;
            }
            was_dead = true;
            rep.dead_ticks += 1;
            // a player respawns by pressing fire once the death animation
            // ends; release and press so the press is seen as new
            press = !press;
            client.set_move(0.0, yaw, 0, 0, if press { 1 } else { 0 });
            target = None;
            client.pump(TICK);
            continue;
        }
        // a respawn or a teleporter moves us further than a run can
        let jumped = last_pos.is_some_and(|q| dist(q, me) > 256.0);
        if was_dead || jumped || !anchored {
            idx = join_point(route, me, hull, None, 0.0);
            rep.reanchors += u32::from(anchored);
            anchored = true;
            was_dead = false;
            stuck = 0;
        }
        if let Some(q) = last_pos {
            stuck = if flat(q, me) < 6.0 { stuck + 1 } else { 0 };
        }
        last_pos = Some(me);

        // ---- the route
        for _ in 0..8 {
            if flat(route[idx], me) >= 64.0 || (route[idx][2] - me[2]).abs() >= 96.0 {
                break;
            }
            let next = (idx + 1) % route.len();
            rep.waypoints_reached += 1;
            if dist(route[idx], route[next]) > ROUTE_GAP {
                // the human respawned or teleported here: resume elsewhere
                idx = join_point(route, me, hull, Some((idx, 40)), 0.0);
                rep.reanchors += 1;
                break;
            }
            idx = next;
        }
        // the point we steer at went out of sight: a corner was cut or we
        // were shoved off the line; rejoin where the route can be seen
        let eye_now = [me[0], me[1], me[2] + EYE];
        let way_eye = [route[idx][0], route[idx][1], route[idx][2] + EYE];
        lost = if detour.is_empty() && hull.is_some_and(|h| !h.line_clear(eye_now, way_eye)) {
            lost + 1
        } else {
            0
        };
        if stuck >= 30 || lost >= 20 {
            // a second and a half without moving, or a second without sight
            // of the route: give the stretch up
            // stuck: the visible points close by are the ones we cannot
            // reach (a step face, a ledge above), so rejoin beyond them
            let (skip, reach) = if stuck >= 30 { (8, 160.0) } else { (0, 0.0) };
            idx = join_point(route, me, hull, Some((idx, skip)), reach);
            if let Some(g) = graph {
                let plan = g
                    .nearest(me, hull)
                    .zip(g.nearest(route[idx], None))
                    .and_then(|(a, b)| g.path(a, b));
                if let Some(nodes) = plan {
                    detour = nodes.iter().map(|&k| g.nodes[k]).collect();
                    rep.detours += 1;
                }
            }
            rep.reanchors += 1;
            stuck = 0;
            lost = 0;
        }
        while detour
            .first()
            .is_some_and(|d| flat(*d, me) < 48.0 && (d[2] - me[2]).abs() < 96.0)
        {
            detour.remove(0);
        }
        if was_dead || jumped {
            detour.clear();
        }
        let way = detour.first().copied().unwrap_or(route[idx]);
        let route_yaw = (way[1] - me[1]).atan2(way[0] - me[0]).to_degrees();

        // ---- sight
        let eye = [me[0], me[1], me[2] + EYE];
        let mut best: Option<(u16, f32, [f32; 3])> = None;
        for (id, e) in &client.world.ents {
            if *id == client.world.my_ent
                || Some(e.model) != client.world.player_model
                || e.updates == 0
            {
                continue;
            }
            let d = dist(e.pos, me);
            if d > profile.sight_range || d < 1.0 {
                continue;
            }
            let aimpt = [e.pos[0], e.pos[1], e.pos[2] + 16.0];
            if hull.is_some_and(|h| !h.line_clear(eye, aimpt)) {
                continue;
            }
            if best.is_none_or(|(_, bd, _)| d < bd) {
                best = Some((*id, d, aimpt));
            }
        }
        match (&target, best) {
            (Some(t), Some((id, _, _))) if t.ent == id => {}
            (_, Some((id, _, _))) => {
                target = Some(Target {
                    ent: id,
                    since: now,
                })
            }
            (_, None) => target = None,
        }

        // ---- aim and fire
        let mut buttons = 0u8;
        let mut fighting = false;
        let mut target_yaw = route_yaw;
        let mut target_d = f32::MAX;
        if let (Some(t), Some((_, d, aimpt))) = (&target, best) {
            rep.sight_ticks += 1;
            fighting = true;
            target_d = d;
            if now >= aim_until {
                aim_off = (
                    rng.normal(profile.aim_sigma_deg),
                    rng.normal(profile.aim_sigma_deg),
                );
                aim_until = now + Duration::from_secs_f32(rng.range(0.3, 0.6));
            }
            let dx = [aimpt[0] - eye[0], aimpt[1] - eye[1], aimpt[2] - eye[2]];
            target_yaw = dx[1].atan2(dx[0]).to_degrees();
            let horiz = (dx[0] * dx[0] + dx[1] * dx[1]).sqrt().max(1.0);
            let want_yaw = target_yaw + aim_off.0;
            let want_pitch = -(dx[2].atan2(horiz).to_degrees()) + aim_off.1;
            let cap = profile.max_turn_dps * dt;
            let ey = angle_diff(yaw, want_yaw);
            yaw += (ey * profile.turn_gain).clamp(-cap, cap);
            let ep = want_pitch - pitch;
            pitch += (ep * profile.turn_gain).clamp(-cap, cap);
            let settled = angle_diff(yaw, target_yaw).abs() < profile.fire_cone_deg;
            if settled && now.duration_since(t.since).as_secs_f32() >= profile.reaction {
                buttons |= 1;
                rep.fire_ticks += 1;
            }
            // ---- weapon
            if client.world.stats_seen
                && now.duration_since(last_switch) > Duration::from_millis(600)
            {
                let want = choose_weapon(client.world.items, client.world.ammo, d);
                if weapon_bit(want) != client.world.weapon {
                    client.set_impulse(want);
                    last_switch = now;
                    rep.weapon_switches += 1;
                }
            }
        } else {
            // looking where it runs, as a player does between fights
            let cap = profile.max_turn_dps * dt;
            yaw += (angle_diff(yaw, route_yaw) * profile.turn_gain).clamp(-cap, cap);
            pitch += (-pitch * profile.turn_gain).clamp(-cap, cap);
        }
        yaw = yaw.rem_euclid(360.0);
        pitch = pitch.clamp(-70.0, 80.0);

        // ---- movement
        let want = if fighting {
            if now >= strafe_until {
                strafe = -strafe;
                strafe_until = now
                    + Duration::from_secs_f32(
                        rng.range(profile.strafe_period.0, profile.strafe_period.1),
                    );
                rep.strafe_reversals += 1;
            }
            // circle the target while drifting along the route; back off
            // inside rocket splash, close in from beyond shotgun reach
            let side_yaw = target_yaw + 90.0 * strafe;
            let (rx, ry) = (route_yaw.to_radians().cos(), route_yaw.to_radians().sin());
            let (sx, sy) = (side_yaw.to_radians().cos(), side_yaw.to_radians().sin());
            let toward = if target_d < 140.0 {
                -0.8
            } else if target_d > 900.0 {
                0.5
            } else {
                0.0
            };
            let (tx, ty) = (target_yaw.to_radians().cos(), target_yaw.to_radians().sin());
            let vx = 0.5 * rx + sx + toward * tx;
            let vy = 0.5 * ry + sy + toward * ty;
            vy.atan2(vx).to_degrees()
        } else {
            route_yaw
        };
        let mut want = want;
        let mut speed = RUN;
        if let Some(h) = hull {
            let risky = |yaw: f32| hazard_ahead(h, me, yaw, 32.0) || hazard_ahead(h, me, yaw, 64.0);
            if risky(want) {
                rep.hazard_refusals += 1;
                if risky(route_yaw) {
                    speed = 0.0;
                } else {
                    want = route_yaw;
                }
            }
        }
        let (fwd, side) = move_relative(yaw, want, speed);
        if stuck >= 4 {
            buttons |= 2; // hop a step or a lip, as a player holds jump
        }
        client.set_move(pitch, yaw, fwd, side, buttons);
        client.pump(TICK);
    }
    client.set_move(pitch, yaw, 0, 0, 0);
    client.pump(Duration::from_millis(200));
    rep.seconds = start.elapsed().as_secs_f64();
    rep
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn angles_wrap_the_short_way() {
        assert_eq!(angle_diff(350.0, 10.0), 20.0);
        assert_eq!(angle_diff(10.0, 350.0), -20.0);
        assert_eq!(angle_diff(0.0, 180.0).abs(), 180.0);
    }

    #[test]
    fn moves_are_relative_to_the_view() {
        assert_eq!(move_relative(90.0, 90.0, 320.0), (320, 0));
        // wanting to go to the right of where we look is a positive side move
        let (f, s) = move_relative(90.0, 0.0, 320.0);
        assert!(f.abs() < 2 && s == 320, "{f} {s}");
        let (f, s) = move_relative(0.0, 90.0, 320.0);
        assert!(f.abs() < 2 && s == -320, "{f} {s}");
    }

    #[test]
    fn weapon_choice_follows_inventory_and_range() {
        let all = IT_SHOTGUN | IT_SUPER_SHOTGUN | IT_ROCKET_LAUNCHER | IT_LIGHTNING;
        assert_eq!(choose_weapon(all, [10, 0, 5, 40], 500.0), 7);
        assert_eq!(
            choose_weapon(all, [10, 0, 5, 40], 100.0),
            8,
            "no rockets at point blank"
        );
        assert_eq!(choose_weapon(all, [10, 0, 0, 0], 500.0), 3);
        assert_eq!(
            choose_weapon(IT_SHOTGUN, [0, 0, 0, 0], 500.0),
            1,
            "dry: axe"
        );
        assert_eq!(choose_weapon(IT_SHOTGUN, [5, 0, 0, 0], 500.0), 2);
    }

    #[test]
    fn the_generator_repeats_and_stays_in_range() {
        let (mut a, mut b) = (Rng::new(7), Rng::new(7));
        for _ in 0..1000 {
            let x = a.next_f32();
            assert_eq!(x, b.next_f32());
            assert!((0.0..1.0).contains(&x));
        }
        let mut r = Rng::new(3);
        let sd = (0..4000).map(|_| r.normal(2.0).powi(2)).sum::<f32>() / 4000.0;
        assert!((sd.sqrt() - 2.0).abs() < 0.2, "{}", sd.sqrt());
    }

    #[test]
    fn joining_without_a_hull_takes_the_nearest_outside_the_skip() {
        let route: Vec<[f32; 3]> = (0..10).map(|i| [i as f32 * 100.0, 0.0, 0.0]).collect();
        assert_eq!(join_point(&route, [310.0, 0.0, 0.0], None, None, 0.0), 3);
        assert_eq!(
            join_point(&route, [310.0, 0.0, 0.0], None, Some((3, 2)), 0.0),
            4
        );
        assert_eq!(
            join_point(&route, [310.0, 0.0, 0.0], None, None, 160.0),
            5,
            "beyond the reach"
        );
    }

    #[test]
    fn the_graph_walks_links_in_their_direction() {
        let g = NavGraph {
            nodes: vec![
                [0.0, 0.0, 0.0],
                [100.0, 0.0, 0.0],
                [200.0, 0.0, 0.0],
                [300.0, 0.0, 0.0],
            ],
            next: vec![vec![1], vec![2], vec![3], vec![]],
        };
        assert_eq!(g.path(0, 3), Some(vec![0, 1, 2, 3]));
        assert_eq!(g.path(3, 0), None, "links are one-way");
        assert_eq!(g.path(2, 2), Some(vec![2]));
        assert_eq!(g.nearest([190.0, 10.0, 0.0], None), Some(2));
    }

    #[test]
    fn the_shipped_dm4_graph_loads() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../src/argus_nav_dm4.qc.json");
        if !path.is_file() {
            return;
        }
        let g = NavGraph::load(&path).unwrap();
        assert!(g.nodes.len() > 100);
        assert!(g.next.iter().any(|v| !v.is_empty()));
    }

    #[test]
    fn the_track_export_gives_the_recorder_path() {
        let dir = std::env::temp_dir().join(format!("argus-standin-tracks-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("s.tracks.json");
        let pos: Vec<[f32; 3]> = (0..50).map(|i| [i as f32 * 10.0, 5.0, 24.0]).collect();
        let doc = serde_json::json!({"tracks": [
            {"entity": 213, "kind": "player", "name": "Carmack", "pos": [[0, 0, 0], [999, 0, 0]]},
            {"entity": 1, "kind": "player", "name": "player", "pos": pos}]});
        std::fs::write(&path, doc.to_string()).unwrap();
        let route = route_from_tracks(&path, 32.0).unwrap();
        assert!(route.iter().all(|p| p[1] == 5.0));
        assert!(route.windows(2).all(|w| dist(w[0], w[1]) >= 32.0));
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_route_comes_from_the_human_track_only() {
        let dir = std::env::temp_dir().join(format!("argus-standin-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("tape.log");
        let mut text = String::from("ARGUS init on dm4\nARGEVT Reap spawned\n");
        for i in 0..20 {
            text.push_str(&format!(
                "ARGLOG Reap t {:.1} pos '0 0 24' spd 0 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                1.0 + i as f32 * 0.5
            ));
            text.push_str(&format!(
                "ARGLOG player t {:.1} pos '{} 0 24' spd 320 yaw 0 mode 0 st 0 gl 0 hp 100 frg 0\n",
                1.0 + i as f32 * 0.5,
                i * 40
            ));
        }
        std::fs::write(&path, text).unwrap();
        let route = route_from_tape(&path, 64.0).unwrap();
        assert!(route.iter().all(|p| p[1] == 0.0 && p[0] >= 0.0));
        assert!(route.windows(2).all(|w| dist(w[0], w[1]) >= 64.0));
        assert_eq!(route.first().unwrap()[0], 0.0);
        let _ = std::fs::remove_dir_all(dir);
    }
}

/// One stand-in match, as `argus-mcp standin` reports it.
#[derive(Debug, Clone, Serialize)]
pub struct StandInRun {
    pub run_name: String,
    pub map: String,
    pub skill: Option<u32>,
    pub seed: u64,
    pub route_from: String,
    pub profile: Profile,
    pub play: StandInReport,
    pub log_path: String,
    pub headline: String,
    /// The tape's own human scorecard: bot kills on the stand-in a minute,
    /// its kills a minute, and the threat ratio. Stand-in numbers, never a
    /// person's.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scorecard: Option<crate::intel::HumanScorecard>,
}

/// The newest human session tape for a map, the default route source.
pub fn default_route_tape(runs: &std::path::Path, map: &str) -> Option<std::path::PathBuf> {
    let prefix = format!("shane_{map}_");
    let mut tapes: Vec<_> = std::fs::read_dir(runs)
        .ok()?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| {
            p.extension().is_some_and(|x| x == "log")
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .is_some_and(|n| n.starts_with(&prefix))
        })
        .collect();
    tapes.sort();
    tapes.pop()
}

/// Run a played-clock match with the stand-in seated for `secs` seconds.
#[allow(clippy::too_many_arguments)]
pub async fn run_match(
    cfg: &crate::config::Config,
    map: &str,
    secs: u32,
    run_name: &str,
    route_tape: &std::path::Path,
    skill: Option<u32>,
    port: u16,
    seed: u64,
    profile: Profile,
) -> Result<StandInRun, String> {
    let (route, route_from) = route_for(route_tape)?;
    let hull = crate::intel::hull0_for_map(cfg, map);
    let graph = NavGraph::load(&cfg.src.join(format!("argus_nav_{map}.qc.json"))).ok();
    let mut ctrl = crate::match_ctrl::MatchCtrl::on_port(port);
    // The stand-in acts on the wall clock (20 Hz moves), so its match must
    // too: a fixed-clock server would run six times faster than it thinks.
    ctrl.start(
        cfg,
        map,
        Some(secs + 15),
        Some(run_name),
        None,
        skill,
        Some(false),
    )
    .await?;
    tokio::time::sleep(Duration::from_secs(3)).await;
    let mut client = match NetClient::connect_match(&ctrl, NAME) {
        Ok(c) => c,
        Err(e) => {
            let _ = ctrl.stop(Duration::from_secs(3)).await;
            return Err(format!("stand-in could not connect: {e}"));
        }
    };
    client.pump(Duration::from_secs(2));
    if client.world.signon < 3 {
        let _ = ctrl.stop(Duration::from_secs(3)).await;
        return Err(format!(
            "stand-in signon stalled at {}",
            client.world.signon
        ));
    }
    let report = play(
        &mut client,
        &route,
        hull.as_ref(),
        graph.as_ref(),
        &profile,
        seed,
        secs as f32,
    );
    client.disconnect();
    let res = ctrl.finish(cfg, map).await?;
    Ok(StandInRun {
        run_name: res.run_name,
        map: map.to_string(),
        skill,
        seed,
        route_from,
        profile,
        play: report,
        log_path: res.log_path,
        headline: res.brief.headline.clone(),
        scorecard: res.brief.human_scorecard.clone(),
    })
}
