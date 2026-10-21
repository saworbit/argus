//! Small, dependency-free source fingerprint shared by build.rs and runtime.

use std::path::{Path, PathBuf};

const FNV_OFFSET: u64 = 0xcbf29ce484222325;
const FNV_PRIME: u64 = 0x100000001b3;

fn collect_rs(dir: &Path, files: &mut Vec<PathBuf>) -> Result<(), String> {
    let entries = std::fs::read_dir(dir).map_err(|error| format!("{}: {error}", dir.display()))?;
    for entry in entries {
        let path = entry.map_err(|error| error.to_string())?.path();
        if path.is_dir() {
            collect_rs(&path, files)?;
        } else if path.extension().is_some_and(|extension| extension == "rs") {
            files.push(path);
        }
    }
    Ok(())
}

fn feed(hash: &mut u64, bytes: &[u8]) {
    for byte in bytes {
        *hash ^= u64::from(*byte);
        *hash = hash.wrapping_mul(FNV_PRIME);
    }
}

/// Fingerprint every Rust source plus the files that select dependencies and
/// build-time behavior. Paths participate so a rename is a different build.
pub fn fingerprint(manifest_dir: &Path) -> Result<String, String> {
    let mut files = vec![
        manifest_dir.join("Cargo.toml"),
        manifest_dir.join("Cargo.lock"),
        manifest_dir.join("build.rs"),
    ];
    collect_rs(&manifest_dir.join("src"), &mut files)?;
    files.sort();

    let mut hash = FNV_OFFSET;
    for path in files {
        let relative = path
            .strip_prefix(manifest_dir)
            .map_err(|error| error.to_string())?
            .to_string_lossy()
            .replace('\\', "/");
        let bytes = std::fs::read(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        feed(&mut hash, relative.as_bytes());
        feed(&mut hash, &[0]);
        feed(&mut hash, &bytes);
        feed(&mut hash, &[0xff]);
    }
    Ok(format!("fnv1a64:{hash:016x}"))
}
