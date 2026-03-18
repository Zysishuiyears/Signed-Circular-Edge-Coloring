from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from signedcoloring.artifacts import write_decision_artifacts, write_optimization_artifacts
from signedcoloring.io import load_instance, load_request, load_witness, verification_payload
from signedcoloring.models import SolveRequest
from signedcoloring.rational import parse_fraction
from signedcoloring.solver import solve_decision, solve_optimization
from signedcoloring.verify import verify_witness


def _build_request_from_args(args: argparse.Namespace, mode: str) -> SolveRequest:
    payload: dict[str, Any] = {}

    if args.config is not None:
        request = load_request(args.config, default_mode=mode)
        payload = {
            "mode": request.mode,
            "instance_path": str(request.instance_path),
            "r": str(request.r) if request.r is not None else None,
            "timeout_ms": request.timeout_ms,
            "output_dir": str(request.output_dir),
            "backend": request.backend,
        }
    else:
        payload["mode"] = mode

    if args.instance is not None:
        payload["instance_path"] = str(Path(args.instance).resolve())
    if getattr(args, "r", None) is not None:
        payload["r"] = args.r
    if args.timeout_ms is not None:
        payload["timeout_ms"] = args.timeout_ms
    if args.output_dir is not None:
        payload["output_dir"] = str(Path(args.output_dir).resolve())
    if args.backend is not None:
        payload["backend"] = args.backend

    if "instance_path" not in payload:
        raise ValueError("An instance path is required.")

    return SolveRequest(
        mode=mode,
        instance_path=Path(payload["instance_path"]),
        r=parse_fraction(payload["r"]) if payload.get("r") is not None else None,
        timeout_ms=payload.get("timeout_ms"),
        output_dir=Path(payload.get("output_dir", "artifacts/runs")),
        backend=payload.get("backend", "z3"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Signed graph circular edge coloring tools.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    decide_parser = subparsers.add_parser("decide", help="Check whether a fixed r is feasible.")
    decide_parser.add_argument("--config", type=Path, help="JSON request file.")
    decide_parser.add_argument(
        "--instance", type=Path, help="Path to the signed-graph instance JSON."
    )
    decide_parser.add_argument(
        "--r", help="Circle circumference as an exact rational, e.g. 3 or 7/2."
    )
    decide_parser.add_argument(
        "--timeout-ms", type=int, help="Optional Z3 timeout in milliseconds."
    )
    decide_parser.add_argument("--output-dir", type=Path, help="Root directory for run artifacts.")
    decide_parser.add_argument(
        "--backend", default=None, help="Solver backend. Only z3 is supported."
    )

    optimize_parser = subparsers.add_parser(
        "optimize", help="Minimize the feasible circumference r."
    )
    optimize_parser.add_argument("--config", type=Path, help="JSON request file.")
    optimize_parser.add_argument(
        "--instance", type=Path, help="Path to the signed-graph instance JSON."
    )
    optimize_parser.add_argument(
        "--timeout-ms", type=int, help="Optional Z3 timeout in milliseconds."
    )
    optimize_parser.add_argument(
        "--output-dir", type=Path, help="Root directory for run artifacts."
    )
    optimize_parser.add_argument(
        "--backend", default=None, help="Solver backend. Only z3 is supported."
    )

    verify_parser = subparsers.add_parser("verify", help="Verify a saved witness independently.")
    verify_parser.add_argument(
        "--instance", type=Path, help="Path to the signed-graph instance JSON."
    )
    verify_parser.add_argument("--witness", type=Path, help="Path to a witness JSON file.")
    verify_parser.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory containing instance.snapshot.json and witness.json.",
    )

    return parser


def _run_decide(args: argparse.Namespace) -> int:
    request = _build_request_from_args(args, mode="decide")
    instance = load_instance(request.instance_path)
    result = solve_decision(instance, r=request.r, timeout_ms=request.timeout_ms)
    run_dir = write_decision_artifacts(request, instance, result)

    print(f"status: {result.status}")
    print(f"feasible: {result.feasible}")
    print(f"r: {result.r}")
    print(f"run_dir: {run_dir}")
    return 0 if result.feasible else 1


def _run_optimize(args: argparse.Namespace) -> int:
    request = _build_request_from_args(args, mode="optimize")
    instance = load_instance(request.instance_path)
    result = solve_optimization(instance, timeout_ms=request.timeout_ms)
    run_dir = write_optimization_artifacts(request, instance, result)

    print(f"status: {result.status}")
    print(f"best_r: {result.best_r}")
    print(f"lower_bound: {result.lower_bound}")
    print(f"upper_bound: {result.upper_bound}")
    print(f"run_dir: {run_dir}")
    return 0 if result.best_r is not None else 2


def _run_verify(args: argparse.Namespace) -> int:
    if args.run_dir is not None:
        instance_path = args.run_dir / "instance.snapshot.json"
        witness_path = args.run_dir / "witness.json"
    else:
        if args.instance is None or args.witness is None:
            raise ValueError("verify requires either --run-dir or both --instance and --witness.")
        instance_path = args.instance
        witness_path = args.witness

    instance = load_instance(instance_path)
    witness = load_witness(witness_path)
    result = verify_witness(instance, witness)

    print(json.dumps(verification_payload(result), indent=2, ensure_ascii=False))
    return 0 if result.valid else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "decide":
            return _run_decide(args)
        if args.command == "optimize":
            return _run_optimize(args)
        if args.command == "verify":
            return _run_verify(args)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unknown command: {args.command}") 
    return 2
