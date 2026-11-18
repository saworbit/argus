# Fixed-clock validation, amendment 1: dm3 and e1m7

Registered 2026-11-18, before any fixed-clock tape of this amendment was
recorded. The question, metrics and criterion are those of
`2026-11-15-fixed-clock-validation.md`, unchanged; only the control and the
build differ, and both differences are stated here (#854).

## What changes

- Build: main at 89b9852 (build 9387e1e77737), not the validation build
  `cbc0176e8e8e`. The fixed arm and the control run the same build.
- Control: the played-rate tapes of that build recorded on 2026-11-18 as the
  control arms of other ladders, skill 2, 185 s, listen class: on dm3
  `study_sw761d3_ctl_r1` to `r5`, `study_j774d3_ctl_r1` to `r3` and
  `study_s775d3_ctl_r1` to `r3`; on e1m7 `study_j782e7_ctl_r1` to `r3` and
  `study_kd785_ctl_r1` to `r10`. Every one of them was recorded, and some of
  their totals were read for those ladders, before this amendment; none was
  recorded for it. That is weaker than the original design, in which the
  control was recorded for the validation itself, and a reader should weigh it.
- Fixed arm: 20 fresh seeds a map, `seed_for(41..=60)`, the default 14.25 ms
  frame, named `fxval2_fixed_<map>_s<seed>`, run after the control set above
  is complete.

## Readings

`tools/argus_clock_validation.py --map <map>` with the control and fixed
sets above, each map accepted or not by the original criterion, recorded in
`tools/lab_instruments.json` and `docs/fixed-clock.md` with its limits.

## Result (recorded 2026-11-18)

Both maps are accepted at 14.25 ms. dm3: 11 wall-clock and 20 fixed tapes;
limits stalls, deaths and routefails, and its lava reads equivalent only
because neither arm had a lava death. e1m7: 13 wall-clock and 19 fixed tapes,
seed 250 excluded as outside the listen tick class; limits stalls, lava and
world deaths, and routefails. The table and the tick-class note are in
[the fixed lab clock](../fixed-clock.md#amendment-1-dm3-and-e1m7-at-1425-ms).

The fixed tapes were run under the arm name `ctl` and recorded as
`study_fxval2_fixed_<map>_ctl_s<seed>`, not the registered
`fxval2_fixed_<map>_s<seed>`; they are committed under the registered names,
unchanged, and the control tapes beside them as `fxval2_played_<map>_<run>`.
Seeds, frame, build and skill are as registered.
