# Attack, cover, return: first playable milestone

Goal: Romero fires, walks out of sight, and returns with a useful shot from a different angle on dm4 A and dm2 C.

Architecture: a bounded tactical state in combat, separate from item routes. Start with the two engine-verified route candidates, resolved against existing graph coordinates and links. Runtime body-cover, shot, angle, floor and clearance checks decide eligibility. This deliberately limits the first release to these encounters; a general local route search follows only after the behaviour proves worthwhile in play.

Tech stack: vanilla QuakeC, existing Argus navigation/physics/trigger code, Argus lab MCP, a developer-only engine fixture and a Python result checker.

Constraints: preserve the checkout's adaptive-aim changes. No generated nav changes, engine extensions or QC file I/O. Use observed enemy coordinates only; abandon on danger, displacement, invalid geometry, target loss or a short deadline. Keep ordinary reaction and aim error. Romero's roster slot, deathmatch skill 1, rocket launcher only. Cooldown after success/failure.

- [x] Capture baseline and build a fixture that measures actual bot movement, body concealment and target damage; observe failure before implementing tactics.
- [x] Add `src/argus_tactics.qc`: candidate validation, post-shot commitment, concealment and return states, bounded safety checks and events.
- [x] Integrate with combat before sight-loss pursuit; keep normal aim/fire on visible legs and surrender to emergency behaviour. Reset on respawn/death.
- [x] Run repeated dm4/dm2 controlled encounters, including opponent departure/push and low health. Verify independent outcomes and actual frame cadence.
- [x] Run both maps through the lab, review the diff, document evidence and remaining limitations.

Results and reproduction: `docs/attack-cover-return.md`. The final engine
suites passed 20 trials across both maps, including six complete manoeuvres
and four damaging return shots. Human feel and natural encounter frequency
remain playtest questions.

Acceptance: a real opening rocket, dry walking through true full-body cover (dm2 n92, never n104), at least 30 degrees around the opponent at first reappearance, actual return attack through normal firing, bounded completion/abort. Tests record outcomes rather than treating a selected route as success.
