# Literature And Status Audit

Audit date: 2026-09-03

## Current Cell

The Keri binary table records

```text
15 <= K_2(11,3) <= 16.
```

The table update log dated 2006-01-17 records the lower bound 15 as a
stepwise-refinement result. The binary table attributes the upper bound 16 to
the Graham-Sloane construction line from 1985. The binary PDF was generated on
2009-10-15, and the latest dated update on the table site is 2011-11-21.

## Freshness Checks

- The formal covering-code database at
  `https://github.com/florath/covering-codes-lean` does not currently certify
  the `15-16` interval. At commit
  `2ecbf887d7a29a8137da6b476d1f5de93c3936d4`, dated 2026-07-17, its
  generated proof-carrying table gives `9-28` for this cell. Its Keri and
  post-Keri reference rows separately record the historical interval `15-16`.
- Version 2 of Gijswijt and Polak's arXiv:2504.01932, updated 2026-06-19,
  reports numerical value `12.4700` at row `n=11`, column `R=3`, in its
  appendix table for binary codes. This is below the historical lower bound
  15.
- Version 2 of Mark Marosi's arXiv:2608.19872, updated 2026-08-23, concerns
  alphabet sizes 5 through 21 and therefore does not close the binary cell
  here.
- Searches for the exact notation, parameter tuple, and a post-2011 exact
  determination did not locate a primary source closing the gap.
## Search Record

The 2026-09-03 refresh used general web search, arXiv search, repository search,
and direct inspection of these source locations:

- Keri's official update log,
  `https://old.sztaki.hu/~keri/codes/index.htm`, and binary table PDF,
  `https://old.sztaki.hu/~keri/codes/2_tables.pdf`;
- the formal database at commit
  `https://github.com/florath/covering-codes-lean/tree/2ecbf887d7a29a8137da6b476d1f5de93c3936d4`;
- `https://arxiv.org/abs/2504.01932v2` and
  `https://arxiv.org/abs/2608.19872v2`.

The exact search strings were:

- `K_2(11,3)`, `K2(11,3)`, and
  `"binary covering code" 11 3 15 16`;
- `K_2(11,3) exact`;
- `K2(11,3) covering code 2012..2026`;
- `binary covering code length 11 radius 3 lower bound`;
- `binary covering code 11 3 certificate`.

The search found no later primary source or checked certificate determining
the exact binary cell. This is a dated literature audit, not a proof of
absence, and it must be refreshed before a materially delayed novelty claim.
The audit was targeted rather than systematic and did not retain a fixed
result-count cutoff.

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

- Gabor Keri, official covering-code update log,
  `https://old.sztaki.hu/~keri/codes/index.htm`, entry dated 2006-01-17;
  binary table generated 2009-10-15 and latest dated site update 2011-11-21.
  No stable paper or retained proof certificate for this computation was
  located.
- Ronald L. Graham and Neil J. A. Sloane, "On the Covering Radius of Codes",
  *IEEE Transactions on Information Theory* 31(3), 385-401, 1985,
  DOI `10.1109/TIT.1985.1057039`.
- Gerard Cohen, Iiro Honkala, Simon Litsyn, and Antoine Lobstein,
  *Covering Codes*, North-Holland, 1997.
- Dion Gijswijt and Sven Polak, "Semidefinite lower bounds for covering
  codes", arXiv:2504.01932v2, 2025-2026.
- Mark Marosi, "New upper and lower bounds on covering codes K_q(n,R) for
  alphabets of size 5 <= q <= 21", arXiv:2608.19872v2, 2026.
