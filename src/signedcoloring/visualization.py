from __future__ import annotations

import json
import math
import re
from fractions import Fraction
from html import escape
from pathlib import Path

import networkx as nx

from signedcoloring.classification import (
    _apply_automorphism,
    _apply_switch_flags,
    build_graph_structure,
    build_signed_instance,
    compute_automorphisms,
)
from signedcoloring.io import load_instance
from signedcoloring.models import SignedGraphInstance, Witness
from signedcoloring.rational import fraction_to_string, normalize_on_circle, parse_fraction
from signedcoloring.verify import verify_witness

PALETTE = (
    "#d73027",
    "#4575b4",
    "#1a9850",
    "#984ea3",
    "#ff7f00",
    "#ffd92f",
    "#a65628",
    "#f781bf",
    "#66c2a5",
    "#e41a1c",
    "#4daf4a",
    "#377eb8",
)


def _switch_flags_from_mask(mask: int, structure: object) -> tuple[int, ...]:
    switch_flags = [0] * len(structure.vertex_order)
    for offset, vertex_index in enumerate(structure.free_vertex_indices):
        if (mask >> offset) & 1:
            switch_flags[vertex_index] = 1
    return tuple(switch_flags)


def _witness_from_payload(payload: dict[str, object]) -> Witness:
    base_colors = {
        edge_id: parse_fraction(value) for edge_id, value in dict(payload["base_colors"]).items()
    }
    incidence_colors = {
        edge_id: {
            vertex: parse_fraction(value) for vertex, value in dict(vertex_colors).items()
        }
        for edge_id, vertex_colors in dict(payload["incidence_colors"]).items()
    }
    return Witness(
        r=parse_fraction(payload["r"]),
        base_colors=base_colors,
        incidence_colors=incidence_colors,
    )


def _load_class_payloads(run_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    payload = json.loads((run_dir / "classes.json").read_text(encoding="utf-8"))
    return payload, list(payload["classes"])


def _parse_grid_coordinate(label: str) -> tuple[int, int] | None:
    direct_match = re.fullmatch(r"\(?\s*(\d+)\s*,\s*(\d+)\s*\)?", label)
    if direct_match is not None:
        return int(direct_match.group(1)), int(direct_match.group(2))

    prefixed_match = re.fullmatch(r"[A-Za-z_]+(\d)(\d)", label)
    if prefixed_match is not None:
        return int(prefixed_match.group(1)), int(prefixed_match.group(2))

    return None


def _polar_point(
    center: tuple[float, float],
    radius: float,
    angle: float,
) -> tuple[float, float]:
    return (
        center[0] + (radius * math.cos(angle)),
        center[1] + (radius * math.sin(angle)),
    )


def _lane_slot(index: int) -> float:
    magnitude = 0.75 * (1 + (index // 2))
    sign = 1.0 if index % 2 == 0 else -1.0
    return magnitude * sign


def _layout_positions(
    instance: SignedGraphInstance,
) -> tuple[dict[str, tuple[float, float]], dict[str, object]]:
    parsed = {vertex: _parse_grid_coordinate(vertex) for vertex in instance.vertices}
    if all(coordinate is not None for coordinate in parsed.values()):
        row_values = sorted(
            {coordinate[0] for coordinate in parsed.values() if coordinate is not None}
        )
        column_values = sorted(
            {coordinate[1] for coordinate in parsed.values() if coordinate is not None}
        )
        if len(row_values) >= 2 and len(column_values) >= 2:
            row_index = {value: index for index, value in enumerate(row_values)}
            column_index = {value: index for index, value in enumerate(column_values)}
            center = (340.0, 360.0)
            inner_radius = 105.0
            outer_radius = 275.0
            radius_step = (
                (outer_radius - inner_radius) / max(1, len(row_values) - 1)
                if len(row_values) > 1
                else 0.0
            )
            positions = {}
            row_by_vertex: dict[str, int] = {}
            column_by_vertex: dict[str, int] = {}
            radius_by_vertex: dict[str, float] = {}
            angle_by_vertex: dict[str, float] = {}
            radial_lane_by_edge_id: dict[str, float] = {}

            for vertex, coordinate in parsed.items():
                if coordinate is None:
                    continue
                normalized_row = row_index[coordinate[0]]
                normalized_column = column_index[coordinate[1]]
                radius = inner_radius + (normalized_row * radius_step)
                angle = (-math.pi / 2.0) + (
                    (2.0 * math.pi * normalized_column) / len(column_values)
                )
                positions[vertex] = _polar_point(center, radius, angle)
                row_by_vertex[vertex] = normalized_row
                column_by_vertex[vertex] = normalized_column
                radius_by_vertex[vertex] = radius
                angle_by_vertex[vertex] = angle

            column_edge_groups: dict[int, list[tuple[tuple[int, int], str]]] = {}
            for edge in instance.edges:
                if column_by_vertex[edge.u] != column_by_vertex[edge.v]:
                    continue
                if row_by_vertex[edge.u] == row_by_vertex[edge.v]:
                    continue
                row_pair = tuple(sorted((row_by_vertex[edge.u], row_by_vertex[edge.v])))
                column_edge_groups.setdefault(column_by_vertex[edge.u], []).append(
                    (row_pair, edge.id)
                )

            for entries in column_edge_groups.values():
                ordered_entries = sorted(
                    entries,
                    key=lambda item: (item[0][0], item[0][1], item[1]),
                )
                if len(ordered_entries) == 1:
                    radial_lane_by_edge_id[ordered_entries[0][1]] = 0.0
                    continue
                for lane_index, (_row_pair, edge_id) in enumerate(ordered_entries):
                    radial_lane_by_edge_id[edge_id] = _lane_slot(lane_index)

            return positions, {
                "kind": "cartesian-rings",
                "center": center,
                "row_by_vertex": row_by_vertex,
                "column_by_vertex": column_by_vertex,
                "radius_by_vertex": radius_by_vertex,
                "angle_by_vertex": angle_by_vertex,
                "column_count": len(column_values),
                "radial_lane_by_edge_id": radial_lane_by_edge_id,
            }

    spring_positions = nx.spring_layout(instance.to_networkx(), seed=0)
    min_x = min(position[0] for position in spring_positions.values())
    max_x = max(position[0] for position in spring_positions.values())
    min_y = min(position[1] for position in spring_positions.values())
    max_y = max(position[1] for position in spring_positions.values())
    span_x = max(max_x - min_x, 1e-6)
    span_y = max(max_y - min_y, 1e-6)
    width = 420.0
    height = 420.0
    margin = 100.0
    return {
        vertex: (
            margin + ((position[0] - min_x) / span_x) * width,
            margin + ((position[1] - min_y) / span_y) * height,
        )
        for vertex, position in spring_positions.items()
    }, {
        "kind": "spring",
    }


def _color_for_index(index: int) -> str:
    if index < len(PALETTE):
        return PALETTE[index]
    hue = (index * 47) % 360
    return f"hsl({hue}, 65%, 45%)"


def _color_map_for_witness(witness: Witness) -> dict[Fraction, str]:
    used_values = sorted(
        {
            color
            for incidence_map in witness.incidence_colors.values()
            for color in incidence_map.values()
        }
    )
    return {value: _color_for_index(index) for index, value in enumerate(used_values)}


def _find_transform_to_preferred(
    *,
    instance: SignedGraphInstance,
    classification_mode: str,
    source_bits: tuple[int, ...],
    target_bits: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    structure = build_graph_structure(instance)
    identity = tuple(range(len(structure.vertex_order)))
    automorphisms = (identity,)
    if classification_mode == "switching+automorphism":
        automorphisms = compute_automorphisms(instance, structure=structure)

    free_switch_count = 1 << len(structure.free_vertex_indices)
    for automorphism in automorphisms:
        transformed_bits = _apply_automorphism(source_bits, structure, automorphism)
        for mask in range(free_switch_count):
            switch_flags = _switch_flags_from_mask(mask, structure)
            candidate_bits = _apply_switch_flags(transformed_bits, switch_flags, structure)
            if candidate_bits == target_bits:
                return automorphism, switch_flags

    raise ValueError(
        "Could not recover an equivalence transform from the canonical "
        "to preferred representative."
    )


def _apply_automorphism_to_witness(
    *,
    instance: SignedGraphInstance,
    witness: Witness,
    automorphism: tuple[int, ...],
) -> Witness:
    structure = build_graph_structure(instance)
    remapped_incidence_colors: dict[str, dict[str, Fraction]] = {}

    for _edge_index, edge in enumerate(structure.edge_order):
        image_u = structure.vertex_order[automorphism[structure.vertex_index[edge.u]]]
        image_v = structure.vertex_order[automorphism[structure.vertex_index[edge.v]]]
        image_edge_index = structure.edge_index_by_pair[
            tuple(sorted((image_u, image_v)))
        ]
        image_edge = structure.edge_order[image_edge_index]
        remapped_incidence_colors[image_edge.id] = {
            image_u: witness.incidence_colors[edge.id][edge.u],
            image_v: witness.incidence_colors[edge.id][edge.v],
        }

    remapped_base_colors = {
        edge.id: normalize_on_circle(remapped_incidence_colors[edge.id][edge.u], witness.r)
        for edge in instance.edges
    }
    return Witness(
        r=witness.r,
        base_colors=remapped_base_colors,
        incidence_colors=remapped_incidence_colors,
    )


def _apply_switching_to_witness(
    *,
    instance: SignedGraphInstance,
    witness: Witness,
    switch_flags: tuple[int, ...],
) -> Witness:
    structure = build_graph_structure(instance)
    switched_incidence_colors: dict[str, dict[str, Fraction]] = {}

    for edge in instance.edges:
        updated = dict(witness.incidence_colors[edge.id])
        for vertex in (edge.u, edge.v):
            if switch_flags[structure.vertex_index[vertex]]:
                updated[vertex] = normalize_on_circle(updated[vertex] + (witness.r / 2), witness.r)
        switched_incidence_colors[edge.id] = updated

    switched_base_colors = {
        edge.id: normalize_on_circle(switched_incidence_colors[edge.id][edge.u], witness.r)
        for edge in instance.edges
    }
    return Witness(
        r=witness.r,
        base_colors=switched_base_colors,
        incidence_colors=switched_incidence_colors,
    )


def _display_witness_for_class(
    *,
    base_instance: SignedGraphInstance,
    class_payload: dict[str, object],
    classification_mode: str,
    run_dir: Path,
) -> tuple[SignedGraphInstance, Witness]:
    witness_payload = class_payload.get("witness")
    if witness_payload is None:
        optimize_run_dir = class_payload.get("optimize_run_dir")
        if optimize_run_dir is None:
            raise ValueError(
                f"Class {class_payload['class_id']} has no embedded witness "
                "and no optimize_run_dir."
            )
        optimize_run_path = Path(str(optimize_run_dir))
        if not optimize_run_path.is_absolute():
            optimize_run_path = (run_dir / optimize_run_path).resolve()
        witness_payload = json.loads(
            (optimize_run_path / "witness.json").read_text(encoding="utf-8")
        )

    canonical_witness = _witness_from_payload(dict(witness_payload))
    preferred_signs = dict(
        class_payload.get("preferred_representative_signs_by_edge_id")
        or class_payload["representative_signs_by_edge_id"]
    )
    displayed_instance = build_signed_instance(
        base_instance,
        preferred_signs,
        name=base_instance.name,
    )

    target_bits = tuple(
        int(bit)
        for bit in (
            class_payload.get("preferred_representative_bits")
            or class_payload["representative_bits"]
        )
    )
    source_bits = tuple(int(bit) for bit in class_payload["representative_bits"])

    if target_bits == source_bits:
        displayed_witness = canonical_witness
    else:
        automorphism, switch_flags = _find_transform_to_preferred(
            instance=base_instance,
            classification_mode=classification_mode,
            source_bits=source_bits,
            target_bits=target_bits,
        )
        displayed_witness = _apply_automorphism_to_witness(
            instance=base_instance,
            witness=canonical_witness,
            automorphism=automorphism,
        )
        displayed_witness = _apply_switching_to_witness(
            instance=base_instance,
            witness=displayed_witness,
            switch_flags=switch_flags,
        )

    verification = verify_witness(displayed_instance, displayed_witness)
    if not verification.valid:
        raise ValueError(
            f"Transformed witness for {class_payload['class_id']} did not verify: "
            + "; ".join(verification.messages)
        )

    return displayed_instance, displayed_witness


def _line_midpoint(
    left: tuple[float, float],
    right: tuple[float, float],
) -> tuple[float, float]:
    return ((left[0] + right[0]) / 2.0, (left[1] + right[1]) / 2.0)


def _label_offset(
    left: tuple[float, float],
    right: tuple[float, float],
) -> tuple[float, float]:
    dx = right[0] - left[0]
    dy = right[1] - left[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return (0.0, -14.0)
    return (-dy / length * 14.0, dx / length * 14.0)


def _edge_label_level(edge_id: str) -> int:
    digits = "".join(character for character in edge_id if character.isdigit())
    return int(digits or "0") % 3


def _normalized_angle_delta(start_angle: float, end_angle: float) -> float:
    return ((end_angle - start_angle + math.pi) % (2.0 * math.pi)) - math.pi


def _arc_path(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    radius: float,
    sweep_clockwise: bool,
) -> str:
    sweep_flag = 1 if sweep_clockwise else 0
    return (
        f"M {start[0]:.2f} {start[1]:.2f} "
        f"A {radius:.2f} {radius:.2f} 0 0 {sweep_flag} {end[0]:.2f} {end[1]:.2f}"
    )


def _quadratic_point(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    t_value: float,
) -> tuple[float, float]:
    inverse = 1.0 - t_value
    return (
        (inverse * inverse * start[0])
        + (2.0 * inverse * t_value * control[0])
        + (t_value * t_value * end[0]),
        (inverse * inverse * start[1])
        + (2.0 * inverse * t_value * control[1])
        + (t_value * t_value * end[1]),
    )


def _quadratic_split(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    t_value: float,
) -> tuple[
    tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
    tuple[tuple[float, float], tuple[float, float], tuple[float, float]],
]:
    first = (
        start[0] + ((control[0] - start[0]) * t_value),
        start[1] + ((control[1] - start[1]) * t_value),
    )
    second = (
        control[0] + ((end[0] - control[0]) * t_value),
        control[1] + ((end[1] - control[1]) * t_value),
    )
    midpoint = (
        first[0] + ((second[0] - first[0]) * t_value),
        first[1] + ((second[1] - first[1]) * t_value),
    )
    return (start, first, midpoint), (midpoint, second, end)


def _quadratic_path(
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
) -> str:
    return (
        f"M {start[0]:.2f} {start[1]:.2f} "
        f"Q {control[0]:.2f} {control[1]:.2f} {end[0]:.2f} {end[1]:.2f}"
    )


def _text_box(
    *,
    text: str,
    x_pos: float,
    y_pos: float,
    edge_id: str,
) -> list[str]:
    width = max(34.0, len(text) * 7.2 + 12.0)
    height = 19.0
    left = x_pos - (width / 2.0)
    top = y_pos - (height / 2.0)
    return [
        (
            f'<rect x="{left:.2f}" y="{top:.2f}" width="{width:.2f}" height="{height:.2f}" '
            f'rx="5" fill="white" fill-opacity="0.92" stroke="#d1d5db" stroke-width="1" '
            f'data-edge-id="{escape(edge_id)}" data-edge-role="label-box"/>'
        ),
        (
            f'<text class="edge-label" x="{x_pos:.2f}" y="{y_pos + 3.5:.2f}" text-anchor="middle" '
            f'data-edge-id="{escape(edge_id)}" data-edge-role="label">{escape(text)}</text>'
        ),
    ]


def _render_svg(
    *,
    displayed_instance: SignedGraphInstance,
    witness: Witness,
    class_payload: dict[str, object],
    graph_name: str,
) -> str:
    positions, layout = _layout_positions(displayed_instance)
    color_map = _color_map_for_witness(witness)
    node_radius = 18.0
    graph_right = max(position[0] for position in positions.values())
    graph_bottom = max(position[1] for position in positions.values())
    legend_left = graph_right + 120.0
    width = legend_left + 260.0
    height = graph_bottom + 240.0

    elements: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" data-layout="{layout["kind"]}" '
            f'width="{width:.0f}" height="{height:.0f}" '
            f'viewBox="0 0 {width:.0f} {height:.0f}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>',
        "text { font-family: 'Segoe UI', Arial, sans-serif; fill: #111827; }",
        ".title { font-size: 20px; font-weight: 600; }",
        ".subtitle { font-size: 13px; }",
        ".vertex-label { font-size: 12px; font-weight: 600; }",
        ".edge-label { font-size: 11px; font-family: Consolas, 'Courier New', monospace; }",
        ".legend-label { font-size: 12px; }",
        "</style>",
    ]

    best_r_label = class_payload.get("best_r", fraction_to_string(witness.r))
    preferred_negative_edge_ids = (
        class_payload.get("preferred_negative_edge_ids")
        or class_payload.get("negative_edge_ids")
        or ()
    )
    title_lines = [f"{graph_name} | {class_payload['class_id']} | best_r = {best_r_label}"]
    if preferred_negative_edge_ids:
        title_lines.append("negative edges = " + ", ".join(preferred_negative_edge_ids))
    for index, line in enumerate(title_lines):
        css_class = "title" if index == 0 else "subtitle"
        elements.append(
            f'<text class="{css_class}" x="40" y="{40 + (index * 22)}">{escape(line)}</text>'
        )

    for edge in displayed_instance.edges:
        left = positions[edge.u]
        right = positions[edge.v]
        midpoint = _line_midpoint(left, right)
        left_color = color_map[witness.incidence_colors[edge.id][edge.u]]
        right_color = color_map[witness.incidence_colors[edge.id][edge.v]]
        label_text = f"{edge.id} {edge.sign}"
        label_level = _edge_label_level(edge.id)
        gap_radius = 7.0

        if layout["kind"] == "cartesian-rings":
            row_by_vertex = layout["row_by_vertex"]
            column_by_vertex = layout["column_by_vertex"]
            if row_by_vertex[edge.u] == row_by_vertex[edge.v]:
                center_x, center_y = layout["center"]
                radius = layout["radius_by_vertex"][edge.u]
                start_angle = layout["angle_by_vertex"][edge.u]
                end_angle = layout["angle_by_vertex"][edge.v]
                delta = _normalized_angle_delta(start_angle, end_angle)
                midpoint_angle = start_angle + (delta / 2.0)
                gap_half_angle = min(abs(delta) / 4.0, 0.09)
                sweep_clockwise = delta >= 0.0
                direction = 1.0 if sweep_clockwise else -1.0
                left_gap_angle = midpoint_angle - (direction * gap_half_angle)
                right_gap_angle = midpoint_angle + (direction * gap_half_angle)
                left_gap_point = _polar_point((center_x, center_y), radius, left_gap_angle)
                right_gap_point = _polar_point((center_x, center_y), radius, right_gap_angle)
                midpoint = _polar_point((center_x, center_y), radius, midpoint_angle)

                left_arc = _arc_path(
                    left,
                    left_gap_point,
                    radius=radius,
                    sweep_clockwise=sweep_clockwise,
                )
                right_arc = _arc_path(
                    right_gap_point,
                    right,
                    radius=radius,
                    sweep_clockwise=sweep_clockwise,
                )
                elements.append(
                    (
                        f'<path d="{left_arc}" stroke="{left_color}" stroke-width="5" '
                        'fill="none" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="left"/>'
                    )
                )
                elements.append(
                    (
                        f'<path d="{right_arc}" stroke="{right_color}" stroke-width="5" '
                        'fill="none" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="right"/>'
                    )
                )
                radial_dx = midpoint[0] - center_x
                radial_dy = midpoint[1] - center_y
                radial_length = math.hypot(radial_dx, radial_dy) or 1.0
                label_x = midpoint[0] + (radial_dx / radial_length) * (26.0 + (label_level * 8.0))
                label_y = midpoint[1] + (radial_dy / radial_length) * (26.0 + (label_level * 8.0))
            elif column_by_vertex[edge.u] == column_by_vertex[edge.v]:
                dx = right[0] - left[0]
                dy = right[1] - left[1]
                length = math.hypot(dx, dy) or 1.0
                unit_x = dx / length
                unit_y = dy / length
                lane_offset = float(layout["radial_lane_by_edge_id"].get(edge.id, 0.0))
                tangent_x = -unit_y
                tangent_y = unit_x
                control = (
                    midpoint[0] + (tangent_x * lane_offset * 28.0),
                    midpoint[1] + (tangent_y * lane_offset * 28.0),
                )
                gap_t = min(0.14, 18.0 / length)
                left_t = 0.5 - (gap_t / 2.0)
                right_t = 0.5 + (gap_t / 2.0)
                left_curve, _ = _quadratic_split(left, control, right, left_t)
                _, right_curve = _quadratic_split(left, control, right, right_t)
                midpoint = _quadratic_point(left, control, right, 0.5)
                elements.append(
                    (
                        f'<path d="{_quadratic_path(*left_curve)}" stroke="{left_color}" '
                        'stroke-width="5" fill="none" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="left" '
                        'data-edge-shape="radial-lane-curve"/>'
                    )
                )
                elements.append(
                    (
                        f'<path d="{_quadratic_path(*right_curve)}" stroke="{right_color}" '
                        'stroke-width="5" fill="none" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="right" '
                        'data-edge-shape="radial-lane-curve"/>'
                    )
                )
                label_sign = (
                    1.0
                    if lane_offset > 0
                    else -1.0
                    if lane_offset < 0
                    else -1.0
                    if (label_level % 2 == 0)
                    else 1.0
                )
                label_distance = 18.0 + (abs(lane_offset) * 14.0) + (label_level * 6.0)
                label_x = midpoint[0] + (tangent_x * label_sign * label_distance)
                label_y = midpoint[1] + (tangent_y * label_sign * label_distance)
            else:
                label_shift = _label_offset(left, right)
                elements.append(
                    (
                        f'<line x1="{left[0]:.2f}" y1="{left[1]:.2f}" '
                        f'x2="{midpoint[0] - 6.0:.2f}" y2="{midpoint[1] - 6.0:.2f}" '
                        f'stroke="{left_color}" stroke-width="5" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="left"/>'
                    )
                )
                elements.append(
                    (
                        f'<line x1="{midpoint[0] + 6.0:.2f}" y1="{midpoint[1] + 6.0:.2f}" '
                        f'x2="{right[0]:.2f}" y2="{right[1]:.2f}" '
                        f'stroke="{right_color}" stroke-width="5" stroke-linecap="round" '
                        f'data-edge-id="{escape(edge.id)}" data-edge-segment="right"/>'
                    )
                )
                label_x = midpoint[0] + label_shift[0]
                label_y = midpoint[1] + label_shift[1]
        else:
            dx = right[0] - left[0]
            dy = right[1] - left[1]
            length = math.hypot(dx, dy) or 1.0
            unit_x = dx / length
            unit_y = dy / length
            left_gap_point = (
                midpoint[0] - (unit_x * gap_radius),
                midpoint[1] - (unit_y * gap_radius),
            )
            right_gap_point = (
                midpoint[0] + (unit_x * gap_radius),
                midpoint[1] + (unit_y * gap_radius),
            )
            elements.append(
                (
                    f'<line x1="{left[0]:.2f}" y1="{left[1]:.2f}" '
                    f'x2="{left_gap_point[0]:.2f}" y2="{left_gap_point[1]:.2f}" '
                    f'stroke="{left_color}" stroke-width="5" stroke-linecap="round" '
                    f'data-edge-id="{escape(edge.id)}" data-edge-segment="left"/>'
                )
            )
            elements.append(
                (
                    f'<line x1="{right_gap_point[0]:.2f}" y1="{right_gap_point[1]:.2f}" '
                    f'x2="{right[0]:.2f}" y2="{right[1]:.2f}" '
                    f'stroke="{right_color}" stroke-width="5" stroke-linecap="round" '
                    f'data-edge-id="{escape(edge.id)}" data-edge-segment="right"/>'
                )
            )
            label_shift = _label_offset(left, right)
            scale = 1.5 + (label_level * 0.35)
            label_x = midpoint[0] + (label_shift[0] * scale)
            label_y = midpoint[1] + (label_shift[1] * scale)

        elements.append(
            (
                f'<circle cx="{midpoint[0]:.2f}" cy="{midpoint[1]:.2f}" r="{gap_radius:.2f}" '
                f'fill="white" stroke="#e5e7eb" stroke-width="1.2" '
                f'data-edge-id="{escape(edge.id)}" data-edge-role="gap"/>'
            )
        )
        elements.extend(
            _text_box(
                text=label_text,
                x_pos=label_x,
                y_pos=label_y,
                edge_id=edge.id,
            )
        )

    for vertex, (x_pos, y_pos) in positions.items():
        elements.append(
            (
                f'<circle cx="{x_pos:.2f}" cy="{y_pos:.2f}" '
                f'r="{node_radius:.2f}" fill="white" stroke="#111827" stroke-width="2"/>'
            )
        )
        elements.append(
            (
                f'<text class="vertex-label" x="{x_pos:.2f}" y="{y_pos + 4:.2f}" '
                f'text-anchor="middle">{escape(vertex)}</text>'
            )
        )

    elements.append(
        (
            f'<text class="subtitle" x="{legend_left:.2f}" y="40">'
            f'Color Legend (r = {escape(fraction_to_string(witness.r))})</text>'
        )
    )
    elements.append(
        (
            f'<text class="legend-label" x="{legend_left:.2f}" y="62">'
            'edge label format: edge_id +/-</text>'
        )
    )
    for index, value in enumerate(sorted(color_map)):
        y_pos = 92 + (index * 24)
        elements.append(
            (
                f'<rect x="{legend_left:.2f}" y="{y_pos - 12:.2f}" width="18" '
                f'height="18" fill="{color_map[value]}" rx="3"/>'
            )
        )
        elements.append(
            (
                f'<text class="legend-label" x="{legend_left + 28:.2f}" '
                f'y="{y_pos + 2:.2f}">{escape(fraction_to_string(value))}</text>'
            )
        )

    elements.append("</svg>")
    return "\n".join(elements)


def render_classification_figures(
    *,
    run_dir: Path,
    output_dir: Path | None = None,
    class_ids: tuple[str, ...] = (),
) -> tuple[Path, tuple[Path, ...]]:
    resolved_run_dir = run_dir.resolve()
    if not (resolved_run_dir / "classes.json").exists():
        raise FileNotFoundError(f"classes.json not found under {resolved_run_dir}.")
    if not (resolved_run_dir / "instance.snapshot.json").exists():
        raise FileNotFoundError(f"instance.snapshot.json not found under {resolved_run_dir}.")

    base_instance = load_instance(resolved_run_dir / "instance.snapshot.json")
    classes_payload_root, classes = _load_class_payloads(resolved_run_dir)
    selected_class_ids = set(class_ids)
    selected_classes = [
        entry
        for entry in classes
        if not selected_class_ids or entry["class_id"] in selected_class_ids
    ]
    if not selected_classes:
        raise ValueError("No matching classes were found for rendering.")

    resolved_output_dir = (output_dir or (resolved_run_dir / "figures")).resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    rendered_paths: list[Path] = []
    classification_mode = str(classes_payload_root["classification_mode"])
    graph_name = str(classes_payload_root["graph_name"])

    for class_payload in selected_classes:
        displayed_instance, displayed_witness = _display_witness_for_class(
            base_instance=base_instance,
            class_payload=class_payload,
            classification_mode=classification_mode,
            run_dir=resolved_run_dir,
        )
        svg = _render_svg(
            displayed_instance=displayed_instance,
            witness=displayed_witness,
            class_payload=class_payload,
            graph_name=graph_name,
        )
        target_path = resolved_output_dir / f"{class_payload['class_id']}.svg"
        target_path.write_text(svg, encoding="utf-8")
        rendered_paths.append(target_path)

    return resolved_output_dir, tuple(rendered_paths)
