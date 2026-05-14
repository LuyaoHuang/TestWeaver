# Graph Visualization

Export the dependency graph in DOT or Mermaid format for visual debugging.

## DOT (Graphviz)

```bash
testweaver graph examples/demo_file_ops.py --format dot
```

Output:

```dot
digraph TestWeaver {
  rankdir=LR;
  s0 [label="(initial)", shape=circle, style=filled, fillcolor=lightblue];
  s1 [label="file.exists", shape=box, style=filled, fillcolor=lightyellow];
  s0 -> s1 [label="create_file_with_echo", color="#2196F3", fontcolor="#2196F3"];
  s0 -> s1 [label="create_file_with_python", color="#2196F3", fontcolor="#2196F3"];
  s0 -> s1 [label="create_file_with_touch", color="#2196F3", fontcolor="#2196F3"];
  s1 -> s0 [label="remove_file", color="#F44336", fontcolor="#F44336"];
}
```

Render with Graphviz:

```bash
testweaver graph examples/demo_file_ops.py --format dot | dot -Tpng -o graph.png
testweaver graph examples/demo_file_ops.py --format dot -o graph.dot  # Save to file
```

## Mermaid

```bash
testweaver graph examples/demo_file_ops.py --format mermaid
```

Output:

```mermaid
graph LR
  s0(("(initial)"))
  s1["file.exists"]
  s0 -->|create_file_with_echo| s1
  s0 -->|create_file_with_python| s1
  s0 -->|create_file_with_touch| s1
  s1 -->|remove_file| s0
```

Paste into GitHub markdown, Mermaid Live Editor, or any compatible renderer.

## Node and Edge Styling

Nodes are styled by role:

| Node Type | DOT Shape | Color |
|-----------|-----------|-------|
| Initial state | Circle | Light blue |
| Dead-end state | Octagon | Light salmon |
| Normal state | Box | Light yellow |

Edges are colored by operation type:

| Operation Type | Color |
|----------------|-------|
| Action | Blue (`#2196F3`) |
| Setup | Green (`#4CAF50`) |
| Cleanup | Red (`#F44336`) |
| Fault | Orange (`#FF9800`) |
