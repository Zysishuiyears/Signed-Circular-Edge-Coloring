from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

import networkx as nx

Sign = Literal["+", "-"]
Mode = Literal["decide", "optimize"]


@dataclass(frozen=True)
class SignedEdge:
    id: str
    u: str
    v: str
    sign: Sign

    @property
    def is_positive(self) -> bool:
        return self.sign == "+"

    def tau(self, vertex: str) -> int:
        if vertex not in {self.u, self.v}:
            raise ValueError(f"Vertex {vertex!r} is not incident to edge {self.id!r}.")
        return int(self.is_positive and vertex == self.v)


@dataclass(frozen=True)
class SignedGraphInstance:
    name: str
    vertices: tuple[str, ...]
    edges: tuple[SignedEdge, ...]

    def __post_init__(self) -> None:
        vertex_set = set(self.vertices)
        if len(vertex_set) != len(self.vertices):
            raise ValueError("Vertices must be unique.")

        edge_ids = set()
        endpoint_pairs = set()
        for edge in self.edges:
            if edge.id in edge_ids:
                raise ValueError(f"Duplicate edge id: {edge.id!r}.")
            if edge.u == edge.v:
                raise ValueError(f"Self-loops are not supported: {edge.id!r}.")
            if edge.u not in vertex_set or edge.v not in vertex_set:
                raise ValueError(f"Edge {edge.id!r} references an unknown vertex.")
            if edge.sign not in {"+", "-"}:
                raise ValueError(f"Invalid edge sign for {edge.id!r}: {edge.sign!r}.")

            normalized_pair = tuple(sorted((edge.u, edge.v)))
            if normalized_pair in endpoint_pairs:
                raise ValueError(
                    "Only simple graphs are supported in v1; found a repeated endpoint pair "
                    f"for edge {edge.id!r}."
                )

            edge_ids.add(edge.id)
            endpoint_pairs.add(normalized_pair)

    @property
    def edge_by_id(self) -> dict[str, SignedEdge]:
        return {edge.id: edge for edge in self.edges}

    def incident_edges(self, vertex: str) -> tuple[SignedEdge, ...]:
        if vertex not in self.vertices:
            raise ValueError(f"Unknown vertex: {vertex!r}.")
        return tuple(edge for edge in self.edges if edge.u == vertex or edge.v == vertex)

    def incident_edges_by_vertex(self) -> dict[str, tuple[SignedEdge, ...]]:
        return {vertex: self.incident_edges(vertex) for vertex in self.vertices}

    def max_degree(self) -> int:
        degrees = {vertex: 0 for vertex in self.vertices}
        for edge in self.edges:
            degrees[edge.u] += 1
            degrees[edge.v] += 1
        return max(degrees.values(), default=0)

    def to_networkx(self) -> nx.Graph:
        graph = nx.Graph()
        graph.add_nodes_from(self.vertices)
        for edge in self.edges:
            graph.add_edge(edge.u, edge.v, id=edge.id, sign=edge.sign)
        return graph


@dataclass(frozen=True)
class Witness:
    r: Fraction
    base_colors: dict[str, Fraction]
    incidence_colors: dict[str, dict[str, Fraction]]


@dataclass(frozen=True)
class SolveRequest:
    mode: Mode
    instance_path: Path
    r: Fraction | None = None
    timeout_ms: int | None = None
    output_dir: Path = Path("artifacts/runs")
    backend: str = "z3"

    def __post_init__(self) -> None:
        if self.mode not in {"decide", "optimize"}:
            raise ValueError(f"Unsupported mode: {self.mode!r}.")
        if self.mode == "decide" and self.r is None:
            raise ValueError("Decision requests require an explicit r.")
        if self.backend != "z3":
            raise ValueError(f"Unsupported backend: {self.backend!r}.")
        if self.timeout_ms is not None and self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive when provided.")


@dataclass(frozen=True)
class DecisionResult:
    feasible: bool
    r: Fraction
    witness: Witness | None
    status: str
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OptimizationResult:
    best_r: Fraction | None
    lower_bound: Fraction
    upper_bound: Fraction
    witness: Witness | None
    status: str
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    messages: tuple[str, ...]
    stats: dict[str, Any] = field(default_factory=dict)
