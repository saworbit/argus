# Organic player model (OPM) triage and adoption record

Date: 2026-08-18 (late night)
Status: SHIPPED 2026-08-18 late night - slice A in v3.27 (spring
gains corrected from the source spec's omega/k confusion, see
below), slice B in v3.28 (2-of-3), slice C in v3.29 (best ladder of
the run). All three in all three installs as v3.29
(3931E542C61738F159882D1EEA70451F). Tapes: ab_dm4_springaim1-7,
ab_dm4_ears1-3, ab_dm4_opmc1-2.
Source: Shane's pasted "Organic human player emulation" specification
(five-tier cognitive stack). This document records what ships, what
is already shipped, what is refused and why, and the parameters
actually used. Where this file and the pasted spec disagree, this
file is the record.

## Already shipped before this spec arrived

- Projectile leading (rockets/nails 1000, grenades 600): v3.19. The
  spec's Argus_PredictAimPoint duplicates it. Its nail speed of 2000
  is wrong (nails fly 1000) and is not adopted.
- Grenade loft d^2/2400 with above-target compensation: v3.17.
- Personality-voiced chat with throttling: v3.12.
- Ballistic dip for well-below targets: v3.17 (the spec's "back wall
  lip" case is covered by the existing dip).
- Skill tiers and per-bot reaction/tracking/error: v3.9.

## Refused, with grounds

- Panic movement inversion ("zigzag backward escape"): this is the
  naive retreat, tried twice and reverted twice (ab_dm4_retreat,
  ab_dm4_retreat2: self-rockets at close range, blind lip-backing,
  lava 3 to 7). The standing verdict holds: no retreat without
  positioning-aware escape headings. Panic in this build affects AIM
  ONLY (tremor scaling), never movement.
- Suppressive fire while fleeing: depends on the refused retreat.
- Roster/name changes (the spec's "Nyx"): personalities are on the
  do-not-reopen list; the fourth bot remains Ares. Differentiating
  Ares from Zeus is deferred M4 work, not this spec.
- Item respawn clocks (tier 4A): sanctioned, but it is campaign
  queue item 4 in its own right and ships as its own slice with its
  own A/B, not inside this bundle.
- Weapon-switch fidget sounds and axe disrespect: gimmicks; skipped.
- Full item denial "even at zero gain": adopted only as a small
  utility bonus (below), not an override.

## Adopted, slice A (aim humanisation, v3.27)

- Damped-spring yaw aim replacing the linear rate limiter. Explicit
  Euler, one integration per combat frame:
  vel += (err * k - vel * c) * dt, yaw += vel * dt + tremor.
  Velocity clamped to 720 deg/s. Stability holds at dt 0.05 worst
  case (k*dt^2 = 0.09 at k 36).
- Parameters live in Argus_SetSkill beside the existing tier fields
  (no runtime sqrt in vanilla QC, so damping is precomputed):
  skill 0: k 14 c 6.0; skill 1: k 20 c 7.2; skill 2: k 28 c 8.5;
  skill 3: k 36 c 9.6 (about 0.8 damping ratio: visible overshoot).
  Personality: Reap k*1.15 (flick), Omi c*1.15 (smooth), Zeus k*1.1
  and c*0.9 (wild overshoot).
- Tremor: 0.3 deg base, 0.8 under 40 health. Aim only.
- Rocket foot-splash: a grounded enemy is aimed at the floor
  (origin_z - 16) instead of centre mass; airborne targets keep the
  existing dip/lift logic. The fire-gate remaining-error check is
  recomputed after the spring step.
- Pitch stays exact at fire time: the error model already perturbs
  the aim point in three axes, which perturbs pitch.

## Adopted, slice B (perception, v3.28)

- Simulated hearing: Argus_HearSound(pos, who, threat) records a
  single-slot audio memory (ar_sndpos/ar_sndtime/ar_sndent) on every
  bot within volume range, wall-damped 1.4x by an eye trace. V1 call
  site is W_Attack only (gunfire is the tactical sound); pickups and
  teleporters are later call sites if the ladder likes this one.
- Glance: a bot with no enemy and a fresh sound (under 2 s) turns
  its facing toward the sound. Facing is decoupled from movement, so
  this cannot steer anyone into lava.
- Soft FOV on NEW acquisitions only: beyond 500u a candidate must be
  roughly in front (dot v_forward > 0.2, about 155 degrees with
  peripheral) OR near a fresh heard sound (300u, 2.5 s). Within 500u
  acquisition stays free (peripheral and audio close up). Tracking
  of the CURRENT enemy remains 360 degrees: losing a fight you are
  in because you turned is not the human failure being modelled.
  The glance-then-acquire loop closes the spec's "hears fire, turns,
  then sees" behaviour with three small pieces.
- METRIC NOTE: engages may shift at this boundary; the ladder
  decides whether it is a boundary or a regression.

## Adopted, slice C (psychology-lite and expression, v3.29)

- Nemesis: Argus_Die records the killer (self.enemy); a third
  consecutive death to the same player triggers vendetta: +600
  target utility for that player in Perceive. Any kill while
  vendetta'd discharges the streak (a vented tilt) and fires a
  revenge chat line (new Argus_Chat case).
- Item denial: a modest utility bonus (+12 before appetite) when a
  live opponent stands within 300u of the item being scored: take
  the armour they were walking toward.
- Corner pre-aim: while routed with no enemy, face the node AFTER
  the current steering target (Argus_GetNext lookahead) instead of
  the travel direction, rate-limited. Bots look through upcoming
  corners the way players do. Facing only; movement untouched.
- Confidence/affect engine: NOT adopted as a state machine. The
  observable effects the spec wants from confidence (bolder push,
  wider engagement) largely exist via weapon-armed hunger and
  pursuit; a full affect engine is idea-bank material pending a
  concrete A/B hypothesis.

## Validation

Each slice ladders on dm4 against the v3.24 boundary baseline
(ab_dm4_parity): player kills 25-37, lava 2-7 with no storm
signature, stalls under 27, engages 68-97, frags positive, spread
tight. Slice B additionally proves the hear-then-turn loop on a dm2
probe (gunfire behind the t6 wall is the natural test). Human-feel
verification (overshoot visible, glances visible, foot rockets) is
Shane's next playtest; the spec's four-point verification matrix
folds into that session.
