# Duration Provenance in Scaled Comparisons

## Problem

Scaled comparisons currently overwrite `Totals.duration_sec` with the
normalization target. That is correct for count arithmetic but destroys the
source tape duration used by the coverage gate. A short control scaled toward a
long candidate can therefore look long enough to gate coverage. Durations at or
below one second are also accepted through clamping or by silently skipping
normalization.

## Decision

`Totals.duration_sec` remains the observed tape duration. Count normalization
uses a target duration without rewriting that field. The scaling helper returns
`Result` and rejects any source or target duration that is not finite or is at
most one second. Public comparison helpers convert those recoverable validation
errors into a `Mixed` report with a clear finding.

Band comparisons check every source brief before calculating the candidate
median. Coverage is eligible only when every source brief in both arms was at
least 120 seconds. Count metrics continue to normalize to the candidate median.

## Alternatives

Adding a second serialized duration field would make provenance explicit but
would expand the public report shape and every constructor. Restoring the
coverage gate after comparison without changing scaling semantics would be a
local patch that leaves future duration-dependent checks exposed to the same
error. Preserving the observed duration fixes the meaning at its source.

## Tests

Regression tests exercise the real comparison functions. They cover a short
control scaled toward a long candidate, malformed durations anywhere in a band,
and the direct scaling helper's source and target validation. Existing tests
continue to prove that count metrics normalize and coverage itself is never
scaled.

## Documentation

The Unreleased changelog records the verdict-safety fix. The lab guide states
that scaled comparisons preserve observed duration for non-rate gates.
