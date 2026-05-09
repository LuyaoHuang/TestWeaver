from __future__ import annotations

from itertools import product

import networkx as nx

from .env import Env
from .errors import UnreachableTargetError
from .schema import Operation, TestCase, TestDefinition


def _state_key(env: Env) -> str:
    return repr(env)


def _apply_operation(env: Env, op: Operation) -> Env | None:
    # 1. Check positive requirements (Consumer.REQUIRE)
    for state in op.requires:
        if not env.is_active(state):
            return None
    # 2. Check negative requirements (Consumer.REQUIRE_N)
    for state in op.excludes:
        if env.is_active(state):
            return None
    # 3. Copy env
    new_env = env.copy()
    # 4. Apply grafts first (like original: Graft/Cut before Provider)
    for g in op.grafts:
        new_env.graft(g.src, g.tgt)
    # 5. Apply cuts (remove subtree)
    for path in op.cuts:
        new_env.clear(path)
    # 6. Apply provides (Provider.SET)
    for state in op.provides:
        new_env.set(state)
    # 7. Apply clears (Provider.CLEAR — single node only)
    for state in op.clears:
        new_env.unset(state)
    return new_env


def build_graph(operations: list[Operation]) -> nx.MultiDiGraph:
    """Build a state-transition graph from operations.

    Nodes are Env objects representing hierarchical state trees.
    Edges are operations that transition between states.
    """
    graph = nx.MultiDiGraph()
    initial = Env()
    graph.add_node(initial, label=_state_key(initial))

    queue = [initial]
    visited = {initial}

    while queue:
        current = queue.pop(0)
        for op in operations:
            if op.type == "check":
                continue

            new_env = _apply_operation(current, op)
            if new_env is None or new_env == current:
                continue

            if new_env not in visited:
                visited.add(new_env)
                graph.add_node(new_env, label=_state_key(new_env))
                queue.append(new_env)

            graph.add_edge(current, new_env, operation=op.name)

    return graph


def _find_target_nodes(
    graph: nx.MultiDiGraph,
    target_op: Operation,
) -> list[Env]:
    nodes = []
    for node in graph.nodes:
        if not all(node.is_active(r) for r in target_op.requires):
            continue
        if any(node.is_active(s) for s in target_op.excludes):
            continue
        nodes.append(node)
    return nodes


def _edges_between(
    graph: nx.MultiDiGraph,
    u: Env,
    v: Env,
) -> list[str]:
    return [data["operation"] for _, data in graph[u][v].items()]


def _find_cleanup_path(
    graph: nx.MultiDiGraph,
    from_state: Env,
    operations: list[Operation],
) -> list[str]:
    initial = Env()
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
            new_env = _apply_operation(current, op)
            if new_env is None or new_env == current:
                continue
            if new_env not in cleanup_graph:
                cleanup_graph.add_node(new_env)
            cleanup_graph.add_edge(current, new_env, operation=op.name)
            if new_env not in visited:
                visited.add(new_env)
                queue.append(new_env)

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
            all_reachable: set[str] = set()
            for node in graph.nodes:
                all_reachable.update(node.to_flat_set())
            raise UnreachableTargetError(target_name, all_reachable)

        initial = Env()
        case_count = 0

        for target_node in target_nodes:
            if case_count >= definition.suite.max_cases:
                break

            try:
                raw_paths = nx.all_simple_paths(graph, initial, target_node)
                seen: set[tuple] = set()
                paths: list[list] = []
                for p in raw_paths:
                    key = tuple(id(n) for n in p)
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
                        final_state = _apply_operation(target_node, target_op)
                        if final_state is None:
                            final_state = target_node
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

    initial = Env()
    all_reachable_states: set[str] = set()
    for node in graph.nodes:
        all_reachable_states.update(node.to_flat_set())

    operation_summary = []
    for op in definition.operations:
        entry: dict = {
            "name": op.name,
            "type": op.type,
            "requires": op.requires,
            "provides": op.provides,
            "clears": op.clears,
            "description": op.description,
        }
        if op.excludes:
            entry["excludes"] = op.excludes
        if op.grafts:
            entry["grafts"] = [{"src": g.src, "tgt": g.tgt} for g in op.grafts]
        if op.cuts:
            entry["cuts"] = op.cuts
        operation_summary.append(entry)

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
