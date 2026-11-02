# Documentation and issue audit, 2 November 2026

Audit range: session baseline 0e49f4d through 3ccb6c3, before this documentation
cleanup. The range includes the merged muzzle-witness repair in
[#746](https://github.com/saworbit/argus/pull/746). Historical tapes, protocols
and rejected prototypes retain their original bytes and evidence limits.

## Documentation matrix

| Area | Current documentation and audit result |
|---|---|
| Development versus installation | [README](../README.md), [changelog](../CHANGELOG.md) and [diagnostics](behaviour-diagnostics.md) distinguish development source from supplied binaries. The installed MD5 remains A3F7AA9428846DE7F7B327506F5F5D3D. No deployment is implied. |
| Setup and local configuration | [Contributing](../CONTRIBUTING.md), [lab workflow](lab-workflow.md) and the [operator configuration](../tools/argus_mcp/README.md#config) cover the tracked agent protocol, TOML-relative paths, cwd-relative environment overrides and source-built lab authority. Machine-local configuration remains outside this cleanup. |
| Tape identity and helper lifecycle | [Telemetry](telemetry.md), the [lab workflow](lab-workflow.md) and [operator guide](../tools/argus_mcp/README.md) distinguish human tracks, quarantined fixtures, source hashes, private outputs, raw console commands and bounded child processes. Existing public flags and examples match the changed code. |
| Navigation artifacts and rendering | [Developer tools](../tools/README.md), the [brand guide](brand/README.md) and [operator guide](../tools/argus_mcp/README.md) describe render-only previews, matching QC/JSON/PNG receipts, bounded link slots, jump anchors and build-bound coverage. No experimental map registration is implied. |
| Movement and combat | [Architecture](architecture.md), [diagnostics](behaviour-diagnostics.md), [controls](controls.md) and the [body-height study](body-height-investigation.md) cover stall ownership, ally barrel checks, finalized motion observations, camera basis restoration and vertical body overlap. The wider body-clearance prototype remains unadopted. |
| Private proof contracts and CI | [Lab workflow](lab-workflow.md) and [operator guide](../tools/argus_mcp/README.md) now point to the registered compile families instead of stale totals. Transfer layout 3, forecast layout 2 and water-route layout 2 have separate historical qualifications. Optimized Python rejection checks remain distinct from native physical outcomes. |
| Historical studies | [e1m5](e1m5-encounters.md), [e1m6](e1m6-decisions.md), [movers](mover-intelligence.md) and [body height](body-height-investigation.md) retain rejected trials and mixed secondary results. Later observers do not retroactively strengthen old receipts. Design specs and frozen protocols remain historical records. |

The root changelog is the release-note target. This cleanup adds a Changed
entry under Unreleased. No new dependency, public API, console command or
configuration key is introduced by the cleanup itself.

## Deferred work and issue deduplication

Existing issues remain the primary records. Their current scope was checked
before adding another issue.

| Work | Tracker and remaining condition |
|---|---|
| Movement reversals | [#697](https://github.com/saworbit/argus/issues/697): instrumentation is ready; the measured reversal excess still needs a causal repair and matched validation. |
| Stationary windows | [#723](https://github.com/saworbit/argus/issues/723), [#637](https://github.com/saworbit/argus/issues/637), [#628](https://github.com/saworbit/argus/issues/628): physical reproduction and internal ownership/support context remain incomplete. Sampled tapes are not exact state replays. |
| Same-floor body hulls | New [#747](https://github.com/saworbit/argus/issues/747): retained wall and diagonal controls fail outside the vertical-overlap repair. Recheck frozen current source before changing production code. Closed [#734](https://github.com/saworbit/argus/pull/734) failed its dm4 combat-preservation comparison. |
| Legacy jump seats | [#719](https://github.com/saworbit/argus/issues/719): engine-proven anchors and legal regeneration remain required. Rejected [draft #741](https://github.com/saworbit/argus/pull/741) has no auto-merge. |
| Mega return and lower-door loops | [#636](https://github.com/saworbit/argus/issues/636), [#643](https://github.com/saworbit/argus/issues/643): generator swim priority is repaired, but the mega graph is unadopted and the door-loop investigation remains open. |
| Experimental maps | [#623](https://github.com/saworbit/argus/issues/623), [#624](https://github.com/saworbit/argus/issues/624): entity budget, item/spawn reach and real-engine proof must precede registration. |
| Baked cover hints | [#652](https://github.com/saworbit/argus/issues/652): [draft #724](https://github.com/saworbit/argus/pull/724) remains blocked by the freeze investigation. Its old mixed initial/respawn skill inputs are qualified separately. |
| Human evidence | [#610](https://github.com/saworbit/argus/issues/610): a real played session and review are still needed. Automated checks do not supply that evidence. |
| Health/inventory release gate | [#583](https://github.com/saworbit/argus/issues/583): the earlier dm4 warning remains unresolved. Proof-guard repairs do not authorize deployment or more perception cohorts. |
| Upstream dependency warning | [#452](https://github.com/saworbit/argus/issues/452): retain the upstream dependency follow-up; this cleanup does not suppress the warning. |

The new hull issue was checked against all-state searches for body blocking,
wall nudges and diagonal overlap. It records two deterministic controls and
links the retained fixture and hashes. It does not reopen the completed
different-floor fix or duplicate the historical height-copy defect in #267.

## Verification and human follow-up

This cleanup changes documentation only. Validate relative links, anchors,
prose, line endings and the diff. No new engine run or gameplay claim is
needed. The earlier implementation's native receipts and targeted test
results remain with their individual changes.

Human follow-up remains a played gait session and review of movement feel.
The unresolved health/inventory warning remains a deployment gate. Existing
drafts and failed prototypes have not been promoted by this audit.
