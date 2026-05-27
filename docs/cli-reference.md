# CLI Reference

## Commands

```bash
testweaver <command> [options]
```

| Command | Description |
|---------|-------------|
| `validate` | Validate a test definition file |
| `generate` | Generate test cases from a definition |
| `run` | Run test cases |
| `graph` | Show or export the dependency graph |
| `matrix` | Preview parameter combinations |
| `analyze` | Analyze test results |
| `schema` | Export JSON Schema for definitions or results |

## validate

Check a definition file for errors.

```bash
testweaver validate <file> [-v] [--debug] [--trace]
```

## generate

Generate test cases without running them.

```bash
testweaver generate <file> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format json\|text` | | Output format (default: json) |
| `-p key=value` | | Override or add parameters |
| `-k pattern` | | Filter cases by ID (fnmatch glob, repeatable) |
| `-t operation` | `--target` | Filter by target operation (repeatable) |
| `--has-step op` | | Filter by step presence (repeatable) |
| `--fault-only` | | Only fault-injection cases |
| `--no-fault` | | Exclude fault-injection cases |
| `-s strategy` | `--sort` | Sort cases: `shortest`, `longest`, `target`, `total`, `fault-first`, `fault-last`, `random` |
| `--sort-seed N` | | Seed for reproducible random sort |
| `--generation-strategy` | `-g` | Generation strategy: `exhaustive`, `pairwise`, `representative` |
| `--max-graph-nodes N` | | Max graph nodes (default: 500) |
| `--max-path-depth N` | | Max steps per case (default: 20) |
| `--max-state-depth N` | | Max active states per node (default: 0 = no limit) |
| `-v` | `--verbose` | INFO-level logging |
| `--debug` | | DEBUG-level logging |
| `--trace` | | TRACE-level logging (very verbose) |

## run

Run test cases and output results.

```bash
testweaver run <file> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format json\|text\|junit\|tap\|html` | | Output format (default: json) |
| `-o file` | `--output` | Write output to file |
| `--timeout N` | | Global timeout per step in seconds (default: 300) |
| `-w N` | `--workers` | Parallel workers (default: 1, 0 = auto) |
| `-p key=value` | | Override or add parameters |
| `-k pattern` | | Filter cases by ID (repeatable) |
| `-t operation` | `--target` | Filter by target operation (repeatable) |
| `--has-step op` | | Filter by step presence (repeatable) |
| `--fault-only` | | Only fault-injection cases |
| `--no-fault` | | Exclude fault-injection cases |
| `-s strategy` | `--sort` | Sort strategy |
| `--sort-seed N` | | Seed for reproducible random sort |
| `--dry-run` | | Preview cases without executing |
| `--retries N` | | Max retries for failed cases (default: 0) |
| `--retry-delay S` | | Seconds between retries (default: 0) |
| `--progress` | | Force progress bar on |
| `--no-progress` | | Force progress bar off |
| `--generation-strategy` | `-g` | Generation strategy |
| `--max-graph-nodes N` | | Max graph nodes |
| `--max-path-depth N` | | Max steps per case |
| `--max-state-depth N` | | Max active states per node |
| `-v` | `--verbose` | INFO-level logging |
| `--debug` | | DEBUG-level logging |
| `--trace` | | TRACE-level logging (very verbose) |
| `--log-file path` | | Write logs to a file |

## graph

Show or export the dependency graph.

```bash
testweaver graph <file> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format json\|text\|dot\|mermaid` | | Output format (default: json) |
| `-o file` | `--output` | Write output to file |
| `-v` | `--verbose` | INFO-level logging |
| `--debug` | | DEBUG-level logging |
| `--trace` | | TRACE-level logging (very verbose) |

```bash
# Render graph as PNG
testweaver graph my_test.yaml --format dot | dot -Tpng -o graph.png

# Mermaid for GitHub markdown
testweaver graph my_test.yaml --format mermaid
```

## matrix

Preview parameter matrix combinations.

```bash
testweaver matrix <file> [--format json|text]
```

## analyze

Analyze test results from a previous run.

```bash
testweaver analyze <results.json> [-d <definition-file>]
```

## schema

Export JSON Schema for validation or code generation.

```bash
testweaver schema [--type definition|results|summary|test_case]
```

## Filtering

All filter options are available on both `generate` and `run`. Filters are AND-combined; within each repeatable option, matching is OR.

```bash
testweaver run my_test.yaml -k "check-*"                    # ID pattern
testweaver run my_test.yaml -t verify_tpm                   # Target operation
testweaver run my_test.yaml --has-step install_swtpm         # Step presence
testweaver run my_test.yaml --fault-only                     # Fault cases only
testweaver run my_test.yaml -k "check-*" --no-fault          # Combine filters
```

See [examples/filtering.md](examples/filtering.md) for details.

## Sorting

```bash
testweaver run my_test.yaml --sort shortest                  # Fewest steps first
testweaver run my_test.yaml --sort target                    # By operation priority
testweaver run my_test.yaml --sort random --sort-seed 42     # Reproducible random
```

See [examples/prioritization.md](examples/prioritization.md) for details.

## Logging

```bash
testweaver run my_test.yaml -v                               # INFO level
testweaver run my_test.yaml --debug                          # DEBUG level
testweaver run my_test.yaml --trace                          # TRACE level (state transitions)
testweaver run my_test.yaml -v --log-file run.log            # Log to file
TESTWEAVER_LOG=DEBUG testweaver run my_test.yaml             # Enable via env var
```

See [examples/logging.md](examples/logging.md) for details.
