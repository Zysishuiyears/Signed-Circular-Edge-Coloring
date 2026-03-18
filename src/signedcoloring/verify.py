from __future__ import annotations

from itertools import combinations

from signedcoloring.models import SignedGraphInstance, VerificationResult, Witness
from signedcoloring.rational import circle_distance, normalize_on_circle


def verify_witness(instance: SignedGraphInstance, witness: Witness) -> VerificationResult:
    messages: list[str] = []
    circumference = witness.r

    if circumference < 2:
        messages.append(f"Invalid witness: r must be at least 2, got {circumference}.")
        return VerificationResult(valid=False, messages=tuple(messages))

    edge_ids = {edge.id for edge in instance.edges}
    if set(witness.base_colors) != edge_ids:
        messages.append("Base colors do not match the instance edge ids.")
    if set(witness.incidence_colors) != edge_ids:
        messages.append("Incidence colors do not match the instance edge ids.")

    for edge in instance.edges:
        if edge.id not in witness.base_colors or edge.id not in witness.incidence_colors:
            continue

        base = normalize_on_circle(witness.base_colors[edge.id], circumference)
        incidence_map = witness.incidence_colors[edge.id]

        if set(incidence_map) != {edge.u, edge.v}:
            messages.append(f"Incidence colors for edge {edge.id!r} must include both endpoints.")
            continue

        expected_u = base
        expected_v = normalize_on_circle(
            base + (circumference / 2 if edge.is_positive else 0), circumference
        )
        actual_u = normalize_on_circle(incidence_map[edge.u], circumference)
        actual_v = normalize_on_circle(incidence_map[edge.v], circumference)

        if actual_u != expected_u:
            messages.append(f"Edge {edge.id!r} has an inconsistent color at vertex {edge.u!r}.")
        if actual_v != expected_v:
            messages.append(f"Edge {edge.id!r} has an inconsistent color at vertex {edge.v!r}.")

        distance = circle_distance(actual_u, actual_v, circumference)
        if edge.is_positive and distance != circumference / 2:
            messages.append(f"Positive edge {edge.id!r} does not realize distance r/2.")
        if not edge.is_positive and actual_u != actual_v:
            messages.append(f"Negative edge {edge.id!r} must have identical endpoint colors.")

    incidence_by_vertex: dict[str, list[tuple[str, object]]] = {
        vertex: [] for vertex in instance.vertices
    }
    for edge in instance.edges:
        if edge.id not in witness.incidence_colors:
            continue
        incidence_map = witness.incidence_colors[edge.id]
        if edge.u in incidence_map:
            incidence_by_vertex[edge.u].append(
                (edge.id, normalize_on_circle(incidence_map[edge.u], circumference))
            )
        if edge.v in incidence_map:
            incidence_by_vertex[edge.v].append(
                (edge.id, normalize_on_circle(incidence_map[edge.v], circumference))
            )

    for vertex, colored_incidents in incidence_by_vertex.items():
        for (edge_id_left, color_left), (edge_id_right, color_right) in combinations(
            colored_incidents, 2
        ):
            if circle_distance(color_left, color_right, circumference) < 1:
                messages.append(
                    f"Vertex {vertex!r} violates the distance bound with edges "
                    f"{edge_id_left!r} and {edge_id_right!r}."
                )

    if not messages:
        messages.append("Witness verification passed.")

    return VerificationResult(
        valid=len(messages) == 1 and messages[0] == "Witness verification passed.",
        messages=tuple(messages),
        stats={
            "num_vertices": len(instance.vertices),
            "num_edges": len(instance.edges),
        },
    )
