# Signed Circular Edge Coloring

Exact computation tools for circular edge coloring on signed graphs.

This repository studies concrete signed-graph instances `(G, sigma)` and currently supports:

- `decide`: exact feasibility checking for a fixed circle circumference `r`
- `optimize`: exact optimization of the minimum feasible circumference
- `verify`: independent witness validation
- `classify-signatures`: exact classification of all signatures on a fixed base graph up to
  switching, and optionally up to switching plus graph automorphism

The intended workflow is:

`data/instances -> classify-signatures -> representatives -> decide/optimize -> artifacts/runs -> curated results`

## Quick Start

Install dependencies:

```powershell
python -m pip install -e .[dev]
```

Run a fixed-`r` feasibility check:

```powershell
python -m signedcoloring decide --instance data/instances/star_k1_3_positive.json --r 3
```

Optimize the minimum feasible circumference:

```powershell
python -m signedcoloring optimize --instance data/instances/star_k1_3_positive.json
```

Verify a saved witness:

```powershell
python -m signedcoloring verify --run-dir artifacts/runs/<timestamp>_star_k1_3_positive_optimize
```

Classify all signatures on a fixed base graph up to switching:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json
```

Classify up to switching plus graph automorphism:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json --mode switching+automorphism
```

Keep only classes that contain a representative with exactly `k` negative edges:

```powershell
python -m signedcoloring classify-signatures --instance data/instances/cycle_c4_one_negative.json --k 1
```

## What `classify-signatures` Does

The classification command treats the input JSON as a carrier of the underlying base graph.
Its current edge signs are ignored. The command then:

1. fixes a deterministic vertex order and edge order
2. builds a deterministic spanning forest
3. canonicalizes each switching class by making every forest edge positive
4. uses the non-tree edges as cycle-space bits to enumerate switching classes exactly
5. optionally takes a further quotient by graph automorphisms of the base graph

This classification layer is meant as infrastructure for later experiments of the form:

1. fix a base graph
2. classify all signature types
3. choose class representatives
4. run the existing exact solver on those representatives
5. aggregate which signature types realize extremal circular parameters

## Input Format

Instances are stored as JSON and currently use the same schema for both solving and classification:

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
- For solving commands, rational parameters such as `r` are best supplied as strings such as
  `"7/2"` or `"3.5"` to preserve exactness.
- For `classify-signatures`, the graph structure is used and the stored signs are ignored.

## Output Files

Each `decide` or `optimize` run writes a timestamped directory under `artifacts/runs/` containing:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `witness.json` when feasible
- `solver_stats.json`

Each `classify-signatures` run writes:

- `request.json`
- `instance.snapshot.json`
- `summary.json`
- `classes.json`

`summary.json` records graph size, component count, cycle rank, class counts, bit convention, and
the deterministic edge order used for encoding representatives. `classes.json` stores stable class
representatives and machine-readable metadata that can later be converted back into signed instances.

## Repository Layout

```text
docs/               Mathematical model and workflow notes
data/instances/     Versioned signed-graph instances
configs/            Parameter-driven sample requests
src/signedcoloring/ Core package: models, IO, solver, verification, classification, CLI
tests/              Unit and integration tests
artifacts/runs/     Raw per-run outputs (ignored by Git)
results/            Curated tables, figures, and notes
scripts/            Thin wrappers only
```

## Documentation

- [docs/model.md](docs/model.md): solver model and signature-classification model
- [docs/workflow.md](docs/workflow.md): recommended experiment workflow
