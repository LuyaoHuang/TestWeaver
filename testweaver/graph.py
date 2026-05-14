from __future__ import annotations

import re
from itertools import combinations, product
from typing import Any

import networkx as nx

from .env import Env
from .errors import UnreachableTargetError
from .schema import GraftDef, Operation, ParamChoice, TestCase, TestDefinition


def _state_key(env: Env) -> str:
    """Return a canonical string key for an environment node."""
    return repr(env)


def _safe_val(value: Any) -> str:
    """Sanitize a value for use in dot-separated state paths."""
    return str(value).replace('.', '_')


def _render_state_paths(op: Operation, params: dict[str, Any]) -> Operation:
    """Substitute parameter placeholders in an operation's state paths."""
    safe_params = {k: _safe_val(v) for k, v in params.items()}

    def render(path: str) -> str:
        if '{' not in path:
            return path
        return path.format_map(safe_params)

    updates: dict[str, Any] = {}
    if any('{' in p for p in op.provides):
        updates['provides'] = [render(p) for p in op.provides]
    if any('{' in p for p in op.requires):
        updates['requires'] = [render(p) for p in op.requires]
    if any('{' in p for p in op.clears):
        updates['clears'] = [render(p) for p in op.clears]
    if any('{' in p for p in op.excludes):
        updates['excludes'] = [render(p) for p in op.excludes]
    if any('{' in p for p in op.cuts):
        updates['cuts'] = [render(p) for p in op.cuts]
    if op.grafts and any('{' in g.src or '{' in g.tgt for g in op.grafts):
        updates['grafts'] = [
            GraftDef(src=render(g.src), tgt=render(g.tgt))
            for g in op.grafts
        ]
    if not updates:
        return op
    return op.model_copy(update=updates)


def _has_instance_templates(op: Operation, instance_names: set[str]) -> bool:
    """Check whether an operation references any instance template variables."""
    all_paths = (
        op.provides + op.requires + op.clears + op.excludes + op.cuts
        + [g.src for g in op.grafts] + [g.tgt for g in op.grafts]
    )
    for path in all_paths:
        for name in instance_names:
            if '{' + name + '}' in path:
                return True
    return False


def _expand_instance_choices(
    operations: list[Operation],
    additive_choices: list[ParamChoice],
) -> list[Operation]:
    """Expand additive param choices into per-value operation copies."""
    instance_names = {pc.name for pc in additive_choices}
    result: list[Operation] = []

    for op in operations:
        if not _has_instance_templates(op, instance_names):
            result.append(op)
            continue

        referenced = [
            pc for pc in additive_choices
            if '{' + pc.name + '}' in str(
                op.provides + op.requires + op.clears + op.excludes + op.cuts
            )
        ]
        if not referenced:
            result.append(op)
            continue

        names = [pc.name for pc in referenced]
        value_lists = [pc.values for pc in referenced]
        for combo_values in product(*value_lists):
            combo = dict(zip(names, combo_values))
            tag = ",".join(f"{k}={_safe_val(v)}" for k, v in sorted(combo.items()))
            rendered = _render_state_paths(op, combo)
            expanded = rendered.model_copy(update={
                'name': f"{op.name}[{tag}]",
                'instance_params': combo,
            })
            result.append(expanded)

    return result


def apply_operation(env: Env, op: Operation) -> Env | None:
    """Apply an operation's state changes to an environment.

    Checks that all ``requires`` are active and no ``excludes`` are active,
    then applies grafts, cuts, provides, and clears in order.

    Args:
        env: Current environment state.
        op: Operation whose preconditions and effects to apply.

    Returns:
        A new Env with the operation's effects applied, or None if
        preconditions are not met.
    """
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
    """Create synthetic operations that set exclusive parameter states."""
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
    """Reconstruct parameter values from the synthetic steps in a path."""
    params = dict(base_params)
    value_map: dict[str, dict[str, Any]] = {}
    for pc in param_choices:
        for val in pc.values:
            key = f"params.{pc.name}.{_safe_val(val)}"
            value_map[key] = (pc.name, val)
    for step in steps:
        op = ops_by_name.get(step)
        if not op:
            continue
        if op.param_provider:
            for state in op.provides:
                if state in value_map:
                    name, val = value_map[state]
                    params[name] = val
        if op.instance_params:
            params.update(op.instance_params)
    return params


def _is_initial_ignoring_params(env: Env) -> bool:
    """Check whether an env is empty except for param-related state."""
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
    """Build the state-transition graph from operations and param choices.

    Performs BFS from the empty initial state, applying each non-check
    operation to discover reachable states and transitions.

    Args:
        operations: All defined operations.
        param_choices: Optional parameter choices to expand into
            synthetic operations.

    Returns:
        A directed multigraph where nodes are Env states and edges
        are labeled with operation names.
    """
    if param_choices:
        additive = [pc for pc in param_choices if pc.mode == 'additive']
        exclusive = [pc for pc in param_choices if pc.mode != 'additive']
        if additive:
            operations = _expand_instance_choices(list(operations), additive)
        if exclusive:
            param_ops = _expand_param_choices(exclusive)
            operations = list(operations) + param_ops
    else:
        operations = list(operations)

    graph = nx.MultiDiGraph()
    initial = Env()
    graph.add_node(initial, label=_state_key(initial))

    queue = [initial]
    visited = {initial}

    while queue:
        current = queue.pop(0)
        for op in operations:
            if op.type in ("check", "fault"):
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
    """Find graph nodes from which a target operation can execute."""
    nodes = []
    for node in graph.nodes:
        if not all(node.is_active(r) for r in target_op.requires):
            continue
        if any(node.is_active(s) for s in target_op.excludes):
            continue
        if param_choices:
            exclusive = [pc for pc in param_choices if pc.mode != 'additive']
            all_params_set = all(
                node.is_active(f"params.{pc.name}")
                for pc in exclusive
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
    """Return all operation names on edges from *u* to *v*."""
    return [data["operation"] for _, data in graph[u][v].items()]


def _find_cleanup_path(
    graph: nx.MultiDiGraph,
    from_state: Env,
    operations: list[Operation],
    has_param_choices: bool = False,
) -> list[str]:
    """Find the shortest sequence of cleanup operations back to the initial state."""
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
    """Generate test cases for a single parameter combination."""
    if all_ops is None:
        all_ops = definition.operations
    ops_by_name = {op.name: op for op in all_ops}
    all_pc = definition.suite.param_choices or []
    has_exclusive_choices = bool([pc for pc in all_pc if pc.mode != 'additive'])
    has_any_choices = bool(all_pc)
    all_cases: list[TestCase] = []
    seen_case_keys: set[tuple] = set()

    effective_targets: list[str] = []
    for t in definition.suite.targets:
        if t in ops_by_name:
            effective_targets.append(t)
        else:
            expanded = [n for n in ops_by_name if n.startswith(t + '[')]
            effective_targets.extend(expanded if expanded else [t])

    for target_name in effective_targets:
        target_op = ops_by_name.get(target_name)
        if target_op is None:
            continue
        target_nodes = _find_target_nodes(
            graph, target_op,
            param_choices=all_pc or None,
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
                    if has_any_choices:
                        case_params = _extract_params_from_steps(
                            all_steps, ops_by_name,
                            all_pc, base_params,
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
                            graph, final_state, all_ops, has_exclusive_choices,
                        )

                    case_id = f"{target_name}-{case_count + 1}"
                    if has_any_choices:
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


def _generate_fault_cases(
    definition: TestDefinition,
    graph: nx.MultiDiGraph,
    base_params: dict[str, Any],
    all_ops: list[Operation] | None = None,
) -> list[TestCase]:
    """Generate test cases for fault operations.

    For each fault operation, finds graph nodes where both the target
    operation's preconditions and the fault's extra conditions are met,
    then generates cases that reach those nodes and execute the fault
    handler instead of the target.
    """
    if all_ops is None:
        all_ops = definition.operations
    ops_by_name = {op.name: op for op in all_ops}
    all_pc = definition.suite.param_choices or []
    has_exclusive_choices = bool([pc for pc in all_pc if pc.mode != 'additive'])
    has_any_choices = bool(all_pc)
    fault_cases: list[TestCase] = []

    fault_ops = [op for op in all_ops if op.type == 'fault']
    if not fault_ops:
        return []

    initial = Env()

    for fault_op in fault_ops:
        target_op = ops_by_name.get(fault_op.fault_for)
        if target_op is None:
            expanded = [
                op for name, op in ops_by_name.items()
                if name.startswith(fault_op.fault_for + '[')
            ]
            if not expanded:
                continue
            target_op = expanded[0]

        eff_requires = list(target_op.requires) + [
            r for r in fault_op.requires if r not in target_op.requires
        ]
        eff_excludes = list(target_op.excludes) + [
            e for e in fault_op.excludes if e not in target_op.excludes
        ]

        match_op = Operation(
            name=f"__fault_match_{fault_op.name}",
            type="check",
            requires=eff_requires,
            excludes=eff_excludes,
        )

        target_nodes = _find_target_nodes(
            graph, match_op,
            param_choices=all_pc or None,
        )

        case_count = 0
        seen_case_keys: set[tuple] = set()

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
                    edge_choices.append(
                        _edges_between(graph, path[i], path[i + 1])
                    )

                for combo in product(*edge_choices):
                    if case_count >= definition.suite.max_cases:
                        break

                    all_steps = list(combo) + [fault_op.name]

                    case_params = base_params
                    if has_any_choices:
                        case_params = _extract_params_from_steps(
                            all_steps, ops_by_name,
                            all_pc, base_params,
                        )

                    visible_steps = [
                        s for s in all_steps
                        if not s.startswith('__set_param_')
                    ]

                    cleanup_steps = []
                    if definition.suite.cleanup:
                        cleanup_steps = _find_cleanup_path(
                            graph, target_node, all_ops,
                            has_exclusive_choices,
                        )

                    case_id = f"fault-{fault_op.name}-{case_count + 1}"
                    if has_any_choices:
                        diff = {
                            k: v for k, v in case_params.items()
                            if k not in base_params or base_params[k] != v
                        }
                        if diff:
                            tag = "_".join(
                                f"{k}={v}" for k, v in sorted(diff.items())
                            )
                            case_id = f"fault-{fault_op.name}-{case_count + 1}-{tag}"

                    step_descriptions = []
                    for s in visible_steps:
                        op = ops_by_name.get(s)
                        if op and op.description:
                            step_descriptions.append(f"{s}: {op.description}")
                        else:
                            step_descriptions.append(s)

                    case_key = (
                        tuple(visible_steps),
                        tuple(sorted(case_params.items())),
                        tuple(cleanup_steps),
                    )
                    if case_key in seen_case_keys:
                        continue
                    seen_case_keys.add(case_key)

                    fault_cases.append(TestCase(
                        case_id=case_id,
                        steps=visible_steps,
                        target=fault_op.name,
                        cleanup_steps=cleanup_steps,
                        description=" -> ".join(step_descriptions),
                        params=case_params,
                        is_fault=True,
                    ))
                    case_count += 1

    return fault_cases


def _normalize_step(step: str) -> str:
    """Replace instance-parameter values with wildcards for shape comparison."""
    return re.sub(r'=([^\],]+)', '=*', step)


def _prune_representative(cases: list[TestCase]) -> list[TestCase]:
    """Keep one representative case per unique step-shape."""
    groups: dict[tuple, TestCase] = {}
    for case in cases:
        shape = tuple(_normalize_step(s) for s in case.steps)
        if shape not in groups:
            groups[shape] = case
    return list(groups.values())


def _prune_pairwise(cases: list[TestCase]) -> list[TestCase]:
    """Select the smallest subset of cases that covers all instance-parameter pairs."""
    case_pairs: list[tuple[TestCase, set[tuple[str, str]]]] = []
    all_pairs: set[tuple[str, str]] = set()
    for case in cases:
        tagged = [s for s in case.steps if '[' in s]
        pairs = set(combinations(tagged, 2))
        case_pairs.append((case, pairs))
        all_pairs.update(pairs)

    if not all_pairs:
        return cases

    uncovered = set(all_pairs)
    selected: list[TestCase] = []
    remaining = list(case_pairs)

    while uncovered and remaining:
        best_idx = max(
            range(len(remaining)),
            key=lambda i: len(remaining[i][1] & uncovered),
        )
        case, pairs = remaining.pop(best_idx)
        if not (pairs & uncovered):
            continue
        selected.append(case)
        uncovered -= pairs

    return selected if selected else cases[:1]


def _apply_strategy(cases: list[TestCase], strategy: str) -> list[TestCase]:
    """Apply the generation strategy to prune the case list."""
    if strategy == "pairwise":
        return _prune_pairwise(cases)
    if strategy == "representative":
        return _prune_representative(cases)
    return cases


def generate_cases(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> list[TestCase]:
    """Generate test cases from a test definition.

    Builds the dependency graph (if not provided), enumerates all valid
    paths to each target, and applies the configured generation strategy.

    Args:
        definition: Complete test definition with operations and suite config.
        graph: Pre-built state graph; built automatically if None.

    Returns:
        List of generated test cases.
    """
    param_choices = definition.suite.param_choices
    param_matrix = definition.suite.param_matrix

    if param_matrix and param_matrix.axes:
        return _generate_cases_with_matrix(definition)

    all_ops = list(definition.operations)
    if param_choices:
        additive = [pc for pc in param_choices if pc.mode == 'additive']
        exclusive = [pc for pc in param_choices if pc.mode != 'additive']
        if additive:
            all_ops = _expand_instance_choices(all_ops, additive)
        if exclusive:
            all_ops = all_ops + _expand_param_choices(exclusive)

    if graph is None:
        graph = build_graph(
            definition.operations,
            param_choices=param_choices or None,
        )

    cases = _generate_cases_single(
        definition, graph, definition.suite.params, all_ops,
    )
    cases = _apply_strategy(cases, definition.suite.generation_strategy)

    if definition.suite.faults:
        fault_cases = _generate_fault_cases(
            definition, graph, definition.suite.params, all_ops,
        )
        fault_cases = _apply_strategy(
            fault_cases, definition.suite.generation_strategy,
        )
        cases.extend(fault_cases)

    return cases


def _generate_cases_with_matrix(
    definition: TestDefinition,
) -> list[TestCase]:
    """Generate cases across all parameter matrix combinations."""
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

        if definition.suite.faults:
            fault_combo = _generate_fault_cases(
                filtered_defn, graph, case_params, filtered_ops,
            )
            for case in fault_combo:
                case.case_id = f"{case.case_id}[{param_tag}]"
                case.params = case_params
            all_cases.extend(fault_combo)

    return _apply_strategy(all_cases, definition.suite.generation_strategy)


def explain_graph(
    definition: TestDefinition,
    graph: nx.MultiDiGraph | None = None,
) -> dict[str, Any]:
    """Produce a summary dict describing the dependency graph.

    Args:
        definition: Complete test definition.
        graph: Pre-built graph; built automatically if None.

    Returns:
        Dict with node/edge counts, reachable states, operation summaries,
        target reachability, and bottleneck analysis.
    """
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

    fault_summary = []
    for op in definition.operations:
        if op.type != 'fault':
            continue
        target_op = ops_by_name.get(op.fault_for)
        if target_op is None:
            continue
        eff_requires = list(set(target_op.requires + op.requires))
        eff_excludes = list(set(target_op.excludes + op.excludes))
        match_op = Operation(
            name=f"__fault_match_{op.name}",
            type="check",
            requires=eff_requires,
            excludes=eff_excludes,
        )
        matching_nodes = _find_target_nodes(
            graph, match_op,
            param_choices=definition.suite.param_choices or None,
        )
        fault_summary.append({
            "name": op.name,
            "fault_for": op.fault_for,
            "extra_requires": op.requires,
            "extra_excludes": op.excludes,
            "triggerable_from_n_states": len(matching_nodes),
            "terminal": op.terminal,
        })
    if fault_summary:
        result["fault_operations"] = fault_summary

    return result


def _node_label(env: Env) -> str:
    """Build a human-readable label for a graph node."""
    states = env.to_flat_set()
    if not states:
        return "(initial)"
    return ", ".join(sorted(states))


def _dot_escape(text: str) -> str:
    """Escape a string for use inside DOT double-quoted labels."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


_EDGE_COLORS = {
    "action": "#2196F3",
    "setup": "#4CAF50",
    "cleanup": "#F44336",
    "fault": "#FF9800",
}

_DOT_NODE_STYLES = {
    "initial": 'shape=circle, style=filled, fillcolor=lightblue',
    "dead_end": 'shape=octagon, style=filled, fillcolor=lightsalmon',
    "normal": 'shape=box, style=filled, fillcolor=lightyellow',
}


def export_graph(
    definition: TestDefinition,
    fmt: str,
    graph: nx.MultiDiGraph | None = None,
) -> str:
    """Export the dependency graph as DOT or Mermaid markup.

    Args:
        definition: Complete test definition.
        fmt: Output format, either ``"dot"`` or ``"mermaid"``.
        graph: Pre-built graph; built automatically if None.

    Returns:
        The graph rendered as a string in the requested format.
    """
    if graph is None:
        graph = build_graph(
            definition.operations,
            param_choices=definition.suite.param_choices or None,
        )

    initial = Env()
    op_types = {op.name: op.type for op in definition.operations}

    nodes = list(graph.nodes)
    node_ids = {node: f"s{i}" for i, node in enumerate(nodes)}

    dead_ends: set[Env] = set()
    for node in nodes:
        if node != initial and graph.in_degree(node) >= 1 and graph.out_degree(node) == 0:
            dead_ends.add(node)

    if fmt == "dot":
        return _export_dot(graph, nodes, node_ids, initial, dead_ends, op_types)
    return _export_mermaid(graph, nodes, node_ids, initial, dead_ends, op_types)


def _export_dot(
    graph: nx.MultiDiGraph,
    nodes: list[Env],
    node_ids: dict[Env, str],
    initial: Env,
    dead_ends: set[Env],
    op_types: dict[str, str],
) -> str:
    lines = ["digraph TestWeaver {", "  rankdir=LR;"]

    for node in nodes:
        nid = node_ids[node]
        label = _dot_escape(_node_label(node))
        if node == initial:
            style = _DOT_NODE_STYLES["initial"]
        elif node in dead_ends:
            style = _DOT_NODE_STYLES["dead_end"]
        else:
            style = _DOT_NODE_STYLES["normal"]
        lines.append(f'  {nid} [label="{label}", {style}];')

    for u, v, data in graph.edges(data=True):
        op_name = data["operation"]
        color = _EDGE_COLORS.get(op_types.get(op_name, ""), "#333333")
        label = _dot_escape(op_name)
        lines.append(f'  {node_ids[u]} -> {node_ids[v]} '
                      f'[label="{label}", color="{color}", fontcolor="{color}"];')

    lines.append("}")
    return "\n".join(lines)


def _mermaid_escape(text: str) -> str:
    """Escape a string for Mermaid node labels."""
    return text.replace('"', '#quot;')


def _export_mermaid(
    graph: nx.MultiDiGraph,
    nodes: list[Env],
    node_ids: dict[Env, str],
    initial: Env,
    dead_ends: set[Env],
    op_types: dict[str, str],
) -> str:
    lines = ["graph LR"]

    for node in nodes:
        nid = node_ids[node]
        label = _mermaid_escape(_node_label(node))
        if node == initial:
            lines.append(f'  {nid}(("{label}"))')
        elif node in dead_ends:
            lines.append(f'  {nid}{{{{"{label}"}}}}')
        else:
            lines.append(f'  {nid}["{label}"]')

    for u, v, data in graph.edges(data=True):
        op_name = data["operation"]
        lines.append(f"  {node_ids[u]} -->|{op_name}| {node_ids[v]}")

    return "\n".join(lines)
