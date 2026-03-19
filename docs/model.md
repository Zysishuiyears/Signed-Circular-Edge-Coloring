# Mathematical Model

## 1. Circular edge coloring solver

For each oriented edge `e = u -> v`, the solver introduces a base color variable `x_e`.

- If `sigma(e) = -`, both incidences use `x_e`.
- If `sigma(e) = +`, the tail incidence at `u` uses `x_e` and the head incidence at `v` uses
  `x_e + r/2` on the circle `C^r`.

At a vertex `v`, for distinct incident edges `e_i, e_j`, define

```text
Delta(v; e_i, e_j) = x_ej - x_ei + (tau(v, e_j) - tau(v, e_i)) * r/2
```

where `tau(v, e) = 1` iff `e` is positive and oriented into `v`, otherwise `0`.

The circular distance condition `d_r(f(v,e_i), f(v,e_j)) >= 1` is encoded by

```text
1 <= Delta(v; e_i, e_j) + k r <= r - 1,    for some k in {-1, 0, 1, 2}.
```

This yields an exact linear real-arithmetic model with finitely many disjunctive choices, solved by
Z3.

## 2. Switching classification on a fixed base graph

For a fixed undirected base graph `G = (V, E)`, a signature is represented as a bit vector on the
edges under a deterministic edge order:

- bit `0` means positive
- bit `1` means negative

Switching at a vertex subset `X` toggles exactly the edges in the cut `delta(X)`. In bit language,
an edge bit is flipped iff exactly one endpoint of that edge lies in `X`.

To classify signatures up to switching, the implementation fixes a deterministic spanning forest `T`.
Every switching class has a unique canonical representative in which all forest edges are positive.
The remaining non-tree edges then record the cycle-space bits of the class.

If `c(G)` is the number of connected components, then the cycle rank is

```text
beta(G) = |E| - |V| + c(G),
```

and the number of switching classes is `2^beta(G)`.

## 3. Switching plus automorphism quotient

After canonical switching representatives are computed, the code may further quotient by graph
automorphisms of the fixed base graph.

For each switching representative:

1. apply every automorphism of the base graph
2. canonicalize the image again by switching
3. take the lexicographically smallest canonical code

That smallest code is used as the stable representative of the combined
switching-plus-automorphism class.

## 4. Negative-edge filtering

The optional parameter `k` keeps only those classes for which there exists at least one signature in
the class with exactly `k` negative edges.

This is implemented exactly for small and medium instances by enumerating the root-fixed switching
orbit inside each switching class. The number of negative edges is not treated as a switching
invariant.
