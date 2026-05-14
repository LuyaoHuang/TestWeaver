# Scalability Controls

Large test definitions with many operations and state transitions can cause the dependency graph to grow exponentially. TestWeaver provides three controls to prevent this.

## Graph Node Limit

Cap the number of states discovered during graph building:

```yaml
suite:
  name: multi_device_test
  targets: [check_all]
  max_graph_nodes: 200   # Default: 500
```

```bash
# Override from CLI
testweaver generate my_test.yaml --max-graph-nodes 100
testweaver run my_test.yaml --max-graph-nodes 100
```

When the limit is reached, BFS stops exploring new states. A warning is logged:

```
WARNING  [testweaver.graph] Graph node limit reached (200); some states were not explored
```

## Path Depth Limit

Limit the maximum number of steps in any generated test case:

```yaml
suite:
  name: deep_test
  targets: [final_check]
  max_path_depth: 10   # Default: 20
```

```bash
testweaver run my_test.yaml --max-path-depth 8
```

This sets the `cutoff` parameter on `nx.all_simple_paths()`. The effective cutoff is `min(shortest_path + 2, max_path_depth)`, so it never generates paths longer than the limit even if the shortest path is much shorter.

## State Depth Limit

Skip states that accumulate too many active entries during graph building:

```yaml
suite:
  name: complex_state_test
  targets: [verify]
  max_state_depth: 6   # Default: 0 (no limit)
```

```bash
testweaver run my_test.yaml --max-state-depth 5
```

This prunes the graph early by discarding Env nodes with more than N leaf states. Useful when multi-instance namespaces create many device sub-states (e.g., `vm.active.TPM:tpm0.ready`, `vm.active.TPM:tpm1.ready`, etc.).

## Combining Controls

All three controls can be used together for maximum effect:

```yaml
suite:
  name: large_integration_test
  targets: [final_check]
  max_graph_nodes: 100
  max_path_depth: 10
  max_state_depth: 5
  max_cases: 50
  generation_strategy: representative
```

```bash
# CLI flags override YAML values
testweaver run my_test.yaml \
  --max-graph-nodes 50 \
  --max-path-depth 8 \
  --max-state-depth 4
```
