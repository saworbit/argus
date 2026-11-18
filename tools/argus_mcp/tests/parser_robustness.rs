//! Never panic, never spin: the stable suite's share of the #849 contract
//! for the lab's three external-input parsers (demo, BSP and PAK, ARGLOG).
//!
//! The cargo-fuzz targets in tools/argus_mcp/fuzz need nightly and run from
//! .github/workflows/fuzz.yml on a schedule. This test runs on every change:
//! a fixed pseudo-random schedule of byte and token mutations over a
//! synthesised protocol 15 demo, a synthesised BSP29 and PAK, and windows of
//! committed runs/*.log tapes. Every input is parsed on a worker thread under
//! a wall-clock bound, so a loop fails the test instead of hanging it, and a
//! failing input is saved under CARGO_TARGET_TMPDIR for a regression test.
//! No recorded demo and no id Software map is ever an input here.

use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::Duration;

use argus_mcp::bsp::{death_is_lava, pak_find_bytes, pak_list_maps_bytes, parse_bsp29, Bsp29};
use argus_mcp::cartograph::parse_entities;
use argus_mcp::demo::parse_demo;
use argus_mcp::parse_arglog::parse_tape;

/// Generous: a debug build parses any input here in milliseconds, and a
/// shared runner can stall for seconds. A loop never returns at all.
const BOUND: Duration = Duration::from_secs(20);

// ------------------------------------------------------------------ harness

/// xorshift64*, so a failure names a case that replays exactly.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }

    fn below(&mut self, n: usize) -> usize {
        (self.next() % n.max(1) as u64) as usize
    }

    fn pick<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[self.below(items.len())]
    }
}

/// Little endian words that sit on the edges a parser forgets: infinities,
/// NaN, the largest float, sign bits, and a block length one over the cap.
const WORDS: [u32; 12] = [
    0x7f80_0000,
    0xff80_0000,
    0x7fc0_0000,
    0x7f7f_ffff,
    0x5f00_0000,
    0x8000_0000,
    0x7fff_ffff,
    0xffff_ffff,
    0,
    1,
    640_001,
    0x0001_0000,
];

/// One to four byte level mutations. With `hot` nonzero, half of them land
/// in the first `hot` bytes, where a format keeps its offsets and lengths.
fn mutate_bytes(rng: &mut Rng, data: &mut Vec<u8>, hot: usize) {
    for _ in 0..1 + rng.below(4) {
        if data.is_empty() {
            data.push(rng.next() as u8);
            continue;
        }
        let span = if hot > 0 && rng.below(2) == 0 {
            hot.min(data.len())
        } else {
            data.len()
        };
        let at = rng.below(span);
        match rng.below(7) {
            0 => data[at] ^= 1 << rng.below(8),
            1 => {
                let noise = rng.next() as u8;
                data[at] = *rng.pick(&[0, 1, 0x7f, 0x80, 0xff, noise]);
            }
            2 if data.len() >= 4 => {
                let at = at.min(data.len() - 4);
                data[at..at + 4].copy_from_slice(&rng.pick(&WORDS).to_le_bytes());
            }
            3 => data.truncate(rng.below(data.len() + 1)),
            4 => {
                let end = (at + 1 + rng.below(64)).min(data.len());
                data.drain(at..end);
            }
            5 => {
                let end = (at + 1 + rng.below(64)).min(data.len());
                let chunk = data[at..end].to_vec();
                let to = rng.below(data.len() + 1);
                data.splice(to..to, chunk);
            }
            _ if data.len() >= 2 => {
                let at = at.min(data.len() - 2);
                let half = *rng.pick(&[0x7fffu16, 0x8000, 0xffff, 0]);
                data[at..at + 2].copy_from_slice(&half.to_le_bytes());
            }
            _ => data[at] = 0,
        }
    }
}

/// Tape mutations: grammar tokens and numbers the regexes accept but a
/// float cannot hold, duplicated and deleted lines, and byte noise.
fn mutate_text(rng: &mut Rng, data: &mut Vec<u8>) {
    let huge = "9".repeat(400);
    let tokens = [
        "ARGLOG ",
        "ARGEVT ",
        "ARGUS ",
        "ARGMOT begin layout 2\n",
        " t ",
        " pos '",
        "' spd ",
        " yaw ",
        " mode ",
        " st ",
        " gl ",
        " hp ",
        " frg ",
        " death ",
        " world pos '",
        " spawned",
        " respawn",
        " thirdparty",
        " hesitate heard",
        " unstick embedded '1 2 3'",
        " tactic abort x",
        "SpawnServer: dm4\n",
        "Couldn't spawn server maps/dm4.bsp\n",
        "BHVFIX begin x\n",
        &huge,
        "-",
        ".",
        "'",
        "0.5",
        "\n",
        "\r\n",
        " ",
        "\u{fffd}",
    ];
    for _ in 0..1 + rng.below(4) {
        match rng.below(5) {
            0 | 1 => {
                let at = rng.below(data.len() + 1);
                let token = rng.pick(&tokens).as_bytes().to_vec();
                data.splice(at..at, token);
            }
            2 if !data.is_empty() => {
                let at = rng.below(data.len());
                let start = data[..at]
                    .iter()
                    .rposition(|b| *b == b'\n')
                    .map_or(0, |i| i + 1);
                let end = data[at..]
                    .iter()
                    .position(|b| *b == b'\n')
                    .map_or(data.len(), |i| at + i + 1);
                let line = data[start..end].to_vec();
                let to = rng.below(data.len() + 1);
                data.splice(to..to, line);
            }
            3 if !data.is_empty() => {
                let at = rng.below(data.len());
                let end = (at + 1 + rng.below(200)).min(data.len());
                data.drain(at..end);
            }
            _ => mutate_bytes(rng, data, 0),
        }
    }
}

fn panic_text(payload: Box<dyn std::any::Any + Send>) -> String {
    payload
        .downcast_ref::<&str>()
        .map(|s| s.to_string())
        .or_else(|| payload.downcast_ref::<String>().cloned())
        .unwrap_or_else(|| "non-string panic".into())
}

/// Parse every case on one worker thread and wait at most BOUND for each.
/// ARGUS_ROBUSTNESS_SCALE multiplies the case count for a longer local run
/// (the schedule only extends, so a failure still names a replayable case).
fn run(
    name: &str,
    seeds: &[Vec<u8>],
    cases: usize,
    mutate: impl Fn(&mut Rng, &mut Vec<u8>),
    parse: fn(&[u8]),
) {
    assert!(!seeds.is_empty(), "{name}: no seeds");
    let (to_worker, jobs) = mpsc::channel::<Vec<u8>>();
    let (to_test, results) = mpsc::channel::<Result<(), String>>();
    std::thread::spawn(move || {
        for input in jobs {
            let outcome = catch_unwind(AssertUnwindSafe(|| parse(&input))).map_err(panic_text);
            if to_test.send(outcome).is_err() {
                break;
            }
        }
    });
    let scale: usize = std::env::var("ARGUS_ROBUSTNESS_SCALE")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(1);
    let mut rng = Rng(0x0849_5eed ^ name.len() as u64);
    for case in 0..cases * scale.max(1) {
        let mut input = seeds[case % seeds.len()].clone();
        // every seed parses unmutated first
        if case >= seeds.len() {
            if rng.below(8) == 0 {
                let other = rng.pick(seeds);
                let at = rng.below(input.len() + 1);
                input.truncate(at);
                input.extend_from_slice(&other[rng.below(other.len() + 1)..]);
            }
            mutate(&mut rng, &mut input);
        }
        to_worker.send(input.clone()).expect("worker alive");
        let verdict = match results.recv_timeout(BOUND) {
            Ok(Ok(())) => continue,
            Ok(Err(message)) => format!("panicked: {message}"),
            Err(_) => format!("did not return within {} s", BOUND.as_secs()),
        };
        let dir = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join("parser_robustness");
        std::fs::create_dir_all(&dir).ok();
        let saved = dir.join(format!("{name}-{case}.bin"));
        std::fs::write(&saved, &input).ok();
        let head: String = input.iter().take(48).map(|b| format!("{b:02x}")).collect();
        panic!(
            "{name} case {case} {verdict}; {} byte input saved to {} (head {head})",
            input.len(),
            saved.display()
        );
    }
}

// --------------------------------------------------------------------- demo

fn zstr(out: &mut Vec<u8>, text: &str) {
    out.extend_from_slice(text.as_bytes());
    out.push(0);
}

fn coord(out: &mut Vec<u8>, value: f32) {
    out.extend_from_slice(&((value * 8.0) as i16).to_le_bytes());
}

fn angle(degrees: f32) -> u8 {
    ((degrees * 256.0 / 360.0) as i32 & 0xff) as u8
}

fn block(out: &mut Vec<u8>, payload: &[u8], pitch: f32, yaw: f32) {
    out.extend_from_slice(&(payload.len() as i32).to_le_bytes());
    for value in [pitch, yaw, 0.0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(payload);
}

/// A fast update carrying origin, pitch and yaw, and the skin when given.
fn update(out: &mut Vec<u8>, entity: u8, origin: [f32; 3], yaw: f32, skin: Option<u8>) {
    let bits: u16 =
        0x01 | 0x02 | 0x04 | 0x08 | 0x10 | 0x100 | if skin.is_some() { 0x1000 } else { 0 };
    out.extend_from_slice(&[0x80 | (bits & 0x7f) as u8, (bits >> 8) as u8, entity]);
    if let Some(skin) = skin {
        out.push(skin);
    }
    coord(out, origin[0]);
    out.push(0);
    coord(out, origin[1]);
    out.push(angle(yaw));
    coord(out, origin[2]);
}

/// A protocol 15 match in miniature: signon, roster, baselines, 30 frames of
/// three moving players with every message type the reader parses, then an
/// intermission and a disconnect.
fn synthetic_demo() -> Vec<u8> {
    let mut out = b"-1\n".to_vec();
    let mut p = vec![11];
    p.extend_from_slice(&15i32.to_le_bytes());
    p.extend_from_slice(&[4, 1]);
    zstr(&mut p, "fuzz seed");
    for model in [
        "maps/fuzz.bsp",
        "progs/player.mdl",
        "progs/missile.mdl",
        "progs/grenade.mdl",
        "",
    ] {
        zstr(&mut p, model);
    }
    zstr(&mut p, "weapons/r_exp3.wav");
    zstr(&mut p, "");
    p.extend_from_slice(&[32, 2, 2, 5, 1, 0, 25, 1]);
    block(&mut out, &p, 0.0, 0.0);

    let mut p = Vec::new();
    for (slot, name) in [(0u8, "player"), (3, "Reap"), (2, "Omi")] {
        p.extend_from_slice(&[13, slot]);
        zstr(&mut p, name);
    }
    p.extend_from_slice(&[14, 3, 2, 0, 17, 3, 0x4c]);
    for (entity, model, skin, origin) in [
        (1i16, 2u8, 0u8, [0.0, 0.0, 24.0]),
        (5, 2, 1, [256.0, 0.0, 24.0]),
        (6, 2, 2, [-256.0, 0.0, 24.0]),
        (9, 3, 0, [0.0, 64.0, 40.0]),
    ] {
        p.push(22);
        p.extend_from_slice(&entity.to_le_bytes());
        p.extend_from_slice(&[model, 0, 0, skin]);
        for axis in origin {
            coord(&mut p, axis);
            p.push(0);
        }
    }
    p.extend_from_slice(&[20, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    p.extend_from_slice(&[29, 8, 0, 8, 0, 8, 0, 1, 255, 1, 12, 0]);
    zstr(&mut p, "m");
    p.push(9);
    zstr(&mut p, "bf\n");
    p.extend_from_slice(&[25, 2, 25, 3]);
    block(&mut out, &p, 0.0, 0.0);

    for i in 0..30u8 {
        let f = f32::from(i);
        let mut p = vec![7];
        p.extend_from_slice(&(1.0 + f * 0.05f32).to_le_bytes());
        // clientdata: viewheight and weapon bits, items, health, ammo, weapon
        p.push(15);
        p.extend_from_slice(&0x4001i16.to_le_bytes());
        p.push(22);
        p.extend_from_slice(&0x2001i32.to_le_bytes());
        p.push(4);
        p.extend_from_slice(&100i16.to_le_bytes());
        p.extend_from_slice(&[25, 25, 0, 25, 0, 32]);
        update(&mut p, 1, [f * 12.0, 0.0, 24.0], f * 7.0, None);
        update(
            &mut p,
            5,
            [256.0 - f * 15.0, f * 4.0, 24.0],
            180.0 - f * 9.0,
            Some(1),
        );
        update(
            &mut p,
            6,
            [-256.0 + f * 10.0, -f * 6.0, 24.0],
            f * 30.0,
            Some(2),
        );
        if i % 6 == 0 {
            update(&mut p, 9, [f * 20.0, 64.0, 40.0], 90.0, None);
        }
        match i {
            3 => p.extend_from_slice(&[6, 0, 41, 0, 1, 8, 0, 16, 0, 24, 0]),
            5 => p.extend_from_slice(&[23, 3, 80, 0, 160, 0, 240, 0]),
            7 => {
                p.extend_from_slice(&[23, 5, 5, 0]);
                for value in [0.0, 0.0, 24.0, 64.0, 0.0, 24.0] {
                    coord(&mut p, value);
                }
            }
            9 => p.extend_from_slice(&[23, 12, 8, 0, 8, 0, 8, 0, 4, 8]),
            11 => p.extend_from_slice(&[18, 40, 0, 40, 0, 40, 0, 1, 2, 3, 73, 20]),
            13 => p.extend_from_slice(&[19, 10, 5, 0, 0, 0, 0, 0, 0]),
            15 => {
                for fragment in ["Omi", " was gibbed by ", "Reap\n"] {
                    p.push(8);
                    zstr(&mut p, fragment);
                }
            }
            17 => {
                p.push(26);
                zstr(&mut p, "Reap got the Quad Damage\n");
            }
            19 => p.extend_from_slice(&[3, 6, 1, 0, 0, 0, 10, 0, 12, 0]),
            21 => p.extend_from_slice(&[16, 9, 0, 24, 0, 1]),
            23 => {
                p.push(8);
                zstr(&mut p, "Reap burst into flames\n");
            }
            25 => p.extend_from_slice(&[4, 15, 0, 0, 0, 27, 28, 33]),
            _ => {}
        }
        block(&mut out, &p, -5.0, f * 11.0);
    }
    block(&mut out, &[30, 2], 0.0, 0.0);
    out
}

fn parse_demo_case(data: &[u8]) {
    let _ = parse_demo("case.dem", data);
}

#[test]
fn synthetic_demo_is_a_valid_seed() {
    let demo = parse_demo("seed.dem", &synthetic_demo()).expect("seed parses");
    let brief = &demo.brief;
    assert_eq!(brief.protocol, 15);
    assert_eq!(brief.level, "fuzz seed");
    assert!(!brief.truncated, "notes {:?}", brief.notes);
    assert!(brief.notes.is_empty(), "notes {:?}", brief.notes);
    let players = brief.tracks.iter().filter(|t| t.kind == "player").count();
    assert_eq!(players, 3, "{:?}", brief.tracks);
    assert!(brief
        .tracks
        .iter()
        .any(|t| t.name.as_deref() == Some("Reap")));
    assert!(brief.highlights.iter().any(|h| h.kind == "first_blood"));
    assert!(brief.highlights.iter().any(|h| h.kind == "quad"));
}

#[test]
fn demo_reader_survives_mutation() {
    run(
        "demo",
        &[synthetic_demo()],
        4000,
        |rng, data| mutate_bytes(rng, data, 0),
        parse_demo_case,
    );
}

// ---------------------------------------------------------------- bsp, pak

fn lump_file(lumps: &[(usize, Vec<u8>)]) -> Vec<u8> {
    let mut out = vec![0u8; 4 + 15 * 8];
    out[..4].copy_from_slice(&29i32.to_le_bytes());
    for index in 0..15 {
        let body = lumps
            .iter()
            .find(|(i, _)| *i == index)
            .map(|(_, b)| b.as_slice())
            .unwrap_or(&[]);
        let at = 4 + index * 8;
        let offset = out.len() as u32;
        out[at..at + 4].copy_from_slice(&offset.to_le_bytes());
        out[at + 4..at + 8].copy_from_slice(&(body.len() as u32).to_le_bytes());
        out.extend_from_slice(body);
    }
    out
}

fn le(out: &mut Vec<u8>, words: &[i32]) {
    for word in words {
        out.extend_from_slice(&word.to_le_bytes());
    }
}

fn le16(out: &mut Vec<u8>, halves: &[i16]) {
    for half in halves {
        out.extend_from_slice(&half.to_le_bytes());
    }
}

/// Three planes, a three-node render tree over empty, lava and water leaves,
/// a two-node clip tree and two models: small, but every lump the reader
/// walks is present and every child kind (node, leaf) occurs.
fn synthetic_bsp() -> Vec<u8> {
    let mut planes = Vec::new();
    for (normal, dist) in [
        ([0.0f32, 0.0, 1.0], 0.0f32),
        ([1.0, 0.0, 0.0], 0.0),
        ([0.0, 1.0, 0.0], 64.0),
    ] {
        for value in normal {
            planes.extend_from_slice(&value.to_le_bytes());
        }
        planes.extend_from_slice(&dist.to_le_bytes());
        le(&mut planes, &[0]);
    }
    let mut nodes = Vec::new();
    for (plane, front, back) in [(0, 1i16, -2i16), (1, 2, -1), (2, -3, -1)] {
        le(&mut nodes, &[plane]);
        le16(
            &mut nodes,
            &[front, back, -128, -128, -128, 128, 128, 128, 0, 0],
        );
    }
    let mut leaves = Vec::new();
    for contents in [-1, -5, -3, -2] {
        le(&mut leaves, &[contents, -1]);
        le16(&mut leaves, &[-128, -128, -128, 128, 128, 128, 0, 0]);
        le(&mut leaves, &[0]);
    }
    let mut clipnodes = Vec::new();
    for (plane, front, back) in [(0, 1i16, -2i16), (1, -1, -2)] {
        le(&mut clipnodes, &[plane]);
        le16(&mut clipnodes, &[front, back]);
    }
    let mut models = Vec::new();
    for (lo, hi, head) in [(-128.0f32, 128.0f32, 0), (16.0, 48.0, 2)] {
        for value in [lo, lo, lo, hi, hi, hi, 0.0, 0.0, 0.0] {
            models.extend_from_slice(&value.to_le_bytes());
        }
        le(&mut models, &[head, head.min(1), 0, 0, 0, 0, 0]);
    }
    let entities = concat!(
        "{\n\"classname\" \"worldspawn\"\n\"message\" \"fuzz seed\"\n}\n",
        "{\n\"classname\" \"info_player_deathmatch\"\n\"origin\" \"0 0 24\"\n}\n",
        "{\n\"classname\" \"func_door\"\n\"model\" \"*1\"\n\"angle\" \"-1\"\n}\n",
        "{\n\"classname\" \"item_health\"\n\"spawnflags\" \"2\"\n\"origin\" \"-32 0 16\"\n}\n\0",
    );
    lump_file(&[
        (0, entities.as_bytes().to_vec()),
        (1, planes),
        (5, nodes),
        (9, clipnodes),
        (10, leaves),
        (14, models),
    ])
}

fn synthetic_pak(files: &[(&str, &[u8])]) -> Vec<u8> {
    let mut out = vec![0u8; 12];
    let mut directory = Vec::new();
    for (name, data) in files {
        let mut entry = [0u8; 56];
        entry[..name.len()].copy_from_slice(name.as_bytes());
        directory.extend_from_slice(&entry);
        le(&mut directory, &[out.len() as i32, data.len() as i32]);
        out.extend_from_slice(data);
    }
    out[..4].copy_from_slice(b"PACK");
    let dir_ofs = out.len() as i32;
    out[4..8].copy_from_slice(&dir_ofs.to_le_bytes());
    out[8..12].copy_from_slice(&(directory.len() as i32).to_le_bytes());
    out.extend_from_slice(&directory);
    out
}

/// What the bsp fuzz target does: parse, then the lab's next steps.
fn exercise(bsp: &Bsp29) {
    let _ = parse_entities(&bsp.entities);
    let (a, b) = (bsp.mins, bsp.maxs);
    let mid = [
        (a[0] + b[0]) / 2.0,
        (a[1] + b[1]) / 2.0,
        (a[2] + b[2]) / 2.0,
    ];
    if let Some(hull) = &bsp.hull0 {
        for p in [a, b, mid] {
            let _ = hull.contents_at(p);
        }
        let _ = hull.line_clear(a, b);
        let _ = death_is_lava(Some(hull), mid[0].into(), mid[1].into(), mid[2].into());
    }
    if let Some(clip) = &bsp.clip {
        for p in [a, b, mid] {
            let _ = clip.contents_at(p);
        }
        let _ = clip.line_clear(a, b);
    }
}

fn parse_map_case(data: &[u8]) {
    if let Ok(bsp) = parse_bsp29(data) {
        exercise(&bsp);
    }
    let _ = pak_list_maps_bytes(data);
    if let Ok(Some(inner)) = pak_find_bytes(data, "fuzz.bsp") {
        if let Ok(bsp) = parse_bsp29(&inner) {
            exercise(&bsp);
        }
    }
}

#[test]
fn synthetic_bsp_and_pak_are_valid_seeds() {
    let raw = synthetic_bsp();
    let bsp = parse_bsp29(&raw).expect("seed parses");
    assert_eq!(bsp.models.len(), 2);
    let hull = bsp.hull0.as_ref().expect("hull 0");
    assert_eq!(
        hull.contents_at([16.0, 0.0, -16.0]),
        -5,
        "lava below the floor"
    );
    assert_eq!(
        hull.contents_at([16.0, 80.0, 16.0]),
        -3,
        "water past the y plane"
    );
    assert_eq!(hull.contents_at([-16.0, 0.0, 16.0]), -1, "empty");
    assert!(bsp.clip.is_some());
    assert_eq!(parse_entities(&bsp.entities).len(), 4);
    let pak = synthetic_pak(&[("maps/fuzz.bsp", &raw), ("sound/x.wav", b"RIFF")]);
    assert_eq!(pak_list_maps_bytes(&pak).unwrap(), ["fuzz.bsp"]);
    assert_eq!(
        pak_find_bytes(&pak, "FUZZ.BSP").unwrap().as_deref(),
        Some(raw.as_slice())
    );
}

#[test]
fn bsp_reader_survives_mutation() {
    run(
        "bsp",
        &[synthetic_bsp()],
        3000,
        |rng, data| mutate_bytes(rng, data, 4 + 15 * 8),
        parse_map_case,
    );
}

#[test]
fn pak_reader_survives_mutation() {
    let raw = synthetic_bsp();
    let pak = synthetic_pak(&[("maps/fuzz.bsp", &raw), ("sound/x.wav", b"RIFF")]);
    run(
        "pak",
        &[pak],
        3000,
        |rng, data| mutate_bytes(rng, data, 12),
        parse_map_case,
    );
}

// ------------------------------------------------------------------ arglog

/// Committed tapes that between them carry samples, events, deaths with and
/// without a third party, motion rows, build and clock identity lines and a
/// fixture marker. They are protected tapes (argus_ci.py tapes), so they stay.
const TAPES: [&str; 5] = [
    "ab_dm2_airlead1.log",
    "ab_dm4_hazard364_floorfinal.log",
    "ally_barrel_v1_health_dm2.log",
    "fxconf_fixed1425_dm2_s1733.log",
    "motion_observer_v2_dm2_played.log",
];

/// A window of about `size` bytes starting on a line boundary at `from`.
fn window(data: &[u8], from: usize, size: usize) -> Vec<u8> {
    let start = match from {
        0 => 0,
        _ => data[from.min(data.len())..]
            .iter()
            .position(|b| *b == b'\n')
            .map_or(data.len(), |i| from + i + 1),
    };
    let end = (start + size).min(data.len());
    let end = data[start..end]
        .iter()
        .rposition(|b| *b == b'\n')
        .map_or(end, |i| start + i + 1);
    data[start..end].to_vec()
}

fn tape_seeds() -> Vec<Vec<u8>> {
    let runs = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../runs");
    let mut seeds = Vec::new();
    for name in TAPES {
        let data =
            std::fs::read(runs.join(name)).unwrap_or_else(|e| panic!("committed tape {name}: {e}"));
        seeds.push(window(&data, 0, 6000));
        seeds.push(window(&data, data.len() / 2, 6000));
    }
    seeds
}

fn parse_tape_case(data: &[u8]) {
    let text = String::from_utf8_lossy(data);
    let tape = parse_tape(&text);
    let _ = tape.summary();
    let _ = tape.freezes();
    let _ = tape.confinements(220.0, 5.0);
    let _ = tape.closest_approach();
    let _ = tape.tick_gap_mean();
    let _ = tape.human_names();
    let _ = tape.instrument_names();
}

#[test]
fn tape_parser_survives_mutation() {
    run("arglog", &tape_seeds(), 600, mutate_text, parse_tape_case);
}
