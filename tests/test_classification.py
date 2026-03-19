from __future__ import annotations

from itertools import product

from signedcoloring.classification import (
    build_graph_structure,
    canonical_switching_rep,
    classify_signatures,
    compute_automorphisms,
    reconstruct_from_cycle_bits,
    switch_signature,
    switching_class_cycle_bits,
)
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
