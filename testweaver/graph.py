from __future__ import annotations

from itertools import product
from typing import Any

import networkx as nx

from .env import Env
from .errors import UnreachableTargetError
from .schema import Operation, ParamChoice, TestCase, TestDefinition


def _state_key(env: Env) -> str:
    return repr(env)


def _safe_val(value: Any) -> str:
    return str(value).replace('.', '_')


def apply_operation(env: Env, op: Operation) -> Env | None:
    for state in op.requires:
        if not env.is_active(state):
            return None
    for state in op.excludes:
        if env.is_active(state):
            return None
    new_env = env.copy()
    for g in op.grafts:
        new_env.graft(g.src, g.tgt)
    for path in op.cuts:
        new_env.clear(path)
    for state in op.provides:
        new_env.set(state)
    for state in op.clears:
        new_env.unset(state)
    return new_env


def _expand_param_choices(
    param_choices: list[ParamChoice],
) -> list[Operation]:
    synthetic = []
    for pc in param_choices:
        all_states = [
            f"params.{pc.name}.{_safe_val(v)}" for v in pc.values
        ]
        for i, val in enumerate(pc.values):
            state = all_states[i]
            siblings = [s for j, s in enumerate(all_states) if j != i]
            synthetic.append(Operation(
                name=f"__set_param_{pc.name}_{_safe_val(val)}",
                type="action",
                provides=[state],
                excludes=[state] + siblings,
                param_provider=pc.name,
            ))
    return synthetic


def _extract_params_from_steps(
    steps: list[str],
    ops_by_name: dict[str, Operation],
    param_choices: list[ParamChoice],
    base_params: dict[str, Any],
) -> dict[str, Any]:
    params = dict(base_params)
    value_map: dict[str, dict[str, Any]] = {}
    for pc in param_choices:
        for val in pc.values:
            key = f"params.{pc.name}.{_safe_val(val)}"
            value_map[key] = (pc.name, val)
    for step in steps:
        op = ops_by_name.get(step)
        if op and op.param_provider:
            for state in op.provides:
                if state in value_map:
                    name, val = value_map[state]
                    params[name] = val
    return params


def _is_initial_ignoring_params(env: Env) -> bool:
    for key, child in env.children.items():
        if key == 'params':
            continue
        if child._has_active():
            return False
    return not env.data


def build_graph(
    operations: list[Operation],
    param_choices: list[ParamChoice] | None = None,
) -> nx.MultiDiGraph:
    if param_choices:
        param_ops = _expand_param_choices(param_choices)
        operations = list(operations) + param_ops

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

            new_env = apply_operation(current, op)
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
    param_choices: list[ParamChoice] | None = None,
) -> list[Env]:
    nodes = []
    for node in graph.nodes:
        if not all(node.is_active(r) for r in target_op.requires):
            continue
        if any(node.is_active(s) for s in target_op.excludes):
            continue
        if param_choices:
            all_params_set = all(
                node.is_active(f"params.{pc.name}")
                for pc in param_choices
            )
            if not all_params_set:
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
    has_param_choices: bool = False,
) -> list[str]:
    initial = Env()

    if has_param_choices:
        if _is_initial_ignoring_params(from_state):
            return []
    elif from_state == initial:
        return []

    cleanup_ops = [
        op for op in operations
        if op.type == "cleanup" and not op.param_provider
    ]
    if not cleanup_ops:
        return []

    cleanup_graph = nx.DiGraph()
    queue = [from_state]
    visited = {from_state}
    cleanup_graph.add_node(from_state)

    while queue:
        current = queue.pop(0)
        for op in cleanup_ops:
            new_env = apply_operation(current, op)
            if new_env is None or new_env == current:
                continue
            if new_env not in cleanup_graph:
                cleanup_graph.add_node(new_env)
            cleanup_graph.add_edge(current, new_env, operation=op.name)
            if new_env not in visited:
                visited.add(new_env)
                queue.append(new_env)

    target_states = []
    if has_param_choices:
        for node in cleanup_graph.nodes:
            if _is_initial_ignoring_params(node):
                target_states.append(node)
    else:
        if initial in cleanup_graph:
            target_states = [initial]

    if not target_states:
        return []

    best_path = None
    for target in target_states:
        try:
            path = nx.shortest_path(cleanup_graph, from_state, target)
            if best_path is None or len(path) < len(best_path):
                best_path = path
        except nx.NetworkXNoPath:
            continue

    if best_path is None:
        return []

    result = []
    for i in range(len(best_path) - 1):
        edge_data = cleanup_graph.edges[best_path[i], best_path[i + 1]]
        result.append(edge_data["operation"])
    return result


def _generate_cases_single(
    definition: TestDefinition,
    graph: nx.MultiDiGraph,
    base_params: dict[str, Any],
    all_ops: list[Operation] | None = None,
) -> list[TestCase]:
    if all_ops is None:
        all_ops = definition.operations
    ops_by_name = {op.name: op for op in all_ops}
    has_param_choices = bool(definition.suite.param_choices)
    all_cases: list[TestCase] = []
    seen_case_keys: set[tuple] = set()

    for target_name in definition.suite.targets:
        target_op = ops_by_name.get(target_name)
        if target_op is None:
            continue
        target_nodes = _find_target_nodes(
            graph, target_op,
            param_choices=definition.suite.param_choices or None,
        )

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
                shortest_len = nx.shortest_path_length(
                    graph, initial, target_node
                )
                max_depth = shortest_len + 2
                raw_paths = nx.all_simple_paths(
                    graph, initial, target_node, cutoff=max_depth,
                )
            except (nx.NodeNotFound, nx.NetworkXNoPath):
                continue

            seen_paths: set[tuple] = set()
            for path in raw_paths:
                path_key = tuple(id(n) for n in path)
                if path_key in seen_paths:
                    continue
                seen_paths.add(path_key)
                if case_count >= definition.suite.max_cases:
                    break

                edge_choices = []
                for i in range(len(path) - 1):
                    edge_choices.append(_edges_between(graph, path[i], path[i + 1]))

                for combo in product(*edge_choices):
                    if case_count >= definition.suite.max_cases:
                        break

                    all_steps = list(combo) + [target_name]

                    case_params = base_params
                    if has_param_choices:
                        case_params = _extract_params_from_steps(
                            all_steps, ops_by_name,
                            definition.suite.param_choices, base_params,
                        )

                    visible_steps = [
                        s for s in all_steps
                        if not s.startswith('__set_param_')
                    ]

                    cleanup_steps = []
                    if definition.suite.cleanup:
                        final_state = apply_operation(target_node, target_op)
                        if final_state is None:
                            final_state = target_node
                        cleanup_steps = _find_cleanup_path(
                            graph, final_state, all_ops, has_param_choices,
                        )

                    case_id = f"{target_name}-{case_count + 1}"
                    if has_param_choices:
                        diff = {
                            k: v for k, v in case_params.items()
                            if k not in base_params or base_params[k] != v
                        }
                        if diff:
                            tag = "_".join(
                                f"{k}={v}" for k, v in sorted(diff.items())
                            )
                            case_id = f"{target_name}-{case_count + 1}-{tag}"

                    case_key = (
                        tuple(visible_steps),
                        tuple(sorted(case_params.items())),
                        tuple(cleanup_steps),
                    )
                    if case_key in seen_case_keys:
                        continue
                    seen_case_keys.add(case_key)

                    step_descriptions = []
                    for s in visible_steps:
                        op = ops_by_name.get(s)
                        if op and op.description:
                            step_descriptions.append(f"{s}: {op.description}")
                        else:
                            step_descriptions.append(s)

                    all_cases.append(TestCase(
                        case_id=case_id,
                        steps=visible_steps,
                        target=target_name,
                        cleanup_steps=cleanup_steps,
                        description=" -> ".join(step_descriptions),
                        params=case_params,
                    ))
                    case_count += 1

    return all_cases


def generate_cases(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> list[TestCase]:
    param_choices = definition.suite.param_choices
    param_matrix = definition.suite.param_matrix

    if param_matrix and param_matrix.axes:
        return _generate_cases_with_matrix(definition)

    all_ops = list(definition.operations)
    if param_choices:
        all_ops = all_ops + _expand_param_choices(param_choices)

    if graph is None:
        graph = build_graph(
            definition.operations,
            param_choices=param_choices or None,
        )

    return _generate_cases_single(
        definition, graph, definition.suite.params, all_ops,
    )


def _generate_cases_with_matrix(
    definition: TestDefinition,
) -> list[TestCase]:
    from .matrix import expand_matrix, get_skip_ops

    matrix = definition.suite.param_matrix
    combinations = expand_matrix(matrix)
    all_cases: list[TestCase] = []

    for combo in combinations:
        case_params = dict(definition.suite.params)
        case_params.update(combo)

        skip = get_skip_ops(combo, matrix.constraints, definition.operations)

        filtered_ops = [
            op for op in definition.operations if op.name not in skip
        ]

        valid_targets = []
        filtered_names = {op.name for op in filtered_ops}
        for t in definition.suite.targets:
            if t in filtered_names:
                valid_targets.append(t)
        if not valid_targets:
            continue

        graph = build_graph(filtered_ops)

        filtered_defn = TestDefinition(
            operations=filtered_ops,
            suite=definition.suite.model_copy(update={"targets": valid_targets}),
        )

        combo_cases = _generate_cases_single(
            filtered_defn, graph, case_params, filtered_ops,
        )

        param_tag = "_".join(f"{k}={v}" for k, v in sorted(combo.items()))
        for case in combo_cases:
            case.case_id = f"{case.case_id}[{param_tag}]"
            case.params = case_params

        all_cases.extend(combo_cases)

    return all_cases


def explain_graph(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> dict:
    if graph is None:
        graph = build_graph(
            definition.operations,
            param_choices=definition.suite.param_choices or None,
        )

    initial = Env()
    all_reachable_states: set[str] = set()
    for node in graph.nodes:
        all_reachable_states.update(node.to_flat_set())

    operation_summary = []
    for op in definition.operations:
        if op.param_provider:
            continue
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
        target_nodes = _find_target_nodes(
            graph, target_op,
            param_choices=definition.suite.param_choices or None,
        )
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

    result = {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "reachable_states": sorted(all_reachable_states),
        "operations": operation_summary,
        "target_reachability": target_reachability,
        "bottlenecks": bottlenecks,
    }

    if definition.suite.param_choices:
        result["param_choices"] = [
            {"name": pc.name, "values": pc.values}
            for pc in definition.suite.param_choices
        ]

    if definition.suite.param_matrix and definition.suite.param_matrix.axes:
        from .matrix import expand_matrix
        combos = expand_matrix(definition.suite.param_matrix)
        result["param_matrix"] = {
            "axes": [
                {"name": a.name, "values": a.values}
                for a in definition.suite.param_matrix.axes
            ],
            "total_combinations": len(combos),
            "constraints": len(definition.suite.param_matrix.constraints),
        }

    return result
