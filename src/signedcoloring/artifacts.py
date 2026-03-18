from __future__ import annotations

from datetime import datetime
from pathlib import Path

from signedcoloring.io import (
    decision_summary_payload,
    dump_instance,
    dump_request,
    dump_witness,
    optimization_summary_payload,
    write_json,
)
from signedcoloring.models import (
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


def write_decision_artifacts(
    request: SolveRequest,
    instance: SignedGraphInstance,
    result: DecisionResult,
) -> Path:
    run_dir = create_run_directory(request.output_dir, instance.name, request.mode)
    write_json(run_dir / "request.json", dump_request(request))
    write_json(run_dir / "instance.snapshot.json", dump_instance(instance))
    write_json(run_dir / "summary.json", decision_summary_payload(result))
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
    write_json(run_dir / "request.json", dump_request(request))
    write_json(run_dir / "instance.snapshot.json", dump_instance(instance))
    write_json(run_dir / "summary.json", optimization_summary_payload(result))
    write_json(run_dir / "solver_stats.json", result.stats)
    if result.witness is not None:
        write_json(run_dir / "witness.json", dump_witness(result.witness))
    return run_dir
