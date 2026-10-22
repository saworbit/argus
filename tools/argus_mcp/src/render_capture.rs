//! Render a recorded protocol-15 POV with the engine's own PNG command.
//! Assets and settings live in a fresh private directory, never the user's game.
use crate::{config::Config, netclient::NetClient};
use serde::Serialize;
use std::path::Path;
use std::time::{Duration, Instant};
use tokio::io::AsyncReadExt;

fn signed_on(world: &crate::netclient::ClientWorld) -> bool {
    // Protocol 15 sends signon 3, then the first entity update completes
    // client startup. Signon 4 is a client state, not a fourth server ack.
    world.signon >= 3 && world.ents.get(&world.my_ent).is_some_and(|e| e.updates > 0)
}

fn tracking_slot(world: &crate::netclient::ClientWorld, slot: u8) -> bool {
    let Some(eye) = world.ents.get(&world.my_ent) else {
        return false;
    };
    // Merely sharing an origin still renders the bot through the camera.
    // The protocol view entity itself must be that bot to hide its model.
    Some(eye.model) == world.player_model && eye.skin == slot + 1 && eye.updates > 0
}

fn impulse(client: &mut NetClient, command: u8, expected: &str) -> Result<String, String> {
    let offset = client.world.prints.len();
    client.set_impulse(command);
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        client.pump(Duration::from_millis(50));
        let text: String = client.world.prints[offset..]
            .iter()
            .map(|(_, s)| s.as_str())
            .collect();
        if text.contains(expected) {
            return Ok(text);
        }
        if client.world.disconnected || Instant::now() >= deadline {
            return Err(format!(
                "camera impulse {command} missing acknowledgement {expected}"
            ));
        }
    }
}

/// Record an ordinary match through the stock spectator controls. Every
/// impulse waits for its client-visible acknowledgement before proceeding.
pub fn record_bot(cfg: &Config, name: &str, slot: u8, seconds: f32) -> Result<String, String> {
    if !crate::paths::valid_run_name(name)
        || name == "."
        || name == ".."
        || slot > 3
        || !seconds.is_finite()
        || !(2.0..=185.0).contains(&seconds)
    {
        return Err("record-pov needs a new name, roster slot 0..3 and 2..185 seconds".into());
    }
    let dir = cfg.runs.join("demos");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("{name}.dem"));
    let mut client = NetClient::connect("127.0.0.1", 26000, "labcamera")?;
    let result = (|| {
        client.start_recording(&path)?;
        let deadline = Instant::now() + Duration::from_secs(8);
        while !signed_on(&client.world) && Instant::now() < deadline {
            client.pump(Duration::from_millis(50));
        }
        if !signed_on(&client.world) {
            return Err("camera client did not complete signon".into());
        }
        impulse(&mut client, 210, "ArgusCam Active")?;
        for expected in ["Focus / Duel", "FreeLook", "Orbit", "1st-Person Bot POV"] {
            impulse(&mut client, 211, expected)?;
        }
        let mut selected = false;
        for _ in 0..4 {
            impulse(&mut client, 212, "Tracking Target:")?;
            client.pump(Duration::from_millis(300));
            // Late clients need not receive earlier fake-scoreboard names.
            // The actual protocol view entity identifies the roster slot.
            if tracking_slot(&client.world, slot) {
                selected = true;
                break;
            }
        }
        if !selected {
            return Err(format!("camera could not select living roster slot {slot}"));
        }
        client.pump(Duration::from_secs_f32(seconds));
        if client.world.disconnected {
            return Err("camera disconnected before recording completed".into());
        }
        client
            .finish_recording()?
            .ok_or("camera demo was not recorded".into())
    })();
    client.disconnect();
    result
}

/// Rendered PNG paths and input identities; times are scheduled playback steps.
#[derive(Debug, Serialize)]
pub struct Capture {
    pub demo: String,
    pub demo_md5: String,
    pub engine_md5: String,
    /// Sorted staged inputs, using paths relative to the isolated basedir.
    pub assets: Vec<AssetIdentity>,
    /// MD5 of the compact JSON serialization of `assets` in the listed order.
    pub assets_md5: String,
    pub directory: String,
    pub frames: Vec<String>,
    pub scheduled_seconds: Vec<f64>,
    pub note: &'static str,
}

/// Content identity only. Asset bytes and machine-local source paths stay local.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct AssetIdentity {
    pub path: String,
    pub bytes: u64,
    pub md5: String,
}

/// Check finite capture bounds and require every frame before the demo's end.
pub fn validate(start: f64, count: u32, interval: f64, duration: f64) -> Result<(), String> {
    validate_frames(start, count, interval, duration, 12)
}

fn validate_frames(
    start: f64,
    count: u32,
    interval: f64,
    duration: f64,
    max: u32,
) -> Result<(), String> {
    if !start.is_finite()
        || !interval.is_finite()
        || !duration.is_finite()
        || !(0.5..=120.0).contains(&start)
        || !(1..=max).contains(&count)
        || !(0.1..=5.0).contains(&interval)
        || start + (count - 1) as f64 * interval >= duration - 0.15
    {
        return Err(format!(
            "capture needs start 0.5..120s, 1..{max} frames, interval 0.1..5s, all before demo end"
        ));
    }
    Ok(())
}

fn copy_tree(from: &Path, to: &Path) -> Result<(), String> {
    if std::fs::symlink_metadata(from)
        .map_err(|e| e.to_string())?
        .is_symlink()
    {
        return Err("capture assets must not contain symlinks".into());
    }
    std::fs::create_dir_all(to).map_err(|e| e.to_string())?;
    for entry in std::fs::read_dir(from).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let ty = entry.file_type().map_err(|e| e.to_string())?;
        if ty.is_symlink() {
            return Err("capture assets must not contain symlinks".into());
        }
        let dest = to.join(entry.file_name());
        if ty.is_dir() {
            copy_tree(&entry.path(), &dest)?;
        } else if ty.is_file() {
            // Independent bytes keep source writes out of the running renderer.
            std::fs::copy(entry.path(), &dest).map_err(|e| e.to_string())?;
        } else {
            return Err("capture assets must be regular files or directories".into());
        }
    }
    Ok(())
}

fn md5(path: &Path) -> Result<String, String> {
    let mut file = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let mut digest = md5::Context::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = std::io::Read::read(&mut file, &mut buffer).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        digest.consume(&buffer[..n]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn stage_paks(from: &Path, to: &Path) -> Result<(), String> {
    if std::fs::symlink_metadata(from)
        .map_err(|e| e.to_string())?
        .is_symlink()
    {
        return Err("capture assets must not contain symlinks".into());
    }
    for entry in std::fs::read_dir(from).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        if path
            .extension()
            .is_some_and(|e| e.eq_ignore_ascii_case("pak"))
        {
            if !entry.file_type().map_err(|e| e.to_string())?.is_file() {
                return Err("capture PAK assets must be regular files, not symlinks".into());
            }
            let dest = to.join(entry.file_name());
            std::fs::copy(&path, dest).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

fn asset_inputs(id1: &Path, game: &Path) -> Result<Vec<AssetIdentity>, String> {
    fn visit(path: &Path, label: &str, out: &mut Vec<AssetIdentity>) -> Result<(), String> {
        let meta = std::fs::symlink_metadata(path).map_err(|e| e.to_string())?;
        if meta.is_symlink() {
            return Err("capture assets must not contain symlinks".into());
        }
        if meta.is_dir() {
            for entry in std::fs::read_dir(path).map_err(|e| e.to_string())? {
                let entry = entry.map_err(|e| e.to_string())?;
                let name = entry.file_name();
                let name = name.to_str().ok_or("asset path is not UTF-8")?;
                visit(&entry.path(), &format!("{label}/{name}"), out)?;
            }
        } else if meta.is_file() {
            out.push(AssetIdentity {
                path: label.into(),
                bytes: meta.len(),
                md5: md5(path)?,
            });
        } else {
            return Err("capture assets must be regular files or directories".into());
        }
        Ok(())
    }
    let mut assets = Vec::new();
    for (base, label) in [(id1, "id1"), (game, "capture")] {
        if std::fs::symlink_metadata(base)
            .map_err(|e| e.to_string())?
            .is_symlink()
        {
            return Err("capture assets must not contain symlinks".into());
        }
        for entry in std::fs::read_dir(base).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            if entry
                .path()
                .extension()
                .is_some_and(|s| s.eq_ignore_ascii_case("pak"))
            {
                if !entry.file_type().map_err(|e| e.to_string())?.is_file() {
                    return Err("capture PAK assets must be regular files, not symlinks".into());
                }
                let name = entry.file_name();
                visit(
                    &entry.path(),
                    &format!(
                        "{label}/{}",
                        name.to_str().ok_or("asset path is not UTF-8")?
                    ),
                    &mut assets,
                )?;
            }
        }
    }
    for name in ["maps", "progs", "sound", "gfx"] {
        let path = game.join(name);
        match std::fs::symlink_metadata(&path) {
            Ok(_) => visit(&path, &format!("capture/{name}"), &mut assets)?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.to_string()),
        }
    }
    assets.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(assets)
}

fn assets_md5(assets: &[AssetIdentity]) -> Result<String, String> {
    let bytes = serde_json::to_vec(assets).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", md5::compute(bytes)))
}

fn verify_assets(id1: &Path, game: &Path, expected: &[AssetIdentity]) -> Result<(), String> {
    if asset_inputs(id1, game)? != expected {
        return Err("asset inputs changed during capture".into());
    }
    Ok(())
}

fn script(start: f64, count: u32, interval: f64) -> String {
    // wait yields one rendered frame. Playback uses a fixed 0.05s step;
    // this changes playback speed only, never the recorded simulation.
    // Zero still draws notifications printed at this exact realtime value,
    // including the screenshot command's synchronous screen refresh. Negative
    // lifetime hides even zero-age text; qconsole.log still keeps every message.
    let mut s = String::from("host_framerate 0.05\nviewsize 100\nfov 90\ngamma 0.7\nscr_conspeed 100000\ncon_notifytime -1\nplaydemo capture\n");
    for i in 0..count {
        let frames = if i == 0 {
            (start / 0.05).round() as usize
        } else {
            (interval / 0.05).round() as usize
        };
        for _ in 0..frames {
            s.push_str("wait\n");
        }
        s.push_str(&format!("screenshot png\necho ARGUS_CAPTURE frame {i}\n"));
    }
    s.push_str("disconnect\ntoggleconsole\nquit\n");
    s
}

fn verify_png(path: &Path) -> Result<(), String> {
    let b = std::fs::read(path).map_err(|e| format!("missing frame {}: {e}", path.display()))?;
    if b.len() < 44
        || &b[..8] != b"\x89PNG\r\n\x1a\n"
        || !b.ends_with(b"\x00\x00\x00\x00IEND\xae\x42\x60\x82")
        || u32::from_be_bytes(b[16..20].try_into().unwrap()) != 640
        || u32::from_be_bytes(b[20..24].try_into().unwrap()) != 480
    {
        return Err(format!("invalid 640x480 engine PNG: {}", path.display()));
    }
    Ok(())
}

async fn wait_render(
    child: &mut tokio::process::Child,
    deadline: Duration,
) -> Result<std::process::ExitStatus, String> {
    match tokio::time::timeout(deadline, child.wait()).await {
        Ok(status) => status.map_err(|e| e.to_string()),
        Err(_) => {
            child
                .kill()
                .await
                .map_err(|e| format!("capture timeout; kill: {e}"))?;
            Err("render client timed out and was reaped".into())
        }
    }
}

fn verify_log(log: &str, count: u32) -> Result<(), String> {
    if !log.contains("Playing demo from capture.dem.")
        || !log.contains("Using protocol 15")
        || ["host_error", "sys_error", "mod_loadmodel:", "error:"]
            .iter()
            .any(|s| log.to_ascii_lowercase().contains(s))
    {
        return Err("renderer did not load the recorded world cleanly".into());
    }
    for i in 0..count {
        if !log
            .lines()
            .any(|l| l.trim() == format!("ARGUS_CAPTURE frame {i}"))
        {
            return Err(format!("missing engine capture acknowledgement {i}"));
        }
    }
    Ok(())
}

/// Replay a complete protocol-15 demo in an isolated asset directory.
/// Return validated PNGs and a manifest, or an error after bounded child cleanup.
pub async fn capture(
    cfg: &Config,
    demo_name: &str,
    start: f64,
    count: u32,
    interval: f64,
) -> Result<Capture, String> {
    capture_frames(cfg, demo_name, start, count, interval, 12).await
}

async fn capture_frames(
    cfg: &Config,
    demo_name: &str,
    start: f64,
    count: u32,
    interval: f64,
    max: u32,
) -> Result<Capture, String> {
    let stem = demo_name.strip_suffix(".dem").unwrap_or(demo_name);
    if !crate::paths::valid_run_name(stem) || stem == "." || stem == ".." {
        return Err("demo must be a local demo stem, not a path".into());
    }
    let demo_path = crate::demo::resolve_demo(cfg, stem)?;
    let demo_md5 = md5(&demo_path)?;
    let demo = crate::demo::read_demo(&demo_path)?;
    if demo.brief.protocol != 15 || demo.brief.truncated {
        return Err("capture requires a complete protocol-15 demo".into());
    }
    validate_frames(start, count, interval, demo.brief.duration_sec, max)?;
    let engine_md5 = md5(&cfg.engine)?;
    let source_id1 = cfg.basedir.join("id1");
    let source_game = cfg.basedir.join(&cfg.game);
    let assets = asset_inputs(&source_id1, &source_game)?;
    let parent = cfg.root.join("backups").join("render_capture");
    std::fs::create_dir_all(&parent).map_err(|e| e.to_string())?;
    // create_dir, not create_dir_all: an existing output can never pass as
    // a new capture. Nanoseconds plus PID also isolate concurrent calls.
    let dir = parent.join(format!(
        "{}-{}",
        chrono::Utc::now().timestamp_nanos_opt().unwrap_or_default(),
        std::process::id()
    ));
    std::fs::create_dir(&dir).map_err(|e| e.to_string())?;
    let game = dir.join("capture");
    std::fs::create_dir(&game).map_err(|e| e.to_string())?;
    let id1 = dir.join("id1");
    std::fs::create_dir(&id1).map_err(|e| e.to_string())?;
    stage_paks(&source_id1, &id1)?;
    stage_paks(&source_game, &game)?;
    for name in ["maps", "progs", "sound", "gfx"] {
        let from = cfg.basedir.join(&cfg.game).join(name);
        if from.is_dir() {
            copy_tree(&from, &game.join(name))?;
        }
    }
    verify_assets(&id1, &game, &assets)?;
    verify_assets(&source_id1, &source_game, &assets)?;
    // Copy mutable outputs, never link a config or the input demo.
    std::fs::copy(&demo_path, game.join("capture.dem")).map_err(|e| e.to_string())?;
    if md5(&game.join("capture.dem"))? != demo_md5 {
        return Err("input demo changed while staging capture".into());
    }
    std::fs::write(game.join("capture.cfg"), script(start, count, interval))
        .map_err(|e| e.to_string())?;
    let mut command = tokio::process::Command::new(&cfg.engine);
    command
        .current_dir(&dir)
        .args([
            "-window",
            "-width",
            "640",
            "-height",
            "480",
            "-nosound",
            "-nocdaudio",
            "-nojoy",
            "-condebug",
            "-basedir",
        ])
        .arg(&dir)
        .args(["-game", "capture", "+exec", "capture.cfg"])
        .env("SDL_VIDEO_WINDOW_POS", "-10000,-10000")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flash
    let mut child = command.spawn().map_err(|e| format!("render client: {e}"))?;
    let status = wait_render(&mut child, Duration::from_secs(45))
        .await
        .map_err(|e| format!("{e}; diagnostics in {}", dir.display()))?;
    if !status.success() {
        return Err(format!(
            "render client exited {status}; diagnostics in {}",
            dir.display()
        ));
    }
    let bytes = std::fs::read(dir.join("qconsole.log")).map_err(|e| format!("capture log: {e}"))?;
    let log = String::from_utf8_lossy(&bytes);
    verify_log(&log, count)?;
    let mut frames = Vec::new();
    for i in 0..count {
        let p = game.join(format!("spasm{i:04}.png"));
        verify_png(&p)?;
        frames.push(p.display().to_string());
    }
    if md5(&demo_path)? != demo_md5 || md5(&game.join("capture.dem"))? != demo_md5 {
        return Err("input demo changed during capture".into());
    }
    if md5(&cfg.engine)? != engine_md5 {
        return Err("render engine changed during capture".into());
    }
    verify_assets(&id1, &game, &assets)?;
    verify_assets(&source_id1, &source_game, &assets)?;
    let assets_md5 = assets_md5(&assets)?;
    let result = Capture { demo: stem.into(), demo_md5, engine_md5, assets, assets_md5, directory: dir.display().to_string(), frames,
        scheduled_seconds: (0..count).map(|i| (start / 0.05).round() * 0.05 + i as f64 * (interval / 0.05).round() * 0.05).collect(),
        note: "Real engine PNGs of the recorded POV. Times are scheduled playback steps, not exact event timestamps. PVS and the recorded viewpoint limit visibility. Playback is fixed-step; use the source tape for simulation rates." };
    std::fs::write(
        dir.join("manifest.json"),
        serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(result)
}

/// Bounded video plus its ordered source-frame evidence and playback timeline.
#[derive(Debug, Serialize)]
pub struct VideoCapture {
    /// Ordered PNG sources, scheduled demo times and demo/engine identities.
    pub capture: Capture,
    /// Absolute path to the verified, newly published VP9 WebM.
    pub video_path: String,
    /// MD5 of the published WebM bytes.
    pub video_md5: String,
    /// Playback speed multiplier; 0.5 means half speed.
    pub playback_rate: f64,
    /// Verified playback frames/sec: ten source samples/sec times playback_rate.
    pub output_fps: f64,
    /// Decoded frame count divided by output_fps, after source-duration rounding.
    pub duration_seconds: f64,
    /// Ordered MD5 hashes of decoded 640x480 YUV420 frames, matching the sources.
    pub decoded_frame_md5: Vec<String>,
    /// The resolved FFmpeg bytes, version/build output and actual VP9 settings.
    pub encoder: EncoderIdentity,
}

#[derive(Debug, Serialize)]
pub struct EncoderIdentity {
    pub executable_md5: String,
    pub version: String,
    /// FFmpeg output options applied to the encoded video.
    pub settings: Vec<String>,
}

const VP9_SETTINGS: &[&str] = &[
    "-c:v",
    "libvpx-vp9",
    "-lossless",
    "1",
    "-deadline",
    "realtime",
    "-cpu-used",
    "8",
    "-pix_fmt",
    "yuv420p",
    "-threads",
    "1",
    "-f",
    "webm",
];

fn video_frames(duration: f64, rate: f64) -> Result<u32, String> {
    if !duration.is_finite()
        || !(0.2..=12.0).contains(&duration)
        || !rate.is_finite()
        || !(0.1..=4.0).contains(&rate)
    {
        return Err("video needs duration 0.2..12s and playback rate 0.1..4".into());
    }
    Ok((duration * 10.0).round() as u32)
}

fn encoder(path: &Path) -> tokio::process::Command {
    let mut command = tokio::process::Command::new(path);
    command
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .kill_on_drop(true);
    #[cfg(windows)]
    command.creation_flags(0x0800_0000);
    command
}

fn resolve_encoder() -> Result<std::path::PathBuf, String> {
    let name = format!("ffmpeg{}", std::env::consts::EXE_SUFFIX);
    for dir in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        let path = dir.join(&name);
        if path.is_file() {
            return path.canonicalize().map_err(|e| format!("FFmpeg path: {e}"));
        }
    }
    Err(
        "video export requires FFmpeg with libvpx-vp9 on PATH; PNG capture remains available"
            .into(),
    )
}

async fn preflight_output(command: &mut tokio::process::Command) -> Result<String, String> {
    async fn read_output(reader: impl tokio::io::AsyncRead + Unpin) -> Result<String, String> {
        let mut bytes = Vec::new();
        reader
            .take(65537)
            .read_to_end(&mut bytes)
            .await
            .map_err(|e| e.to_string())?;
        if bytes.len() > 65536 {
            return Err("FFmpeg preflight output exceeded 64 KiB".into());
        }
        Ok(String::from_utf8_lossy(&bytes).into_owned())
    }
    let mut child = command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("FFmpeg preflight: {e}"))?;
    let stdout = child.stdout.take().ok_or("missing FFmpeg stdout")?;
    let stderr = child.stderr.take().ok_or("missing FFmpeg stderr")?;
    let (status, stdout, stderr) = tokio::join!(
        wait_render(&mut child, Duration::from_secs(5)),
        read_output(stdout),
        read_output(stderr)
    );
    let text = format!("{}{}", stdout?, stderr?);
    if !status?.success() {
        return Err(format!("FFmpeg preflight failed: {text}"));
    }
    Ok(text)
}

fn verify_encoder(path: &Path, identity: &EncoderIdentity) -> Result<(), String> {
    if md5(path)? != identity.executable_md5 {
        return Err("FFmpeg executable changed during video capture".into());
    }
    Ok(())
}

async fn preflight_encoder(path: &Path) -> Result<EncoderIdentity, String> {
    let executable_md5 = md5(path)?;
    let version = preflight_output(encoder(path).arg("-version")).await?;
    // Prove the actual codec and settings work, with no capture directory or
    // renderer. Help and version commands can succeed without an encoder.
    preflight_output(
        encoder(path)
            .args([
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=16x16:r=1",
                "-frames:v",
                "1",
            ])
            .args(VP9_SETTINGS)
            .arg("-"),
    )
    .await
    .map_err(|e| {
        format!("video export requires working libvpx-vp9: {e}; PNG capture remains available")
    })?;
    let identity = EncoderIdentity {
        executable_md5,
        version,
        settings: VP9_SETTINGS.iter().map(|s| (*s).into()).collect(),
    };
    verify_encoder(path, &identity)?;
    Ok(identity)
}

async fn encode_step(command: &mut tokio::process::Command, dir: &Path) -> Result<(), String> {
    let log = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("encoder.log"))
        .map_err(|e| e.to_string())?;
    let mut child = command
        .stderr(log)
        .spawn()
        .map_err(|e| format!("FFmpeg: {e}"))?;
    let status = wait_render(&mut child, Duration::from_secs(45)).await?;
    if !status.success() {
        return Err(format!(
            "FFmpeg exited {status}; diagnostics in {}",
            dir.display()
        ));
    }
    Ok(())
}

fn frame_hashes(text: &str, count: u32, fps: f64) -> Result<Vec<String>, String> {
    let timebase = text
        .lines()
        .find_map(|line| line.strip_prefix("#tb 0: "))
        .and_then(|s| s.split_once('/'))
        .and_then(|(n, d)| Some((n.parse::<f64>().ok()?, d.parse::<f64>().ok()?)))
        .map(|(n, d)| d / n)
        .ok_or("video verification found no timebase")?;
    if !timebase.is_finite() || (timebase - fps).abs() > 0.000001 {
        return Err("video verification found the wrong playback rate".into());
    }
    let mut hashes = Vec::new();
    for line in text
        .lines()
        .filter(|s| !s.starts_with('#') && !s.trim().is_empty())
    {
        let fields: Vec<_> = line.split(',').map(str::trim).collect();
        let i = hashes.len().to_string();
        if fields.len() != 6
            || fields[0] != "0"
            || fields[1] != i
            || fields[2] != i
            || fields[3] != "1"
            || fields[4] != "460800"
            || fields[5].len() != 32
            || !fields[5].bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err("video verification found an invalid frame or playback timestamp".into());
        }
        hashes.push(fields[5].to_string());
    }
    if hashes.len() != count as usize {
        return Err("video verification found a missing or extra frame".into());
    }
    Ok(hashes)
}

/// Export a recorded POV at 10 source frames/sec, with explicit playback speed.
/// `start` is 0.5..120 demo seconds, rounded to the renderer's 0.05-second step.
/// `duration` is 0.2..12 source seconds, rounded to 0.1 seconds; `rate` is a
/// 0.1..4 playback multiplier. Every source sample must precede the demo's end.
/// FFmpeg with libvpx-vp9 is required on PATH; PNG capture needs no encoder.
/// A bounded one-frame VP9 preflight completes before the renderer starts.
/// PNG-to-YUV420 conversion precedes lossless encoding. Verify decoded frame
/// order, hashes and timing before publishing a fresh WebM and video manifest.
/// Manifests include staged asset digests, the FFmpeg build and codec settings.
/// Input mutation fails capture. Failures after staging retain diagnostics.
pub async fn capture_video(
    cfg: &Config,
    demo: &str,
    start: f64,
    duration: f64,
    rate: f64,
) -> Result<VideoCapture, String> {
    let path = resolve_encoder()?;
    capture_video_with_encoder(cfg, demo, start, duration, rate, &path).await
}

async fn capture_video_with_encoder(
    cfg: &Config,
    demo: &str,
    start: f64,
    duration: f64,
    rate: f64,
    encoder_path: &Path,
) -> Result<VideoCapture, String> {
    let count = video_frames(duration, rate)?;
    let mut encoder_identity = preflight_encoder(encoder_path).await?;
    let capture = capture_frames(cfg, demo, start, count, 0.1, 120).await?;
    verify_encoder(encoder_path, &encoder_identity)?;
    let dir = std::path::PathBuf::from(&capture.directory);
    let fps = (10.0 * rate).to_string();
    let frames = count.to_string();
    let input = dir.join("capture/spasm%04d.png");
    let partial = dir.join("clip.part.webm");
    let source_hashes = dir.join("source.framemd5");
    let decoded_hashes = dir.join("decoded.framemd5");
    encode_step(
        encoder(encoder_path)
            .args([
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-framerate",
                &fps,
                "-start_number",
                "0",
                "-i",
            ])
            .arg(&input)
            .args([
                "-frames:v",
                &frames,
                "-vf",
                "format=yuv420p",
                "-threads",
                "1",
                "-f",
                "framemd5",
            ])
            .arg(&source_hashes),
        &dir,
    )
    .await?;
    verify_encoder(encoder_path, &encoder_identity)?;
    encode_step(
        encoder(encoder_path)
            .args([
                "-v",
                "error",
                "-nostdin",
                "-n",
                "-framerate",
                &fps,
                "-start_number",
                "0",
                "-i",
            ])
            .arg(&input)
            .args(["-frames:v", &frames])
            .args(VP9_SETTINGS)
            .arg(&partial),
        &dir,
    )
    .await?;
    verify_encoder(encoder_path, &encoder_identity)?;
    encode_step(
        encoder(encoder_path)
            .args(["-v", "error", "-nostdin", "-n", "-i"])
            .arg(&partial)
            .args([
                "-map",
                "0:v:0",
                "-fps_mode",
                "passthrough",
                "-pix_fmt",
                "yuv420p",
                "-threads",
                "1",
                "-f",
                "framemd5",
            ])
            .arg(&decoded_hashes),
        &dir,
    )
    .await?;
    verify_encoder(encoder_path, &encoder_identity)?;
    let read_hashes = |p: &Path| -> Result<Vec<String>, String> {
        frame_hashes(
            &std::fs::read_to_string(p).map_err(|e| e.to_string())?,
            count,
            10.0 * rate,
        )
    };
    let expected = read_hashes(&source_hashes)?;
    let decoded = read_hashes(&decoded_hashes)?;
    if expected != decoded {
        return Err("decoded video frames differ from the ordered source frames".into());
    }
    encoder_identity
        .settings
        .extend(["-framerate".into(), fps, "-frames:v".into(), frames]);
    let path = dir.join("clip.webm");
    let result = VideoCapture {
        video_md5: md5(&partial)?,
        video_path: path.display().to_string(),
        capture,
        playback_rate: rate,
        output_fps: 10.0 * rate,
        duration_seconds: count as f64 / (10.0 * rate),
        decoded_frame_md5: decoded,
        encoder: encoder_identity,
    };
    publish_video(
        &dir,
        &serde_json::to_vec_pretty(&result).map_err(|e| e.to_string())?,
    )?;
    Ok(result)
}

fn publish_video(dir: &Path, manifest: &[u8]) -> Result<(), String> {
    use std::io::Write;
    let partial_manifest = dir.join("video_manifest.part.json");
    std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&partial_manifest)
        .and_then(|mut f| f.write_all(manifest))
        .map_err(|e| e.to_string())?;
    let path = dir.join("clip.webm");
    // Only complete verified outputs get final names. If the manifest cannot
    // be published, roll back our video link and retain diagnostic partials.
    std::fs::hard_link(dir.join("clip.part.webm"), &path).map_err(|e| e.to_string())?;
    if let Err(error) = std::fs::hard_link(&partial_manifest, dir.join("video_manifest.json")) {
        std::fs::remove_file(&path)
            .map_err(|e| format!("manifest: {error}; video rollback: {e}"))?;
        return Err(format!("video manifest: {error}"));
    }
    Ok(())
}

#[cfg(test)]
#[allow(clippy::field_reassign_with_default)]
mod tests {
    use super::*;

    #[test]
    fn staged_assets_are_identified_and_isolated_from_source_writes() {
        let dir = crate::test_support::TestDir::new("capture-inputs").unwrap();
        let source = dir.path().join("source");
        let staged = dir.path().join("staged");
        for base in [&source, &staged] {
            std::fs::create_dir_all(base.join("id1")).unwrap();
            std::fs::create_dir_all(base.join("capture/progs")).unwrap();
        }
        std::fs::write(source.join("id1/pak0.pak"), b"base").unwrap();
        std::fs::write(source.join("capture/pak0.pak"), b"mod").unwrap();
        std::fs::write(source.join("capture/progs/player.mdl"), b"skin one").unwrap();
        let expected = asset_inputs(&source.join("id1"), &source.join("capture")).unwrap();
        stage_paks(&source.join("id1"), &staged.join("id1")).unwrap();
        stage_paks(&source.join("capture"), &staged.join("capture")).unwrap();
        copy_tree(&source.join("capture/progs"), &staged.join("capture/progs")).unwrap();
        assert_eq!(
            expected,
            asset_inputs(&staged.join("id1"), &staged.join("capture")).unwrap()
        );
        assert_eq!(
            expected.iter().map(|a| a.path.as_str()).collect::<Vec<_>>(),
            [
                "capture/pak0.pak",
                "capture/progs/player.mdl",
                "id1/pak0.pak"
            ]
        );
        let identity = assets_md5(&expected).unwrap();
        std::fs::write(source.join("capture/pak0.pak"), b"new mod").unwrap();
        assert_eq!(
            std::fs::read(staged.join("capture/pak0.pak")).unwrap(),
            b"mod"
        );
        assert!(verify_assets(&source.join("id1"), &source.join("capture"), &expected).is_err());
        let changed = asset_inputs(&source.join("id1"), &source.join("capture")).unwrap();
        assert_ne!(identity, assets_md5(&changed).unwrap());
        std::fs::write(staged.join("capture/progs/player.mdl"), b"skin two").unwrap();
        assert!(verify_assets(&staged.join("id1"), &staged.join("capture"), &expected).is_err());
        std::fs::write(staged.join("capture/progs/player.mdl"), b"skin one").unwrap();
        std::fs::remove_file(staged.join("id1/pak0.pak")).unwrap();
        assert!(verify_assets(&staged.join("id1"), &staged.join("capture"), &expected).is_err());
    }

    #[test]
    fn changed_encoder_bytes_cannot_keep_the_preflight_identity() {
        let dir = crate::test_support::TestDir::new("encoder-identity").unwrap();
        let path = dir.path().join("ffmpeg");
        std::fs::write(&path, b"build one").unwrap();
        let identity = EncoderIdentity {
            executable_md5: md5(&path).unwrap(),
            version: "build one".into(),
            settings: Vec::new(),
        };
        verify_encoder(&path, &identity).unwrap();
        std::fs::write(&path, b"build two").unwrap();
        assert!(verify_encoder(&path, &identity)
            .unwrap_err()
            .contains("changed"));
    }

    #[test]
    fn manifest_failure_rolls_back_only_the_new_video() {
        let dir = crate::test_support::TestDir::new("video-publication").unwrap();
        std::fs::write(dir.path().join("clip.part.webm"), b"verified video").unwrap();
        std::fs::write(dir.path().join("video_manifest.json"), b"existing").unwrap();
        assert!(publish_video(dir.path(), b"new manifest").is_err());
        assert!(!dir.path().join("clip.webm").exists());
        assert_eq!(
            std::fs::read(dir.path().join("video_manifest.json")).unwrap(),
            b"existing"
        );
        assert!(dir.path().join("clip.part.webm").exists());
        std::fs::remove_file(dir.path().join("video_manifest.json")).unwrap();
        std::fs::remove_file(dir.path().join("video_manifest.part.json")).unwrap();
        publish_video(dir.path(), b"new manifest").unwrap();
        assert_eq!(
            std::fs::read(dir.path().join("clip.webm")).unwrap(),
            b"verified video"
        );
        assert_eq!(
            std::fs::read(dir.path().join("video_manifest.json")).unwrap(),
            b"new manifest"
        );
    }

    #[tokio::test]
    async fn missing_vp9_fails_before_demo_lookup_or_capture_output() {
        let dir = crate::test_support::TestDir::new("capture-no-vp9").unwrap();
        let source = dir.path().join("encoder.rs");
        let executable = dir
            .path()
            .join(format!("ffmpeg{}", std::env::consts::EXE_SUFFIX));
        // A real child that passes the old startup check but has no encoder.
        std::fs::write(
            &source,
            r#"fn main() {
            if std::env::args().nth(1).as_deref() == Some("-version") {
                println!("ffmpeg fixture without libvpx-vp9");
            } else { eprintln!("Unknown encoder libvpx-vp9"); std::process::exit(1); }
        }"#,
        )
        .unwrap();
        assert!(std::process::Command::new("rustc")
            .arg(&source)
            .arg("-o")
            .arg(&executable)
            .status()
            .unwrap()
            .success());
        let mut cfg = crate::config::load_for_reads_from(
            &std::collections::HashMap::from([(
                "ARGUS_ROOT".into(),
                dir.path().display().to_string(),
            )]),
            dir.path(),
        )
        .unwrap();
        cfg.engine = dir.path().join("renderer-must-not-start");
        let error = capture_video_with_encoder(&cfg, "absent", 0.5, 0.2, 1.0, &executable)
            .await
            .unwrap_err();
        assert!(error.contains("libvpx-vp9"), "{error}");
        assert!(error.contains("Unknown encoder"), "{error}");
        assert!(
            !cfg.root.join("backups").exists(),
            "failed preflight created capture output"
        );
    }

    #[test]
    fn mod_paks_keep_names_and_bytes_without_copying_configs() {
        let temp = std::env::temp_dir().canonicalize().unwrap();
        let dir = temp.join(format!(
            "argus-capture-paks-{}-{}",
            std::process::id(),
            chrono::Utc::now().timestamp_nanos_opt().unwrap()
        ));
        let from = dir.join("mod");
        let to = dir.join("capture");
        std::fs::create_dir_all(&from).unwrap();
        std::fs::create_dir(&to).unwrap();
        for name in [
            "pak0.pak",
            "pak1.pak",
            "pak2.PAK",
            "config.cfg",
            "qconsole.log",
        ] {
            std::fs::write(from.join(name), name.as_bytes()).unwrap();
        }
        stage_paks(&from, &to).unwrap();
        for name in ["pak0.pak", "pak1.pak", "pak2.PAK"] {
            assert_eq!(std::fs::read(to.join(name)).unwrap(), name.as_bytes());
        }
        assert!(!to.join("config.cfg").exists());
        assert!(!to.join("qconsole.log").exists());
        assert!(dir.is_absolute() && dir.parent() == Some(temp.as_path()));
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn video_verification_rejects_missing_reordered_and_retimed_frames() {
        let header = "#tb 0: 1/5\n";
        let a = "0, 0, 0, 1, 460800, 0123456789abcdef0123456789abcdef\n";
        let b = "0, 1, 1, 1, 460800, abcdef0123456789abcdef0123456789\n";
        assert_eq!(
            frame_hashes(&format!("{header}{a}{b}"), 2, 5.0)
                .unwrap()
                .len(),
            2
        );
        assert!(frame_hashes(&format!("{header}{a}"), 2, 5.0).is_err());
        assert!(frame_hashes(&format!("{header}{b}{a}"), 2, 5.0).is_err());
        assert!(frame_hashes(&format!("{header}{}", a.replace(", 1,", ", 2,")), 1, 5.0).is_err());
        assert!(frame_hashes(&format!("{header}{a}"), 1, 10.0).is_err());
        assert!(video_frames(f64::NAN, 1.0).is_err());
        assert!(video_frames(13.0, 1.0).is_err());
        assert!(video_frames(1.0, 0.0).is_err());
        assert_eq!(video_frames(2.4, 0.5).unwrap(), 24);
    }

    #[tokio::test]
    #[allow(clippy::await_holding_lock)]
    async fn bot_pov_viewentity_roundtrip_when_requested() {
        if std::env::var("ARGUS_CAMERA_TEST").ok().as_deref() != Some("1") {
            return;
        }
        let _gate = crate::engine::ENGINE_TEST_LOCK
            .lock()
            .unwrap_or_else(|p| p.into_inner());
        let mut cfg = Config::load().unwrap();
        cfg.runs = cfg.root.join("backups/camera_viewentity").join(
            chrono::Utc::now()
                .timestamp_nanos_opt()
                .unwrap()
                .to_string(),
        );
        let mut ctrl = crate::match_ctrl::MatchCtrl::on_port(26018);
        ctrl.begin(
            &cfg,
            "dm4",
            40,
            Some("camera_roundtrip"),
            Some(8),
            Some(1),
            None,
        )
        .await
        .unwrap();
        let result = (|| -> Result<(bool, bool, bool), String> {
            let mut client = NetClient::connect("127.0.0.1", 26018, "cameratest")?;
            let observed = (|| {
                let deadline = std::time::Instant::now() + Duration::from_secs(5);
                while !signed_on(&client.world) && std::time::Instant::now() < deadline {
                    client.pump(Duration::from_millis(50));
                }
                if !signed_on(&client.world) {
                    return Err("camera test signon failed".into());
                }
                let own = client.world.my_ent;
                let own_model = client.world.ents[&own].model;
                impulse(&mut client, 210, "ArgusCam Active")?;
                for mode in ["Focus / Duel", "FreeLook", "Orbit", "1st-Person Bot POV"] {
                    impulse(&mut client, 211, mode)?;
                }
                let deadline = std::time::Instant::now() + Duration::from_secs(2);
                while client.world.my_ent == own && std::time::Instant::now() < deadline {
                    client.pump(Duration::from_millis(50));
                }
                let pov = client.world.my_ent != own
                    && (0..4).any(|slot| tracking_slot(&client.world, slot))
                    && client.world.ents[&own].model == 0;
                impulse(&mut client, 211, "Smart Chase")?;
                client.pump(Duration::from_millis(200));
                let chase = client.world.my_ent == own;
                for mode in [
                    "AI Broadcast Director",
                    "Focus / Duel",
                    "FreeLook",
                    "Orbit",
                    "1st-Person Bot POV",
                ] {
                    impulse(&mut client, 211, mode)?;
                }
                client.pump(Duration::from_millis(200));
                if client.world.my_ent == own {
                    return Err("camera failed to reenter POV".into());
                }
                impulse(&mut client, 210, "ArgusCam Deactivated")?;
                client.pump(Duration::from_millis(200));
                Ok((
                    pov,
                    chase,
                    client.world.my_ent == own && client.world.ents[&own].model == own_model,
                ))
            })();
            client.disconnect();
            observed
        })();
        ctrl.stop(Duration::from_secs(3)).await.unwrap();
        let (pov, chase, off) = result.unwrap();
        assert!(
            pov,
            "POV must select the bot view entity so its own model is hidden"
        );
        assert!(chase, "chase must restore the observer view entity");
        assert!(off, "camera exit must restore the observer view entity");
    }
    #[test]
    fn a_menu_screenshot_or_missing_ack_cannot_pass_as_a_world_frame() {
        let good = "Playing demo from capture.dem.\nUsing protocol 15\nARGUS_CAPTURE frame 0\n";
        assert!(verify_log(good, 1).is_ok());
        assert!(verify_log(good, 2).is_err());
        assert!(verify_log("ARGUS_CAPTURE frame 0\n", 1).is_err());
        assert!(verify_log(&format!("{good}Host_Error: model not found\n"), 1).is_err());
    }
    #[tokio::test]
    async fn timeout_kills_and_reaps_only_the_owned_renderer() {
        #[cfg(windows)]
        let mut command = {
            let mut c = tokio::process::Command::new("powershell.exe");
            c.args([
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "Start-Sleep -Seconds 30",
            ])
            .creation_flags(0x0800_0000);
            c
        };
        #[cfg(not(windows))]
        let mut command = {
            let mut c = tokio::process::Command::new("sleep");
            c.arg("30");
            c
        };
        let mut child = command.kill_on_drop(true).spawn().unwrap();
        assert!(wait_render(&mut child, Duration::from_millis(20))
            .await
            .unwrap_err()
            .contains("timed out"));
        assert!(
            child.try_wait().unwrap().is_some(),
            "timed-out child must be reaped"
        );
    }
    #[test]
    fn selection_requires_the_bot_view_entity_without_scoreboard_names() {
        let mut world = crate::netclient::ClientWorld::default();
        world.my_ent = 1;
        world.player_model = Some(8);
        let mut eye = crate::netclient::WorldEnt::default();
        eye.pos = [1.0, 2.0, 3.0];
        world.ents.insert(1, eye);
        let mut bot = crate::netclient::WorldEnt::default();
        bot.model = 8;
        bot.skin = 2;
        bot.updates = 1;
        bot.pos = [1.0, 2.0, 3.0];
        world.ents.insert(100, bot);
        assert!(
            !tracking_slot(&world, 1),
            "co-located observer still sees the body"
        );
        world.my_ent = 100;
        assert!(tracking_slot(&world, 1));
        assert!(!tracking_slot(&world, 0));
        world.ents.get_mut(&100).unwrap().skin = 3;
        assert!(!tracking_slot(&world, 1));
    }
    #[test]
    fn signon_requires_the_first_entity_update_after_server_stage_three() {
        let mut world = crate::netclient::ClientWorld::default();
        world.signon = 3;
        world.my_ent = 1;
        assert!(!signed_on(&world));
        let mut entity = crate::netclient::WorldEnt::default();
        entity.updates = 1;
        world.ents.insert(1, entity);
        assert!(signed_on(&world));
    }
    #[test]
    fn bounds_reject_menu_frames_and_unbounded_work() {
        assert!(validate(1.0, 12, 0.2, 10.0).is_ok());
        for (s, n, i, d) in [
            (f64::NAN, 1, 1.0, 10.0),
            (1.0, 0, 1.0, 10.0),
            (1.0, 13, 1.0, 30.0),
            (1.0, 2, 0.0, 10.0),
            (9.0, 2, 1.0, 10.0),
            (121.0, 1, 1.0, 150.0),
        ] {
            assert!(validate(s, n, i, d).is_err());
        }
    }
    #[test]
    fn script_uses_engine_png_and_exits_through_console() {
        let s = script(1.0, 3, 0.2);
        assert_eq!(s.matches("screenshot png").count(), 3);
        assert_eq!(s.matches("wait\n").count(), 28);
        assert!(s.ends_with("disconnect\ntoggleconsole\nquit\n"));
        assert!(s.contains("con_notifytime -1\n"));
    }
}
