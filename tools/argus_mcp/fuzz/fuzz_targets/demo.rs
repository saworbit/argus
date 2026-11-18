//! Protocol 15 .dem reader: never panic, never spin, on any bytes.
#![no_main]

use argus_mcp::demo::parse_demo;
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    // the file as given
    let _ = parse_demo("fuzz.dem", data);

    // The same bytes framed as one block: the first 12 are the POV angles
    // and the rest is the message payload. A raw input has to learn the
    // header line and the block length before it reaches the svc parser;
    // this reaches it on the first run.
    let (angles, payload) = data.split_at(data.len().min(12));
    let mut framed = Vec::with_capacity(data.len() + 7);
    framed.extend_from_slice(b"-1\n");
    framed.extend_from_slice(&(payload.len() as i32).to_le_bytes());
    framed.extend_from_slice(angles);
    framed.resize(framed.len() + 12 - angles.len(), 0);
    framed.extend_from_slice(payload);
    let _ = parse_demo("fuzz.dem", &framed);
});
