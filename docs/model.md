# Mathematical Model

For each oriented edge `e = u -> v`, introduce a base color variable `x_e`.

- If `σ(e) = -`, both incidences use `x_e`.
- If `σ(e) = +`, the tail incidence at `u` uses `x_e`, and the head incidence at `v` uses
  `x_e + r/2` on the circle `C^r`.

At a vertex `v`, for any two distinct incident edges `e_i, e_j`, define:

```text
Δ(v; e_i, e_j) = x_ej - x_ei + (τ(v, e_j) - τ(v, e_i)) * r/2
```

where `τ(v, e) = 1` iff `e` is positive and oriented into `v`, otherwise `0`.

The circular distance condition `d_r(f(v,e_i), f(v,e_j)) >= 1` is encoded by the finite disjunction:

```text
1 <= Δ(v; e_i, e_j) + k r <= r - 1,    for some k in {-1, 0, 1, 2}.
```

This gives a linear real-arithmetic model with a finite number of disjunctive choices, suitable for
exact solving with Z3.
