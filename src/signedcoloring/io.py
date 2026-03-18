from __future__ import annotations

import json
from dataclasses import is_dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from signedcoloring.models import (
    DecisionResult,
    OptimizationResult,
    SignedEdge,
    SignedGraphInstance,
    SolveRequest,
    VerificationResult,
    Witness,
)
from signedcoloring.rational import fraction_to_string, parse_fraction

SIGN_ALIASES = {
    "+": "+",
    "plus": "+",
    "positive": "+",
    "-": "-",
    "minus": "-",
    "negative": "-",
}


def _normalize_sign(raw_sign: Any) -> str:
    normalized = str(raw_sign).strip().lower()
    if normalized not in SIGN_ALIASES:
        raise ValueError(f"Unsupported edge sign: {raw_sign!r}.")
    return SIGN_ALIASES[normalized]


def _resolve_path(raw_path: str | Path, base_dir: Path | None = None) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    if base_dir is not None:
        return (base_dir / path).resolve()
    return path.resolve()


def load_instance(path: str | Path) -> SignedGraphInstance:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    vertices = tuple(str(vertex) for vertex in payload["vertices"])
    edges = tuple(
        SignedEdge(
            id=str(edge_payload["id"]),
            u=str(edge_payload["u"]),
            v=str(edge_payload["v"]),
            sign=_normalize_sign(edge_payload["sign"]),
        )
        for edge_payload in payload["edges"]
    )
    return SignedGraphInstance(
        name=str(payload["name"]),
        vertices=vertices,
        edges=edges,
    )


def dump_instance(instance: SignedGraphInstance) -> dict[str, Any]:
    return {
        "name": instance.name,
        "vertices": list(instance.vertices),
        "edges": [
            {
                "id": edge.id,
                "u": edge.u,
                "v": edge.v,
                "sign": edge.sign,
            }
            for edge in instance.edges
        ],
    }


def request_from_payload(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
    default_mode: str | None = None,
) -> SolveRequest:
    mode = payload.get("mode", default_mode)
    if mode is None:
        raise ValueError("Request payload is missing mode.")

    return SolveRequest(
        mode=mode,
        instance_path=_resolve_path(payload["instance_path"], base_dir),
        r=parse_fraction(payload["r"]) if payload.get("r") is not None else None,
        timeout_ms=payload.get("timeout_ms"),
        output_dir=(
            _resolve_path(payload["output_dir"], base_dir)
            if payload.get("output_dir") is not None
            else Path("artifacts/runs")
        ),
        backend=payload.get("backend", "z3"),
    )


def load_request(path: str | Path, *, default_mode: str | None = None) -> SolveRequest:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    return request_from_payload(payload, base_dir=source.parent, default_mode=default_mode)


def dump_request(request: SolveRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": request.mode,
        "instance_path": str(request.instance_path),
        "output_dir": str(request.output_dir),
        "backend": request.backend,
    }
    if request.r is not None:
        payload["r"] = fraction_to_string(request.r)
    if request.timeout_ms is not None:
        payload["timeout_ms"] = request.timeout_ms
    return payload


def load_witness(path: str | Path) -> Witness:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    base_colors = {
        edge_id: parse_fraction(value) for edge_id, value in payload["base_colors"].items()
    }
    incidence_colors = {
        edge_id: {vertex: parse_fraction(value) for vertex, value in color_map.items()}
        for edge_id, color_map in payload["incidence_colors"].items()
    }
    return Witness(
        r=parse_fraction(payload["r"]),
        base_colors=base_colors,
        incidence_colors=incidence_colors,
    )


def dump_witness(witness: Witness) -> dict[str, Any]:
    return {
        "r": fraction_to_string(witness.r),
        "base_colors": {
            edge_id: fraction_to_string(color)
            for edge_id, color in sorted(witness.base_colors.items())
        },
        "incidence_colors": {
            edge_id: {
                vertex: fraction_to_string(color) for vertex, color in sorted(vertex_colors.items())
            }
            for edge_id, vertex_colors in sorted(witness.incidence_colors.items())
        },
    }


def decision_summary_payload(result: DecisionResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "decide",
        "status": result.status,
        "feasible": result.feasible,
        "r": fraction_to_string(result.r),
        "stats": to_jsonable(result.stats),
    }
    if result.witness is not None:
        payload["witness_available"] = True
    return payload


def optimization_summary_payload(result: OptimizationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "optimize",
        "status": result.status,
        "lower_bound": fraction_to_string(result.lower_bound),
        "upper_bound": fraction_to_string(result.upper_bound),
        "stats": to_jsonable(result.stats),
    }
    if result.best_r is not None:
        payload["best_r"] = fraction_to_string(result.best_r)
    if result.witness is not None:
        payload["witness_available"] = True
    return payload


def verification_payload(result: VerificationResult) -> dict[str, Any]:
    return {
        "valid": result.valid,
        "messages": list(result.messages),
        "stats": to_jsonable(result.stats),
    }


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Fraction):
        return fraction_to_string(value)
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: to_jsonable(raw_value) for key, raw_value in value.__dict__.items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(to_jsonable(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
