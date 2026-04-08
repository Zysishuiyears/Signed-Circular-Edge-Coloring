from __future__ import annotations

import json
from dataclasses import is_dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from signedcoloring.models import (
    ClassificationRequest,
    ClassificationResult,
    DecisionResult,
    OptimizationResult,
    SignatureClassEntry,
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


def classification_request_from_payload(
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> ClassificationRequest:
    mode = payload.get("mode", "classify-signatures")
    if mode != "classify-signatures":
        raise ValueError(f"Unsupported classification request mode: {mode!r}.")

    return ClassificationRequest(
        instance_path=_resolve_path(payload["instance_path"], base_dir),
        classification_mode=payload.get("classification_mode", "switching-only"),
        classification_backend=payload.get("classification_backend", "generic"),
        jobs=payload.get("jobs", 1),
        k=payload.get("k"),
        limit=payload.get("limit"),
        emit_representatives=payload.get("emit_representatives", False),
        optimize_representatives=payload.get("optimize_representatives", False),
        optimize_timeout_ms=payload.get("optimize_timeout_ms"),
        output_dir=(
            _resolve_path(payload["output_dir"], base_dir)
            if payload.get("output_dir") is not None
            else Path("artifacts/runs")
        ),
    )


def load_classification_request(path: str | Path) -> ClassificationRequest:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    return classification_request_from_payload(payload, base_dir=source.parent)


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


def dump_classification_request(request: ClassificationRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "classify-signatures",
        "instance_path": str(request.instance_path),
        "classification_mode": request.classification_mode,
        "classification_backend": request.classification_backend,
        "jobs": request.jobs,
        "emit_representatives": request.emit_representatives,
        "optimize_representatives": request.optimize_representatives,
        "output_dir": str(request.output_dir),
    }
    if request.k is not None:
        payload["k"] = request.k
    if request.limit is not None:
        payload["limit"] = request.limit
    if request.optimize_timeout_ms is not None:
        payload["optimize_timeout_ms"] = request.optimize_timeout_ms
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


def classification_summary_payload(result: ClassificationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "graph_name": result.graph_name,
        "classification_mode": result.classification_mode,
        "classification_backend": result.classification_backend,
        "num_vertices": result.num_vertices,
        "num_edges": result.num_edges,
        "num_components": result.num_components,
        "cycle_rank": result.cycle_rank,
        "theoretical_switching_class_count": result.theoretical_switching_class_count,
        "switching_class_count": result.switching_class_count,
        "bit_convention": result.bit_convention,
        "representative_encoding": "bitstring over edge_order",
        "cycle_bit_encoding": "bitstring over non-tree edges after forest canonicalization",
        "edge_order": list(result.edge_order),
        "k_filter_applied": result.k is not None,
        "optimize_representatives": result.optimize_representatives,
        "stats": to_jsonable(result.stats),
    }
    if result.combined_class_count is not None:
        payload["combined_class_count"] = result.combined_class_count
    if result.k is not None:
        payload["k"] = result.k
    if result.optimized_class_count is not None:
        payload["optimized_class_count"] = result.optimized_class_count
    if result.delta is not None:
        payload["delta"] = result.delta
    if result.global_min_best_r is not None:
        payload["global_min_best_r"] = fraction_to_string(result.global_min_best_r)
    if result.global_max_best_r is not None:
        payload["global_max_best_r"] = fraction_to_string(result.global_max_best_r)
    if result.global_min_class_ids:
        payload["global_min_class_ids"] = list(result.global_min_class_ids)
    if result.global_max_class_ids:
        payload["global_max_class_ids"] = list(result.global_max_class_ids)
    if result.global_min_representative_codes:
        payload["global_min_representative_codes"] = list(result.global_min_representative_codes)
    if result.global_max_representative_codes:
        payload["global_max_representative_codes"] = list(result.global_max_representative_codes)
    return payload


def _class_entry_payload(
    entry: SignatureClassEntry,
    *,
    optimize_run_dirs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "class_id": entry.class_id,
        "representative_code": entry.representative_code,
        "cycle_bit_code": entry.cycle_bit_code,
        "representative_bits": list(entry.representative_bits),
        "representative_signs_by_edge_id": dict(entry.representative_signs_by_edge_id),
    }
    if entry.switching_orbit_size is not None:
        payload["switching_orbit_size"] = entry.switching_orbit_size
    if entry.automorphism_orbit_size is not None:
        payload["automorphism_orbit_size"] = entry.automorphism_orbit_size
    if entry.reachable_negative_edge_counts is not None:
        payload["reachable_negative_edge_counts"] = list(entry.reachable_negative_edge_counts)
    if entry.negative_edge_ids is not None:
        payload["negative_edge_ids"] = list(entry.negative_edge_ids)
    if entry.negative_edges is not None:
        payload["negative_edges"] = [
            {"edge_id": edge_id, "u": u, "v": v} for edge_id, u, v in entry.negative_edges
        ]
    if entry.best_r is not None:
        payload["best_r"] = fraction_to_string(entry.best_r)
    if entry.best_r_minus_delta is not None:
        payload["best_r_minus_delta"] = fraction_to_string(entry.best_r_minus_delta)
    if entry.best_r_over_delta is not None:
        payload["best_r_over_delta"] = fraction_to_string(entry.best_r_over_delta)
    if entry.optimize_status is not None:
        payload["optimize_status"] = entry.optimize_status
    if entry.witness is not None:
        payload["witness"] = dump_witness(entry.witness)
    if entry.attains_global_min_best_r is not None:
        payload["attains_global_min_best_r"] = entry.attains_global_min_best_r
    if entry.attains_global_max_best_r is not None:
        payload["attains_global_max_best_r"] = entry.attains_global_max_best_r
    if optimize_run_dirs is not None and entry.class_id in optimize_run_dirs:
        payload["optimize_run_dir"] = str(optimize_run_dirs[entry.class_id])
    return payload


def classification_classes_payload(
    result: ClassificationResult,
    *,
    optimize_run_dirs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    return {
        "graph_name": result.graph_name,
        "classification_mode": result.classification_mode,
        "bit_convention": result.bit_convention,
        "edge_order": list(result.edge_order),
        "classes": [
            _class_entry_payload(entry, optimize_run_dirs=optimize_run_dirs)
            for entry in result.classes
        ],
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
