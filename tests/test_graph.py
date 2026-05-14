from testweaver.schema import Operation, TestSuite as Suite, TestDefinition as Defn
from testweaver.graph import build_graph, generate_cases, explain_graph, export_graph


def _make_definition(operations, targets, **kwargs):
    return Defn(
        operations=operations,
        suite=Suite(name="test", targets=targets, **kwargs),
    )


def test_build_graph_simple():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    graph = build_graph(ops)
    # Nodes: {} and {ready}
    assert graph.number_of_nodes() == 2
    # Edges: {} -> {ready} (setup), {ready} -> {} (teardown)
    assert graph.number_of_edges() == 2


def test_build_graph_multi_state():
    ops = [
        Operation(name="step1", type="action", provides=["a"]),
        Operation(name="step2", type="action", provides=["b"], requires=["a"]),
        Operation(name="check", type="check", requires=["a", "b"]),
        Operation(name="clean_b", type="cleanup", requires=["b"], clears=["b"]),
        Operation(name="clean_a", type="cleanup", requires=["a"], clears=["a"]),
    ]
    graph = build_graph(ops)
    # Nodes: {}, {a}, {a,b}, {b} (clean_a from {a,b} produces {b})
    assert graph.number_of_nodes() == 4


def test_generate_cases_simple():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["setup", "check"]
    assert cases[0].cleanup_steps == ["teardown"]


def test_generate_cases_multiple_paths():
    ops = [
        Operation(name="setup_a", type="action", provides=["ready"], description="A"),
        Operation(name="setup_b", type="action", provides=["ready"], description="B"),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    assert len(cases) == 2
    step_sets = {tuple(c.steps) for c in cases}
    assert ("setup_a", "check") in step_sets
    assert ("setup_b", "check") in step_sets


def test_generate_cases_chain():
    ops = [
        Operation(name="step1", type="action", provides=["a"]),
        Operation(name="step2", type="action", provides=["b"], requires=["a"]),
        Operation(name="check", type="check", requires=["a", "b"]),
        Operation(name="clean_b", type="cleanup", requires=["b"], clears=["b"]),
        Operation(name="clean_a", type="cleanup", requires=["a"], clears=["a"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    assert len(cases) >= 1
    assert cases[0].steps == ["step1", "step2", "check"]


def test_generate_cases_max_cases():
    ops = [
        Operation(name=f"setup_{i}", type="action", provides=["ready"])
        for i in range(10)
    ] + [
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"], max_cases=3)
    cases = generate_cases(defn)
    assert len(cases) == 3


def test_explain_graph():
    ops = [
        Operation(name="setup", type="action", provides=["ready"], description="Do setup"),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    info = explain_graph(defn)
    assert info["node_count"] == 2
    assert info["edge_count"] == 2
    assert "ready" in info["reachable_states"]
    assert info["target_reachability"]["check"]["reachable"] is True


def test_no_cleanup_when_disabled():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].cleanup_steps == []


def test_case_ids_are_unique():
    ops = [
        Operation(name="setup_a", type="action", provides=["ready"]),
        Operation(name="setup_b", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids))


def test_export_graph_dot():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    dot = export_graph(defn, "dot")
    assert dot.startswith("digraph TestWeaver {")
    assert "rankdir=LR" in dot
    assert "setup" in dot
    assert "teardown" in dot
    assert 's0' in dot
    assert 's1' in dot
    assert "->" in dot
    assert dot.strip().endswith("}")


def test_export_graph_mermaid():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    mermaid = export_graph(defn, "mermaid")
    assert mermaid.startswith("graph LR")
    assert "-->|setup|" in mermaid
    assert "-->|teardown|" in mermaid
    assert "(initial)" in mermaid


def test_export_graph_labels():
    ops = [
        Operation(name="step1", type="action", provides=["a"]),
        Operation(name="step2", type="action", provides=["b"], requires=["a"]),
        Operation(name="check", type="check", requires=["a", "b"]),
    ]
    defn = _make_definition(ops, ["check"])
    dot = export_graph(defn, "dot")
    assert "(initial)" in dot
    assert '"a"' in dot or "a, b" in dot
    assert "_struct_key" not in dot
    assert "Env(" not in dot
