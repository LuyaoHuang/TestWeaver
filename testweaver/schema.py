from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ParamDef(BaseModel):
    name: str
    type: Literal["string", "integer", "float", "boolean", "list", "dict"] = "string"
    description: str = ""
    default: Any = None
    required: bool = True


class Operation(BaseModel):
    name: str
    description: str = ""
    type: Literal["action", "check", "setup", "cleanup"] = "action"
    provides: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    clears: list[str] = Field(default_factory=list)
    params: list[ParamDef] = Field(default_factory=list)
    run: str = ""

    @model_validator(mode="after")
    def check_cleanup_has_clears(self) -> Operation:
        if self.type == "cleanup" and not self.clears:
            raise ValueError(
                f"Operation '{self.name}' is type 'cleanup' but has no 'clears' entries"
            )
        return self


class TestSuite(BaseModel):
    name: str
    description: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    targets: list[str]
    max_cases: int = 100
    cleanup: bool = True


class TestDefinition(BaseModel):
    operations: list[Operation]
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
        all_provided = set()
        all_cleared = set()
        for op in self.operations:
            all_provided.update(op.provides)
            all_cleared.update(op.clears)

        all_states = all_provided | all_cleared

        for op in self.operations:
            for req in op.requires:
                if req not in all_states:
                    raise ValueError(
                        f"Operation '{op.name}' requires state '{req}' "
                        f"which is never provided or cleared by any operation"
                    )
        return self


class StepResult(BaseModel):
    operation: str
    status: Literal["pass", "fail", "skip", "error"] = "pass"
    duration_ms: float = 0.0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class CaseResult(BaseModel):
    case_id: str
    steps: list[StepResult] = Field(default_factory=list)
    status: Literal["pass", "fail", "error"] = "pass"
    duration_ms: float = 0.0


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


def load_definition(path: str | Path) -> TestDefinition:
    path = Path(path)
    with open(path) as f:
        data = yaml.safe_load(f)
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
