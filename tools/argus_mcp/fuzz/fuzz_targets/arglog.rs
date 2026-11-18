//! ARGLOG/ARGEVT console tape parser and the scans the lab runs over a
//! parsed tape. Never panic, never spin.
#![no_main]

use argus_mcp::parse_arglog::parse_tape;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // paths::read_engine_text decodes a console log the same way
    let text = String::from_utf8_lossy(data);
    let tape = parse_tape(&text);
    let _ = tape.summary();
    let _ = tape.freezes();
    let _ = tape.confinements(220.0, 5.0);
    let _ = tape.closest_approach();
    let _ = tape.tick_gap_mean();
    let _ = tape.human_names();
    let _ = tape.instrument_names();
});
