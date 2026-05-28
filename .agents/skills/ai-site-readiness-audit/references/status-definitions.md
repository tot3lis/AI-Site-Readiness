# Status Definitions

## Result Labels

- `PASS`: Static evidence confirms the signal is present and useful.
- `PARTIAL`: Some signal exists, but it is incomplete, ambiguous, weak, thin, noisy, poorly structured, or only present on part of the sample.
- `MISSING`: The signal was checked and not found, an expected file returned 404/empty, or a sampled page has effectively no extractable body content.
- `UNKNOWN`: The check could not be completed or evidence was inconclusive. Unknown earns no points, but must not be described as a proven failure.

For content extraction, classify thin readable pages as `PARTIAL`, not `MISSING`. Use `MISSING` only when there is effectively no extractable body content. Use `UNKNOWN` when pages could not be fetched or evaluated.

## Priority Labels

- `HIGH`: Likely to affect AI crawlability, extraction, citation, or agent readiness in a meaningful way.
- `MEDIUM`: Worth fixing after high-priority gaps, or important for specific site types.
- `LOW`: Useful improvement, low urgency, or emerging convention.
- `NONE`: No fix required.

Use only these labels in the scorecard matrix and JSON.
