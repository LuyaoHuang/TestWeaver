class TestWeaverError(Exception):
    """Base exception for all TestWeaver errors."""


class SchemaError(TestWeaverError):
    """Raised when a test definition fails schema validation."""


class GraphError(TestWeaverError):
    """Raised when graph construction or traversal fails."""


class ExecutionError(TestWeaverError):
    """Raised when test step execution fails unexpectedly."""


class UnreachableTargetError(GraphError):
    """Raised when a target operation cannot be reached from the initial state."""

    def __init__(self, target: str, available_states: set[str]):
        self.target = target
        self.available_states = available_states
        super().__init__(
            f"Target '{target}' requires states not reachable from initial state. "
            f"Available states: {available_states}"
        )
