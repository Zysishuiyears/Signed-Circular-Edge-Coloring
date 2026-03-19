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
