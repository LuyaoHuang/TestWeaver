from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParamDef(BaseModel):
    name: str
    type: Literal["string", "integer", "float", "boolean", "list", "dict"] = "string"
    description: str = ""
    default: Any = None
    required: bool = True


class GraftDef(BaseModel):
    src: str
    tgt: str


class ParamChoice(BaseModel):
    name: str
    values: list[Any]
    description: str = ""


class ParamAxis(BaseModel):
    name: str
    values: list[Any]
    description: str = ""


class ParamConstraint(BaseModel):
    when: dict[str, Any]
    skip_ops: list[str] = Field(default_factory=list)
    exclude: bool = False
    reason: str = ""


class ParamMatrix(BaseModel):
    axes: list[ParamAxis] = Field(default_factory=list)
    constraints: list[ParamConstraint] = Field(default_factory=list)


class Operation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str = ""
    type: Literal["action", "check", "setup", "cleanup"] = "action"
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    clears: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    grafts: list[GraftDef] = Field(default_factory=list)
    cuts: list[str] = Field(default_factory=list)
    params: list[ParamDef] = Field(default_factory=list)
    skip_when: list[dict[str, Any]] = Field(default_factory=list)
    run: str = ""
    callable: Callable | None = Field(default=None, exclude=True)
    param_provider: str | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def check_cleanup_has_clears(self) -> Operation:
        if self.type == "cleanup" and not self.clears and not self.cuts:
            raise ValueError(
                f"Operation '{self.name}' is type 'cleanup' but has no 'clears' or 'cuts' entries"
            )
        return self


class TestSuite(BaseModel):
    name: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    param_choices: list[ParamChoice] = Field(default_factory=list)
    param_matrix: ParamMatrix | None = None
    targets: list[str]
    max_cases: int = 100
    cleanup: bool = True


class TestDefinition(BaseModel):
    operations: list[Operation] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    suite: TestSuite

    @model_validator(mode="after")
    def validate_targets_exist(self) -> TestDefinition:
        op_names = {op.name for op in self.operations}
        for target in self.suite.targets:
            if target not in op_names:
                raise ValueError(
                    f"Target '{target}' not found in operations: {op_names}"
                )
        return self

    @model_validator(mode="after")
    def validate_state_references(self) -> TestDefinition:
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
            for req in op.requires:
                if req.startswith('params.'):
                    continue
                if not _state_is_reachable(req, all_states):
                    raise ValueError(
                        f"Operation '{op.name}' requires state '{req}' "
                        f"which is never provided or cleared by any operation"
                    )
        return self

    @model_validator(mode="after")
    def validate_no_dual_param_modes(self) -> TestDefinition:
        has_choices = bool(self.suite.param_choices)
        has_matrix = self.suite.param_matrix and bool(self.suite.param_matrix.axes)
        if has_choices and has_matrix:
            raise ValueError(
                "Cannot use both 'param_choices' and 'param_matrix' in the same suite"
            )
        return self


class ObserverResult(BaseModel):
    observer_name: str
    status: Literal["pass", "fail", "error"] = "pass"
    error: str | None = None
    duration_ms: float = 0.0


class StepResult(BaseModel):
    operation: str
    status: Literal["pass", "fail", "skip", "error"] = "pass"
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    modifier_type: str | None = None
    modifier_detail: str | None = None
    injected: bool = False
    observer_results: list[ObserverResult] = Field(default_factory=list)


class CaseResult(BaseModel):
    case_id: str
    steps: list[StepResult] = Field(default_factory=list)
    status: Literal["pass", "fail", "error"] = "pass"
    duration_ms: float = 0.0
    replanned: bool = False
    replan_reason: str | None = None


class RunSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_ms: float = 0.0
    failure_patterns: list[str] = Field(default_factory=list)
    slowest_steps: list[dict[str, Any]] = Field(default_factory=list)


class FailureDetail(BaseModel):
    case_id: str
    failed_step: str
    step_index: int
    stderr: str = ""
    error: str | None = None
    required_states: list[str] = Field(default_factory=list)
    active_states: list[str] = Field(default_factory=list)


class DebugSuggestion(BaseModel):
    failure: FailureDetail
    likely_cause: str = ""
    suggested_operations: list[str] = Field(default_factory=list)
    message: str = ""


class TestCase(BaseModel):
    case_id: str
    steps: list[str]
    target: str
    cleanup_steps: list[str] = Field(default_factory=list)
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


def _load_definition_from_module(path: Path) -> TestDefinition:
    from .loader import load_module, extract_operations
    module = load_module(path)
    op_pairs = extract_operations(module)
    operations = []
    for op, func in op_pairs:
        op.callable = func
        operations.append(op)
    targets = [op.name for op in operations if op.type == "check"]
    if not targets:
        targets = [operations[-1].name] if operations else []
    return TestDefinition(
        operations=operations,
        suite=TestSuite(
            name=path.stem,
            targets=targets,
        ),
    )


def _state_is_reachable(required: str, all_states: set[str]) -> bool:
    if required in all_states:
        return True
    # Hierarchical: requiring 'a.b' is satisfied if 'a.b.c' is provided
    prefix = required + '.'
    return any(s.startswith(prefix) for s in all_states)


def load_definition(path: str | Path) -> TestDefinition:
    path = Path(path)

    if path.suffix == '.py':
        return _load_definition_from_module(path)

    with open(path) as f:
        data = yaml.safe_load(f)

    module_paths = data.get('modules', [])
    if module_paths:
        from .loader import load_operations_from_modules
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
        return defn

    return TestDefinition.model_validate(data)


def export_json_schema(model_type: str = "definition") -> dict:
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
    return obj.model_dump_json(indent=2)


def dump_dict(obj: BaseModel) -> dict:
    return obj.model_dump()
