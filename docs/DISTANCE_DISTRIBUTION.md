# Distance-Distribution Bounds

Let `p_d` be the number of unordered codeword pairs at Hamming distance `d`
in a hypothetical 15-word radius-3 cover.

## Pair And Shell Identities

There are 105 unordered pairs:

```text
sum_d p_d = 105.
```

For a fixed codeword and a target shell at distance `j`, define

```text
H(d,j) = sum_a C(d,a) C(11-d,j-a),
```

where the sum uses exactly those `a` for which `d + j - 2a <= 3`.
Covering every target in shells `4 <= j <= 11` gives

```text
2 sum_d H(d,j) p_d >= 15 C(11,j).
```

## Parity-Refined Delsarte Inequalities

For the binary Krawtchouk polynomial `K_k(d)`, Fourier expansion gives

```text
15 C(11,k) + 2 sum_d K_k(d) p_d
  = sum_{weight(a)=k} (sum_{c in C} (-1)^(a dot c))^2.
```

Every inner character sum is odd because the code has 15 words. Its square is
therefore at least 1 and congruent to 1 modulo 8. In particular,

```text
2 sum_d K_k(d) p_d >= -14 C(11,k).
```

## Exact Rational Certificates

`evidence/distance-distribution-bounds.json` contains two dual combinations
checked with exact rational arithmetic:

```text
p_1 + ... + p_6 >= 28,
p_1 + ... + p_5 >= 12467/1230.
```

The second left side is an integer, so

```text
p_1 + ... + p_5 >= 11.
```

Every hypothetical cover therefore has minimum pair distance at most 5.
After translating one endpoint of a closest pair to zero and permuting
coordinates, the complete first-word symmetry split needs only weights 1
through 5. All weight-6 cases are impossible.

## Pair-Ball Overlap

Let `O` be the sum, over unordered codeword pairs, of the intersection size
of their radius-3 Hamming balls. The intersection coefficients for pair
distances 1 through 11 are

```text
112, 112, 56, 56, 20, 20, 0, 0, 0, 0, 0.
```

Normalize the shell-10, shell-11, degree-1 Delsarte, and degree-11 Delsarte
rows as `J10`, `J11`, `D1`, and `D11`. Exact coefficient comparison gives

```text
O = 20P + 4J10 + 4J11 + 9D1 + 9D11
    + 20(p1+p2) + 4(p9+p10) + 40p11,
```

where `P = 105`. The row bounds are

```text
J10 >= 83,
J11 >= 8,
D1 >= -77,
D11 >= -7.
```

If `u = J10-83` and `v = J11-8`, then every coefficient of `J10+J11`
is divisible by 4, while `83+8` is congruent to 3 modulo 4. Thus

```text
u + v is congruent to 1 modulo 4,
```

so `u+v >= 1`. Substitution proves the strengthened inequality

```text
O >= 1712 + 20(p1+p2) + 4(p9+p10) + 40p11.
```

In particular, every hypothetical cover has `O >= 1712`. The retained row
system is sharp at 1712: `evidence/overlap-bound.json` contains three integer
distance distributions attaining equality while satisfying every retained
row. This means the same row system alone cannot raise the constant.

## Triple-Ball Overlap

Let `T` be the sum of common intersection sizes over unordered triples of
codeword balls. If an ambient word has coverage multiplicity `m`, then

```text
C(m,3) >= C(m,2) - (m-1).
```

The total incidence excess of fifteen radius-3 balls over the 2,048 ambient
words is

```text
15 * 232 - 2048 = 1432.
```

Therefore

```text
T >= O - 1432 >= 280.
```

`tools/verify_overlap_bound.py` checks the integer identity, modular
refinement, three sharp row-system witnesses, and the pointwise
triple-overlap inequality.
