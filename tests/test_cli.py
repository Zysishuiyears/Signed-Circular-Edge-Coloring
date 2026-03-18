from __future__ import annotations

import json
from pathlib import Path

from signedcoloring.cli import main


def test_optimize_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "star_k1_3_positive.json"
    )

    exit_code = main(
        [
            "optimize",
            "--instance",
            str(instance_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    assert (run_dir / "request.json").exists()
    assert (run_dir / "instance.snapshot.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "witness.json").exists()
    assert (run_dir / "solver_stats.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["best_r"] == "3"
