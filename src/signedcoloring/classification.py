from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import networkx as nx
from networkx.algorithms import isomorphism

from signedcoloring.models import (
    ClassificationMode,
    ClassificationResult,
    SignatureClassEntry,
    SignedEdge,
    SignedGraphInstance,
)

POSITIVE_BIT = 0
NEGATIVE_BIT = 1
BIT_CONVENTION = "0=+,1=-"


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


def enumerate_switching_classes(
    instance: SignedGraphInstance,
    *,
    k: int | None = None,
    structure: _GraphStructure | None = None,
) -> tuple[_SwitchingClassRecord, ...]:
    structure = structure or build_graph_structure(instance)
    records: list[_SwitchingClassRecord] = []

    for value in range(1 << structure.cycle_rank):
        cycle_bits = _int_to_bits(value, structure.cycle_rank)
        representative_bits = reconstruct_from_cycle_bits(cycle_bits, structure)
        reachable_negative_edge_counts = None
        if k is not None:
            reachable_negative_edge_counts = _reachable_negative_edge_counts(
                representative_bits,
                structure,
            )
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


def classify_signatures(
    instance: SignedGraphInstance,
    *,
    mode: ClassificationMode = "switching-only",
    k: int | None = None,
    limit: int | None = None,
) -> ClassificationResult:
    started_at = perf_counter()
    structure = build_graph_structure(instance)
    switching_records = enumerate_switching_classes(instance, k=k, structure=structure)
    theoretical_switching_class_count = 1 << structure.cycle_rank

    automorphisms: tuple[tuple[int, ...], ...] = ((tuple(range(len(structure.vertex_order)))),)
    combined_class_count: int | None = None

    if mode == "switching+automorphism":
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
                SignatureClassEntry(
                    class_id=f"class-{class_number:04d}",
                    representative_code=_bits_to_code(representative_bits),
                    cycle_bit_code=_bits_to_code(cycle_bits),
                    representative_bits=representative_bits,
                    representative_signs_by_edge_id=_bits_to_signs_by_edge_id(
                        representative_bits,
                        structure,
                    ),
                    switching_orbit_size=structure.switching_orbit_size,
                    automorphism_orbit_size=len(group),
                    reachable_negative_edge_counts=reachable_counts,
                )
            )
        combined_class_count = len(final_entries)
    else:
        final_entries = []
        for class_number, record in enumerate(switching_records, start=1):
            final_entries.append(
                SignatureClassEntry(
                    class_id=f"class-{class_number:04d}",
                    representative_code=_bits_to_code(record.representative_bits),
                    cycle_bit_code=_bits_to_code(record.cycle_bits),
                    representative_bits=record.representative_bits,
                    representative_signs_by_edge_id=_bits_to_signs_by_edge_id(
                        record.representative_bits,
                        structure,
                    ),
                    switching_orbit_size=record.switching_orbit_size,
                    reachable_negative_edge_counts=record.reachable_negative_edge_counts,
                )
            )

    full_class_count = len(final_entries)
    emitted_entries = tuple(final_entries[:limit] if limit is not None else final_entries)
    elapsed_seconds = perf_counter() - started_at

    return ClassificationResult(
        graph_name=instance.name,
        classification_mode=mode,
        num_vertices=len(structure.vertex_order),
        num_edges=len(structure.edge_order),
        num_components=structure.num_components,
        cycle_rank=structure.cycle_rank,
        theoretical_switching_class_count=theoretical_switching_class_count,
        switching_class_count=len(switching_records),
        combined_class_count=combined_class_count,
        k=k,
        bit_convention=BIT_CONVENTION,
        edge_order=tuple(edge.id for edge in structure.edge_order),
        classes=emitted_entries,
        stats={
            "classification_mode": mode,
            "elapsed_seconds": round(elapsed_seconds, 6),
            "emitted_class_count": len(emitted_entries),
            "full_class_count": full_class_count,
            "k_filter_applied": k is not None,
            "limit": limit,
            "num_automorphisms": len(automorphisms) if mode == "switching+automorphism" else None,
            "truncated": limit is not None and len(emitted_entries) < full_class_count,
        },
    )
