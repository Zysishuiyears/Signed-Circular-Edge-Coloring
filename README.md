# Signed Graph Circular Edge Coloring

`signedcoloring` is a small Python project for exact computation of the circular edge coloring number
of a signed graph `(G, σ)` under the incidence-color formulation described in the project notes.

## Repository layout

```text
docs/               Mathematical model, input format, and workflow notes
data/instances/     Versioned signed-graph instances
configs/            Parameter-driven sample requests
src/signedcoloring/ Core package: models, IO, solver, verification, CLI
tests/              Unit and integration tests
artifacts/runs/     Raw per-run outputs (ignored by Git)
results/            Curated tables, figures, and notes
scripts/            Thin wrappers only
```

## Quick start

1. Install dependencies:

```powershell
python -m pip install -e .[dev]
```

2. Solve a fixed-`r` decision problem:

```powershell
signedcoloring decide --instance data/instances/star_k1_3_positive.json --r 3
```

3. Optimize the minimum circular length:

```powershell
signedcoloring optimize --instance data/instances/star_k1_3_positive.json
```

4. Verify a saved witness:

```powershell
signedcoloring verify --run-dir artifacts/runs/<timestamp>_star_k1_3_positive_optimize
```

## Input format

Instances are stored as JSON:

```json
{
  "name": "single_positive_edge",
  "vertices": ["u", "v"],
  "edges": [
    {"id": "e1", "u": "u", "v": "v", "sign": "+"}
  ]
}
```

- `sign` accepts `"+"`, `"-"`, `"positive"`, `"negative"`, `"plus"`, `"minus"`.
- Rational parameters such as `r` are best supplied as strings (`"7/2"`, `"3.5"`) to preserve exactness.

## Artifact layout

Each `decide` or `optimize` run writes a timestamped directory under `artifacts/runs/` containing:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `witness.json` when feasible
- `solver_stats.json`

Curated outputs should be copied or summarized into `results/`.
