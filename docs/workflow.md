# Workflow Notes

## Recommended loop

1. Add or update an instance in `data/instances/`.
2. Run `signedcoloring decide` or `signedcoloring optimize`.
3. Inspect the raw output under `artifacts/runs/`.
4. Copy stable summaries into `results/tables/` or `results/notes/`.

## Raw versus curated outputs

- `artifacts/runs/` is for parameter-driven raw outputs and is ignored by Git.
- `results/` is for curated outputs that should be tracked and shared.

## Config-driven runs

Sample request JSON files live in `configs/`. The CLI accepts `--config` for both `decide` and
`optimize`, so experiment parameters can be versioned separately from the code.
