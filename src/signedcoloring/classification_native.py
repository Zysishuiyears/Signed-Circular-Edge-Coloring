from __future__ import annotations

from typing import Any

try:
    from signedcoloring import _classification_native as _native
except ImportError:  # pragma: no cover - exercised through integration behavior
    _native = None


def native_module_available() -> bool:
    return _native is not None


def run_native_canonical_scan(
    *,
    num_vertices: int,
    edge_endpoints: tuple[tuple[int, int], ...],
    non_tree_edge_indices: tuple[int, ...],
    jobs: int,
) -> dict[str, Any]:
    if _native is None:
        raise ImportError(
            "The native classification backend is unavailable. "
            "Reinstall the project with a working C++ toolchain, pybind11, and vendored Bliss "
            "sources, then retry with --classification-backend native-orbit-search."
        )

    result = _native.canonical_scan(
        num_vertices,
        [tuple(endpoint_pair) for endpoint_pair in edge_endpoints],
        list(non_tree_edge_indices),
        jobs,
    )
    return {
        "classes": tuple(
            {
                "cycle_mask": int(entry["cycle_mask"]),
                "switching_class_count": int(entry["switching_class_count"]),
            }
            for entry in result["classes"]
        ),
        "jobs_used": int(result["jobs_used"]),
        "enumerated_switching_class_count": int(result["enumerated_switching_class_count"]),
        "generator_count": int(result["generator_count"]),
        "merge_elapsed_seconds": float(result["merge_elapsed_seconds"]),
        "native_elapsed_seconds": float(result["native_elapsed_seconds"]),
    }
