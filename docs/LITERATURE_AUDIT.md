# Literature And Status Audit

Audit date: 2026-09-02

## Current Cell

The Keri binary table records

```text
15 <= K_2(11,3) <= 16.
```

The table attributes the lower bound to Keri's 2006 computation and the upper
bound to the Graham-Sloane construction line. The binary PDF was generated on
2009-10-15, and the table site reports a final revision in 2011.

## Freshness Checks

- The formal covering-code database at
  `https://github.com/florath/covering-codes-lean` does not currently certify
  the `15-16` interval. At commit
  `2ecbf887d7a29a8137da6b476d1f5de93c3936d4`, dated 2026-07-17, its
  generated closure table gives `9-28` for this cell. Its imported Keri data
  separately records the historical lower bound 15 and upper bound 16.
- The semidefinite hierarchy in arXiv:2504.01932 reports numerical value
  `12.4700` for the relevant binary cell, below the historical lower bound 15.
- The preprint arXiv:2608.19872, submitted on 2026-08-20, reports improved
  covering-code bounds for alphabet sizes 6 and 7, not for the binary cell
  here.
- Searches for the exact notation, parameter tuple, and a post-2011 exact
  determination did not locate a primary source closing the gap.
- Neighboring one-gap covering problems have been closed recently with
  proof-logged SAT and formal checking. That makes proof format and independent
  replay mandatory for any lower-bound claim here.

## Provenance And Licensing

- The Keri tables are used as bibliographic reference data only.
- The formal database is BSD-3-Clause, but no source is copied into this
  repository.
- All implementation code here is independent and MIT licensed.
- A historical code or certificate will not be redistributed without an
  explicit compatible license.

## Novelty Boundary

The following are not new results:

- a 16-word code;
- direct verification of that code;
- an unproved solver timeout at size 15;
- a CP-SAT infeasibility status without proof output.

A potentially new result is either a verified 15-word code or a checked
proof that all 15-word codes are impossible. A search or structural lemma may
also be publishable if it strictly improves the proof frontier and survives a
refreshed audit.

## References

- Gabor Keri, tables of bounds for covering codes, binary table generated
  2009-10-15 and table site last revised in 2011.
- Gerard Cohen, Iiro Honkala, Simon Litsyn, and Antoine Lobstein,
  *Covering Codes*, North-Holland, 1997.
- Dion Gijswijt and Sven Polak, "Semidefinite lower bounds for covering
  codes", arXiv:2504.01932, 2025.
- Badih Ghazi, Pablo Piantanida, Aravind Velingker, and Jialin Zheng,
  "Improved covering codes over medium-sized alphabets", arXiv:2608.19872,
  2026.
