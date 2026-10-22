# Attack, cover, return - repair plan

Restore the saved feature from c4c6716 onto current main and address the deep
review without including the separate adaptive-aim tuning. Keep main's 0.35
share and ordinary imperfect aim; the 0.60 patch and human scorecards are
preserved in issue #527 and backups/pr-cleanup-20261022/.

- [x] Isolate tactical physics from preserved item routes.
- [x] Cancel shared shop floods and per-bot latches together on every reset.
- [x] Reject unsafe braking envelopes and widen the validated return radius.
- [x] Respect weapon selection, suppress discarded movement and item telemetry,
  reset concealed aim velocity, and yield promptly at blocked or hidden exits.
- [x] Use firing acknowledgements and clear the opening transition's fire button.
- [x] Refuse overlapping fixtures and clear removed-edict references.
- [x] Apply failed-life veto after GOAP substitutions and reset typed hops.
- [x] Strengthen the checker against post-abort falls and later-shot damage.
- [x] Run and retain repeated dm4/dm2 engine suites at measured frame rates.
- [x] Record final source/binary hashes, normal regression matches and checks.

Final validation: 44 controlled engine trials across both maps and both
measured cadences, 114 Python tests and 271 Rust tests.

The previous feature's passing tapes and subsequent integration failure are
historical evidence only. New acceptance uses the repaired checker and keeps
the original two damaging returns from three stationary encounters minimum.
Details and reproduction: [manoeuvre guide](../attack-cover-return.md).

The acknowledged-suite follow-up passed 68 more controlled trials: full
15-trial suites on both maps at played cadence and measured 10 Hz, plus
unlimited-ammo encounters. The driver and independent projectile observer
close #515, #516 and #529. The dedicated GOAP failed-life veto regression (#530) also passes on both
maps and rejects ordering and typed-hop mutations. Remaining work is human
encounter frequency and readability (#517). See the manoeuvre guide for
the separate checkpoint identities.
