from __future__ import annotations

from itertools import product

import networkx as nx

from .errors import UnreachableTargetError
from .schema import Operation, TestCase, TestDefinition


def _state_key(state: frozenset[str]) -> str:
    if not state:
        return "{}"
    return "{" + ", ".join(sorted(state)) + "}"


def build_graph(operations: list[Operation]) -> nx.MultiDiGraph:
    """Build a state-transition graph from operations.

    Nodes are frozensets of active state keys.
    Edges are operations that transition between states.
    Uses MultiDiGraph to support multiple operations between the same state pair.
    """
    graph = nx.MultiDiGraph()
    initial = frozenset()
    graph.add_node(initial, label="{}")

    queue = [initial]
    visited = {initial}

    while queue:
        current = queue.pop(0)
        for op in operations:
            if op.type == "check":
                continue

            if not set(op.requires).issubset(current):
                continue

            next_state = (current | frozenset(op.provides)) - frozenset(op.clears)

            if next_state == current:
                continue

            if next_state not in visited:
                visited.add(next_state)
                graph.add_node(next_state, label=_state_key(next_state))
                queue.append(next_state)

            graph.add_edge(current, next_state, operation=op.name)

    return graph


def _find_target_nodes(
    graph: nx.MultiDiGraph,
    target_op: Operation,
) -> list[frozenset[str]]:
    required = set(target_op.requires)
    return [
        node for node in graph.nodes
        if required.issubset(node)
    ]


def _edges_between(
    graph: nx.MultiDiGraph,
    u: frozenset[str],
    v: frozenset[str],
) -> list[str]:
    return [data["operation"] for _, data in graph[u][v].items()]


def _find_cleanup_path(
    graph: nx.MultiDiGraph,
    from_state: frozenset[str],
    operations: list[Operation],
) -> list[str]:
    initial = frozenset()
    if from_state == initial:
        return []

    cleanup_ops = [op for op in operations if op.type == "cleanup"]
    if not cleanup_ops:
        return []

    cleanup_graph = nx.DiGraph()
    queue = [from_state]
    visited = {from_state}
    cleanup_graph.add_node(from_state)

    while queue:
        current = queue.pop(0)
        for op in cleanup_ops:
            if not set(op.requires).issubset(current):
                continue
            next_state = (current | frozenset(op.provides)) - frozenset(op.clears)
            if next_state == current:
                continue
            if next_state not in cleanup_graph:
                cleanup_graph.add_node(next_state)
            cleanup_graph.add_edge(current, next_state, operation=op.name)
            if next_state not in visited:
                visited.add(next_state)
                queue.append(next_state)

    if initial not in cleanup_graph:
        return []

    try:
        path = nx.shortest_path(cleanup_graph, from_state, initial)
    except nx.NetworkXNoPath:
        return []

    result = []
    for i in range(len(path) - 1):
        edge_data = cleanup_graph.edges[path[i], path[i + 1]]
        result.append(edge_data["operation"])
    return result


def generate_cases(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> list[TestCase]:
    if graph is None:
        graph = build_graph(definition.operations)

    ops_by_name = {op.name: op for op in definition.operations}
    all_cases: list[TestCase] = []

    for target_name in definition.suite.targets:
        target_op = ops_by_name[target_name]
        target_nodes = _find_target_nodes(graph, target_op)

        if not target_nodes:
            all_reachable = set()
            for node in graph.nodes:
                all_reachable.update(node)
            raise UnreachableTargetError(target_name, all_reachable)

        initial = frozenset()
        case_count = 0

        for target_node in target_nodes:
            if case_count >= definition.suite.max_cases:
                break

            try:
                raw_paths = nx.all_simple_paths(graph, initial, target_node)
                seen: set[tuple] = set()
                paths: list[list] = []
                for p in raw_paths:
                    key = tuple(p)
                    if key not in seen:
                        seen.add(key)
                        paths.append(p)
            except nx.NodeNotFound:
                continue

            for path in paths:
                if case_count >= definition.suite.max_cases:
                    break

                edge_choices = []
                for i in range(len(path) - 1):
                    edge_choices.append(_edges_between(graph, path[i], path[i + 1]))

                for combo in product(*edge_choices):
                    if case_count >= definition.suite.max_cases:
                        break

                    steps = list(combo) + [target_name]

                    cleanup_steps = []
                    if definition.suite.cleanup:
                        final_state = target_node | frozenset(target_op.provides)
                        cleanup_steps = _find_cleanup_path(
                            graph, final_state, definition.operations
                        )

                    case_id = f"{target_name}-{case_count + 1}"
                    step_descriptions = []
                    for s in steps:
                        op = ops_by_name[s]
                        step_descriptions.append(
                            f"{s}: {op.description}" if op.description else s
                        )

                    all_cases.append(TestCase(
                        case_id=case_id,
                        steps=steps,
                        target=target_name,
                        cleanup_steps=cleanup_steps,
                        description=" -> ".join(step_descriptions),
                    ))
                    case_count += 1

    return all_cases


def explain_graph(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> dict:
    if graph is None:
        graph = build_graph(definition.operations)

    initial = frozenset()
    all_reachable_states: set[str] = set()
    for node in graph.nodes:
        all_reachable_states.update(node)

    operation_summary = []
    for op in definition.operations:
        operation_summary.append({
            "name": op.name,
            "type": op.type,
            "requires": op.requires,
            "provides": op.provides,
            "clears": op.clears,
            "description": op.description,
        })

    ops_by_name = {op.name: op for op in definition.operations}
    target_reachability = {}
    for target_name in definition.suite.targets:
        target_op = ops_by_name[target_name]
        target_nodes = _find_target_nodes(graph, target_op)
        target_reachability[target_name] = {
            "reachable": len(target_nodes) > 0,
            "reachable_from_n_states": len(target_nodes),
            "requires": target_op.requires,
        }

    bottlenecks = []
    for node in graph.nodes:
        if node == initial:
            continue
        in_degree = graph.in_degree(node)
        out_degree = graph.out_degree(node)
        if in_degree >= 1 and out_degree == 0:
            bottlenecks.append({
                "state": _state_key(node),
                "dead_end": True,
                "in_degree": in_degree,
            })

    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "reachable_states": sorted(all_reachable_states),
        "operations": operation_summary,
        "target_reachability": target_reachability,
        "bottlenecks": bottlenecks,
    }
