# Workflow Notes

## Recommended experiment loop

1. Add or update a base graph instance in `data/instances/`.
2. Run `classify-signatures` to enumerate switching classes, or switching-plus-automorphism classes.
3. Inspect the generated `classes.json` and choose stable representatives.
4. Convert selected representatives into signed instances for `decide` or `optimize`.
5. Inspect raw outputs under `artifacts/runs/`.
6. Copy stable summaries into `results/tables/` or `results/notes/`.

## Raw versus curated outputs

- `artifacts/runs/` is for parameter-driven raw outputs and is ignored by Git.
- `results/` is for curated outputs that should be tracked and shared.

## Classification-first workflow

The new classification command is intended as research infrastructure for experiments of the form:

```text
fixed base graph
-> switching classes
-> switching + automorphism classes
-> representative signatures
-> exact solver
-> aggregate circular parameter data
```

This keeps representative generation separate from the exact coloring solver and makes later
comparative experiments easier to organize.

## Exactness and scope

- `decide`, `optimize`, and `verify` remain exact.
- `classify-signatures` enumerates switching classes exactly via cycle-space bits.
- The optional `k` filter is also exact, but intended for small and medium instances.
- No performance claims are made for large-scale exhaustive graph-family studies yet.

## Practical scale notes

The current `classify-signatures` implementation is exact but generic. In the current branch:

- switching classes are enumerated by a serial `2^beta` loop
- automorphisms are enumerated serially before quotienting
- `--optimize-representatives` runs each representative `optimize` serially
- the solver currently sets only `timeout`; it does not explicitly configure multi-core Z3 search

Because of that, moving the project to a stronger server usually improves wall-clock time for instances that are already close to feasible, but it does not automatically turn a combinatorially explosive instance into a realistic one.

Use the following rule of thumb before launching a larger experiment:

| Condition | Current expectation |
| --- | --- |
| `beta <= 9` | Usually practical on the current generic backend |
| `beta ≈ 10-14` | Boundary zone; strongly depends on `|Aut(G)|`, `--k`, and `--optimize-representatives` |
| `beta >= 20` | Usually unrealistic for `switching+automorphism` on the current branch |

Current anchor points in this repository are consistent with that table:

- small cycle examples are trivial
- Petersen has `beta = 6` and is practical
- `K_{4,4}` has `beta = 9` and is practical on the current branch
- `K_{6,6}` has `beta = 25` and is not currently realistic under the generic exact backend
