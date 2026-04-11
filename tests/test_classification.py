from __future__ import annotations

from fractions import Fraction
from itertools import product

import pytest

from signedcoloring.classification import (
    build_graph_structure,
    canonical_switching_rep,
    classify_and_optimize_representatives,
    classify_signatures,
    compute_automorphisms,
    reconstruct_from_cycle_bits,
    switch_signature,
    switching_class_cycle_bits,
)
from signedcoloring.classification_native import native_module_available
from signedcoloring.models import SignedEdge, SignedGraphInstance


def _make_instance(
    name: str,
    vertices: tuple[str, ...],
    edges: tuple[tuple[str, str, str, str], ...],
) -> SignedGraphInstance:
    return SignedGraphInstance(
        name=name,
        vertices=vertices,
        edges=tuple(SignedEdge(id=edge_id, u=u, v=v, sign=sign) for edge_id, u, v, sign in edges),
    )


def _path_instance() -> SignedGraphInstance:
    return _make_instance(
        "path_p4",
        ("v1", "v2", "v3", "v4"),
        (
            ("e1", "v1", "v2", "+"),
            ("e2", "v2", "v3", "+"),
            ("e3", "v3", "v4", "+"),
        ),
    )


def _cycle_c4_instance() -> SignedGraphInstance:
    return _make_instance(
        "cycle_c4",
        ("v1", "v2", "v3", "v4"),
        (
            ("e1", "v1", "v2", "+"),
            ("e2", "v2", "v3", "+"),
            ("e3", "v3", "v4", "+"),
            ("e4", "v4", "v1", "+"),
        ),
    )


def _triangle_plus_edge_instance() -> SignedGraphInstance:
    return _make_instance(
        "triangle_plus_edge",
        ("a", "b", "c", "d", "e"),
        (
            ("e1", "a", "b", "+"),
            ("e2", "b", "c", "+"),
            ("e3", "c", "a", "+"),
            ("e4", "d", "e", "+"),
        ),
    )


def _cube_q3_instance() -> SignedGraphInstance:
    vertices = tuple(f"{x}{y}{z}" for x, y, z in product("01", repeat=3))
    edges: list[tuple[str, str, str, str]] = []
    edge_number = 1
    for vertex in vertices:
        for position in range(3):
            flipped_bit = "1" if vertex[position] == "0" else "0"
            neighbor = vertex[:position] + flipped_bit + vertex[position + 1 :]
            if vertex < neighbor:
                edges.append((f"e{edge_number}", vertex, neighbor, "+"))
                edge_number += 1
    return _make_instance("cube_q3", vertices, tuple(edges))


def _petersen_instance() -> SignedGraphInstance:
    vertices = tuple(str(index) for index in range(10))
    edge_specs = (
        ("e1", "0", "1", "+"),
        ("e2", "1", "2", "+"),
        ("e3", "2", "3", "+"),
        ("e4", "3", "4", "+"),
        ("e5", "0", "4", "+"),
        ("e6", "0", "5", "+"),
        ("e7", "1", "6", "+"),
        ("e8", "2", "7", "+"),
        ("e9", "3", "8", "+"),
        ("e10", "4", "9", "+"),
        ("e11", "5", "7", "+"),
        ("e12", "5", "8", "+"),
        ("e13", "6", "8", "+"),
        ("e14", "6", "9", "+"),
        ("e15", "7", "9", "+"),
    )
    return _make_instance("petersen", vertices, edge_specs)


def _c3_square_c3_instance() -> SignedGraphInstance:
    vertices = tuple(f"v{row}{column}" for row in range(3) for column in range(3))
    endpoint_pairs: set[tuple[str, str]] = set()
    for row in range(3):
        for column in range(3):
            vertex = f"v{row}{column}"
            right = f"v{row}{(column + 1) % 3}"
            down = f"v{(row + 1) % 3}{column}"
            endpoint_pairs.add(tuple(sorted((vertex, right))))
            endpoint_pairs.add(tuple(sorted((vertex, down))))

    edges = tuple(
        (f"e{index:02d}", left, right, "+")
        for index, (left, right) in enumerate(sorted(endpoint_pairs), start=1)
    )
    return _make_instance("c3_square_c3", vertices, edges)


def _complete_bipartite_instance(left_size: int, right_size: int) -> SignedGraphInstance:
    left = tuple(f"a{i}" for i in range(1, left_size + 1))
    right = tuple(f"b{i}" for i in range(1, right_size + 1))
    edges: list[tuple[str, str, str, str]] = []
    edge_number = 1
    for left_vertex in left:
        for right_vertex in right:
            edges.append((f"e{edge_number}", left_vertex, right_vertex, "+"))
            edge_number += 1
    return _make_instance(f"k_{left_size}_{right_size}", left + right, tuple(edges))


def _int_to_bits(value: int, width: int) -> tuple[int, ...]:
    return tuple((value >> shift) & 1 for shift in reversed(range(width)))


def _all_signatures(instance: SignedGraphInstance) -> tuple[tuple[int, ...], ...]:
    structure = build_graph_structure(instance)
    edge_count = len(structure.edge_order)
    return tuple(_int_to_bits(value, edge_count) for value in range(1 << edge_count))


def _brute_switching_orbit(
    bits: tuple[int, ...],
    instance: SignedGraphInstance,
) -> set[tuple[int, ...]]:
    structure = build_graph_structure(instance)
    orbit: set[tuple[int, ...]] = set()
    for mask in range(1 << len(structure.vertex_order)):
        subset = {
            structure.vertex_order[index]
            for index in range(len(structure.vertex_order))
            if (mask >> index) & 1
        }
        orbit.add(switch_signature(bits, subset, structure))
    return orbit


def _brute_switching_partitions(
    instance: SignedGraphInstance,
) -> list[set[tuple[int, ...]]]:
    unseen = set(_all_signatures(instance))
    orbits: list[set[tuple[int, ...]]] = []

    while unseen:
        seed = min(unseen)
        orbit = _brute_switching_orbit(seed, instance)
        orbits.append(orbit)
        unseen -= orbit

    return orbits


def test_switch_signature_flips_exactly_the_cut_edges() -> None:
    instance = _path_instance()
    structure = build_graph_structure(instance)
    bits = (0, 1, 0)

    switched = switch_signature(bits, {"v1", "v3"}, structure)

    assert switched == (1, 0, 1)


def test_canonical_switching_rep_is_unique_and_tree_positive() -> None:
    instance = _cycle_c4_instance()
    structure = build_graph_structure(instance)

    for orbit in _brute_switching_partitions(instance):
        canonical_reps = {canonical_switching_rep(bits, structure) for bits in orbit}
        assert len(canonical_reps) == 1

        canonical_bits = next(iter(canonical_reps))
        assert all(canonical_bits[index] == 0 for index in structure.tree_edge_indices)
        cycle_bits = switching_class_cycle_bits(canonical_bits, structure)
        assert reconstruct_from_cycle_bits(cycle_bits, structure) == canonical_bits


def test_switching_class_count_matches_cycle_rank_formula() -> None:
    cases = (
        (_path_instance(), 1),
        (_cycle_c4_instance(), 2),
        (_triangle_plus_edge_instance(), 2),
        (_cube_q3_instance(), 32),
    )

    for instance, expected_count in cases:
        result = classify_signatures(instance)
        assert result.switching_class_count == expected_count


def test_cycle_space_enumeration_matches_bruteforce_on_c4() -> None:
    instance = _cycle_c4_instance()
    structure = build_graph_structure(instance)
    brute_orbits = _brute_switching_partitions(instance)

    brute_codes = {
        "".join(str(bit) for bit in canonical_switching_rep(min(orbit), structure))
        for orbit in brute_orbits
    }
    classified_codes = {
        entry.representative_code for entry in classify_signatures(instance).classes
    }

    assert classified_codes == brute_codes


def test_k_filter_is_exact_for_c4() -> None:
    instance = _cycle_c4_instance()
    brute_orbits = _brute_switching_partitions(instance)

    brute_count = sum(1 for orbit in brute_orbits if any(sum(bits) == 1 for bits in orbit))

    result = classify_signatures(instance, k=1)

    assert result.switching_class_count == brute_count
    assert len(result.classes) == brute_count


def test_switching_plus_automorphism_counts_on_path_and_c4() -> None:
    path_result = classify_signatures(_path_instance(), mode="switching+automorphism")
    cycle_result = classify_signatures(_cycle_c4_instance(), mode="switching+automorphism")

    assert path_result.switching_class_count == 1
    assert path_result.combined_class_count == 1
    assert cycle_result.switching_class_count == 2
    assert cycle_result.combined_class_count == 2


def test_cube_q3_classification_is_deterministic() -> None:
    instance = _cube_q3_instance()

    first = classify_signatures(instance, mode="switching+automorphism")
    second = classify_signatures(instance, mode="switching+automorphism")

    assert [entry.representative_code for entry in first.classes] == [
        entry.representative_code for entry in second.classes
    ]
    assert [entry.cycle_bit_code for entry in first.classes] == [
        entry.cycle_bit_code for entry in second.classes
    ]
    assert compute_automorphisms(instance) == compute_automorphisms(instance)


@pytest.mark.skipif(
    not native_module_available(),
    reason="native classification extension is unavailable",
)
def test_native_orbit_search_matches_generic_backend() -> None:
    instances = (
        _path_instance(),
        _cycle_c4_instance(),
        _petersen_instance(),
        _complete_bipartite_instance(3, 3),
        _complete_bipartite_instance(4, 4),
    )

    for instance in instances:
        generic = classify_signatures(instance, mode="switching+automorphism")
        native = classify_signatures(
            instance,
            mode="switching+automorphism",
            classification_backend="native-orbit-search",
        )

        assert native.classification_backend in {"generic", "native-orbit-search"}
        assert native.switching_class_count == generic.switching_class_count
        assert native.combined_class_count == generic.combined_class_count
        assert [entry.representative_code for entry in native.classes] == [
            entry.representative_code for entry in generic.classes
        ]
        assert [entry.cycle_bit_code for entry in native.classes] == [
            entry.cycle_bit_code for entry in generic.classes
        ]
        assert [entry.reachable_negative_edge_counts for entry in native.classes] == [
            entry.reachable_negative_edge_counts for entry in generic.classes
        ]
        assert [entry.preferred_representative_code for entry in native.classes] == [
            entry.preferred_representative_code for entry in generic.classes
        ]


@pytest.mark.skipif(
    not native_module_available(),
    reason="native classification extension is unavailable",
)
def test_native_orbit_search_preserves_global_best_r_extrema() -> None:
    generic = classify_and_optimize_representatives(
        _cycle_c4_instance(),
        mode="switching+automorphism",
    )
    native = classify_and_optimize_representatives(
        _cycle_c4_instance(),
        mode="switching+automorphism",
        classification_backend="native-orbit-search",
        jobs=2,
    )

    assert native.global_min_best_r == generic.global_min_best_r
    assert native.global_max_best_r == generic.global_max_best_r
    assert native.global_min_class_ids == generic.global_min_class_ids
    assert native.global_max_class_ids == generic.global_max_class_ids


@pytest.mark.skipif(
    not native_module_available(),
    reason="native classification extension is unavailable",
)
def test_native_orbit_search_parallel_jobs_match_single_thread() -> None:
    instance = _complete_bipartite_instance(4, 4)

    single = classify_signatures(
        instance,
        mode="switching+automorphism",
        classification_backend="native-orbit-search",
        jobs=1,
    )
    parallel = classify_signatures(
        instance,
        mode="switching+automorphism",
        classification_backend="native-orbit-search",
        jobs=2,
    )

    assert single.switching_class_count == parallel.switching_class_count
    assert single.combined_class_count == parallel.combined_class_count
    assert [entry.representative_code for entry in single.classes] == [
        entry.representative_code for entry in parallel.classes
    ]
    assert [entry.cycle_bit_code for entry in single.classes] == [
        entry.cycle_bit_code for entry in parallel.classes
    ]


def test_classify_and_optimize_representatives_tracks_global_min_and_max() -> None:
    result = classify_and_optimize_representatives(
        _cycle_c4_instance(),
        mode="switching+automorphism",
    )

    assert result.optimize_representatives is True
    assert result.optimized_class_count == 2
    assert result.global_min_best_r == Fraction(2, 1)
    assert result.global_max_best_r == Fraction(8, 3)
    assert result.global_min_class_ids == ("class-0001",)
    assert result.global_max_class_ids == ("class-0002",)

    classes_by_id = {entry.class_id: entry for entry in result.classes}
    assert classes_by_id["class-0001"].best_r == Fraction(2, 1)
    assert classes_by_id["class-0001"].attains_global_min_best_r is True
    assert classes_by_id["class-0001"].attains_global_max_best_r is False
    assert classes_by_id["class-0002"].best_r == Fraction(8, 3)
    assert classes_by_id["class-0002"].attains_global_min_best_r is False
    assert classes_by_id["class-0002"].attains_global_max_best_r is True
    assert classes_by_id["class-0002"].witness is not None


def test_single_class_can_attain_both_global_min_and_max_best_r() -> None:
    result = classify_and_optimize_representatives(
        _path_instance(),
        mode="switching+automorphism",
    )

    assert len(result.classes) == 1
    entry = result.classes[0]
    assert result.global_min_best_r == result.global_max_best_r == entry.best_r
    assert entry.attains_global_min_best_r is True
    assert entry.attains_global_max_best_r is True


def test_preferred_display_representatives_track_minimum_negative_edges() -> None:
    result = classify_signatures(
        _c3_square_c3_instance(),
        mode="switching+automorphism",
        include_reachable_negative_edge_counts=True,
    )

    assert result.stats["preferred_representatives_exact"] is True

    found_strict_improvement = False
    for entry in result.classes:
        assert entry.preferred_negative_edge_count == min(
            entry.reachable_negative_edge_counts or ()
        )
        if entry.preferred_negative_edge_count < sum(entry.representative_bits):
            found_strict_improvement = True

    assert found_strict_improvement is True
