from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from . import __version__
from .analyzer import find_failures, suggest_debug, summarize_run
from .engine import _substitute_params, run_all
from .filtering import filter_cases
from .graph import build_graph, explain_graph, export_graph, generate_cases
from .reporters import to_html, to_junit_xml, to_tap
from .schema import (
    CaseResult,
    Operation,
    TestCase,
    TestDefinition,
    export_json_schema,
    load_definition,
)


def _configure_logging(
    verbose: bool = False,
    debug: bool = False,
    log_file: str | None = None,
    workers: int = 1,
) -> None:
    """Set up logging for the testweaver package."""
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    tw_logger = logging.getLogger("testweaver")
    tw_logger.setLevel(level)

    if tw_logger.handlers:
        return

    if workers > 1:
        fmt = "%(asctime)s %(levelname)-5s [%(name)s] [%(threadName)s] %(message)s"
    else:
        fmt = "%(asctime)s %(levelname)-5s [%(name)s] %(message)s"
    formatter = logging.Formatter(fmt)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    tw_logger.addHandler(stderr_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        tw_logger.addHandler(file_handler)


def _parse_param_overrides(params: tuple[str, ...]) -> dict[str, str]:
    """Parse ``key=value`` parameter strings into a dict."""
    result: dict[str, str] = {}
    for p in params:
        if '=' not in p:
            raise click.BadParameter(f"Invalid param format '{p}', expected key=value")
        key, val = p.split('=', 1)
        result[key.strip()] = val.strip()
    return result


def _format_step_line(
    index: int,
    op_name: str,
    operation: Operation | None,
    params: dict[str, Any],
) -> str:
    """Format a single step line for dry-run output."""
    prefix = f"  {index}. {op_name}"
    if operation is None:
        return f"{prefix:<40s} [unknown operation]"
    if operation.callable is not None:
        qual = getattr(operation.callable, "__qualname__",
                       getattr(operation.callable, "__name__", "callable"))
        return f"{prefix:<40s} [callable: {qual}]"
    if operation.run:
        resolved = _substitute_params(operation.run, params)
        if resolved != operation.run:
            return f"{prefix:<40s} run: {operation.run}  ->  {resolved}"
        return f"{prefix:<40s} run: {operation.run}"
    return f"{prefix:<40s} [no-op]"


def _print_dry_run(
    cases: list[TestCase],
    definition: TestDefinition,
    output_path: str | None,
) -> None:
    """Print a preview of test cases without executing them."""
    ops_by_name = {op.name: op for op in definition.operations}
    lines: list[str] = []
    lines.append(f"Dry-run: {len(cases)} test case(s) would be executed")

    for case in cases:
        fault_tag = " [FAULT]" if case.is_fault else ""
        lines.append(f"\n--- {case.case_id}{fault_tag} ---")
        lines.append(f"Target: {case.target}")
        params = case.params if case.params else dict(definition.suite.params)
        if params:
            lines.append(f"Params: {params}")
        lines.append("Steps:")
        for i, step_name in enumerate(case.steps, 1):
            op = ops_by_name.get(step_name)
            lines.append(_format_step_line(i, step_name, op, params))
        if case.cleanup_steps:
            lines.append("Cleanup:")
            for i, step_name in enumerate(case.cleanup_steps, 1):
                op = ops_by_name.get(step_name)
                lines.append(_format_step_line(i, step_name, op, params))

    rendered = "\n".join(lines)
    click.echo(rendered)
    if output_path:
        Path(output_path).write_text(rendered)
        click.echo(f"Dry-run preview saved to {output_path}", err=True)


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """TestWeaver: AI-native test case generation framework."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show INFO-level logs")
@click.option("--debug", is_flag=True, default=False, help="Show DEBUG-level logs")
def validate(path: str, verbose: bool, debug: bool) -> None:
    """Validate a test definition file."""
    _configure_logging(verbose=verbose, debug=debug)
    try:
        definition = load_definition(path)
        click.echo(json.dumps({
            "valid": True,
            "operations": len(definition.operations),
            "targets": definition.suite.targets,
        }, indent=2))
    except Exception as e:
        click.echo(json.dumps({
            "valid": False,
            "error": str(e),
        }, indent=2), err=True)
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.option("--param", "-p", multiple=True, help="Override parameter: key=value")
@click.option("--filter", "-k", "filters", multiple=True,
              help="Filter cases by ID pattern (fnmatch glob, repeatable)")
@click.option("--target", "-t", "filter_targets", multiple=True,
              help="Keep only cases targeting these operations (repeatable)")
@click.option("--has-step", "filter_steps", multiple=True,
              help="Keep cases containing this step (repeatable)")
@click.option("--fault-only", is_flag=True, default=False,
              help="Keep only fault-injection cases")
@click.option("--no-fault", is_flag=True, default=False,
              help="Exclude fault-injection cases")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show INFO-level logs")
@click.option("--debug", is_flag=True, default=False, help="Show DEBUG-level logs")
def generate(path: str, fmt: str, param: tuple[str, ...],
             filters: tuple[str, ...], filter_targets: tuple[str, ...],
             filter_steps: tuple[str, ...], fault_only: bool,
             no_fault: bool, verbose: bool, debug: bool) -> None:
    """Generate test cases from a definition file."""
    _configure_logging(verbose=verbose, debug=debug)
    definition = load_definition(path)
    if param:
        overrides = _parse_param_overrides(param)
        definition.suite.params.update(overrides)

    cases = generate_cases(definition)
    cases = filter_cases(
        cases,
        ids=list(filters) or None,
        targets=list(filter_targets) or None,
        steps=list(filter_steps) or None,
        fault_only=fault_only,
        no_fault=no_fault,
    )

    if fmt == "json":
        output = [json.loads(c.model_dump_json()) for c in cases]
        click.echo(json.dumps(output, indent=2))
    else:
        for case in cases:
            fault_tag = " [FAULT]" if case.is_fault else ""
            click.echo(f"\n--- {case.case_id}{fault_tag} ---")
            click.echo(f"Target: {case.target}")
            if case.params:
                click.echo(f"Params: {case.params}")
            click.echo(f"Steps: {' -> '.join(case.steps)}")
            if case.cleanup_steps:
                click.echo(f"Cleanup: {' -> '.join(case.cleanup_steps)}")
            click.echo(f"Description: {case.description}")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.option("--timeout", default=300, help="Per-step timeout in seconds")
@click.option("--format", "fmt",
              type=click.Choice(["json", "text", "junit", "tap", "html"]), default="json")
@click.option("--param", "-p", multiple=True, help="Override parameter: key=value")
@click.option("--workers", "-w", default=1, help="Parallel workers (0=auto, 1=sequential)")
@click.option("--retries", default=0, help="Number of retries for failed cases (default: 0)")
@click.option("--retry-delay", default=0.0, type=float,
              help="Seconds to wait between retry attempts (default: 0)")
@click.option("--filter", "-k", "filters", multiple=True,
              help="Filter cases by ID pattern (fnmatch glob, repeatable)")
@click.option("--target", "-t", "filter_targets", multiple=True,
              help="Keep only cases targeting these operations (repeatable)")
@click.option("--has-step", "filter_steps", multiple=True,
              help="Keep cases containing this step (repeatable)")
@click.option("--fault-only", is_flag=True, default=False,
              help="Keep only fault-injection cases")
@click.option("--no-fault", is_flag=True, default=False,
              help="Exclude fault-injection cases")
@click.option("--verbose", "-v", is_flag=True, default=False,
              help="Show INFO-level execution logs on stderr")
@click.option("--debug", is_flag=True, default=False,
              help="Show DEBUG-level execution logs on stderr")
@click.option("--log-file", type=click.Path(), default=None,
              help="Also write logs to this file")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview test cases without executing them")
def run(path: str, output: str | None, timeout: int, fmt: str, param: tuple[str, ...],
        workers: int, retries: int, retry_delay: float,
        filters: tuple[str, ...], filter_targets: tuple[str, ...],
        filter_steps: tuple[str, ...], fault_only: bool, no_fault: bool,
        verbose: bool, debug: bool, log_file: str | None, dry_run: bool) -> None:
    """Run test cases from a definition file."""
    _configure_logging(verbose=verbose, debug=debug, log_file=log_file, workers=workers)
    definition = load_definition(path)
    if param:
        overrides = _parse_param_overrides(param)
        definition.suite.params.update(overrides)

    from .graph import build_graph
    param_choices = definition.suite.param_choices or None
    graph = build_graph(definition.operations, param_choices=param_choices)
    cases = generate_cases(definition, graph)
    cases = filter_cases(
        cases,
        ids=list(filters) or None,
        targets=list(filter_targets) or None,
        steps=list(filter_steps) or None,
        fault_only=fault_only,
        no_fault=no_fault,
    )

    if dry_run:
        _print_dry_run(cases, definition, output)
        return

    worker_info = f" with {workers} worker(s)" if workers != 1 else ""
    retry_info = f", {retries} retries" if retries > 0 else ""
    click.echo(f"Running {len(cases)} test case(s){worker_info}{retry_info}...", err=True)
    results, suite_hooks = run_all(cases, definition, timeout, graph=graph,
                                   workers=workers, retries=retries,
                                   retry_delay=retry_delay)
    summary = summarize_run(results, suite_hook_results=suite_hooks)

    if fmt == "json":
        data = {
            "summary": json.loads(summary.model_dump_json()),
            "results": [json.loads(r.model_dump_json()) for r in results],
        }
        rendered = json.dumps(data, indent=2)
    elif fmt == "junit":
        rendered = to_junit_xml(results, summary,
                                suite_name=definition.suite.name)
    elif fmt == "tap":
        rendered = to_tap(results, summary)
    elif fmt == "html":
        rendered = to_html(results, summary)
    else:
        click.echo(f"\nTotal: {summary.total}  Passed: {summary.passed}  "
                    f"Failed: {summary.failed}  Errors: {summary.errors}")
        fault_count = sum(1 for r in results if r.is_fault)
        if fault_count:
            click.echo(f"Fault cases: {fault_count}")
        if summary.retried:
            click.echo(f"Retried: {summary.retried}")
        if summary.flaky:
            click.echo(f"Flaky: {summary.flaky}")
        click.echo(f"Duration: {summary.duration_ms:.0f}ms")
        for r in results:
            status_icon = "PASS" if r.status == "pass" else "FAIL"
            fault_tag = " [FAULT]" if r.is_fault else ""
            flaky_tag = " [FLAKY]" if r.flaky else ""
            retry_tag = f" (retried {r.retry_count}x)" if r.retry_count > 0 else ""
            click.echo(f"  [{status_icon}] {r.case_id}{fault_tag}{flaky_tag}{retry_tag} ({r.duration_ms:.0f}ms)")
        rendered = None

    if rendered is not None:
        click.echo(rendered)
        if output:
            Path(output).write_text(rendered)
            click.echo(f"Results saved to {output}", err=True)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--definition", "-d", type=click.Path(exists=True),
              help="Original definition file for debug suggestions")
def analyze(path: str, definition: str | None) -> None:
    """Analyze test results from a JSON file."""
    data = json.loads(Path(path).read_text())

    if "results" in data:
        results_data = data["results"]
    else:
        results_data = data if isinstance(data, list) else [data]

    results = [CaseResult.model_validate(r) for r in results_data]
    summary = summarize_run(results)

    output: dict = {"summary": json.loads(summary.model_dump_json())}

    if definition:
        defn = load_definition(definition)
        failures = find_failures(results, defn.operations)
        suggestions = [suggest_debug(f, defn.operations) for f in failures]
        output["failures"] = [json.loads(f.model_dump_json()) for f in failures]
        output["debug_suggestions"] = [json.loads(s.model_dump_json()) for s in suggestions]
    else:
        failures = find_failures(results)
        output["failures"] = [json.loads(f.model_dump_json()) for f in failures]

    click.echo(json.dumps(output, indent=2))


@main.command("graph")
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "fmt",
              type=click.Choice(["json", "text", "dot", "mermaid"]), default="json")
@click.option("--output", "-o", type=click.Path(), help="Save output to file")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Show INFO-level logs")
@click.option("--debug", is_flag=True, default=False, help="Show DEBUG-level logs")
def show_graph(path: str, fmt: str, output: str | None, verbose: bool, debug: bool) -> None:
    """Show the dependency graph for a definition file."""
    _configure_logging(verbose=verbose, debug=debug)
    definition = load_definition(path)

    if fmt in ("dot", "mermaid"):
        result = export_graph(definition, fmt)
        click.echo(result)
        if output:
            Path(output).write_text(result)
            click.echo(f"Graph saved to {output}", err=True)
        return

    info = explain_graph(definition)

    if fmt == "json":
        click.echo(json.dumps(info, indent=2))
    else:
        click.echo(f"Nodes: {info['node_count']}  Edges: {info['edge_count']}")
        click.echo(f"Reachable states: {', '.join(info['reachable_states'])}")
        click.echo("\nOperations:")
        for op in info["operations"]:
            click.echo(f"  {op['name']} ({op['type']}): "
                        f"requires={op['requires']} provides={op['provides']} "
                        f"clears={op['clears']}")
        click.echo("\nTarget reachability:")
        for name, reach in info["target_reachability"].items():
            status = "reachable" if reach["reachable"] else "UNREACHABLE"
            click.echo(f"  {name}: {status} (from {reach['reachable_from_n_states']} state(s))")

        if "fault_operations" in info:
            click.echo("\nFault operations:")
            for f in info["fault_operations"]:
                status = f"triggerable from {f['triggerable_from_n_states']} state(s)"
                click.echo(f"  {f['name']} (fault for {f['fault_for']}): {status}")
                if f['extra_requires']:
                    click.echo(f"    extra requires: {f['extra_requires']}")
                if f['extra_excludes']:
                    click.echo(f"    extra excludes: {f['extra_excludes']}")
        if "param_choices" in info:
            click.echo("\nParameter choices:")
            for pc in info["param_choices"]:
                click.echo(f"  {pc['name']}: {pc['values']}")
        if "param_matrix" in info:
            pm = info["param_matrix"]
            click.echo(f"\nParameter matrix: {pm['total_combinations']} combinations")
            for a in pm["axes"]:
                click.echo(f"  {a['name']}: {a['values']}")


@main.command("matrix")
@click.argument("path", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
def show_matrix(path: str, fmt: str) -> None:
    """Show parameter combinations for a definition."""
    definition = load_definition(path)

    if definition.suite.param_choices:
        from itertools import product as cartesian_product
        axes = definition.suite.param_choices
        names = [pc.name for pc in axes]
        value_lists = [pc.values for pc in axes]
        combos = [dict(zip(names, vals)) for vals in cartesian_product(*value_lists)]
    elif definition.suite.param_matrix and definition.suite.param_matrix.axes:
        from .matrix import expand_matrix
        combos = expand_matrix(definition.suite.param_matrix)
    else:
        click.echo("No parameter choices or matrix defined.", err=True)
        sys.exit(1)

    if fmt == "json":
        click.echo(json.dumps(combos, indent=2))
    else:
        click.echo(f"Total combinations: {len(combos)}\n")
        for i, combo in enumerate(combos, 1):
            parts = ", ".join(f"{k}={v}" for k, v in sorted(combo.items()))
            click.echo(f"  {i}. {parts}")


@main.command("schema")
@click.option("--type", "schema_type",
              type=click.Choice(["definition", "results", "summary", "test_case"]),
              default="definition")
def show_schema(schema_type: str) -> None:
    """Export JSON Schema for AI agents."""
    schema = export_json_schema(schema_type)
    click.echo(json.dumps(schema, indent=2))


if __name__ == "__main__":
    main()
