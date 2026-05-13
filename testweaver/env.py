"""Hierarchical state environment for dependency graph nodes.

Ported from depend-test-framework's Env class, simplified for TestWeaver.
States are dot-separated paths (e.g., 'vm.config.tpm') stored in a tree.
A node is "active" if its data is True or any of its children are active.
"""
from __future__ import annotations

import copy
from fnmatch import fnmatch


class Env:
    """Hierarchical state tree representing the test environment.

    Each node holds a boolean ``data`` flag and a dict of named children.
    States are addressed by dot-separated paths (e.g. ``'vm.config.tpm'``).

    Attributes:
        data: Whether this node is explicitly active.
        children: Named child nodes forming the state subtree.
    """

    __slots__ = ('data', 'children')

    def __init__(self, data: bool = False, children: dict[str, Env] | None = None):
        """Initialize an environment node."""
        self.data = data
        self.children = children if children is not None else {}

    def _get_node(self, path: str, create: bool = False) -> Env | None:
        """Traverse to the node at a dot-separated path, optionally creating intermediates."""
        parts = path.split('.')
        node = self
        for part in parts:
            child = node.children.get(part)
            if child is None:
                if not create:
                    return None
                child = Env()
                node.children[part] = child
            node = child
        return node

    def set(self, path: str) -> None:
        """Activate the state at the given dot-separated path.

        Args:
            path: Dot-separated state path (e.g. ``'vm.config.tpm'``).
        """
        node = self._get_node(path, create=True)
        node.data = True

    def unset(self, path: str) -> None:
        """Deactivate the leaf node at the given path without removing children.

        Args:
            path: Dot-separated state path.
        """
        node = self._get_node(path)
        if node is not None:
            node.data = False

    def is_active(self, path: str) -> bool:
        """Check whether a state path is active, supporting glob wildcards.

        Args:
            path: Dot-separated state path, may contain ``*`` wildcards.

        Returns:
            True if the node (or any matching glob node) is active.
        """
        if '*' in path:
            return self._is_active_glob(path.split('.'), 0)
        node = self._get_node(path)
        if node is None:
            return False
        return node._has_active()

    def _is_active_glob(self, parts: list[str], idx: int) -> bool:
        """Recursively match glob segments against the tree."""
        if idx >= len(parts):
            return self._has_active()
        segment = parts[idx]
        if '*' in segment:
            return any(
                child._is_active_glob(parts, idx + 1)
                for key, child in self.children.items()
                if fnmatch(key, segment)
            )
        child = self.children.get(segment)
        if child is None:
            return False
        return child._is_active_glob(parts, idx + 1)

    def _has_active(self) -> bool:
        """Return True if this node or any descendant is active."""
        if self.data:
            return True
        return any(child._has_active() for child in self.children.values())

    def clear(self, path: str) -> None:
        """Remove the entire subtree at the given path.

        Args:
            path: Dot-separated state path to clear.
        """
        node = self._get_node(path)
        if node is not None:
            node.data = False
            node.children = {}

    def graft(self, src: str, tgt: str) -> None:
        """Deep-copy the subtree at *src* onto *tgt*.

        Args:
            src: Source path to copy from.
            tgt: Target path to copy into (created if missing).
        """
        src_node = self._get_node(src)
        if src_node is None:
            return
        src_copy = copy.deepcopy(src_node)
        tgt_node = self._get_node(tgt, create=True)
        tgt_node.data = src_copy.data if src_copy.data else True
        tgt_node.children = src_copy.children

    def copy(self) -> Env:
        """Return a deep copy of this environment."""
        return copy.deepcopy(self)

    def _struct_key(self) -> str:
        """Build a canonical string key for hashing and equality."""
        if not self.children:
            return '{}'
        parts = []
        for key in sorted(self.children):
            child = self.children[key]
            if child._has_active():
                parts.append(f'{key}|{bool(child.data)}:{child._struct_key()}')
        if not parts:
            return '{}'
        return '{' + ', '.join(parts) + '}'

    def __hash__(self) -> int:
        """Hash based on the canonical structure key."""
        return hash(self._struct_key())

    def __eq__(self, other: object) -> bool:
        """Compare environments by structural equality."""
        if not isinstance(other, Env):
            return NotImplemented
        return self._struct_key() == other._struct_key()

    def __le__(self, other: Env) -> bool:
        """Return True if this environment is a subset of *other*."""
        return self._is_subset_of(other)

    def __ge__(self, other: Env) -> bool:
        """Return True if this environment is a superset of *other*."""
        return other._is_subset_of(self)

    def _is_subset_of(self, target: Env) -> bool:
        """Check whether every active node in self is also active in target."""
        for key, child in self.children.items():
            tgt_child = target.children.get(key)
            if child.data and (tgt_child is None or not tgt_child.data):
                return False
            if tgt_child is None:
                tgt_child = Env()
            if not child._is_subset_of(tgt_child):
                return False
        return True

    def __repr__(self) -> str:
        """Return a compact string representation of the tree."""
        return f'Env({self._struct_key()})'

    def to_flat_set(self) -> set[str]:
        """Collect all active state paths as a flat set of dot-separated strings.

        Returns:
            Set of paths where each leaf node has ``data=True``.
        """
        result: set[str] = set()
        self._collect_active_paths('', result)
        return result

    def _collect_active_paths(self, prefix: str, result: set[str]) -> None:
        """Recursively gather active paths into *result*."""
        for key in sorted(self.children):
            child = self.children[key]
            path = f'{prefix}{key}' if not prefix else f'{prefix}.{key}'
            if child.data:
                result.add(path)
            child._collect_active_paths(path, result)

    @classmethod
    def from_states(cls, states: list[str]) -> Env:
        """Create an environment with the given states pre-activated.

        Args:
            states: List of dot-separated state paths to activate.

        Returns:
            A new Env instance with all given states active.
        """
        env = cls()
        for state in states:
            env.set(state)
        return env
