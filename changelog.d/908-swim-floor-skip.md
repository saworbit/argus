Fixed
Swimming bots skip the early-switch dry-floor check in `Argus_WalkArrivalReady` when `ar_feettype` is water ([#908](https://github.com/saworbit/argus/issues/908)), raising dm3 swim events from 1125 to 1566 over three played 185 s pairs while keeping dm3 and dm4 `argus_lab.py skeptic` parity clean.
