# Duration Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep scaled count comparisons honest when tapes are short or carry malformed durations.

**Architecture:** Validate duration values at the scaling boundary, keep each brief's observed duration intact, and let scaled comparison wrappers translate validation failures into `Mixed` reports. Band coverage eligibility is derived from every original brief before count normalization.

**Tech Stack:** Rust 2021, Argus MCP library tests, Markdown documentation.

## Global Constraints

- Change only the Rust comparison path and documentation made stale by it.
- Keep count metrics normalized to the candidate median duration.
- Never gate coverage when any original source tape is shorter than 120 seconds.
- Treat non-finite durations and durations at or below one second as invalid.
- Do not change QuakeC, generated navigation, or engine behavior.

---

### Task 1: Guard scaled comparison inputs

**Files:**
- Modify: `tools/argus_mcp/src/intel.rs`

**Interfaces:**
- Consumes: `MatchBrief`, `CompareReport`, `Verdict`, `COVER_GATE_MIN_SEC`.
- Produces: `scale_brief_to_duration(...) -> Result<MatchBrief, String>` and recoverable `Mixed` reports from scaled comparison wrappers.

- [ ] **Step 1: Write failing regression tests**

Add tests that call the real scaled comparison helpers and assert:

```rust
assert!(scale_brief_to_duration(invalid_source, 30.0).is_err());
assert!(scale_brief_to_duration(valid_source, f64::NAN).is_err());
assert_eq!(compare_band_primary_scaled(&candidates, &controls, None).verdict, Verdict::Mixed);
```

The malformed band must place an invalid duration in a non-representative brief
so the test proves every input is validated.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```text
cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib intel::tests::scaled_
```

Expected: compilation or assertion failure because scaling still returns a bare
brief and malformed durations still produce ordinary verdicts.

- [ ] **Step 3: Implement duration validation**

Add a small validator using `duration.is_finite() && duration > 1.0`. Change the
scaling helper to return `Result`, validate source and target, scale count fields,
and leave `Totals.duration_sec` unchanged. Add a helper that creates a clear
`Mixed` report for recoverable validation failures.

- [ ] **Step 4: Preserve band-wide coverage provenance**

Validate every candidate and control before calculating the median. After the
scaled band comparison, mark coverage ungated whenever any original brief was
shorter than `COVER_GATE_MIN_SEC`, then rebuild the gate card from the corrected
gate state.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```text
cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib intel::tests::scaled_
```

Expected: all focused scaled-comparison tests pass.

### Task 2: Prove reverse scaling keeps coverage ungated

**Files:**
- Modify: `tools/argus_mcp/src/intel.rs`

**Interfaces:**
- Consumes: `compare_briefs_scaled` and `compare_band_primary_scaled`.
- Produces: coverage diagnostics based on source durations while count metrics use normalized durations.

- [ ] **Step 1: Add the reverse-scaling regression**

Create a 30 second control with high coverage and a 180 second candidate with low
coverage but equal per-second engagement counts. Assert normalized engagement
parity and a passing coverage gate whose note says it is not gated.

- [ ] **Step 2: Run the regression and verify RED against the parent commit**

Run the test before the implementation from Task 1. Expected: coverage fails
because both briefs appear to be 180 seconds after scaling.

- [ ] **Step 3: Run the regression and full Rust library suite after the fix**

Run:

```text
cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib
```

Expected: the reverse-scaling test and all existing library tests pass.

### Task 3: Update user-facing documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `tools/argus_mcp/README.md`

**Interfaces:**
- Consumes: the final comparison behavior.
- Produces: an Unreleased changelog entry and an accurate scaling description.

- [ ] **Step 1: Update the changelog and lab guide**

State that malformed durations now produce `Mixed`, count normalization preserves
observed duration, and coverage remains ungated if any source tape was short.

- [ ] **Step 2: Format and verify**

Run:

```text
cargo fmt --manifest-path tools/argus_mcp/Cargo.toml -- --check
cargo test --manifest-path tools/argus_mcp/Cargo.toml --lib
```

Expected: formatting is clean and all library tests pass.

- [ ] **Step 3: Commit**

Commit the implementation, tests, changelog, and lab guide with an imperative,
specific message.
