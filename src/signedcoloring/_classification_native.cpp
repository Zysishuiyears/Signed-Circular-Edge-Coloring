#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <functional>
#include <memory>
#include <queue>
#include <set>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>

#include "graph.hh"
#include "stats.hh"

namespace py = pybind11;

namespace {

using CycleMask = std::uint64_t;
using EdgeEndpoints = std::vector<std::pair<unsigned int, unsigned int>>;

struct GeneratorAction {
    std::vector<CycleMask> column_masks;
};

struct CanonicalClass {
    CycleMask cycle_mask = 0;
    std::uint64_t switching_class_count = 0;
};

struct ScanResult {
    std::vector<CanonicalClass> classes;
    std::uint64_t jobs_used = 1;
    std::uint64_t enumerated_switching_class_count = 0;
    std::uint64_t generator_count = 0;
    double native_elapsed_seconds = 0.0;
};

struct GraphStructure {
    unsigned int num_vertices = 0;
    EdgeEndpoints edge_endpoints;
    std::vector<unsigned int> tree_edge_indices;
    std::vector<unsigned int> non_tree_edge_indices;
    std::vector<unsigned int> non_tree_offset_by_edge;
    std::vector<std::vector<std::pair<unsigned int, unsigned int>>> tree_adjacency;
    std::vector<unsigned int> component_roots;
    std::unordered_map<std::uint64_t, unsigned int> edge_index_by_pair;
};

std::uint64_t edge_key(unsigned int left, unsigned int right) {
    const auto min_vertex = std::min(left, right);
    const auto max_vertex = std::max(left, right);
    return (static_cast<std::uint64_t>(min_vertex) << 32) | static_cast<std::uint64_t>(max_vertex);
}

unsigned int cycle_bit_at_offset(
    const CycleMask cycle_mask,
    const std::size_t cycle_rank,
    const std::size_t offset
) {
    const auto shift = static_cast<unsigned int>(cycle_rank - 1U - offset);
    return static_cast<unsigned int>((cycle_mask >> shift) & 1ULL);
}

bool cycle_mask_is_lex_smaller(
    const CycleMask left_mask,
    const CycleMask right_mask,
    const std::vector<unsigned int>& non_tree_offset_by_edge
) {
    if (left_mask == right_mask) {
        return false;
    }

    const auto cycle_rank = std::count_if(
        non_tree_offset_by_edge.begin(),
        non_tree_offset_by_edge.end(),
        [](const unsigned int offset) { return offset != static_cast<unsigned int>(-1); }
    );

    for (std::size_t edge_index = 0; edge_index < non_tree_offset_by_edge.size(); ++edge_index) {
        const auto offset = non_tree_offset_by_edge[edge_index];
        if (offset == static_cast<unsigned int>(-1)) {
            continue;
        }
        const auto left_bit = cycle_bit_at_offset(left_mask, cycle_rank, offset);
        const auto right_bit = cycle_bit_at_offset(right_mask, cycle_rank, offset);
        if (left_bit != right_bit) {
            return left_bit < right_bit;
        }
    }

    return false;
}

GraphStructure build_graph_structure(
    const int num_vertices,
    const EdgeEndpoints& edge_endpoints,
    const std::vector<unsigned int>& non_tree_edge_indices
) {
    if (num_vertices <= 0) {
        throw std::runtime_error("num_vertices must be positive.");
    }

    GraphStructure structure;
    structure.num_vertices = static_cast<unsigned int>(num_vertices);
    structure.edge_endpoints = edge_endpoints;
    structure.non_tree_edge_indices = non_tree_edge_indices;
    structure.non_tree_offset_by_edge.assign(edge_endpoints.size(), static_cast<unsigned int>(-1));
    structure.tree_adjacency.assign(num_vertices, {});

    for (std::size_t edge_index = 0; edge_index < edge_endpoints.size(); ++edge_index) {
        structure.edge_index_by_pair.emplace(
            edge_key(edge_endpoints[edge_index].first, edge_endpoints[edge_index].second),
            static_cast<unsigned int>(edge_index)
        );
    }

    for (std::size_t offset = 0; offset < non_tree_edge_indices.size(); ++offset) {
        structure.non_tree_offset_by_edge[non_tree_edge_indices[offset]] = static_cast<unsigned int>(offset);
    }

    for (std::size_t edge_index = 0; edge_index < edge_endpoints.size(); ++edge_index) {
        if (structure.non_tree_offset_by_edge[edge_index] == static_cast<unsigned int>(-1)) {
            structure.tree_edge_indices.push_back(static_cast<unsigned int>(edge_index));
            const auto [left, right] = edge_endpoints[edge_index];
            structure.tree_adjacency[left].push_back({right, static_cast<unsigned int>(edge_index)});
            structure.tree_adjacency[right].push_back({left, static_cast<unsigned int>(edge_index)});
        }
    }

    std::vector<bool> seen(num_vertices, false);
    for (int vertex = 0; vertex < num_vertices; ++vertex) {
        if (seen[vertex]) {
            continue;
        }
        structure.component_roots.push_back(static_cast<unsigned int>(vertex));
        std::queue<unsigned int> queue;
        queue.push(static_cast<unsigned int>(vertex));
        seen[vertex] = true;
        while (!queue.empty()) {
            const auto current = queue.front();
            queue.pop();
            for (const auto& [neighbor, _] : structure.tree_adjacency[current]) {
                if (seen[neighbor]) {
                    continue;
                }
                seen[neighbor] = true;
                queue.push(neighbor);
            }
        }
    }

    return structure;
}

std::vector<unsigned int> reconstruct_bits(
    const CycleMask cycle_mask,
    const GraphStructure& structure
) {
    std::vector<unsigned int> bits(structure.edge_endpoints.size(), 0);
    const auto cycle_rank = structure.non_tree_edge_indices.size();
    for (std::size_t offset = 0; offset < cycle_rank; ++offset) {
        const auto edge_index = structure.non_tree_edge_indices[offset];
        bits[edge_index] = cycle_bit_at_offset(cycle_mask, cycle_rank, offset);
    }
    return bits;
}

std::vector<unsigned int> apply_switch_flags(
    const std::vector<unsigned int>& bits,
    const std::vector<unsigned int>& switch_flags,
    const GraphStructure& structure
) {
    std::vector<unsigned int> switched(bits.size(), 0);
    for (std::size_t edge_index = 0; edge_index < bits.size(); ++edge_index) {
        const auto [left, right] = structure.edge_endpoints[edge_index];
        switched[edge_index] = bits[edge_index] ^ switch_flags[left] ^ switch_flags[right];
    }
    return switched;
}

std::vector<unsigned int> canonical_switching_rep(
    const std::vector<unsigned int>& bits,
    const GraphStructure& structure
) {
    std::vector<unsigned int> switch_flags(structure.num_vertices, 0);
    std::vector<bool> seen(structure.num_vertices, false);

    for (const auto root : structure.component_roots) {
        std::queue<unsigned int> queue;
        queue.push(root);
        seen[root] = true;
        while (!queue.empty()) {
            const auto current = queue.front();
            queue.pop();
            for (const auto& [neighbor, edge_index] : structure.tree_adjacency[current]) {
                if (seen[neighbor]) {
                    continue;
                }
                switch_flags[neighbor] = switch_flags[current] ^ bits[edge_index];
                seen[neighbor] = true;
                queue.push(neighbor);
            }
        }
    }

    return apply_switch_flags(bits, switch_flags, structure);
}

CycleMask extract_cycle_mask(
    const std::vector<unsigned int>& bits,
    const GraphStructure& structure
) {
    CycleMask cycle_mask = 0;
    const auto cycle_rank = structure.non_tree_edge_indices.size();
    for (std::size_t offset = 0; offset < cycle_rank; ++offset) {
        const auto edge_index = structure.non_tree_edge_indices[offset];
        if (bits[edge_index] == 0) {
            continue;
        }
        const auto shift = static_cast<unsigned int>(cycle_rank - 1U - offset);
        cycle_mask |= (CycleMask{1} << shift);
    }
    return cycle_mask;
}

std::vector<unsigned int> apply_vertex_permutation_to_bits(
    const std::vector<unsigned int>& bits,
    const std::vector<unsigned int>& permutation,
    const GraphStructure& structure
) {
    std::vector<unsigned int> transformed(bits.size(), 0);
    for (std::size_t edge_index = 0; edge_index < bits.size(); ++edge_index) {
        const auto [left, right] = structure.edge_endpoints[edge_index];
        const auto image_left = permutation[left];
        const auto image_right = permutation[right];
        const auto image_edge = structure.edge_index_by_pair.at(edge_key(image_left, image_right));
        transformed[image_edge] = bits[edge_index];
    }
    return transformed;
}

std::vector<GeneratorAction> compute_generator_actions(const GraphStructure& structure) {
    bliss::Graph graph(structure.num_vertices);
    graph.set_splitting_heuristic(bliss::Graph::shs_fsm);
    for (unsigned int vertex = 0; vertex < structure.num_vertices; ++vertex) {
        graph.change_color(vertex, 0);
    }
    for (const auto& [left, right] : structure.edge_endpoints) {
        graph.add_edge(left, right);
    }

    std::set<std::vector<unsigned int>> generators;
    bliss::Stats stats;
    graph.find_automorphisms(
        stats,
        [&generators](const unsigned int n, const unsigned int* automorphism) {
            std::vector<unsigned int> permutation(automorphism, automorphism + n);
            generators.insert(std::move(permutation));
        }
    );

    const auto cycle_rank = structure.non_tree_edge_indices.size();
    std::vector<GeneratorAction> actions;
    actions.reserve(generators.size());

    for (const auto& generator : generators) {
        bool is_identity = true;
        for (std::size_t index = 0; index < generator.size(); ++index) {
            if (generator[index] != index) {
                is_identity = false;
                break;
            }
        }
        if (is_identity) {
            continue;
        }

        GeneratorAction action;
        action.column_masks.reserve(cycle_rank);
        for (std::size_t offset = 0; offset < cycle_rank; ++offset) {
            const auto shift = static_cast<unsigned int>(cycle_rank - 1U - offset);
            const CycleMask basis_mask = (CycleMask{1} << shift);
            const auto basis_bits = reconstruct_bits(basis_mask, structure);
            const auto transformed_bits = apply_vertex_permutation_to_bits(
                basis_bits,
                generator,
                structure
            );
            const auto canonical_bits = canonical_switching_rep(transformed_bits, structure);
            action.column_masks.push_back(extract_cycle_mask(canonical_bits, structure));
        }
        actions.push_back(std::move(action));
    }

    return actions;
}

CycleMask apply_generator_action(
    const CycleMask cycle_mask,
    const GeneratorAction& action,
    const std::size_t cycle_rank
) {
    CycleMask result = 0;
    for (std::size_t offset = 0; offset < cycle_rank; ++offset) {
        if (cycle_bit_at_offset(cycle_mask, cycle_rank, offset) == 0U) {
            continue;
        }
        result ^= action.column_masks[offset];
    }
    return result;
}

ScanResult canonical_scan_impl(
    const int num_vertices,
    const EdgeEndpoints& edge_endpoints,
    const std::vector<unsigned int>& non_tree_edge_indices,
    const int /*requested_jobs*/
) {
    const GraphStructure structure = build_graph_structure(
        num_vertices,
        edge_endpoints,
        non_tree_edge_indices
    );
    const auto cycle_rank = structure.non_tree_edge_indices.size();
    if (cycle_rank == 0 || cycle_rank > 63) {
        throw std::runtime_error(
            "native-orbit-search supports cycle rank between 1 and 63."
        );
    }

    const auto started_at = std::chrono::steady_clock::now();
    const auto actions = compute_generator_actions(structure);
    const CycleMask total_masks = (CycleMask{1} << cycle_rank);

    std::vector<std::uint8_t> visited(static_cast<std::size_t>(total_masks), 0);
    std::vector<CanonicalClass> classes;

    for (CycleMask seed = 0; seed < total_masks; ++seed) {
        if (visited[static_cast<std::size_t>(seed)] != 0U) {
            continue;
        }

        visited[static_cast<std::size_t>(seed)] = 1U;
        std::vector<CycleMask> queue;
        queue.push_back(seed);

        std::uint64_t orbit_size = 0;
        CycleMask best_cycle_mask = seed;

        for (std::size_t index = 0; index < queue.size(); ++index) {
            const auto current = queue[index];
            orbit_size += 1;
            if (cycle_mask_is_lex_smaller(
                current,
                best_cycle_mask,
                structure.non_tree_offset_by_edge
            )) {
                best_cycle_mask = current;
            }

            for (const auto& action : actions) {
                const auto image = apply_generator_action(current, action, cycle_rank);
                if (visited[static_cast<std::size_t>(image)] != 0U) {
                    continue;
                }
                visited[static_cast<std::size_t>(image)] = 1U;
                queue.push_back(image);
            }
        }

        classes.push_back(CanonicalClass{best_cycle_mask, orbit_size});
    }

    std::sort(
        classes.begin(),
        classes.end(),
        [&structure](const CanonicalClass& left, const CanonicalClass& right) {
            return cycle_mask_is_lex_smaller(
                left.cycle_mask,
                right.cycle_mask,
                structure.non_tree_offset_by_edge
            );
        }
    );

    const auto finished_at = std::chrono::steady_clock::now();
    return ScanResult{
        std::move(classes),
        1,
        total_masks,
        static_cast<std::uint64_t>(actions.size()),
        std::chrono::duration<double>(finished_at - started_at).count(),
    };
}

py::dict canonical_scan(
    const int num_vertices,
    const EdgeEndpoints& edge_endpoints,
    const std::vector<unsigned int>& non_tree_edge_indices,
    const int jobs
) {
    ScanResult result;
    {
        py::gil_scoped_release release;
        result = canonical_scan_impl(
            num_vertices,
            edge_endpoints,
            non_tree_edge_indices,
            jobs
        );
    }

    py::list classes;
    for (const auto& entry : result.classes) {
        py::dict payload;
        payload["cycle_mask"] = py::int_(entry.cycle_mask);
        payload["switching_class_count"] = py::int_(entry.switching_class_count);
        classes.append(payload);
    }

    py::dict payload;
    payload["classes"] = classes;
    payload["jobs_used"] = py::int_(result.jobs_used);
    payload["enumerated_switching_class_count"] = py::int_(result.enumerated_switching_class_count);
    payload["generator_count"] = py::int_(result.generator_count);
    payload["merge_elapsed_seconds"] = py::float_(0.0);
    payload["native_elapsed_seconds"] = py::float_(result.native_elapsed_seconds);
    return payload;
}

}  // namespace

PYBIND11_MODULE(_classification_native, module) {
    module.doc() = "Native orbit-scan utilities for signedcoloring classification.";
    module.def(
        "canonical_scan",
        &canonical_scan,
        py::arg("num_vertices"),
        py::arg("edge_endpoints"),
        py::arg("non_tree_edge_indices"),
        py::arg("jobs")
    );
}
