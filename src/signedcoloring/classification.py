from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from fractions import Fraction
from time import perf_counter

import networkx as nx
from networkx.algorithms import isomorphism

from signedcoloring.classification_native import run_native_canonical_scan
from signedcoloring.models import (
    ClassificationBackend,
    ClassificationMode,
    ClassificationResult,
    OptimizationResult,
    SignatureClassEntry,
    SignedEdge,
    SignedGraphInstance,
)
from signedcoloring.solver import solve_optimization

POSITIVE_BIT = 0
NEGATIVE_BIT = 1
BIT_CONVENTION = "0=+,1=-"
EXACT_PREFERRED_SWITCHING_CLASS_LIMIT = 1 << 12


@dataclass(frozen=True)
class _GraphStructure:
    vertex_order: tuple[str, ...]
    vertex_index: dict[str, int]
    edge_order: tuple[SignedEdge, ...]
    edge_endpoints: tuple[tuple[int, int], ...]
    edge_index_by_pair: dict[tuple[str, str], int]
    tree_edge_indices: tuple[int, ...]
    non_tree_edge_indices: tuple[int, ...]
    component_roots: tuple[int, ...]
    free_vertex_indices: tuple[int, ...]
    tree_adjacency: tuple[tuple[tuple[int, int], ...], ...]
    num_components: int
    cycle_rank: int
    switching_orbit_size: int


@dataclass(frozen=True)
class _SwitchingClassRecord:
    representative_bits: tuple[int, ...]
    cycle_bits: tuple[int, ...]
    switching_orbit_size: int
    reachable_negative_edge_counts: tuple[int, ...] | None


def _normalized_pair(u: str, v: str) -> tuple[str, str]:
    return (u, v) if u <= v else (v, u)


def deterministic_vertex_order(instance: SignedGraphInstance) -> tuple[str, ...]:
    return tuple(sorted(instance.vertices))


def deterministic_edge_order(instance: SignedGraphInstance) -> tuple[SignedEdge, ...]:
    return tuple(
        sorted(
            instance.edges,
            key=lambda edge: (_normalized_pair(edge.u, edge.v), edge.id),
        )
    )


def build_graph_structure(instance: SignedGraphInstance) -> _GraphStructure:
    vertex_order = deterministic_vertex_order(instance)
    vertex_index = {vertex: index for index, vertex in enumerate(vertex_order)}
    edge_order = deterministic_edge_order(instance)
    edge_endpoints = tuple((vertex_index[edge.u], vertex_index[edge.v]) for edge in edge_order)
    edge_index_by_pair = {
        _normalized_pair(edge.u, edge.v): index for index, edge in enumerate(edge_order)
    }

    parents = list(range(len(vertex_order)))

    def find(node: int) -> int:
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    def union(left: int, right: int) -> bool:
        root_left = find(left)
        root_right = find(right)
        if root_left == root_right:
            return False
        parents[root_right] = root_left
        return True

    tree_edge_indices: list[int] = []
    non_tree_edge_indices: list[int] = []
    adjacency: list[list[tuple[int, int]]] = [[] for _ in vertex_order]

    for edge_index, (left, right) in enumerate(edge_endpoints):
        if union(left, right):
            tree_edge_indices.append(edge_index)
            adjacency[left].append((right, edge_index))
            adjacency[right].append((left, edge_index))
        else:
            non_tree_edge_indices.append(edge_index)

    graph = instance.to_networkx()
    components = sorted(
        (tuple(sorted(component)) for component in nx.connected_components(graph)),
        key=lambda component: component[0],
    )
    component_roots = tuple(vertex_index[component[0]] for component in components)
    free_vertex_indices = tuple(
        index for index in range(len(vertex_order)) if index not in set(component_roots)
    )

    return _GraphStructure(
        vertex_order=vertex_order,
        vertex_index=vertex_index,
        edge_order=edge_order,
        edge_endpoints=edge_endpoints,
        edge_index_by_pair=edge_index_by_pair,
        tree_edge_indices=tuple(tree_edge_indices),
        non_tree_edge_indices=tuple(non_tree_edge_indices),
        component_roots=component_roots,
        free_vertex_indices=free_vertex_indices,
        tree_adjacency=tuple(tuple(neighbors) for neighbors in adjacency),
        num_components=len(components),
        cycle_rank=len(non_tree_edge_indices),
        switching_orbit_size=1 << max(0, len(vertex_order) - len(components)),
    )


def build_spanning_forest(
    instance: SignedGraphInstance,
) -> tuple[tuple[SignedEdge, ...], tuple[SignedEdge, ...]]:
    structure = build_graph_structure(instance)
    tree_edges = tuple(structure.edge_order[index] for index in structure.tree_edge_indices)
    non_tree_edges = tuple(structure.edge_order[index] for index in structure.non_tree_edge_indices)
    return tree_edges, non_tree_edges


def signature_to_bits(
    instance: SignedGraphInstance,
    edge_order: tuple[SignedEdge, ...] | None = None,
) -> tuple[int, ...]:
    ordered_edges = edge_order or deterministic_edge_order(instance)
    return tuple(POSITIVE_BIT if edge.sign == "+" else NEGATIVE_BIT for edge in ordered_edges)


def _apply_switch_flags(
    bits: tuple[int, ...],
    switch_flags: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    switched_bits = []
    for edge_index, bit in enumerate(bits):
        left, right = structure.edge_endpoints[edge_index]
        switched_bits.append(bit ^ switch_flags[left] ^ switch_flags[right])
    return tuple(switched_bits)


def switch_signature(
    bits: tuple[int, ...],
    vertex_subset: set[str] | tuple[str, ...] | list[str],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    switch_flags = [0] * len(structure.vertex_order)
    for vertex in vertex_subset:
        switch_flags[structure.vertex_index[vertex]] = 1
    return _apply_switch_flags(bits, tuple(switch_flags), structure)


def canonical_switching_rep(
    bits: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    switch_flags = [0] * len(structure.vertex_order)
    visited: set[int] = set()

    for root in structure.component_roots:
        stack = [root]
        visited.add(root)
        while stack:
            vertex = stack.pop()
            for neighbor, edge_index in structure.tree_adjacency[vertex]:
                if neighbor in visited:
                    continue
                switch_flags[neighbor] = switch_flags[vertex] ^ bits[edge_index]
                visited.add(neighbor)
                stack.append(neighbor)

    return _apply_switch_flags(bits, tuple(switch_flags), structure)


def switching_class_cycle_bits(
    bits: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    canonical_bits = canonical_switching_rep(bits, structure)
    return tuple(canonical_bits[index] for index in structure.non_tree_edge_indices)


def reconstruct_from_cycle_bits(
    cycle_bits: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    if len(cycle_bits) != len(structure.non_tree_edge_indices):
        raise ValueError("cycle_bits length does not match the graph cycle rank.")
    bits = [POSITIVE_BIT] * len(structure.edge_order)
    for offset, edge_index in enumerate(structure.non_tree_edge_indices):
        bits[edge_index] = cycle_bits[offset]
    return tuple(bits)


def is_switching_equivalent(
    left_bits: tuple[int, ...],
    right_bits: tuple[int, ...],
    structure: _GraphStructure,
) -> bool:
    return canonical_switching_rep(left_bits, structure) == canonical_switching_rep(
        right_bits, structure
    )


def _bits_to_code(bits: tuple[int, ...]) -> str:
    return "".join(str(bit) for bit in bits)


def _int_to_bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> shift) & 1 for shift in reversed(range(width)))


def _bits_to_signs_by_edge_id(
    bits: tuple[int, ...],
    structure: _GraphStructure,
) -> dict[str, str]:
    signs: dict[str, str] = {}
    for bit, edge in zip(bits, structure.edge_order, strict=True):
        signs[edge.id] = "+" if bit == POSITIVE_BIT else "-"
    return signs


def _negative_edge_ids_from_bits(
    bits: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[str, ...]:
    return tuple(
        edge.id
        for bit, edge in zip(bits, structure.edge_order, strict=True)
        if bit == NEGATIVE_BIT
    )


def _negative_edges_from_ids(
    edge_ids: tuple[str, ...],
    structure: _GraphStructure,
) -> tuple[tuple[str, str, str], ...]:
    edge_by_id = {edge.id: edge for edge in structure.edge_order}
    return tuple((edge_id, edge_by_id[edge_id].u, edge_by_id[edge_id].v) for edge_id in edge_ids)


def _switch_flags_from_mask(mask: int, structure: _GraphStructure) -> tuple[int, ...]:
    switch_flags = [0] * len(structure.vertex_order)
    for offset, vertex_index in enumerate(structure.free_vertex_indices):
        if (mask >> offset) & 1:
            switch_flags[vertex_index] = 1
    return tuple(switch_flags)


def _preferred_display_bits_from_switching_class_reps(
    representative_bits_orbit: tuple[tuple[int, ...], ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    best_bits: tuple[int, ...] | None = None
    free_switch_count = 1 << len(structure.free_vertex_indices)

    for switching_class_bits in representative_bits_orbit:
        for mask in range(free_switch_count):
            switch_flags = _switch_flags_from_mask(mask, structure)
            candidate_bits = _apply_switch_flags(
                switching_class_bits,
                switch_flags,
                structure,
            )
            if best_bits is None:
                best_bits = candidate_bits
                continue
            candidate_key = (sum(candidate_bits), candidate_bits)
            best_key = (sum(best_bits), best_bits)
            if candidate_key < best_key:
                best_bits = candidate_bits

    if best_bits is None:
        raise ValueError("At least one representative is required to compute a preferred display.")

    return best_bits


def _entry_with_preferred_display_bits(
    entry: SignatureClassEntry,
    preferred_bits: tuple[int, ...],
    structure: _GraphStructure,
) -> SignatureClassEntry:
    preferred_negative_edge_ids = _negative_edge_ids_from_bits(preferred_bits, structure)
    return replace(
        entry,
        preferred_representative_code=_bits_to_code(preferred_bits),
        preferred_representative_bits=preferred_bits,
        preferred_representative_signs_by_edge_id=_bits_to_signs_by_edge_id(
            preferred_bits,
            structure,
        ),
        preferred_negative_edge_ids=preferred_negative_edge_ids,
        preferred_negative_edges=_negative_edges_from_ids(preferred_negative_edge_ids, structure),
        preferred_negative_edge_count=len(preferred_negative_edge_ids),
    )


def _reachable_negative_edge_counts(
    representative_bits: tuple[int, ...],
    structure: _GraphStructure,
) -> tuple[int, ...]:
    counts: set[int] = set()
    free_vertices = structure.free_vertex_indices

    for mask in range(1 << len(free_vertices)):
        switch_flags = [0] * len(structure.vertex_order)
        for offset, vertex_index in enumerate(free_vertices):
            if (mask >> offset) & 1:
                switch_flags[vertex_index] = 1
        switched_bits = _apply_switch_flags(
            representative_bits,
            tuple(switch_flags),
            structure,
        )
        counts.add(sum(switched_bits))

    return tuple(sorted(counts))


def _make_signature_class_entry(
    *,
    class_number: int,
    representative_bits: tuple[int, ...],
    cycle_bits: tuple[int, ...],
    structure: _GraphStructure,
    switching_orbit_size: int | None = None,
    automorphism_orbit_size: int | None = None,
    reachable_negative_edge_counts: tuple[int, ...] | None = None,
) -> SignatureClassEntry:
    entry = SignatureClassEntry(
        class_id=f"class-{class_number:04d}",
        representative_code=_bits_to_code(representative_bits),
        cycle_bit_code=_bits_to_code(cycle_bits),
        representative_bits=representative_bits,
        representative_signs_by_edge_id=_bits_to_signs_by_edge_id(
            representative_bits,
            structure,
        ),
        switching_orbit_size=switching_orbit_size,
        automorphism_orbit_size=automorphism_orbit_size,
        reachable_negative_edge_counts=reachable_negative_edge_counts,
    )
    return _entry_with_preferred_display_bits(entry, representative_bits, structure)


def _solve_class_entry_optimization_task(
    task: tuple[SignedGraphInstance, str, dict[str, str], int | None],
) -> tuple[str, OptimizationResult]:
    instance, class_id, representative_signs_by_edge_id, timeout_ms = task
    representative_instance = build_signed_instance(
        instance,
        representative_signs_by_edge_id,
        name=f"{instance.name}_{class_id}",
    )
    return class_id, solve_optimization(representative_instance, timeout_ms=timeout_ms)


def enumerate_switching_classes(
    instance: SignedGraphInstance,
    *,
    k: int | None = None,
    include_reachable_negative_edge_counts: bool = False,
    structure: _GraphStructure | None = None,
) -> tuple[_SwitchingClassRecord, ...]:
    structure = structure or build_graph_structure(instance)
    records: list[_SwitchingClassRecord] = []

    for value in range(1 << structure.cycle_rank):
        cycle_bits = _int_to_bits(value, structure.cycle_rank)
        representative_bits = reconstruct_from_cycle_bits(cycle_bits, structure)
        reachable_negative_edge_counts = None
        if k is not None or include_reachable_negative_edge_counts:
            reachable_negative_edge_counts = _reachable_negative_edge_counts(
                representative_bits,
                structure,
            )
        if k is not None:
            if k not in reachable_negative_edge_counts:
                continue

        records.append(
            _SwitchingClassRecord(
                representative_bits=representative_bits,
                cycle_bits=cycle_bits,
                switching_orbit_size=structure.switching_orbit_size,
                reachable_negative_edge_counts=reachable_negative_edge_counts,
            )
        )

    return tuple(records)


def compute_automorphisms(
    instance: SignedGraphInstance,
    *,
    structure: _GraphStructure | None = None,
) -> tuple[tuple[int, ...], ...]:
    structure = structure or build_graph_structure(instance)
    graph = nx.Graph()
    graph.add_nodes_from(structure.vertex_order)
    graph.add_edges_from((_normalized_pair(edge.u, edge.v) for edge in structure.edge_order))

    matcher = isomorphism.GraphMatcher(graph, graph)
    seen: set[tuple[int, ...]] = set()
    automorphisms: list[tuple[int, ...]] = []

    for mapping in matcher.isomorphisms_iter():
        image = tuple(structure.vertex_index[mapping[vertex]] for vertex in structure.vertex_order)
        if image not in seen:
            seen.add(image)
            automorphisms.append(image)

    automorphisms.sort()
    return tuple(automorphisms)


def _apply_automorphism(
    bits: tuple[int, ...],
    structure: _GraphStructure,
    automorphism: tuple[int, ...],
) -> tuple[int, ...]:
    permuted_bits = [POSITIVE_BIT] * len(bits)
    for edge_index, edge in enumerate(structure.edge_order):
        image_u = structure.vertex_order[automorphism[structure.vertex_index[edge.u]]]
        image_v = structure.vertex_order[automorphism[structure.vertex_index[edge.v]]]
        image_index = structure.edge_index_by_pair[_normalized_pair(image_u, image_v)]
        permuted_bits[image_index] = bits[edge_index]
    return tuple(permuted_bits)


def canonical_combined_rep(
    bits: tuple[int, ...],
    structure: _GraphStructure,
    automorphisms: tuple[tuple[int, ...], ...],
) -> tuple[int, ...]:
    best_bits: tuple[int, ...] | None = None
    for automorphism in automorphisms:
        transformed_bits = _apply_automorphism(bits, structure, automorphism)
        canonical_bits = canonical_switching_rep(transformed_bits, structure)
        if best_bits is None or canonical_bits < best_bits:
            best_bits = canonical_bits
    if best_bits is None:
        raise ValueError("At least one automorphism is required.")
    return best_bits


def _build_exact_preferred_orbits(
    instance: SignedGraphInstance,
    *,
    mode: ClassificationMode,
    structure: _GraphStructure,
) -> dict[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    if mode == "switching-only":
        switching_records = enumerate_switching_classes(instance, structure=structure)
        return {
            record.representative_bits: (record.representative_bits,)
            for record in switching_records
        }

    switching_records = enumerate_switching_classes(instance, structure=structure)
    automorphisms = compute_automorphisms(instance, structure=structure)
    grouped_records: dict[tuple[int, ...], list[tuple[int, ...]]] = {}
    for record in switching_records:
        combined_bits = canonical_combined_rep(
            record.representative_bits,
            structure,
            automorphisms,
        )
        grouped_records.setdefault(combined_bits, []).append(record.representative_bits)

    return {
        combined_bits: tuple(representatives)
        for combined_bits, representatives in grouped_records.items()
    }


def _attach_preferred_display_representatives(
    instance: SignedGraphInstance,
    *,
    mode: ClassificationMode,
    classification_backend: ClassificationBackend,
    structure: _GraphStructure,
    theoretical_switching_class_count: int,
    entries: tuple[SignatureClassEntry, ...],
) -> tuple[tuple[SignatureClassEntry, ...], dict[str, bool | int | str]]:
    if not entries:
        return entries, {
            "preferred_representatives_available": True,
            "preferred_representatives_exact": True,
            "preferred_representative_strategy": "minimum-negative-orbit-search",
        }

    exact_preferred = (
        mode == "switching-only"
        or classification_backend == "generic"
        or theoretical_switching_class_count <= EXACT_PREFERRED_SWITCHING_CLASS_LIMIT
    )

    if exact_preferred:
        preferred_orbits = _build_exact_preferred_orbits(
            instance,
            mode=mode,
            structure=structure,
        )
        finalized_entries = tuple(
            _entry_with_preferred_display_bits(
                entry,
                _preferred_display_bits_from_switching_class_reps(
                    preferred_orbits.get(entry.representative_bits, (entry.representative_bits,)),
                    structure,
                ),
                structure,
            )
            for entry in entries
        )
        return finalized_entries, {
            "preferred_representatives_available": True,
            "preferred_representatives_exact": True,
            "preferred_representative_strategy": "minimum-negative-orbit-search",
        }

    return entries, {
        "preferred_representatives_available": True,
        "preferred_representatives_exact": False,
        "preferred_representative_strategy": "canonical-fallback",
        "preferred_exact_switching_class_limit": EXACT_PREFERRED_SWITCHING_CLASS_LIMIT,
    }


def _enumerate_native_combined_classes(
    *,
    structure: _GraphStructure,
    jobs: int,
    k: int | None,
    include_reachable_negative_edge_counts: bool,
) -> tuple[tuple[SignatureClassEntry, ...], int, dict[str, float | int]]:
    native_result = run_native_canonical_scan(
        num_vertices=len(structure.vertex_order),
        edge_endpoints=structure.edge_endpoints,
        non_tree_edge_indices=structure.non_tree_edge_indices,
        jobs=jobs,
    )

    grouped_records: list[SignatureClassEntry] = []
    switching_class_count = 0

    for native_class in native_result["classes"]:
        cycle_mask = native_class["cycle_mask"]
        cycle_bits = _int_to_bits(cycle_mask, structure.cycle_rank)
        representative_bits = reconstruct_from_cycle_bits(cycle_bits, structure)
        reachable_negative_edge_counts = None
        if k is not None or include_reachable_negative_edge_counts:
            reachable_negative_edge_counts = _reachable_negative_edge_counts(
                representative_bits,
                structure,
            )
        if k is not None and k not in reachable_negative_edge_counts:
            continue

        orbit_size = native_class["switching_class_count"]
        switching_class_count += orbit_size
        grouped_records.append(
            _make_signature_class_entry(
                class_number=len(grouped_records) + 1,
                representative_bits=representative_bits,
                cycle_bits=cycle_bits,
                structure=structure,
                switching_orbit_size=structure.switching_orbit_size,
                automorphism_orbit_size=orbit_size,
                reachable_negative_edge_counts=reachable_negative_edge_counts,
            )
        )

    stats: dict[str, float | int] = {
        "native_algorithm": "generator-orbit-scan",
        "native_jobs_used": native_result["jobs_used"],
        "enumerated_switching_class_count": native_result["enumerated_switching_class_count"],
        "generator_count": native_result["generator_count"],
        "merge_elapsed_seconds": round(native_result["merge_elapsed_seconds"], 6),
        "native_elapsed_seconds": round(native_result["native_elapsed_seconds"], 6),
    }
    return tuple(grouped_records), switching_class_count, stats


def classify_signatures(
    instance: SignedGraphInstance,
    *,
    mode: ClassificationMode = "switching-only",
    classification_backend: ClassificationBackend = "generic",
    jobs: int = 1,
    k: int | None = None,
    limit: int | None = None,
    include_reachable_negative_edge_counts: bool = False,
) -> ClassificationResult:
    started_at = perf_counter()
    structure = build_graph_structure(instance)
    theoretical_switching_class_count = 1 << structure.cycle_rank
    actual_backend = classification_backend
    if actual_backend == "native-orbit-search":
        if mode != "switching+automorphism" or structure.cycle_rank == 0:
            actual_backend = "generic"
        elif structure.cycle_rank > 63:
            raise ValueError("native-orbit-search supports cycle rank up to 63.")

    switching_records: tuple[_SwitchingClassRecord, ...] = ()
    automorphisms: tuple[tuple[int, ...], ...] = ((tuple(range(len(structure.vertex_order)))),)
    combined_class_count: int | None = None
    backend_stats: dict[str, float | int | bool | str | None] = {}

    if mode == "switching+automorphism" and actual_backend == "native-orbit-search":
        final_entries, switching_class_count, backend_stats = _enumerate_native_combined_classes(
            structure=structure,
            jobs=jobs,
            k=k,
            include_reachable_negative_edge_counts=include_reachable_negative_edge_counts,
        )
        combined_class_count = len(final_entries)
    elif mode == "switching+automorphism":
        switching_records = enumerate_switching_classes(
            instance,
            k=k,
            include_reachable_negative_edge_counts=include_reachable_negative_edge_counts,
            structure=structure,
        )
        automorphisms = compute_automorphisms(instance, structure=structure)
        grouped_records: dict[tuple[int, ...], list[_SwitchingClassRecord]] = {}
        for record in switching_records:
            combined_bits = canonical_combined_rep(
                record.representative_bits,
                structure,
                automorphisms,
            )
            grouped_records.setdefault(combined_bits, []).append(record)

        ordered_group_keys = sorted(grouped_records)
        final_entries: list[SignatureClassEntry] = []
        for class_number, group_key in enumerate(ordered_group_keys, start=1):
            representative_bits = group_key
            cycle_bits = switching_class_cycle_bits(representative_bits, structure)
            group = grouped_records[group_key]
            reachable_counts = group[0].reachable_negative_edge_counts
            final_entries.append(
                _make_signature_class_entry(
                    class_number=class_number,
                    representative_bits=representative_bits,
                    cycle_bits=cycle_bits,
                    structure=structure,
                    switching_orbit_size=structure.switching_orbit_size,
                    automorphism_orbit_size=len(group),
                    reachable_negative_edge_counts=reachable_counts,
                )
            )
        combined_class_count = len(final_entries)
        switching_class_count = len(switching_records)
        backend_stats["automorphism_count"] = len(automorphisms)
    else:
        switching_records = enumerate_switching_classes(
            instance,
            k=k,
            include_reachable_negative_edge_counts=include_reachable_negative_edge_counts,
            structure=structure,
        )
        final_entries = []
        for class_number, record in enumerate(switching_records, start=1):
            final_entries.append(
                _make_signature_class_entry(
                    class_number=class_number,
                    representative_bits=record.representative_bits,
                    cycle_bits=record.cycle_bits,
                    structure=structure,
                    switching_orbit_size=record.switching_orbit_size,
                    reachable_negative_edge_counts=record.reachable_negative_edge_counts,
                )
            )
        switching_class_count = len(switching_records)

    final_entries, preferred_stats = _attach_preferred_display_representatives(
        instance,
        mode=mode,
        classification_backend=actual_backend,
        structure=structure,
        theoretical_switching_class_count=theoretical_switching_class_count,
        entries=tuple(final_entries),
    )
    full_class_count = len(final_entries)
    emitted_entries = tuple(final_entries[:limit] if limit is not None else final_entries)
    elapsed_seconds = perf_counter() - started_at

    stats: dict[str, float | int | bool | str | None] = {
        "classification_mode": mode,
        "classification_backend": actual_backend,
        "jobs": jobs,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "classification_phase_elapsed_seconds": round(elapsed_seconds, 6),
        "emitted_class_count": len(emitted_entries),
        "full_class_count": full_class_count,
        "include_reachable_negative_edge_counts": include_reachable_negative_edge_counts,
        "k_filter_applied": k is not None,
        "limit": limit,
        "truncated": limit is not None and len(emitted_entries) < full_class_count,
    }
    if actual_backend != classification_backend:
        stats["requested_classification_backend"] = classification_backend
    if mode == "switching+automorphism" and actual_backend == "generic":
        stats["num_automorphisms"] = len(automorphisms)
        stats["automorphism_count"] = len(automorphisms)
    stats.update(backend_stats)
    stats.update(preferred_stats)

    return ClassificationResult(
        graph_name=instance.name,
        classification_mode=mode,
        num_vertices=len(structure.vertex_order),
        num_edges=len(structure.edge_order),
        num_components=structure.num_components,
        cycle_rank=structure.cycle_rank,
        theoretical_switching_class_count=theoretical_switching_class_count,
        switching_class_count=switching_class_count,
        combined_class_count=combined_class_count,
        k=k,
        bit_convention=BIT_CONVENTION,
        edge_order=tuple(edge.id for edge in structure.edge_order),
        classes=emitted_entries,
        classification_backend=actual_backend,
        stats=stats,
    )


def build_signed_instance(
    base_instance: SignedGraphInstance,
    representative_signs_by_edge_id: dict[str, str],
    *,
    name: str | None = None,
) -> SignedGraphInstance:
    edges = tuple(
        SignedEdge(
            id=edge.id,
            u=edge.u,
            v=edge.v,
            sign=representative_signs_by_edge_id[edge.id],
        )
        for edge in base_instance.edges
    )
    return SignedGraphInstance(
        name=name or base_instance.name,
        vertices=base_instance.vertices,
        edges=edges,
    )


def classify_and_optimize_representatives(
    instance: SignedGraphInstance,
    *,
    mode: ClassificationMode = "switching-only",
    classification_backend: ClassificationBackend = "generic",
    jobs: int = 1,
    k: int | None = None,
    limit: int | None = None,
    timeout_ms: int | None = None,
) -> ClassificationResult:
    classification_started_at = perf_counter()
    classification_result = classify_signatures(
        instance,
        mode=mode,
        classification_backend=classification_backend,
        jobs=jobs,
        k=k,
        limit=limit,
        include_reachable_negative_edge_counts=(k is None),
    )
    classification_phase_elapsed_seconds = perf_counter() - classification_started_at
    edge_by_id = instance.edge_by_id
    delta = instance.max_degree()
    optimization_started_at = perf_counter()
    optimization_results_by_class_id: dict[str, OptimizationResult] = {}
    tasks = tuple(
        (
            instance,
            entry.class_id,
            entry.representative_signs_by_edge_id,
            timeout_ms,
        )
        for entry in classification_result.classes
    )
    if jobs > 1 and classification_result.classes:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            for class_id, optimization_result in executor.map(
                _solve_class_entry_optimization_task,
                tasks,
            ):
                optimization_results_by_class_id[class_id] = optimization_result
    else:
        for task in tasks:
            class_id, optimization_result = _solve_class_entry_optimization_task(task)
            optimization_results_by_class_id[class_id] = optimization_result
    optimization_phase_elapsed_seconds = perf_counter() - optimization_started_at

    optimized_entries: list[SignatureClassEntry] = []
    for entry in classification_result.classes:
        negative_edge_ids = tuple(
            edge_id
            for edge_id in classification_result.edge_order
            if entry.representative_signs_by_edge_id[edge_id] == "-"
        )
        negative_edges = tuple(
            (edge_id, edge_by_id[edge_id].u, edge_by_id[edge_id].v) for edge_id in negative_edge_ids
        )
        optimization_result = optimization_results_by_class_id[entry.class_id]
        best_r = optimization_result.best_r
        best_r_minus_delta = best_r - delta if best_r is not None else None
        best_r_over_delta = (
            best_r / Fraction(delta, 1) if best_r is not None and delta > 0 else None
        )

        optimized_entries.append(
            replace(
                entry,
                negative_edge_ids=negative_edge_ids,
                negative_edges=negative_edges,
                best_r=best_r,
                best_r_minus_delta=best_r_minus_delta,
                best_r_over_delta=best_r_over_delta,
                optimize_status=optimization_result.status,
                witness=optimization_result.witness,
                optimization_result=optimization_result,
            )
        )

    best_r_values = tuple(entry.best_r for entry in optimized_entries if entry.best_r is not None)
    global_min_best_r = min(best_r_values) if best_r_values else None
    global_max_best_r = max(best_r_values) if best_r_values else None

    finalized_entries: list[SignatureClassEntry] = []
    for entry in optimized_entries:
        finalized_entries.append(
            replace(
                entry,
                attains_global_min_best_r=(
                    entry.best_r == global_min_best_r if global_min_best_r is not None else None
                ),
                attains_global_max_best_r=(
                    entry.best_r == global_max_best_r if global_max_best_r is not None else None
                ),
            )
        )

    global_min_class_ids = tuple(
        entry.class_id for entry in finalized_entries if entry.attains_global_min_best_r
    )
    global_max_class_ids = tuple(
        entry.class_id for entry in finalized_entries if entry.attains_global_max_best_r
    )
    global_min_representative_codes = tuple(
        entry.representative_code for entry in finalized_entries if entry.attains_global_min_best_r
    )
    global_max_representative_codes = tuple(
        entry.representative_code for entry in finalized_entries if entry.attains_global_max_best_r
    )

    stats = dict(classification_result.stats)
    stats.update(
        {
            "optimize_representatives": True,
            "optimize_timeout_ms": timeout_ms,
            "jobs": jobs,
            "optimized_class_count": len(finalized_entries),
            "classification_phase_elapsed_seconds": round(
                classification_phase_elapsed_seconds,
                6,
            ),
            "optimization_phase_elapsed_seconds": round(optimization_phase_elapsed_seconds, 6),
        }
    )

    return replace(
        classification_result,
        classes=tuple(finalized_entries),
        optimize_representatives=True,
        optimized_class_count=len(finalized_entries),
        delta=delta,
        global_min_best_r=global_min_best_r,
        global_max_best_r=global_max_best_r,
        global_min_class_ids=global_min_class_ids,
        global_max_class_ids=global_max_class_ids,
        global_min_representative_codes=global_min_representative_codes,
        global_max_representative_codes=global_max_representative_codes,
        stats=stats,
    )
