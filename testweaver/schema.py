from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)


class ParamDef(BaseModel):
    """Definition of a single test parameter."""

    name: str
    type: Literal["string", "integer", "float", "boolean", "list", "dict"] = "string"
    description: str = ""
    default: Any = None
    required: bool = True


class GraftDef(BaseModel):
    """Source-to-target mapping for a state graft operation."""

    src: str
    tgt: str


class ParamChoice(BaseModel):
    """Named set of parameter values for combinatorial test generation."""

    name: str
    values: list[Any]
    description: str = ""
    mode: Literal["exclusive", "additive"] = "exclusive"


class ParamAxis(BaseModel):
    """Single axis of a parameter matrix."""

    name: str
    values: list[Any]
    description: str = ""


class ParamConstraint(BaseModel):
    """Constraint that excludes or skips operations for specific parameter values."""

    when: dict[str, Any]
    skip_ops: list[str] = Field(default_factory=list)
    exclude: bool = False
    reason: str = ""


class ParamMatrix(BaseModel):
    """Multi-axis parameter matrix with optional constraints."""

    axes: list[ParamAxis] = Field(default_factory=list)
    constraints: list[ParamConstraint] = Field(default_factory=list)


class Operation(BaseModel):
    """A single test operation with state dependencies and an executable action.

    Attributes:
        name: Unique operation identifier.
        type: Role in the test graph (action, check, setup, or cleanup).
        provides: States activated after successful execution.
        requires: States that must be active before execution.
        clears: States deactivated after execution.
        excludes: States that must not be active for this operation to run.
        callable: Python function to execute (set when loaded from a module).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    type: Literal["action", "check", "setup", "cleanup", "fault"] = "action"
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    clears: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    grafts: list[GraftDef] = Field(default_factory=list)
    cuts: list[str] = Field(default_factory=list)
    params: list[ParamDef] = Field(default_factory=list)
    skip_when: list[dict[str, Any]] = Field(default_factory=list)
    run: str = ""
    verify: str = ""
    timeout: int | None = None
    callable: Callable | None = Field(default=None, exclude=True)
    verify_callable: Callable | None = Field(default=None, exclude=True)
    param_provider: str | None = Field(default=None, exclude=True)
    fault_for: str | None = Field(default=None)
    terminal: bool = True
    priority: int = 0
    instance_params: dict[str, Any] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="after")
    def check_fault_constraints(self) -> Operation:
        """Ensure fault operations have no state-write fields and specify fault_for."""
        if self.type == "fault":
            if not self.fault_for:
                raise ValueError(
                    f"Fault operation '{self.name}' must specify 'fault_for'"
                )
            for field in ("provides", "clears", "cuts"):
                if getattr(self, field):
                    raise ValueError(
                        f"Fault operation '{self.name}' must not declare "
                        f"'{field}' (faults don't change state)"
                    )
            if self.grafts:
                raise ValueError(
                    f"Fault operation '{self.name}' must not declare "
                    f"'grafts' (faults don't change state)"
                )
        return self

    @model_validator(mode="after")
    def check_cleanup_has_clears(self) -> Operation:
        """Ensure cleanup operations declare at least one clears or cuts entry."""
        if self.type == "cleanup" and not self.clears and not self.cuts:
            raise ValueError(
                f"Operation '{self.name}' is type 'cleanup' but has no 'clears' or 'cuts' entries"
            )
        return self


class TestSuite(BaseModel):
    """Configuration for test case generation."""

    name: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    param_choices: list[ParamChoice] = Field(default_factory=list)
    param_matrix: ParamMatrix | None = None
    targets: list[str]
    max_cases: int = 100
    max_graph_nodes: int = 500
    max_path_depth: int = 20
    max_state_depth: int = 0
    cleanup: bool = True
    faults: bool = True
    generation_strategy: Literal["exhaustive", "pairwise", "representative"] = "exhaustive"


class LifecycleHooks(BaseModel):
    """Container for lifecycle hook callables extracted from test modules."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    suite_setup: list[Callable] = Field(default_factory=list, exclude=True)
    suite_teardown: list[Callable] = Field(default_factory=list, exclude=True)
    case_setup: list[Callable] = Field(default_factory=list, exclude=True)
    case_teardown: list[Callable] = Field(default_factory=list, exclude=True)


class TestDefinition(BaseModel):
    """Complete test definition: operations, modules, and suite configuration.

    Validators enforce referential integrity between operations and suite
    targets, and reject invalid configurations like dual param modes.
    """

    operations: list[Operation] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    suite: TestSuite
    hooks: LifecycleHooks = Field(default_factory=LifecycleHooks)

    @model_validator(mode="after")
    def validate_targets_exist(self) -> TestDefinition:
        """Ensure all suite targets reference defined operations."""
        op_names = {op.name for op in self.operations}
        for target in self.suite.targets:
            if target not in op_names:
                raise ValueError(
                    f"Target '{target}' not found in operations: {op_names}"
                )
        return self

    @model_validator(mode="after")
    def validate_fault_targets_exist(self) -> TestDefinition:
        """Ensure all fault_for references point to existing operations."""
        op_names = {op.name for op in self.operations}
        for op in self.operations:
            if op.fault_for and op.fault_for not in op_names:
                raise ValueError(
                    f"Fault operation '{op.name}' references target "
                    f"'{op.fault_for}' which is not defined"
                )
        return self

    @model_validator(mode="after")
    def validate_state_references(self) -> TestDefinition:
        """Ensure all required states are reachable from some provider."""
        all_provided: set[str] = set()
        all_cleared: set[str] = set()
        all_grafts: list[tuple[str, str]] = []
        for op in self.operations:
            all_provided.update(op.provides)
            all_cleared.update(op.clears)
            all_cleared.update(op.cuts)
            for g in op.grafts:
                all_provided.add(g.tgt)
                all_grafts.append((g.src, g.tgt))

        all_states = all_provided | all_cleared

        # Graft copies subtrees: if src.X is provided and graft(src, tgt)
        # exists, then tgt.X is also reachable
        for src, tgt in all_grafts:
            src_prefix = src + '.'
            for state in list(all_states):
                if state.startswith(src_prefix):
                    all_states.add(tgt + state[len(src):])

        for op in self.operations:
            if op.type == 'fault':
                continue
            for req in op.requires:
                if req.startswith('params.'):
                    continue
                if '{' in req or '*' in req:
                    continue
                if not _state_is_reachable(req, all_states):
                    raise ValueError(
                        f"Operation '{op.name}' requires state '{req}' "
                        f"which is never provided or cleared by any operation"
                    )
        return self

    @model_validator(mode="after")
    def validate_no_dual_param_modes(self) -> TestDefinition:
        """Ensure param_choices and param_matrix are not used simultaneously."""
        has_choices = bool(self.suite.param_choices)
        has_matrix = self.suite.param_matrix and bool(self.suite.param_matrix.axes)
        if has_choices and has_matrix:
            raise ValueError(
                "Cannot use both 'param_choices' and 'param_matrix' in the same suite"
            )
        return self

    @model_validator(mode="after")
    def validate_no_wildcards_in_writes(self) -> TestDefinition:
        """Ensure wildcards are not used in write paths (provides/clears/cuts/grafts)."""
        for op in self.operations:
            for path in op.provides + op.clears + op.cuts:
                if '*' in path:
                    raise ValueError(
                        f"Operation '{op.name}': wildcard '*' is not allowed "
                        f"in write paths (provides/clears/cuts): '{path}'"
                    )
            for g in op.grafts:
                if '*' in g.src or '*' in g.tgt:
                    raise ValueError(
                        f"Operation '{op.name}': wildcard '*' is not allowed "
                        f"in graft paths: src='{g.src}', tgt='{g.tgt}'"
                    )
        return self


class HookResult(BaseModel):
    """Result from a lifecycle hook execution."""

    hook_name: str
    hook_type: Literal["suite_setup", "suite_teardown", "case_setup", "case_teardown"]
    status: Literal["pass", "fail", "error"] = "pass"
    error: str | None = None
    duration_ms: float = 0.0


class ObserverResult(BaseModel):
    """Result from a transition observer or verify callback."""

    observer_name: str
    status: Literal["pass", "fail", "error"] = "pass"
    error: str | None = None
    duration_ms: float = 0.0


class StepResult(BaseModel):
    """Execution result for a single test step."""

    operation: str
    status: Literal["pass", "fail", "skip", "error"] = "pass"
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    modifier_type: str | None = None
    modifier_detail: str | None = None
    injected: bool = False
    verify_result: ObserverResult | None = None
    observer_results: list[ObserverResult] = Field(default_factory=list)


class AttemptResult(BaseModel):
    """Result of a single attempt at running a test case."""

    attempt: int
    steps: list[StepResult] = Field(default_factory=list)
    status: Literal["pass", "fail", "error"] = "pass"
    duration_ms: float = 0.0


class CaseResult(BaseModel):
    """Aggregate result for a single test case."""

    case_id: str
    steps: list[StepResult] = Field(default_factory=list)
    status: Literal["pass", "fail", "error"] = "pass"
    duration_ms: float = 0.0
    replanned: bool = False
    replan_reason: str | None = None
    is_fault: bool = False
    attempts: list[AttemptResult] = Field(default_factory=list)
    flaky: bool = False
    retry_count: int = 0
    hook_results: list[HookResult] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Summary statistics for a complete test run."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    failure_patterns: list[str] = Field(default_factory=list)
    slowest_steps: list[dict[str, Any]] = Field(default_factory=list)
    flaky: int = 0
    retried: int = 0
    suite_hook_results: list[HookResult] = Field(default_factory=list)


class FailureDetail(BaseModel):
    """Detailed information about a single test failure."""

    case_id: str
    failed_step: str
    step_index: int
    stderr: str = ""
    error: str | None = None
    required_states: list[str] = Field(default_factory=list)
    active_states: list[str] = Field(default_factory=list)


class DebugSuggestion(BaseModel):
    """Debugging suggestion generated from a failure detail."""

    failure: FailureDetail
    likely_cause: str = ""
    suggested_operations: list[str] = Field(default_factory=list)
    message: str = ""


class TestCase(BaseModel):
    """A generated test case with steps, target, and parameters."""

    case_id: str
    steps: list[str]
    target: str
    cleanup_steps: list[str] = Field(default_factory=list)
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    is_fault: bool = False
    priority: float = 0.0


def _load_definition_from_module(path: Path) -> TestDefinition:
    """Load a test definition from a single Python module file."""
    from .loader import extract_hooks, extract_operations, load_module
    module = load_module(path)
    op_pairs = extract_operations(module)
    operations = []
    for op, func in op_pairs:
        op.callable = func
        operations.append(op)
    targets = [op.name for op in operations if op.type == "check"]
    if not targets:
        targets = [operations[-1].name] if operations else []
    hook_map = extract_hooks(module)
    return TestDefinition(
        operations=operations,
        suite=TestSuite(
            name=path.stem,
            targets=targets,
        ),
        hooks=LifecycleHooks(**hook_map),
    )


def _state_is_reachable(required: str, all_states: set[str]) -> bool:
    """Check whether a required state is provided by any operation."""
    if required in all_states:
        return True
    # Hierarchical: requiring 'a.b' is satisfied if 'a.b.c' is provided
    prefix = required + '.'
    return any(s.startswith(prefix) for s in all_states)


def load_definition(path: str | Path) -> TestDefinition:
    """Load a test definition from a YAML file or Python module.

    Args:
        path: Path to a ``.yaml`` or ``.py`` definition file.

    Returns:
        Parsed and validated test definition.

    Raises:
        SchemaError: If the definition fails validation.
    """
    path = Path(path)
    logger.info("Loading definition from %s", path)

    if path.suffix == '.py':
        defn = _load_definition_from_module(path)
        logger.info("Definition loaded: %d operations, targets=%s", len(defn.operations), defn.suite.targets)
        return defn

    with open(path) as f:
        data = yaml.safe_load(f)

    module_paths = data.get('modules', [])
    if module_paths:
        logger.debug("Loading %d external module(s)", len(module_paths))
        from .loader import extract_hooks, load_module, load_operations_from_modules
        op_pairs = load_operations_from_modules(module_paths, base_dir=path.parent)
        module_ops = []
        for op, func in op_pairs:
            op.callable = func
            module_ops.append(op)
        existing = data.get('operations', [])
        data['operations'] = existing + [
            op.model_dump(exclude={'callable'}) for op in module_ops
        ]
        data.pop('modules', None)
        defn = TestDefinition.model_validate(data)
        op_by_name = {op.name: op for op in defn.operations}
        for op, func in op_pairs:
            if op.name in op_by_name:
                op_by_name[op.name].callable = func
        all_hooks: dict[str, list] = {
            'suite_setup': [], 'suite_teardown': [],
            'case_setup': [], 'case_teardown': [],
        }
        for mod_path in module_paths:
            p = Path(mod_path)
            if not p.is_absolute():
                p = path.parent / p
            module = load_module(p)
            hook_map = extract_hooks(module)
            for key in all_hooks:
                all_hooks[key].extend(hook_map[key])
        defn.hooks = LifecycleHooks(**all_hooks)
        logger.info("Definition loaded: %d operations, targets=%s", len(defn.operations), defn.suite.targets)
        return defn

    defn = TestDefinition.model_validate(data)
    logger.info("Definition loaded: %d operations, targets=%s", len(defn.operations), defn.suite.targets)
    return defn


def export_json_schema(model_type: str = "definition") -> dict[str, Any]:
    """Export a Pydantic model's JSON Schema.

    Args:
        model_type: One of ``"definition"``, ``"results"``, ``"summary"``,
            or ``"test_case"``.

    Returns:
        JSON Schema dict for the requested model.

    Raises:
        ValueError: If *model_type* is not recognized.
    """
    schemas = {
        "definition": TestDefinition,
        "results": CaseResult,
        "summary": RunSummary,
        "test_case": TestCase,
    }
    model = schemas.get(model_type)
    if model is None:
        raise ValueError(f"Unknown schema type '{model_type}'. Available: {list(schemas.keys())}")
    return model.model_json_schema()


def dump_json(obj: BaseModel) -> str:
    """Serialize a Pydantic model to a JSON string."""
    return obj.model_dump_json(indent=2)


def dump_dict(obj: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic model to a plain dict."""
    return obj.model_dump()
