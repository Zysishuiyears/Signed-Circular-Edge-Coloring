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


def test_classify_signatures_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
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
    assert (run_dir / "classes.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    classes_payload = json.loads((run_dir / "classes.json").read_text(encoding="utf-8"))
    assert summary["classification_mode"] == "switching+automorphism"
    assert summary["switching_class_count"] == 2
    assert summary["combined_class_count"] == 2
    assert len(classes_payload["classes"]) == 2


def test_classify_signatures_cli_can_optimize_representatives(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
            "--optimize-representatives",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    optimize_runs_dir = run_dir / "optimize_runs"
    assert optimize_runs_dir.exists()

    subdirs = sorted(path for path in optimize_runs_dir.iterdir() if path.is_dir())
    assert len(subdirs) == 2
    for subdir in subdirs:
        assert (subdir / "request.json").exists()
        assert (subdir / "instance.snapshot.json").exists()
        assert (subdir / "summary.json").exists()
        assert (subdir / "witness.json").exists()
        assert (subdir / "solver_stats.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    classes_payload = json.loads((run_dir / "classes.json").read_text(encoding="utf-8"))
    assert summary["optimize_representatives"] is True
    assert summary["optimized_class_count"] == 2
    assert summary["global_min_best_r"] == "2"
    assert summary["global_max_best_r"] == "8/3"
    assert summary["global_min_class_ids"] == ["class-0001"]
    assert summary["global_max_class_ids"] == ["class-0002"]

    classes = {entry["class_id"]: entry for entry in classes_payload["classes"]}
    assert classes["class-0001"]["best_r"] == "2"
    assert classes["class-0001"]["attains_global_min_best_r"] is True
    assert classes["class-0001"]["attains_global_max_best_r"] is False
    assert classes["class-0002"]["best_r"] == "8/3"
    assert classes["class-0002"]["attains_global_min_best_r"] is False
    assert classes["class-0002"]["attains_global_max_best_r"] is True
    assert "witness" in classes["class-0002"]
    assert "optimize_run_dir" in classes["class-0002"]
