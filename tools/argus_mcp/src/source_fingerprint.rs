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

/// Feed file content with every CRLF read as LF, so the identity follows the
/// text and not the checkout's line-ending settings (#777). A worktree checks
/// these files out LF while an older checkout can hold CRLF copies, and raw
/// bytes made every worktree compare read as a stale lab. An LF file feeds
/// exactly the bytes it always did.
fn feed_text(hash: &mut u64, bytes: &[u8]) {
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'\r' && bytes.get(index + 1) == Some(&b'\n') {
            index += 1;
            continue;
        }
        feed(hash, &bytes[index..index + 1]);
        index += 1;
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
        feed_text(&mut hash, &bytes);
        feed(&mut hash, &[0xff]);
    }
    Ok(format!("fnv1a64:{hash:016x}"))
}

#[cfg(test)]
mod tests {
    use super::fingerprint;
    use std::path::Path;

    fn tree(root: &Path, newline: &str) {
        std::fs::create_dir_all(root.join("src/inner")).unwrap();
        let text = |lines: &[&str]| lines.join(newline) + newline;
        std::fs::write(
            root.join("Cargo.toml"),
            text(&["[package]", "name = \"x\""]),
        )
        .unwrap();
        std::fs::write(root.join("Cargo.lock"), text(&["version = 4"])).unwrap();
        std::fs::write(root.join("build.rs"), text(&["fn main() {}"])).unwrap();
        std::fs::write(root.join("src/lib.rs"), text(&["//! x", "pub mod inner;"])).unwrap();
        std::fs::write(
            root.join("src/inner/mod.rs"),
            text(&["pub fn f() {}", "// lone \r stays"]),
        )
        .unwrap();
    }

    #[test]
    fn crlf_and_lf_checkouts_share_one_fingerprint() {
        let base = std::env::temp_dir().join(format!("argus-fp-{}", std::process::id()));
        let (lf, crlf) = (base.join("lf"), base.join("crlf"));
        tree(&lf, "\n");
        tree(&crlf, "\r\n");
        let lf_print = fingerprint(&lf).unwrap();
        assert_eq!(lf_print, fingerprint(&crlf).unwrap());
        // Content still counts: a changed line is a different build.
        std::fs::write(lf.join("build.rs"), "fn main() { let _ = 1; }\n").unwrap();
        assert_ne!(lf_print, fingerprint(&lf).unwrap());
        let _ = std::fs::remove_dir_all(&base);
    }
}
