//! The lab connects as a real NetQuake CLIENT (the fourth instrument).
//!
//! Telemetry is the 1 Hz ruler, cartography the static map, demos the
//! after-the-fact microscope; this is the LIVE one. A puppet client is
//! a real player edict on the server, which buys the lab things no
//! other instrument can reach:
//!
//!   * empirical link verification - drive the puppet along a minted
//!     link and OBSERVE whether the walking works. Exactly the ground
//!     truth the 2026-08-28 beeline criteria (three graves) tried to
//!     approximate from geometry.
//!   * live full-rate observation without demo files.
//!   * the say channel - a client legally reads chat broadcasts, which
//!     vanilla QC never can (the v3.12 finding); keyword chat and the
//!     parked SLM ideas get their channel through here.
//!   * scoreboard verification from a real client's seat
//!     (svc_updatename / colors reach us like any NetQuake client).
//!
//! Protocol notes: NetQuake datagram layer per net_dgrm.c - control
//! packets carry NETFLAG_CTL and big-endian header ints; game packets
//! are [u32 BE length|flags][u32 BE sequence][payload]; reliable DATA
//! is ACKed per packet and EOM closes a message; MSG_* payload fields
//! are little-endian throughout. The svc vocabulary mirrors demo.rs
//! (the same stream, minus the demo block framing) - a deliberate
//! parallel implementation, same precedent as the python/rust parser
//! split: the two readers guard each other.

use std::collections::{BTreeMap, VecDeque};
use std::net::UdpSocket;
use std::time::{Duration, Instant};

use serde::Serialize;

const NETFLAG_DATA: u32 = 0x0001_0000;
const NETFLAG_ACK: u32 = 0x0002_0000;
const NETFLAG_EOM: u32 = 0x0008_0000;
const NETFLAG_UNRELIABLE: u32 = 0x0010_0000;
const NETFLAG_CTL: u32 = 0x8000_0000;

const CCREQ_CONNECT: u8 = 0x01;
const CCREP_ACCEPT: u8 = 0x81;
const CCREP_REJECT: u8 = 0x82;
const NET_PROTOCOL_VERSION: u8 = 3;

const CLC_DISCONNECT: u8 = 2;
const CLC_MOVE: u8 = 3;
const CLC_STRINGCMD: u8 = 4;

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

const U_MOREBITS: u16 = 1;
const U_ORIGIN1: u16 = 1 << 1;
const U_ORIGIN2: u16 = 1 << 2;
const U_ORIGIN3: u16 = 1 << 3;
const U_ANGLE2: u16 = 1 << 4;
const U_NOLERP: u16 = 1 << 5;
const U_FRAME: u16 = 1 << 6;
const U_ANGLE1: u16 = 1 << 8;
const U_ANGLE3: u16 = 1 << 9;
const U_MODEL: u16 = 1 << 10;
const U_COLORMAP: u16 = 1 << 11;
const U_SKIN: u16 = 1 << 12;
const U_EFFECTS: u16 = 1 << 13;
const U_LONGENTITY: u16 = 1 << 14;

const SU_VIEWHEIGHT: u16 = 1;
const SU_IDEALPITCH: u16 = 1 << 1;
const SU_PUNCH1: u16 = 1 << 2;
const SU_VELOCITY1: u16 = 1 << 5;
const SU_WEAPONFRAME: u16 = 1 << 12;
const SU_ARMOR: u16 = 1 << 13;
const SU_WEAPON: u16 = 1 << 14;

struct Rd<'a> {
    d: &'a [u8],
    p: usize,
}

impl<'a> Rd<'a> {
    fn new(d: &'a [u8]) -> Self {
        Rd { d, p: 0 }
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

#[derive(Default, Clone, Serialize)]
pub struct WorldEnt {
    pub model: u16,
    pub skin: u8,
    pub pos: [f32; 3],
    pub yaw: f32,
    #[serde(skip)]
    base_pos: [f32; 3],
    #[serde(skip)]
    base_model: u16,
    #[serde(skip)]
    base_skin: u8,
    pub updates: usize,
}

#[derive(Default)]
pub struct ClientWorld {
    pub protocol: i32,
    pub maxclients: u8,
    pub level: String,
    pub models: Vec<String>,
    pub player_model: Option<u16>,
    pub names: BTreeMap<u8, String>,
    pub ents: BTreeMap<u16, WorldEnt>,
    pub my_ent: u16,
    pub time: f64,
    pub signon: u8,
    pub prints: Vec<(f64, String)>,
    print_buf: String,
    pub disconnected: bool,
    pub unknown_svc: Vec<u8>,
}

pub struct NetClient {
    sock: UdpSocket,
    rx_rel_seq: u32,
    rx_unrel_seq: u32,
    tx_rel_seq: u32,
    tx_unrel_seq: u32,
    rbuf: Vec<u8>,
    queue: VecDeque<Vec<u8>>,
    inflight: Option<(u32, Vec<u8>, Instant)>,
    pub world: ClientWorld,
    name: String,
    last_move: Instant,
    pub yaw: f32,
    pub pitch: f32,
    fwd: i16,
    side: i16,
    buttons: u8,
    impulse: u8,
}

impl NetClient {
    /// CCREQ_CONNECT handshake, then hand back a socket locked to the
    /// per-client game port the server assigns.
    pub fn connect(host: &str, port: u16, name: &str) -> Result<NetClient, String> {
        let sock = UdpSocket::bind("0.0.0.0:0").map_err(|e| format!("bind: {e}"))?;
        sock.set_read_timeout(Some(Duration::from_millis(300)))
            .map_err(|e| format!("timeout: {e}"))?;
        // control packets carry a FOUR byte header only - big-endian
        // NETFLAG_CTL | total length - then the request body
        // (net_dgrm.c Datagram_CheckNewConnections)
        let pkt = {
            let mut p = vec![0u8; 4];
            p.push(CCREQ_CONNECT);
            p.extend_from_slice(b"QUAKE\0");
            p.push(NET_PROTOCOL_VERSION);
            let l = p.len() as u32;
            p[0..4].copy_from_slice(&(NETFLAG_CTL | l).to_be_bytes());
            p
        };
        // WinQuake binds its UDP socket to the address gethostbyname
        // returns for the local hostname, NOT loopback - on this rig
        // that was a link-local 169.254 adapter and 127.0.0.1 came
        // back ICMP-refused. Mirror the engine: when asked for
        // localhost, also try the hostname-resolved address.
        let mut hosts: Vec<String> = vec![host.to_string()];
        if host == "127.0.0.1" || host.eq_ignore_ascii_case("localhost") {
            // COMPUTERNAME is the Windows spelling; Unix rigs and CI
            // containers carry HOSTNAME instead, and without it the
            // hostname-adapter retry never runs off Windows.
            let hostname = std::env::var("COMPUTERNAME")
                .or_else(|_| std::env::var("HOSTNAME"))
                .or_else(|_| {
                    std::process::Command::new("hostname")
                        .output()
                        .map_err(|_| std::env::VarError::NotPresent)
                        .and_then(|o| {
                            let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
                            if s.is_empty() {
                                Err(std::env::VarError::NotPresent)
                            } else {
                                Ok(s)
                            }
                        })
                });
            if let Ok(name) = hostname {
                use std::net::ToSocketAddrs;
                if let Ok(addrs) = (name.as_str(), port).to_socket_addrs() {
                    for a in addrs {
                        if a.is_ipv4() {
                            let ip = a.ip().to_string();
                            if !hosts.contains(&ip) {
                                hosts.push(ip);
                            }
                        }
                    }
                }
            }
        }
        let mut game_host = hosts[0].clone();
        let mut game_port = 0u16;
        let mut last_err = String::from("no CCREP within 3 s");
        'outer: for _ in 0..5 {
            for h in &hosts {
                sock.send_to(&pkt, (h.as_str(), port))
                    .map_err(|e| format!("send: {e}"))?;
                let mut buf = [0u8; 1400];
                match sock.recv_from(&mut buf) {
                    Ok((n, from)) if n >= 5 => {
                        let hdr = u32::from_be_bytes(buf[0..4].try_into().unwrap());
                        if hdr & NETFLAG_CTL == 0 {
                            continue;
                        }
                        match buf[4] {
                            CCREP_ACCEPT if n >= 9 => {
                                game_port = i32::from_le_bytes(
                                    buf[5..9].try_into().unwrap(),
                                ) as u16;
                                game_host = from.ip().to_string();
                                break 'outer;
                            }
                            CCREP_REJECT => {
                                let msg = buf[5..n]
                                    .split(|b| *b == 0)
                                    .next()
                                    .map(|s| String::from_utf8_lossy(s).into_owned())
                                    .unwrap_or_default();
                                return Err(format!("server rejected: {msg}"));
                            }
                            _ => {}
                        }
                    }
                    Ok(_) => {}
                    Err(_) => {
                        last_err = "connect request timed out".into();
                    }
                }
            }
        }
        if game_port == 0 {
            return Err(last_err);
        }
        sock.connect((game_host.as_str(), game_port))
            .map_err(|e| format!("connect: {e}"))?;
        sock.set_read_timeout(Some(Duration::from_millis(30)))
            .map_err(|e| format!("timeout: {e}"))?;
        Ok(NetClient {
            sock,
            rx_rel_seq: 0,
            rx_unrel_seq: 0,
            tx_rel_seq: 0,
            tx_unrel_seq: 0,
            rbuf: Vec::new(),
            queue: VecDeque::new(),
            inflight: None,
            world: ClientWorld::default(),
            name: name.to_string(),
            last_move: Instant::now(),
            yaw: 0.0,
            pitch: 0.0,
            fwd: 0,
            side: 0,
            buttons: 0,
            impulse: 0,
        })
    }

    pub fn stringcmd(&mut self, cmd: &str) {
        let mut msg = vec![CLC_STRINGCMD];
        msg.extend_from_slice(cmd.as_bytes());
        msg.push(0);
        self.queue.push_back(msg);
    }

    fn send_reliable_now(&mut self, payload: &[u8], seq: u32) {
        let mut pkt = Vec::with_capacity(8 + payload.len());
        let hdr = NETFLAG_DATA | NETFLAG_EOM | (8 + payload.len() as u32);
        pkt.extend_from_slice(&hdr.to_be_bytes());
        pkt.extend_from_slice(&seq.to_be_bytes());
        pkt.extend_from_slice(payload);
        let _ = self.sock.send(&pkt);
    }

    fn send_unreliable(&mut self, payload: &[u8]) {
        let mut pkt = Vec::with_capacity(8 + payload.len());
        let hdr = NETFLAG_UNRELIABLE | (8 + payload.len() as u32);
        pkt.extend_from_slice(&hdr.to_be_bytes());
        pkt.extend_from_slice(&self.tx_unrel_seq.to_be_bytes());
        self.tx_unrel_seq += 1;
        pkt.extend_from_slice(payload);
        let _ = self.sock.send(&pkt);
    }

    /// Set the standing move the keepalive tick repeats (~20 Hz).
    pub fn set_move(&mut self, pitch: f32, yaw: f32, fwd: i16, side: i16, buttons: u8) {
        self.pitch = pitch;
        self.yaw = yaw;
        self.fwd = fwd;
        self.side = side;
        self.buttons = buttons;
    }

    pub fn set_impulse(&mut self, imp: u8) {
        self.impulse = imp;
    }

    fn send_move_now(&mut self) {
        let mut m = vec![CLC_MOVE];
        m.extend_from_slice(&(self.world.time as f32).to_le_bytes());
        for a in [self.pitch, self.yaw, 0.0] {
            m.push(((a * 256.0 / 360.0) as i32 & 255) as u8);
        }
        m.extend_from_slice(&self.fwd.to_le_bytes());
        m.extend_from_slice(&self.side.to_le_bytes());
        m.extend_from_slice(&0i16.to_le_bytes());
        m.push(self.buttons);
        m.push(self.impulse);
        self.impulse = 0;
        self.send_unreliable(&m);
    }

    /// Process network + drive the signon dance + keepalive for `dur`.
    pub fn pump(&mut self, dur: Duration) {
        let end = Instant::now() + dur;
        while Instant::now() < end && !self.world.disconnected {
            // reliable send window: one in flight, 300 ms retransmit
            match &self.inflight {
                None => {
                    if let Some(payload) = self.queue.pop_front() {
                        let seq = self.tx_rel_seq;
                        self.send_reliable_now(&payload, seq);
                        self.inflight = Some((seq, payload, Instant::now()));
                    }
                }
                Some((seq, payload, at)) if at.elapsed() > Duration::from_millis(300) => {
                    let (seq, payload) = (*seq, payload.clone());
                    self.send_reliable_now(&payload, seq);
                    self.inflight = Some((seq, payload, Instant::now()));
                }
                _ => {}
            }
            if self.world.signon >= 2 && self.last_move.elapsed() > Duration::from_millis(50)
            {
                self.send_move_now();
                self.last_move = Instant::now();
            }
            let mut buf = [0u8; 65536];
            match self.sock.recv(&mut buf) {
                Ok(n) if n >= 8 => self.handle_packet(&buf[..n]),
                Ok(_) => {}
                Err(_) => {}
            }
        }
    }

    fn handle_packet(&mut self, buf: &[u8]) {
        let hdr = u32::from_be_bytes(buf[0..4].try_into().unwrap());
        let seq = u32::from_be_bytes(buf[4..8].try_into().unwrap());
        let flags = hdr & 0xffff_0000;
        let payload = &buf[8..];
        if flags & NETFLAG_UNRELIABLE != 0 {
            if seq >= self.rx_unrel_seq {
                self.rx_unrel_seq = seq + 1;
                self.process_message(payload.to_vec());
            }
        } else if flags & NETFLAG_ACK != 0 {
            if let Some((s, _, _)) = &self.inflight {
                if *s == seq {
                    self.inflight = None;
                    self.tx_rel_seq += 1;
                }
            }
        } else if flags & NETFLAG_DATA != 0 {
            let mut ack = Vec::with_capacity(8);
            ack.extend_from_slice(&(NETFLAG_ACK | 8).to_be_bytes());
            ack.extend_from_slice(&seq.to_be_bytes());
            let _ = self.sock.send(&ack);
            if seq == self.rx_rel_seq {
                self.rx_rel_seq += 1;
                self.rbuf.extend_from_slice(payload);
                if flags & NETFLAG_EOM != 0 {
                    let msg = std::mem::take(&mut self.rbuf);
                    self.process_message(msg);
                }
            }
        }
    }

    fn on_signon(&mut self, n: u8) {
        self.world.signon = n;
        match n {
            1 => self.stringcmd("prespawn"),
            2 => {
                let name = self.name.clone();
                self.stringcmd(&format!("name \"{name}\"\n"));
                self.stringcmd("color 0 0\n");
                self.stringcmd("spawn ");
            }
            3 => self.stringcmd("begin"),
            _ => {}
        }
    }

    fn process_message(&mut self, data: Vec<u8>) {
        let mut r = Rd::new(&data);
        macro_rules! need {
            ($e:expr) => {
                match $e {
                    Some(v) => v,
                    None => return,
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
                let st = self.world.ents.entry(ent).or_default();
                let mut pos = st.base_pos;
                let mut model = st.base_model;
                let mut skin = st.base_skin;
                let mut yaw = st.yaw;
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
                    yaw = need!(r.angle());
                }
                if bits & U_ORIGIN3 != 0 {
                    pos[2] = need!(r.coord());
                }
                if bits & U_ANGLE3 != 0 {
                    need!(r.angle());
                }
                let _ = bits & U_NOLERP;
                st.model = model;
                st.skin = skin;
                st.pos = pos;
                st.yaw = yaw;
                st.updates += 1;
                continue;
            }
            match cmd {
                0 | SVC_KILLEDMONSTER | SVC_FOUNDSECRET | SVC_INTERMISSION
                | SVC_SELLSCREEN => {}
                SVC_DISCONNECT => {
                    self.world.disconnected = true;
                    return;
                }
                SVC_UPDATESTAT => {
                    need!(r.u8());
                    need!(r.i32());
                }
                SVC_VERSION => {
                    self.world.protocol = need!(r.i32());
                }
                SVC_SETVIEW => {
                    self.world.my_ent = need!(r.i16()) as u16;
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
                    self.world.time = need!(r.f32()) as f64;
                }
                SVC_PRINT => {
                    let s = need!(r.string());
                    self.world.print_buf.push_str(&s.replace(['\u{1}', '\u{2}'], ""));
                    while let Some(nl) = self.world.print_buf.find('\n') {
                        let line = self.world.print_buf[..nl].trim().to_string();
                        self.world.print_buf.drain(..=nl);
                        if !line.is_empty() {
                            let t = self.world.time;
                            self.world.prints.push((t, line));
                        }
                    }
                }
                SVC_CENTERPRINT => {
                    let s = need!(r.string());
                    let s = s.trim().replace('\n', " / ");
                    if !s.is_empty() {
                        let t = self.world.time;
                        self.world.prints.push((t, s));
                    }
                }
                SVC_STUFFTEXT | SVC_FINALE | SVC_CUTSCENE => {
                    need!(r.string());
                }
                SVC_SETANGLE => {
                    let p = need!(r.angle());
                    let y = need!(r.angle());
                    need!(r.angle());
                    self.pitch = p;
                    self.yaw = y;
                }
                SVC_SERVERINFO => {
                    self.world.protocol = need!(r.i32());
                    self.world.maxclients = need!(r.u8());
                    need!(r.u8());
                    self.world.level = need!(r.string());
                    self.world.models.clear();
                    loop {
                        let m = need!(r.string());
                        if m.is_empty() {
                            break;
                        }
                        self.world.models.push(m);
                    }
                    loop {
                        let s = need!(r.string());
                        if s.is_empty() {
                            break;
                        }
                    }
                    self.world.player_model = self
                        .world
                        .models
                        .iter()
                        .position(|m| m.ends_with("player.mdl"))
                        .map(|i| i as u16 + 1);
                }
                SVC_LIGHTSTYLE => {
                    need!(r.u8());
                    need!(r.string());
                }
                SVC_UPDATENAME => {
                    let slot = need!(r.u8());
                    let name = need!(r.string());
                    if name.is_empty() {
                        self.world.names.remove(&slot);
                    } else {
                        self.world.names.insert(slot, name);
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
                    need!(r.i32());
                    if bits & SU_WEAPONFRAME != 0 {
                        need!(r.u8());
                    }
                    if bits & SU_ARMOR != 0 {
                        need!(r.u8());
                    }
                    if bits & SU_WEAPON != 0 {
                        need!(r.u8());
                    }
                    need!(r.i16());
                    for _ in 0..5 {
                        need!(r.u8());
                    }
                    need!(r.u8());
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
                    need!(r.u8());
                    need!(r.u8());
                    let skin = need!(r.u8());
                    let mut pos = [0f32; 3];
                    let mut yaw = 0f32;
                    for (i, item) in pos.iter_mut().enumerate() {
                        *item = need!(r.coord());
                        let a = need!(r.angle());
                        if i == 1 {
                            yaw = a;
                        }
                    }
                    let st = self.world.ents.entry(ent).or_default();
                    st.base_model = model;
                    st.base_skin = skin;
                    st.base_pos = pos;
                    st.model = model;
                    st.skin = skin;
                    st.pos = pos;
                    st.yaw = yaw;
                }
                SVC_TEMP_ENTITY => {
                    let t = need!(r.u8());
                    match t {
                        5 | 6 | 9 | 13 => {
                            need!(r.i16());
                            for _ in 0..6 {
                                need!(r.coord());
                            }
                        }
                        12 => {
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
                SVC_SETPAUSE => {
                    need!(r.u8());
                }
                SVC_SIGNONNUM => {
                    let n = need!(r.u8());
                    self.on_signon(n);
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
                    if !self.world.unknown_svc.contains(&other) {
                        self.world.unknown_svc.push(other);
                    }
                    return;
                }
            }
        }
    }

    pub fn my_pos(&self) -> Option<[f32; 3]> {
        self.world.ents.get(&self.world.my_ent).map(|e| e.pos)
    }

    /// Steer toward a point by resending the standing move each tick;
    /// returns the closest approach. The controller is deliberately
    /// dumb - a straight-line walk at run speed IS the experiment.
    pub fn walk_toward(&mut self, target: [f32; 3], secs: f32) -> WalkOutcome {
        let end = Instant::now() + Duration::from_secs_f32(secs);
        let mut closest = f32::MAX;
        let mut track: Vec<[f32; 3]> = Vec::new();
        let mut stuck = 0u32;
        while Instant::now() < end {
            if let Some(p) = self.my_pos() {
                let dx = target[0] - p[0];
                let dy = target[1] - p[1];
                let h = (dx * dx + dy * dy).sqrt();
                let dz = (target[2] - p[2]).abs();
                if h < closest {
                    closest = h;
                }
                // auto-hop: a human holds +jump at ledges and steps
                // without thinking; when progress stagnates for a few
                // ticks, tap jump. This is what lets the puppet
                // verify jump-typed links too - the arc happens at
                // whatever speed the approach carried.
                if let Some(prev) = track.last() {
                    let step = ((p[0] - prev[0]).powi(2) + (p[1] - prev[1]).powi(2)).sqrt();
                    if step < 8.0 {
                        stuck += 1;
                    } else {
                        stuck = 0;
                    }
                }
                track.push(p);
                if h < 24.0 && dz < 72.0 {
                    self.set_move(0.0, 0.0, 0, 0, 0);
                    return WalkOutcome { reached: true, closest, final_pos: p, track };
                }
                let yaw = dy.atan2(dx).to_degrees();
                let buttons = if stuck >= 4 { 2 } else { 0 };
                self.set_move(0.0, yaw, 320, 0, buttons);
            }
            self.pump(Duration::from_millis(50));
        }
        let fp = self.my_pos().unwrap_or_default();
        self.set_move(0.0, 0.0, 0, 0, 0);
        WalkOutcome { reached: false, closest, final_pos: fp, track }
    }

    pub fn disconnect(mut self) {
        let msg = [CLC_DISCONNECT];
        self.send_unreliable(&msg);
    }
}

#[derive(Serialize)]
pub struct WalkOutcome {
    pub reached: bool,
    pub closest: f32,
    pub final_pos: [f32; 3],
    #[serde(skip)]
    pub track: Vec<[f32; 3]>,
}

#[derive(Serialize)]
pub struct ObserveReport {
    pub level: String,
    pub protocol: i32,
    pub maxclients: u8,
    pub signon: u8,
    pub my_ent: u16,
    pub my_pos: Option<[f32; 3]>,
    pub names: BTreeMap<u8, String>,
    pub player_ents: usize,
    pub total_ents: usize,
    pub time: f64,
    pub last_prints: Vec<String>,
    pub unknown_svc: Vec<u8>,
}

/// Connect, complete the signon dance, observe for `secs`, report.
pub fn observe(host: &str, port: u16, secs: f32, name: &str) -> Result<ObserveReport, String> {
    let mut c = NetClient::connect(host, port, name)?;
    c.pump(Duration::from_secs_f32(secs.max(2.0)));
    let players = c
        .world
        .ents
        .values()
        .filter(|e| Some(e.model) == c.world.player_model && e.updates > 0)
        .count();
    let report = ObserveReport {
        level: c.world.level.clone(),
        protocol: c.world.protocol,
        maxclients: c.world.maxclients,
        signon: c.world.signon,
        my_ent: c.world.my_ent,
        my_pos: c.my_pos(),
        names: c.world.names.clone(),
        player_ents: players,
        total_ents: c.world.ents.len(),
        time: c.world.time,
        last_prints: c
            .world
            .prints
            .iter()
            .rev()
            .take(12)
            .rev()
            .map(|(t, s)| format!("{t:.1} {s}"))
            .collect(),
        unknown_svc: c.world.unknown_svc.clone(),
    };
    c.disconnect();
    Ok(report)
}

#[derive(Serialize)]
pub struct LinkVerdict {
    pub a: usize,
    pub b: usize,
    pub from: [f32; 3],
    pub to: [f32; 3],
    pub h: f32,
    pub reached: bool,
    pub closest: f32,
    pub note: String,
}

#[derive(Serialize)]
pub struct ProbeReport {
    pub map: String,
    pub probed: usize,
    pub passed: usize,
    pub failed: usize,
    pub teleport_failures: usize,
    pub failed_links: Vec<LinkVerdict>,
    pub passed_sample: Vec<String>,
}

/// EMPIRICAL LINK VERIFICATION - the referee the v3.84 graveyard's
/// three geometric criteria were approximating. Spawn the lab
/// engine, connect the puppet, and for each walk link: teleport to
/// the start (dev impulse 216 reads the scratch cvars; both set
/// through the console-inject tune path) and WALK the line. A link
/// the puppet cannot walk is a link no bot can walk - the engine
/// itself is the judge.
pub async fn probe_links(
    cfg: &crate::config::Config,
    map: &str,
    limit: usize,
    skip: usize,
) -> Result<ProbeReport, String> {
    let navj = cfg.root.join("src").join(format!("argus_nav_{map}.qc.json"));
    let nav: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(&navj).map_err(|e| format!("{}: {e}", navj.display()))?,
    )
    .map_err(|e| format!("nav json: {e}"))?;
    let nodes: Vec<[f32; 3]> = nav["nodes"]
        .as_array()
        .ok_or("no nodes")?
        .iter()
        .map(|n| {
            let a = n.as_array().unwrap();
            [
                a[0].as_f64().unwrap() as f32,
                a[1].as_f64().unwrap() as f32,
                a[2].as_f64().unwrap() as f32,
            ]
        })
        .collect();
    let jump: std::collections::HashSet<(usize, usize)> = nav["jlinks"]
        .as_array()
        .map(|v| {
            v.iter()
                .map(|e| {
                    let a = e.as_array().unwrap();
                    (
                        a[0].as_u64().unwrap() as usize,
                        a[1].as_u64().unwrap() as usize,
                    )
                })
                .collect()
        })
        .unwrap_or_default();
    let links: Vec<(usize, usize)> = nav["links"]
        .as_array()
        .ok_or("no links")?
        .iter()
        .map(|e| {
            let a = e.as_array().unwrap();
            (
                a[0].as_u64().unwrap() as usize,
                a[1].as_u64().unwrap() as usize,
            )
        })
        .filter(|p| !jump.contains(p))
        .collect();
    let todo: Vec<(usize, usize)> = links.into_iter().skip(skip).take(limit.min(80)).collect();
    if todo.is_empty() {
        return Err("no links in range".into());
    }

    let secs = (todo.len() as u32) * 9 + 40;
    let mut ctrl = crate::match_ctrl::MatchCtrl::default();
    ctrl.start(cfg, map, Some(secs.min(590)), Some("probe_links_run"), None, Some(0), None)
        .await
        .map_err(|e| format!("engine start: {e}"))?;
    tokio::time::sleep(Duration::from_secs(4)).await;

    let mut client = match NetClient::connect("127.0.0.1", 26000, "labprobe") {
        Ok(c) => c,
        Err(e) => {
            let _ = ctrl.stop(Duration::from_secs(3)).await;
            return Err(e);
        }
    };
    client.pump(Duration::from_secs(3));
    if client.world.signon < 3 {
        let _ = ctrl.stop(Duration::from_secs(3)).await;
        return Err(format!("signon stalled at {}", client.world.signon));
    }

    let mut report = ProbeReport {
        map: map.to_string(),
        probed: 0,
        passed: 0,
        failed: 0,
        teleport_failures: 0,
        failed_links: Vec::new(),
        passed_sample: Vec::new(),
    };
    for (a, b) in todo {
        let from = nodes[a];
        let to = nodes[b];
        // scratch cvars through the tune inject - ONE line per link
        // (semicolons parse in the console; rapid separate attaches
        // dropped every inject after the first link's batch and the
        // puppet kept landing on the stale coordinates)
        if let Err(e) = ctrl.command(&format!(
            "scratch2 {}; scratch3 {}; scratch4 {}",
            from[0], from[1], from[2]
        ))
        .await
        {
            let _ = ctrl.stop(Duration::from_secs(3)).await;
            return Err(format!("inject: {e}"));
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
        let mut landed = false;
        for _ in 0..4 {
            client.set_impulse(216);
            client.pump(Duration::from_millis(400));
            if let Some(p) = client.my_pos() {
                let d = ((p[0] - from[0]).powi(2) + (p[1] - from[1]).powi(2)).sqrt();
                if d < 64.0 && (p[2] - from[2]).abs() < 72.0 {
                    landed = true;
                    break;
                }
            }
        }
        report.probed += 1;
        if !landed {
            report.teleport_failures += 1;
            continue;
        }
        let h = ((to[0] - from[0]).powi(2) + (to[1] - from[1]).powi(2)).sqrt();
        let out = client.walk_toward(to, h / 240.0 + 3.0);
        if out.reached {
            report.passed += 1;
            if report.passed_sample.len() < 8 {
                report.passed_sample.push(format!("n{a}->n{b} h {h:.0}"));
            }
        } else {
            report.failed += 1;
            report.failed_links.push(LinkVerdict {
                a,
                b,
                from,
                to,
                h,
                reached: false,
                closest: out.closest,
                note: format!(
                    "stopped {} short at ({:.0} {:.0} {:.0})",
                    out.closest as i32, out.final_pos[0], out.final_pos[1], out.final_pos[2]
                ),
            });
        }
        if client.world.disconnected {
            break;
        }
    }
    client.disconnect();
    let _ = ctrl.stop(Duration::from_secs(3)).await;

    // persist verdicts BY COORDINATE (indices shift per regen, same
    // as the costs.json convention): navgen drops any link whose
    // endpoints match a failed pair. Merged, not overwritten - the
    // verdict file grows across sweeps.
    let vpath = cfg.root.join("src").join(format!("argus_nav_{map}.probe.json"));
    let mut doc: serde_json::Value = std::fs::read_to_string(&vpath)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| serde_json::json!({"failed": [], "passed": []}));
    let push_pair = |arr: &mut Vec<serde_json::Value>, from: [f32; 3], to: [f32; 3]| {
        let pair = serde_json::json!([from, to]);
        if !arr.contains(&pair) {
            arr.push(pair);
        }
    };
    {
        let failed = doc["failed"].as_array().cloned().unwrap_or_default();
        let mut failed = failed;
        for v in &report.failed_links {
            push_pair(&mut failed, v.from, v.to);
        }
        doc["failed"] = serde_json::Value::Array(failed);
    }
    if let Ok(s) = serde_json::to_string_pretty(&doc) {
        let _ = std::fs::write(&vpath, s);
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    /// Live integration: spawn the lab's own dedicated engine, connect
    /// as a real client, complete the signon dance, and require the
    /// world to flow - level name, roster names, our own entity
    /// moving through svc updates. Machine-local: skips without the
    /// engine. Binds the engine port: never run during a live match.
    #[tokio::test]
    async fn netclient_connects_and_sees_the_world_if_engine_present() {
        if !cfg!(windows) {
            return;
        }
        // recover from poison: a failed engine test elsewhere must not
        // cascade into this one (each reports on its own merits)
        let _gate = crate::engine::ENGINE_TEST_LOCK
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        let mut env = std::collections::HashMap::new();
        env.insert("ARGUS_ROOT".into(), root.display().to_string());
        let Ok(cfg) = crate::config::load_for_reads_from(&env, &root) else {
            return;
        };
        if !cfg.engine.exists() {
            return;
        }
        let mut ctrl = crate::match_ctrl::MatchCtrl::default();
        if ctrl
            .start(&cfg, "dm4", Some(40), Some("probe_netclient_test"), None, Some(1), None)
            .await
            .is_err()
        {
            return; // port busy: not this test's fault
        }
        tokio::time::sleep(std::time::Duration::from_secs(4)).await;
        let report = tokio::task::spawn_blocking(|| {
            crate::netclient::observe("127.0.0.1", 26000, 6.0, "labprobe")
        })
        .await
        .expect("join");
        let _ = ctrl.stop(std::time::Duration::from_secs(3)).await;
        let report = report.expect("client must connect to the lab engine");
        assert_eq!(report.protocol, 15, "lab matches are protocol 15");
        assert!(report.signon >= 3, "signon dance must complete, got {}", report.signon);
        assert!(
            !report.names.is_empty(),
            "scoreboard names must arrive (bots write fake slots)"
        );
        assert!(
            report.total_ents > 10,
            "entity world must flow, got {}",
            report.total_ents
        );
    }
}
