# Encoding Semantics

## Primary Variables

For each word `c` in `F_2^n`, primary variable `x_c` is true exactly when
`c` is selected as a codeword. Each target word `t` receives the clause

```text
OR_{d(c,t) <= R} x_c.
```

Thus all coverage clauses hold exactly when the selected words have covering
radius at most `R`.

## Exact Cardinality

For primary literals `x_1,...,x_N`, auxiliary variable `s(i,j)` denotes:

```text
at least j of x_1,...,x_{i+1} are true.
```

The first-row clauses encode `s(0,1) <-> x_1` and force `s(0,j)` false for
`j >= 2`. Every later row encodes the recurrence

```text
s(i,j) <-> s(i-1,j) OR (x_{i+1} AND s(i-1,j-1)).
```

For `j=1`, the second term reduces to `x_{i+1}`. Induction on `i` proves the
stated invariant. The final unit clauses require `s(N-1,k)` and forbid
`s(N-1,k+1)`, so exactly `k` primary literals are true.

Tests exhaust every primary assignment through six variables and compare the
projection against PySAT's totalizer encoding, which uses a different
cardinality construction.

## Translation Anchor

If `C` is a nonempty binary code and `a` is in `C`, define

```text
C + a = {c XOR a : c in C}.
```

XOR by `a` is a bijection and preserves Hamming distance:

```text
d(x XOR a, c XOR a) = d(x,c).
```

Therefore translation preserves code size and covering radius, while the
translated code contains zero because `a XOR a = 0`. Fixing `x_0` true loses
no size-15 covering code.

## Exact Size Versus At-Most Size

Adding codewords cannot make a covered target uncovered. Any cover with fewer
than 15 words can therefore be padded with distinct ambient words to obtain a
15-word cover. Deciding exact size 15 is equivalent to deciding whether the
covering number is at most 15.

## Proof Boundary

These arguments establish the meaning of the generated formula. They do not
establish satisfiability or unsatisfiability. A lower-bound result still
requires a complete solver proof trace checked by an independent proof
checker.
