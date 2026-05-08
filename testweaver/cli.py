from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import __version__
from .analyzer import find_failures, suggest_debug, summarize_run
from .engine import run_all
from .graph import build_graph, explain_graph, generate_cases
from .schema import CaseResult, TestDefinition, export_json_schema, load_definition


@click.group()
@click.version_option(version=__version__)
def main():
    """TestWeaver: AI-native test case generation framework."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
def validate(path: str):
    """Validate a test definition file."""
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
def generate(path: str, fmt: str):
    """Generate test cases from a definition file."""
    definition = load_definition(path)
    graph = build_graph(definition.operations)
    cases = generate_cases(definition, graph)

    if fmt == "json":
        output = [json.loads(c.model_dump_json()) for c in cases]
        click.echo(json.dumps(output, indent=2))
    else:
        for case in cases:
            click.echo(f"\n--- {case.case_id} ---")
            click.echo(f"Target: {case.target}")
            click.echo(f"Steps: {' -> '.join(case.steps)}")
            if case.cleanup_steps:
                click.echo(f"Cleanup: {' -> '.join(case.cleanup_steps)}")
            click.echo(f"Description: {case.description}")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Save results to file")
@click.option("--timeout", default=300, help="Per-step timeout in seconds")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
def run(path: str, output: str | None, timeout: int, fmt: str):
    """Run test cases from a definition file."""
    definition = load_definition(path)
    graph = build_graph(definition.operations)
    cases = generate_cases(definition, graph)

    click.echo(f"Running {len(cases)} test case(s)...", err=True)
    results = run_all(cases, definition, timeout)
    summary = summarize_run(results)

    if fmt == "json":
        data = {
            "summary": json.loads(summary.model_dump_json()),
            "results": [json.loads(r.model_dump_json()) for r in results],
        }
        result_json = json.dumps(data, indent=2)
        click.echo(result_json)
        if output:
            Path(output).write_text(result_json)
            click.echo(f"Results saved to {output}", err=True)
    else:
        click.echo(f"\nTotal: {summary.total}  Passed: {summary.passed}  "
                    f"Failed: {summary.failed}  Errors: {summary.errors}")
        click.echo(f"Duration: {summary.duration_ms:.0f}ms")
        for r in results:
            status_icon = "PASS" if r.status == "pass" else "FAIL"
            click.echo(f"  [{status_icon}] {r.case_id} ({r.duration_ms:.0f}ms)")


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--definition", "-d", type=click.Path(exists=True),
              help="Original definition file for debug suggestions")
def analyze(path: str, definition: str | None):
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
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
def show_graph(path: str, fmt: str):
    """Show the dependency graph for a definition file."""
    definition = load_definition(path)
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


@main.command("schema")
@click.option("--type", "schema_type",
              type=click.Choice(["definition", "results", "summary", "test_case"]),
              default="definition")
def show_schema(schema_type: str):
    """Export JSON Schema for AI agents."""
    schema = export_json_schema(schema_type)
    click.echo(json.dumps(schema, indent=2))


if __name__ == "__main__":
    main()
