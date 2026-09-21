#[path = "src/source_fingerprint.rs"]
mod source_fingerprint;

fn main() {
    let manifest = std::path::PathBuf::from(
        std::env::var_os("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"),
    );
    let fingerprint = source_fingerprint::fingerprint(&manifest)
        .expect("fingerprint Argus MCP sources at build time");
    println!("cargo:rustc-env=ARGUS_BUILD_SOURCE_FINGERPRINT={fingerprint}");
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed=Cargo.toml");
    println!("cargo:rerun-if-changed=Cargo.lock");
    println!("cargo:rerun-if-changed=src");
}
