from __future__ import annotations

from datetime import datetime
from pathlib import Path

from signedcoloring.classification import build_signed_instance
from signedcoloring.io import (
    classification_classes_payload,
    classification_summary_payload,
    decision_summary_payload,
    dump_classification_request,
    dump_instance,
    dump_request,
    dump_witness,
    optimization_summary_payload,
    write_json,
)
from signedcoloring.models import (
    ClassificationRequest,
    ClassificationResult,
    DecisionResult,
    OptimizationResult,
    SignedGraphInstance,
    SolveRequest,
)


def create_run_directory(root: Path, instance_name: str, mode: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_dir = root / f"{timestamp}_{instance_name}_{mode}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_decision_artifacts_to_directory(
    run_dir: Path,
    request: SolveRequest,
    instance: SignedGraphInstance,
    result: DecisionResult,
) -> Path:
    write_json(run_dir / "request.json", dump_request(request))
    write_json(run_dir / "instance.snapshot.json", dump_instance(instance))
    write_json(run_dir / "summary.json", decision_summary_payload(result))
    write_json(run_dir / "solver_stats.json", result.stats)
    if result.witness is not None:
        write_json(run_dir / "witness.json", dump_witness(result.witness))
    return run_dir


def write_decision_artifacts(
    request: SolveRequest,
    instance: SignedGraphInstance,
    result: DecisionResult,
) -> Path:
    run_dir = create_run_directory(request.output_dir, instance.name, request.mode)
    return _write_decision_artifacts_to_directory(run_dir, request, instance, result)


def _write_optimization_artifacts_to_directory(
    run_dir: Path,
    request: SolveRequest,
    instance: SignedGraphInstance,
    result: OptimizationResult,
) -> Path:
    write_json(run_dir / "request.json", dump_request(request))
    write_json(run_dir / "instance.snapshot.json", dump_instance(instance))
    write_json(run_dir / "summary.json", optimization_summary_payload(result))
    write_json(run_dir / "solver_stats.json", result.stats)
    if result.witness is not None:
        write_json(run_dir / "witness.json", dump_witness(result.witness))
    return run_dir


def write_optimization_artifacts(
    request: SolveRequest,
    instance: SignedGraphInstance,
    result: OptimizationResult,
) -> Path:
    run_dir = create_run_directory(request.output_dir, instance.name, request.mode)
    return _write_optimization_artifacts_to_directory(run_dir, request, instance, result)


def write_classification_artifacts(
    request: ClassificationRequest,
    instance: SignedGraphInstance,
    result: ClassificationResult,
) -> Path:
    run_dir = create_run_directory(request.output_dir, instance.name, "classify-signatures")
    optimize_run_dirs: dict[str, Path] = {}
    if result.optimize_representatives:
        optimize_root = run_dir / "optimize_runs"
        optimize_root.mkdir(parents=True, exist_ok=False)
        for entry in result.classes:
            if entry.optimization_result is None:
                continue
            representative_instance = build_signed_instance(
                instance,
                entry.representative_signs_by_edge_id,
                name=f"{instance.name}_{entry.class_id}",
            )
            optimize_run_dir = optimize_root / f"{entry.class_id}_optimize"
            optimize_run_dir.mkdir(parents=True, exist_ok=False)
            optimize_request = SolveRequest(
                mode="optimize",
                instance_path=optimize_run_dir / "instance.snapshot.json",
                timeout_ms=request.optimize_timeout_ms,
                output_dir=optimize_root,
                backend="z3",
            )
            _write_optimization_artifacts_to_directory(
                optimize_run_dir,
                optimize_request,
                representative_instance,
                entry.optimization_result,
            )
            optimize_run_dirs[entry.class_id] = optimize_run_dir

    write_json(run_dir / "request.json", dump_classification_request(request))
    write_json(run_dir / "instance.snapshot.json", dump_instance(instance))
    write_json(run_dir / "summary.json", classification_summary_payload(result))
    write_json(
        run_dir / "classes.json",
        classification_classes_payload(result, optimize_run_dirs=optimize_run_dirs),
    )
    return run_dir
