"""Load operations from Python modules with decorator-based definitions."""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Any, Callable

from .schema import GraftDef, Operation


def load_module(path: str | Path) -> Any:
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_operations(module: Any) -> list[tuple[Operation, Callable | None]]:
    results = []
    for name, obj in inspect.getmembers(module, inspect.isfunction):
        meta = getattr(obj, '_tw_meta', None)
        if meta is None:
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
        )
        results.append((op, obj))
    return results


def load_operations_from_modules(
    module_paths: list[str],
    base_dir: Path | None = None,
) -> list[tuple[Operation, Callable | None]]:
    all_ops = []
    for mod_path in module_paths:
        p = Path(mod_path)
        if not p.is_absolute() and base_dir:
            p = base_dir / p
        module = load_module(p)
        all_ops.extend(extract_operations(module))
    return all_ops
