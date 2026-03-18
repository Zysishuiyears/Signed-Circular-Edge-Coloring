from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from time import perf_counter
from typing import Any

import networkx as nx
import z3

from signedcoloring.models import DecisionResult, OptimizationResult, SignedGraphInstance, Witness
from signedcoloring.rational import normalize_on_circle

K_CHOICES = (-1, 0, 1, 2)


@dataclass(frozen=True)
class _ModelContext:
    r_expr: z3.ArithRef
    x_vars: dict[str, z3.ArithRef]
    lower_bound: Fraction
    upper_bound: Fraction
    vertex_pair_constraints: int


def _z3_fraction(value: Fraction) -> z3.ArithRef:
    return z3.Q(value.numerator, value.denominator)


def _z3_value_to_fraction(value: z3.ExprRef) -> Fraction:
    simplified = z3.simplify(value)
    if z3.is_rational_value(simplified):
        return Fraction(simplified.numerator_as_long(), simplified.denominator_as_long())
    raise TypeError(f"Expected a rational Z3 value, got {simplified!r}.")


def greedy_edge_coloring_upper_bound(instance: SignedGraphInstance) -> Fraction:
    if not instance.edges:
        return Fraction(2, 1)

    graph = instance.to_networkx()
    line_graph = nx.line_graph(graph)
    coloring = nx.coloring.greedy_color(line_graph, strategy="largest_first")
    num_colors = max(coloring.values(), default=-1) + 1 if coloring else 1
    return Fraction(max(2 * num_colors, instance.max_degree(), 2), 1)


def compute_bounds(instance: SignedGraphInstance) -> tuple[Fraction, Fraction]:
    lower_bound = Fraction(max(2, instance.max_degree()), 1)
    upper_bound = greedy_edge_coloring_upper_bound(instance)
    if upper_bound < lower_bound:
        upper_bound = lower_bound
    return lower_bound, upper_bound


def _build_model(
    instance: SignedGraphInstance,
    engine: z3.Solver | z3.Optimize,
    *,
    optimize_r: bool,
    fixed_r: Fraction | None = None,
) -> _ModelContext:
    lower_bound, upper_bound = compute_bounds(instance)
    r_expr = z3.Real("r") if optimize_r else _z3_fraction(fixed_r or Fraction(0, 1))
    x_vars = {edge.id: z3.Real(f"x_{index}") for index, edge in enumerate(instance.edges)}

    engine.add(r_expr >= _z3_fraction(lower_bound))
    if optimize_r:
        engine.add(r_expr <= _z3_fraction(upper_bound))

    for edge in instance.edges:
        x_var = x_vars[edge.id]
        engine.add(x_var >= 0)
        engine.add(x_var <= r_expr)

    if instance.edges:
        engine.add(x_vars[instance.edges[0].id] == 0)

    vertex_pair_constraints = 0
    for vertex, incident_edges in instance.incident_edges_by_vertex().items():
        for left_edge, right_edge in combinations(incident_edges, 2):
            diff = x_vars[right_edge.id] - x_vars[left_edge.id]
            tau_delta = right_edge.tau(vertex) - left_edge.tau(vertex)
            if tau_delta == 1:
                diff = diff + r_expr / 2
            elif tau_delta == -1:
                diff = diff - r_expr / 2

            disjuncts = []
            for winding in K_CHOICES:
                shifted = diff + (winding * r_expr)
                disjuncts.append(z3.And(shifted >= 1, shifted <= r_expr - 1))
            engine.add(z3.Or(*disjuncts))
            vertex_pair_constraints += 1

    return _ModelContext(
        r_expr=r_expr,
        x_vars=x_vars,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        vertex_pair_constraints=vertex_pair_constraints,
    )


def _extract_witness(
    instance: SignedGraphInstance,
    *,
    model: z3.ModelRef,
    x_vars: dict[str, z3.ArithRef],
    r_value: Fraction,
) -> Witness:
    base_colors: dict[str, Fraction] = {}
    incidence_colors: dict[str, dict[str, Fraction]] = {}

    for edge in instance.edges:
        raw_value = _z3_value_to_fraction(model.eval(x_vars[edge.id], model_completion=True))
        base_color = normalize_on_circle(raw_value, r_value)
        base_colors[edge.id] = base_color
        incidence_colors[edge.id] = {
            edge.u: base_color,
            edge.v: normalize_on_circle(
                base_color + (r_value / 2 if edge.is_positive else 0), r_value
            ),
        }

    return Witness(r=r_value, base_colors=base_colors, incidence_colors=incidence_colors)


def solve_decision(
    instance: SignedGraphInstance,
    *,
    r: Fraction,
    timeout_ms: int | None = None,
) -> DecisionResult:
    if r < 2:
        raise ValueError("r must be at least 2.")

    if not instance.edges:
        return DecisionResult(
            feasible=True,
            r=r,
            witness=Witness(r=r, base_colors={}, incidence_colors={}),
            status="sat",
            stats={
                "mode": "decide",
                "status": "sat",
                "lower_bound": Fraction(2, 1),
                "upper_bound": Fraction(2, 1),
                "num_vertices": len(instance.vertices),
                "num_edges": 0,
                "num_vertex_pair_constraints": 0,
                "elapsed_seconds": 0.0,
            },
        )

    solver = z3.Solver()
    if timeout_ms is not None:
        solver.set(timeout=timeout_ms)

    context = _build_model(instance, solver, optimize_r=False, fixed_r=r)

    started_at = perf_counter()
    status = solver.check()
    elapsed_seconds = perf_counter() - started_at

    witness = None
    feasible = status == z3.sat
    if feasible:
        witness = _extract_witness(
            instance,
            model=solver.model(),
            x_vars=context.x_vars,
            r_value=r,
        )

    stats: dict[str, Any] = {
        "mode": "decide",
        "status": str(status),
        "lower_bound": context.lower_bound,
        "upper_bound": context.upper_bound,
        "num_vertices": len(instance.vertices),
        "num_edges": len(instance.edges),
        "num_vertex_pair_constraints": context.vertex_pair_constraints,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "timeout_ms": timeout_ms,
    }
    if status == z3.unknown:
        stats["reason_unknown"] = solver.reason_unknown()

    return DecisionResult(
        feasible=feasible,
        r=r,
        witness=witness,
        status=str(status),
        stats=stats,
    )


def solve_optimization(
    instance: SignedGraphInstance,
    *,
    timeout_ms: int | None = None,
) -> OptimizationResult:
    lower_bound, upper_bound = compute_bounds(instance)

    if not instance.edges:
        return OptimizationResult(
            best_r=Fraction(2, 1),
            lower_bound=Fraction(2, 1),
            upper_bound=Fraction(2, 1),
            witness=Witness(r=Fraction(2, 1), base_colors={}, incidence_colors={}),
            status="sat",
            stats={
                "mode": "optimize",
                "status": "sat",
                "lower_bound": Fraction(2, 1),
                "upper_bound": Fraction(2, 1),
                "num_vertices": len(instance.vertices),
                "num_edges": 0,
                "num_vertex_pair_constraints": 0,
                "elapsed_seconds": 0.0,
            },
        )

    optimizer = z3.Optimize()
    if timeout_ms is not None:
        optimizer.set(timeout=timeout_ms)

    context = _build_model(instance, optimizer, optimize_r=True)
    objective = optimizer.minimize(context.r_expr)

    started_at = perf_counter()
    status = optimizer.check()
    elapsed_seconds = perf_counter() - started_at

    best_r = None
    witness = None
    if status == z3.sat:
        model = optimizer.model()
        try:
            best_r = _z3_value_to_fraction(optimizer.lower(objective))
        except TypeError:
            best_r = _z3_value_to_fraction(model.eval(context.r_expr, model_completion=True))
        witness = _extract_witness(
            instance,
            model=model,
            x_vars=context.x_vars,
            r_value=best_r,
        )

    stats: dict[str, Any] = {
        "mode": "optimize",
        "status": str(status),
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "num_vertices": len(instance.vertices),
        "num_edges": len(instance.edges),
        "num_vertex_pair_constraints": context.vertex_pair_constraints,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "timeout_ms": timeout_ms,
    }
    if best_r is not None:
        stats["best_r"] = best_r
    if status == z3.unknown:
        stats["reason_unknown"] = optimizer.reason_unknown()

    return OptimizationResult(
        best_r=best_r,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        witness=witness,
        status=str(status),
        stats=stats,
    )
