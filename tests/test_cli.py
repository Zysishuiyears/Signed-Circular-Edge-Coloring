from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from signedcoloring.classification_native import native_module_available
from signedcoloring.cli import main
from signedcoloring.models import SignedEdge, SignedGraphInstance, Witness
from signedcoloring.visualization import _layout_positions, _render_svg


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


def test_optimize_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "star_k1_3_positive.json"
    )

    exit_code = main(
        [
            "optimize",
            "--instance",
            str(instance_path),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    assert (run_dir / "request.json").exists()
    assert (run_dir / "instance.snapshot.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "witness.json").exists()
    assert (run_dir / "solver_stats.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["best_r"] == "3"


def test_classify_signatures_cli_writes_expected_artifacts(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    assert (run_dir / "request.json").exists()
    assert (run_dir / "instance.snapshot.json").exists()
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "classes.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    classes_payload = json.loads((run_dir / "classes.json").read_text(encoding="utf-8"))
    assert summary["classification_mode"] == "switching+automorphism"
    assert summary["switching_class_count"] == 2
    assert summary["combined_class_count"] == 2
    assert len(classes_payload["classes"]) == 2
    assert "preferred_representative_code" in classes_payload["classes"][0]
    assert "preferred_negative_edge_count" in classes_payload["classes"][0]


def test_classify_signatures_cli_can_optimize_representatives(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
            "--optimize-representatives",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    run_dir = run_dirs[0]
    optimize_runs_dir = run_dir / "optimize_runs"
    assert optimize_runs_dir.exists()

    subdirs = sorted(path for path in optimize_runs_dir.iterdir() if path.is_dir())
    assert len(subdirs) == 2
    for subdir in subdirs:
        assert (subdir / "request.json").exists()
        assert (subdir / "instance.snapshot.json").exists()
        assert (subdir / "summary.json").exists()
        assert (subdir / "witness.json").exists()
        assert (subdir / "solver_stats.json").exists()

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    classes_payload = json.loads((run_dir / "classes.json").read_text(encoding="utf-8"))
    assert summary["optimize_representatives"] is True
    assert summary["optimized_class_count"] == 2
    assert summary["global_min_best_r"] == "2"
    assert summary["global_max_best_r"] == "8/3"
    assert summary["global_min_class_ids"] == ["class-0001"]
    assert summary["global_max_class_ids"] == ["class-0002"]

    classes = {entry["class_id"]: entry for entry in classes_payload["classes"]}
    assert classes["class-0001"]["best_r"] == "2"
    assert classes["class-0001"]["attains_global_min_best_r"] is True
    assert classes["class-0001"]["attains_global_max_best_r"] is False
    assert classes["class-0002"]["best_r"] == "8/3"
    assert classes["class-0002"]["attains_global_min_best_r"] is False
    assert classes["class-0002"]["attains_global_max_best_r"] is True
    assert "witness" in classes["class-0002"]
    assert "optimize_run_dir" in classes["class-0002"]


@pytest.mark.skipif(
    not native_module_available(),
    reason="native classification extension is unavailable",
)
def test_classify_signatures_cli_supports_native_backend(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
            "--classification-backend",
            "native-orbit-search",
            "--jobs",
            "2",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1

    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["classification_backend"] == "native-orbit-search"
    assert summary["combined_class_count"] == 2
    assert summary["stats"]["jobs"] == 2
    assert summary["stats"]["native_jobs_used"] == 1
    assert summary["stats"]["native_algorithm"] == "generator-orbit-scan"


def test_render_classification_figures_cli_writes_svg_output(tmp_path: Path) -> None:
    instance_path = (
        Path(__file__).resolve().parents[1] / "data" / "instances" / "cycle_c4_one_negative.json"
    )

    classify_exit_code = main(
        [
            "classify-signatures",
            "--instance",
            str(instance_path),
            "--mode",
            "switching+automorphism",
            "--optimize-representatives",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert classify_exit_code == 0

    run_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    render_exit_code = main(
        [
            "render-classification-figures",
            "--run-dir",
            str(run_dir),
        ]
    )

    assert render_exit_code == 0

    figures_dir = run_dir / "figures"
    assert figures_dir.exists()
    svg_paths = sorted(figures_dir.glob("*.svg"))
    assert len(svg_paths) == 2
    svg_content = svg_paths[0].read_text(encoding="utf-8")
    assert "<svg" in svg_content
    assert "best_r" in svg_content
    assert "canonical =" not in svg_content
    assert "preferred =" not in svg_content
    assert 'data-edge-segment="left"' in svg_content
    assert 'data-edge-segment="right"' in svg_content
    assert 'data-edge-role="gap"' in svg_content


def test_layout_positions_use_cartesian_rings_for_grid_labels() -> None:
    positions, layout = _layout_positions(_c3_square_c3_instance())

    assert layout["kind"] == "cartesian-rings"
    center_x, center_y = layout["center"]
    radii = {
        round(((x_pos - center_x) ** 2 + (y_pos - center_y) ** 2) ** 0.5, 6)
        for x_pos, y_pos in positions.values()
    }
    assert len(radii) == 3


def test_render_svg_uses_lane_curves_for_same_column_edges() -> None:
    instance = _c3_square_c3_instance()
    witness = Witness(
        r=Fraction(5, 1),
        base_colors={edge.id: Fraction(0, 1) for edge in instance.edges},
        incidence_colors={
            edge.id: {
                edge.u: Fraction(0, 1),
                edge.v: Fraction(1, 1),
            }
            for edge in instance.edges
        },
    )
    class_payload = {
        "class_id": "class-0042",
        "best_r": "5",
        "negative_edge_ids": ["e04", "e07", "e09", "e10", "e11", "e16"],
    }

    svg = _render_svg(
        displayed_instance=instance,
        witness=witness,
        class_payload=class_payload,
        graph_name="c3_square_c3",
    )

    assert 'data-layout="cartesian-rings"' in svg
    assert 'data-edge-id="e15" data-edge-segment="left" data-edge-shape="radial-lane-curve"' in svg
    assert 'data-edge-id="e15" data-edge-segment="right" data-edge-shape="radial-lane-curve"' in svg
