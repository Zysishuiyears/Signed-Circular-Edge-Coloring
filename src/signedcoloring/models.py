from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

import networkx as nx

Sign = Literal["+", "-"]
Mode = Literal["decide", "optimize"]
ClassificationMode = Literal["switching-only", "switching+automorphism"]
ClassificationBackend = Literal["generic", "native-orbit-search"]


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


@dataclass(frozen=True)
class ClassificationRequest:
    instance_path: Path
    classification_mode: ClassificationMode = "switching-only"
    classification_backend: ClassificationBackend = "generic"
    jobs: int = 1
    k: int | None = None
    limit: int | None = None
    emit_representatives: bool = False
    optimize_representatives: bool = False
    optimize_timeout_ms: int | None = None
    output_dir: Path = Path("artifacts/runs")

    def __post_init__(self) -> None:
        if self.classification_mode not in {"switching-only", "switching+automorphism"}:
            raise ValueError(f"Unsupported classification mode: {self.classification_mode!r}.")
        if self.classification_backend not in {"generic", "native-orbit-search"}:
            raise ValueError(
                f"Unsupported classification backend: {self.classification_backend!r}."
            )
        if self.jobs <= 0:
            raise ValueError("jobs must be positive.")
        if self.k is not None and self.k < 0:
            raise ValueError("k must be non-negative when provided.")
        if self.limit is not None and self.limit <= 0:
            raise ValueError("limit must be positive when provided.")
        if self.optimize_timeout_ms is not None and self.optimize_timeout_ms <= 0:
            raise ValueError("optimize_timeout_ms must be positive when provided.")


@dataclass(frozen=True)
class SignatureClassEntry:
    class_id: str
    representative_code: str
    cycle_bit_code: str
    representative_bits: tuple[int, ...]
    representative_signs_by_edge_id: dict[str, Sign]
    preferred_representative_code: str | None = None
    preferred_representative_bits: tuple[int, ...] | None = None
    preferred_representative_signs_by_edge_id: dict[str, Sign] | None = None
    preferred_negative_edge_ids: tuple[str, ...] | None = None
    preferred_negative_edges: tuple[tuple[str, str, str], ...] | None = None
    preferred_negative_edge_count: int | None = None
    switching_orbit_size: int | None = None
    automorphism_orbit_size: int | None = None
    reachable_negative_edge_counts: tuple[int, ...] | None = None
    negative_edge_ids: tuple[str, ...] | None = None
    negative_edges: tuple[tuple[str, str, str], ...] | None = None
    best_r: Fraction | None = None
    best_r_minus_delta: Fraction | None = None
    best_r_over_delta: Fraction | None = None
    optimize_status: str | None = None
    witness: Witness | None = None
    optimization_result: OptimizationResult | None = None
    attains_global_min_best_r: bool | None = None
    attains_global_max_best_r: bool | None = None


@dataclass(frozen=True)
class ClassificationResult:
    graph_name: str
    classification_mode: ClassificationMode
    num_vertices: int
    num_edges: int
    num_components: int
    cycle_rank: int
    theoretical_switching_class_count: int
    switching_class_count: int
    combined_class_count: int | None
    k: int | None
    bit_convention: str
    edge_order: tuple[str, ...]
    classes: tuple[SignatureClassEntry, ...]
    classification_backend: ClassificationBackend = "generic"
    optimize_representatives: bool = False
    optimized_class_count: int | None = None
    delta: int | None = None
    global_min_best_r: Fraction | None = None
    global_max_best_r: Fraction | None = None
    global_min_class_ids: tuple[str, ...] = ()
    global_max_class_ids: tuple[str, ...] = ()
    global_min_representative_codes: tuple[str, ...] = ()
    global_max_representative_codes: tuple[str, ...] = ()
    stats: dict[str, Any] = field(default_factory=dict)
