class TestWeaverError(Exception):
    pass


class SchemaError(TestWeaverError):
    pass


class GraphError(TestWeaverError):
    pass


class ExecutionError(TestWeaverError):
    pass


class UnreachableTargetError(GraphError):
    def __init__(self, target: str, available_states: set[str]):
        self.target = target
        self.available_states = available_states
        super().__init__(
            f"Target '{target}' requires states not reachable from initial state. "
            f"Available states: {available_states}"
        )
