//! BSP29 and PAK readers, plus what the lab does next with a parsed map:
//! the entity lump parse and the hull queries. Never panic, never spin.
#![no_main]

use argus_mcp::bsp::{death_is_lava, pak_find_bytes, pak_list_maps_bytes, parse_bsp29, Bsp29};
use argus_mcp::cartograph::parse_entities;
use libfuzzer_sys::fuzz_target;

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

fuzz_target!(|data: &[u8]| {
    if let Ok(bsp) = parse_bsp29(data) {
        exercise(&bsp);
    }
    // seed_corpus.py packs its maps as maps/fuzz.bsp
    let _ = pak_list_maps_bytes(data);
    if let Ok(Some(inner)) = pak_find_bytes(data, "fuzz.bsp") {
        if let Ok(bsp) = parse_bsp29(&inner) {
            exercise(&bsp);
        }
    }
});
