"""Load operations from Python modules with decorator-based definitions."""
from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable

from .schema import GraftDef, Operation

logger = logging.getLogger(__name__)


def load_module(path: str | Path) -> Any:
    """Load a Python module from a file path.

    Args:
        path: Filesystem path to a ``.py`` file.

    Returns:
        The loaded module object.

    Raises:
        ImportError: If the module cannot be loaded.
    """
    path = Path(path).resolve()
    logger.debug("Loading module from %s", path)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    logger.info("Loaded module: %s", path.name)
    return module


def extract_operations(module: Any) -> list[tuple[Operation, Callable | None]]:
    """Extract Operation definitions from a loaded module.

    Scans all functions in *module* for ``_tw_meta`` attributes set by
    TestWeaver decorators and converts them into Operation models.

    Args:
        module: A loaded Python module.

    Returns:
        List of ``(Operation, callable)`` pairs.
    """
    results = []
    verify_funcs: dict[str, Callable] = {}
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        meta = getattr(obj, '_tw_meta', None)
        if meta is None:
            continue
        verify_target = meta.get('verify_for')
        if verify_target is not None:
            verify_funcs[verify_target] = obj
            continue
        if meta.get('hook'):
            continue
        grafts_raw = meta.get('grafts', [])
        grafts = [GraftDef(**g) for g in grafts_raw]
        op = Operation(
            name=name,
            description=(obj.__doc__ or "").strip(),
            type=meta.get('type', 'action'),
            provides=meta.get('provides', []),
            requires=meta.get('requires', []),
            clears=meta.get('clears', []),
            excludes=meta.get('excludes', []),
            grafts=grafts,
            cuts=meta.get('cuts', []),
            skip_when=meta.get('skip_when', []),
            fault_for=meta.get('fault_for'),
            terminal=meta.get('terminal', True),
            timeout=meta.get('timeout'),
            priority=meta.get('priority', 0),
        )
        logger.debug("Extracted operation: %s (type=%s)", name, op.type)
        results.append((op, obj))
    for op, _ in results:
        if op.name in verify_funcs:
            op.verify_callable = verify_funcs[op.name]
    logger.info("Extracted %d operation(s) from module", len(results))
    return results


def extract_hooks(module: Any) -> dict[str, list[Callable]]:
    """Extract lifecycle hook functions from a loaded module.

    Scans all functions in *module* for ``_tw_meta`` attributes with
    a ``'hook'`` key set by lifecycle hook decorators.

    Args:
        module: A loaded Python module.

    Returns:
        Dict mapping hook type names to lists of callables.
    """
    hooks: dict[str, list[Callable]] = {
        'suite_setup': [],
        'suite_teardown': [],
        'case_setup': [],
        'case_teardown': [],
    }
    for _name, obj in inspect.getmembers(module, inspect.isfunction):
        meta = getattr(obj, '_tw_meta', None)
        if meta is None:
            continue
        hook_type = meta.get('hook')
        if hook_type and hook_type in hooks:
            hooks[hook_type].append(obj)
    return hooks


def load_operations_from_modules(
    module_paths: list[str],
    base_dir: Path | None = None,
) -> list[tuple[Operation, Callable | None]]:
    """Load and extract operations from multiple module files.

    Args:
        module_paths: List of paths to Python modules.
        base_dir: Base directory for resolving relative paths.

    Returns:
        Combined list of ``(Operation, callable)`` pairs from all modules.
    """
    all_ops = []
    for mod_path in module_paths:
        p = Path(mod_path)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        module = load_module(p)
        all_ops.extend(extract_operations(module))
    return all_ops
