# Combat target decisions

[Architecture](architecture.md) | [Telemetry](telemetry.md) |
[Decision and match evidence](../runs/combat-attention.results.json)

## Behaviour

Previously a live opponent kept the bot's attention until death or several
seconds out of sight. A second visible player could damage it without
changing that choice. The development policy now reassesses opponents during
an ongoing fight, using observed opportunities and its own recent damage.
This changes who the bot chooses to fight; aim gains, weapon selection and
movement physics are unchanged.

The current opponent keeps a 250-point preference. A new choice must beat
that margin, and a choice is held for at least 0.8 seconds. Challenger scans
run at most every 0.4 seconds. Existing current-target observation continues
normally; these clocks limit decisions rather than the visual sample rate.

The score retains distance, visible quad and the existing nemesis preference.
A recent hostile player hit adds up to 900 points, decaying over two seconds.
Visible invulnerability subtracts 900 points. This makes a fresh aggressor
or a vulnerable alternative worth considering without changing targets for
every small distance difference. The additional policy starts at the
existing cognition threshold of 0.5; warmup partners keep their old focus.
Co-op and active authored tactics retain their target ownership.

Taking damage records an identity and time, not a visual position. A fresh
attacker can justify looking behind, but must still pass ordinary visibility
and ring checks. A hidden current opponent supplies cached position/powerup
cues. Exact opponent health, armour and ammunition never enter the utility.
Respawn clears the history and decision clocks. Roster removal also forgets
a recorded attacker before its entity slot can be reused.

A switch restarts the existing reaction and tracking delays, clears the
speculative-shot state and invalidates the old secondary-threat cache. It
preserves the item goal and route. An existing retreat is retained, repinned
to the newly observed weapon class, and given a fresh cover decision without
resetting its cooldown. `ARGEVT <bot> retarget <opponent>` records
the choice separately from an initial `engage`; switching cannot inflate
the old engagement counter.

## Controlled evidence

The private fixture calls production pain and perception code, using actual
BSP traces to establish visible and occluded positions. It fixes and counts
random inputs, emits the recognised `BHVRPL begin` quarantine marker, and
does not substitute a Python targeting policy.

The final study has eight tapes: unchanged and candidate source on dm6 and
lqdm2, each at measured played and 100 ms cadence. The candidate passes all
21 checks on every tape. The unchanged source fails exactly the three
declared feature cases: reacting to another visible aggressor, restarting
reaction after that switch, and leaving an invulnerable target for a
vulnerable opponent. Its other guards pass.

The checks also cover the switch margin, hold and scan clocks, goal ownership,
warmup/tactic ownership, occluded attackers, hidden-state/RNG independence,
cached current-target cues, ring visibility, expired aggression, ally/world/
self damage, attacker removal, retreat intent and respawn reset.

The first prototype passed 18 checks but failed an added crossfire invariant:
its new primary could remain cached as the old secondary threat. That
negative tape and the superseded normal matches remain separate. Clearing
the secondary identity and scan clock fixes that transition; no score or
acceptance threshold was changed after those tapes. A later transition audit
also reproduced the loss of an existing retreat; its negative tape is
retained, and the final policy preserves that intent. All earlier source
variants remain separate from the final comparison.

## Normal matches and limits

The pre-registered comparison uses two 60-second skill-2 matches per arm on
dm3, dm6, lqdm2, e1m1, e1m2, e1m5, e1m6 and e1m7. The registered native primary
is engagements as a combat-participation safety check, not a measure of
decision quality by itself. The final candidate
runs in two four-map shards with identical compiled binaries; every map still
has the registered duration and two repeats per arm. Severe freezes remain
hard vetoes. All eight native cards report parity.

| Across 16 matches per arm | Unchanged | Candidate |
|---|---:|---:|
| Engagement starts | 195 | 169 |
| Mid-fight retargets | 0 | 40 |
| Consumed current-goal pickups | 52 | 53 |
| Frags | 51 | 59 |
| Stalls | 76 | 83 |
| Freezes / under-fire freezes | 1 / 1 | 0 / 0 |
| World/lava deaths | 5 | 2 |

These totals describe this sample, not a statistically established win rate.
Both e1m5 candidate tapes have zero engagement starts and zero retargets,
against two and six starts in the controls. The native parity band includes
zero; [#631](https://github.com/saworbit/argus/issues/631) tracks the
encounter/visibility investigation rather than a
claim that the new decisions were exercised on that map. On e1m6, mean stalls
rise from 4.5 to 10; the existing [platform follow-up](https://github.com/saworbit/argus/issues/622)
remains open. Neither observation establishes causation from this change.

The machine-readable evidence retains the per-map native band cards, source/
binary identities and raw hashes. Retargets and third-party deaths are
reported separately; a small match set cannot establish better human play.
The controlled decisions establish the intended policy difference. Existing
map-execution and perception follow-ups retain their own evidence.
Installed gameplay binaries are unchanged; existing release and human-play
verification gates still apply.

## Reproduction

Use the source-matched native lab and existing local engine/map assets.
These drivers compile into private assets and preserve installed binaries.

```text
python tools/verify_target_attention.py --output backups/attention/played --prefix attention_played
python tools/verify_target_attention.py --output backups/attention/slow --prefix attention_slow --ticrate .1
python tools/verify_target_attention.py --output backups/attention/control --prefix attention_control --source <frozen-control-src> --legacy-control
python tools/test_target_attention.py
```

Use fresh output directories and prefixes. A declared legacy control must
reproduce exactly the known failures; unexpected passes, extra failures,
missing guards, wrong maps/rates or missing quarantine fail the verifier.
The `attention` family is part of private compilation, and the receipt/privacy
tests run in fast CI. Historical health-perception definitions remain frozen
through an exact reverse amendment; the new active source is checked separately.
