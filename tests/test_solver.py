from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from signedcoloring.io import load_instance
from signedcoloring.solver import solve_decision, solve_optimization
from signedcoloring.verify import verify_witness


def _instance_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "instances" / name


def test_single_positive_edge_optimizes_to_two() -> None:
    instance = load_instance(_instance_path("single_positive_edge.json"))

    result = solve_optimization(instance)

    assert result.best_r == Fraction(2, 1)
    assert result.witness is not None
    assert verify_witness(instance, result.witness).valid


def test_star_k13_decide_matches_expectation() -> None:
    instance = load_instance(_instance_path("star_k1_3_positive.json"))

    feasible = solve_decision(instance, r=Fraction(3, 1))
    infeasible = solve_decision(instance, r=Fraction(5, 2))

    assert feasible.feasible is True
    assert feasible.witness is not None
    assert verify_witness(instance, feasible.witness).valid
    assert infeasible.feasible is False


def test_star_k13_optimizes_to_three() -> None:
    instance = load_instance(_instance_path("star_k1_3_positive.json"))

    result = solve_optimization(instance)

    assert result.best_r == Fraction(3, 1)
    assert result.witness is not None
    assert verify_witness(instance, result.witness).valid
