"""Fluent assertion API for TestWeaver.

Use ``assert_that(value)`` inside operation callables to verify expected
conditions with rich failure messages that include expected vs actual diffs.

    from testweaver import assert_that

    @check
    @requires('vm.active')
    def verify_vm(params, env):
        node = env._get_node('vm.active')
        assert_that(node.value['status']).equals('running')
        assert_that(node.value['cpu_count']).greater_than(0)
        assert_that(node.value['uuid']).matches(r'^[0-9a-f-]{36}$')
"""

from __future__ import annotations

import contextlib
import re
from typing import Any, Callable, Type


class AssertionError(AssertionError):
    """Assertion failure with structured expected/actual information.

    The engine catches this in :func:`_run_callable` and surfaces the
    message in test reports.
    """

    def __init__(
        self,
        message: str,
        expected: Any = ...,
        actual: Any = ...,
    ) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


def _format_value(value: Any) -> str:
    """Format a value for display in error messages."""
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bytes):
        return repr(value)
    if isinstance(value, type):
        return value.__name__
    return repr(value)


def _diff_message(
    description: str | None,
    expected: Any,
    actual: Any,
    *,
    show_expected: bool = True,
) -> str:
    """Build a multi-line failure message with expected vs actual."""
    lines = []
    actual_repr = _format_value(actual)
    if description:
        lines.append(description)
    if show_expected:
        expected_repr = _format_value(expected)
        lines.append(f"  expected: {expected_repr}")
    lines.append(f"    actual: {actual_repr}")
    return "\n".join(lines)


class _Assertion:
    """Fluent assertion wrapper around a value.

    Each method raises :class:`AssertionError` on failure and returns
    ``self`` on success, so assertions can be chained::

        assert_that(result).is_not_none().equals(42)
    """

    __slots__ = ('_actual', '_description')

    def __init__(self, actual: Any, description: str | None = None) -> None:
        self._actual = actual
        self._description = description

    def described_as(self, description: str) -> _Assertion:
        """Attach a human-readable label used in failure messages."""
        self._description = description
        return self

    # -- equality -------------------------------------------------------

    def equals(self, expected: Any) -> _Assertion:
        if self._actual != expected:
            msg = _diff_message(
                self._description or "Values are not equal",
                expected, self._actual,
            )
            raise AssertionError(msg, expected=expected, actual=self._actual)
        return self

    def not_equals(self, expected: Any) -> _Assertion:
        if self._actual == expected:
            msg = _diff_message(
                self._description or f"Value equals {_format_value(expected)} unexpectedly",
                f"not {_format_value(expected)}", self._actual,
            )
            raise AssertionError(msg, expected=f"not {expected}", actual=self._actual)
        return self

    # -- identity / truthiness ------------------------------------------

    def is_true(self) -> _Assertion:
        if not self._actual:
            msg = _diff_message(
                self._description or "Expected truthy value",
                "truthy", self._actual,
            )
            raise AssertionError(msg, expected="truthy", actual=self._actual)
        return self

    def is_false(self) -> _Assertion:
        if self._actual:
            msg = _diff_message(
                self._description or "Expected falsy value",
                "falsy", self._actual,
            )
            raise AssertionError(msg, expected="falsy", actual=self._actual)
        return self

    def is_none(self) -> _Assertion:
        if self._actual is not None:
            msg = _diff_message(
                self._description or "Expected None",
                None, self._actual,
            )
            raise AssertionError(msg, expected=None, actual=self._actual)
        return self

    def is_not_none(self) -> _Assertion:
        if self._actual is None:
            raise AssertionError(
                self._description or "Expected non-None value",
                expected="not None",
                actual=None,
            )
        return self

    # -- numeric --------------------------------------------------------

    def greater_than(self, threshold: int | float) -> _Assertion:
        if not isinstance(self._actual, (int, float)):
            raise AssertionError(
                _diff_message(
                    self._description or f"Cannot compare {type(self._actual).__name__} with >",
                    f"numeric > {threshold}", self._actual,
                )
            )
        if not (self._actual > threshold):
            msg = _diff_message(
                self._description or f"Expected value greater than {threshold}",
                f"> {threshold}", self._actual,
            )
            raise AssertionError(msg, expected=f"> {threshold}", actual=self._actual)
        return self

    def greater_than_or_equal_to(self, threshold: int | float) -> _Assertion:
        if not isinstance(self._actual, (int, float)):
            raise AssertionError(
                _diff_message(
                    self._description or f"Cannot compare {type(self._actual).__name__} with >=",
                    f"numeric >= {threshold}", self._actual,
                )
            )
        if not (self._actual >= threshold):
            msg = _diff_message(
                self._description or f"Expected value >= {threshold}",
                f">= {threshold}", self._actual,
            )
            raise AssertionError(msg, expected=f">= {threshold}", actual=self._actual)
        return self

    def less_than(self, threshold: int | float) -> _Assertion:
        if not isinstance(self._actual, (int, float)):
            raise AssertionError(
                _diff_message(
                    self._description or f"Cannot compare {type(self._actual).__name__} with <",
                    f"numeric < {threshold}", self._actual,
                )
            )
        if not (self._actual < threshold):
            msg = _diff_message(
                self._description or f"Expected value less than {threshold}",
                f"< {threshold}", self._actual,
            )
            raise AssertionError(msg, expected=f"< {threshold}", actual=self._actual)
        return self

    def less_than_or_equal_to(self, threshold: int | float) -> _Assertion:
        if not isinstance(self._actual, (int, float)):
            raise AssertionError(
                _diff_message(
                    self._description or f"Cannot compare {type(self._actual).__name__} with <=",
                    f"numeric <= {threshold}", self._actual,
                )
            )
        if not (self._actual <= threshold):
            msg = _diff_message(
                self._description or f"Expected value <= {threshold}",
                f"<= {threshold}", self._actual,
            )
            raise AssertionError(msg, expected=f"<= {threshold}", actual=self._actual)
        return self

    # -- membership -----------------------------------------------------

    def contains(self, item: Any) -> _Assertion:
        if item not in self._actual:
            msg = _diff_message(
                self._description or f"Expected {_format_value(self._actual)} to contain {_format_value(item)}",
                f"contains {_format_value(item)}", self._actual,
            )
            raise AssertionError(msg, expected=f"contains {item}", actual=self._actual)
        return self

    def not_contains(self, item: Any) -> _Assertion:
        if item in self._actual:
            msg = _diff_message(
                self._description or f"Expected {_format_value(self._actual)} to not contain {_format_value(item)}",
                f"not contains {_format_value(item)}", self._actual,
            )
            raise AssertionError(msg, expected=f"not contains {item}", actual=self._actual)
        return self

    # -- length ---------------------------------------------------------

    def has_length(self, length: int) -> _Assertion:
        try:
            actual_len = len(self._actual)
        except TypeError:
            raise AssertionError(
                _diff_message(
                    self._description or f"{type(self._actual).__name__} has no len()",
                    f"length {length}", self._actual,
                )
            )
        if actual_len != length:
            msg = _diff_message(
                self._description or f"Expected length {length}",
                f"length {length}", f"length {actual_len}",
            )
            raise AssertionError(msg, expected=f"length={length}", actual=f"length={actual_len}")
        return self

    # -- type -----------------------------------------------------------

    def is_instance_of(self, cls: type | tuple[type, ...]) -> _Assertion:
        if not isinstance(self._actual, cls):
            cls_name = (
                ", ".join(c.__name__ for c in cls)
                if isinstance(cls, tuple)
                else cls.__name__
            )
            msg = _diff_message(
                self._description or f"Expected instance of {cls_name}",
                cls_name, type(self._actual).__name__,
            )
            raise AssertionError(msg, expected=cls_name, actual=type(self._actual).__name__)
        return self

    # -- regex ----------------------------------------------------------

    def matches(self, pattern: str | re.Pattern) -> _Assertion:
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        if not isinstance(self._actual, str):
            raise AssertionError(
                _diff_message(
                    self._description or f"Cannot regex-match non-string value",
                    f"string matching {pattern.pattern}", self._actual,
                )
            )
        if not pattern.search(self._actual):
            msg = _diff_message(
                self._description or f"Expected string matching pattern",
                f"matches /{pattern.pattern}/", self._actual,
            )
            raise AssertionError(msg, expected=f"matches /{pattern.pattern}/", actual=self._actual)
        return self


def assert_that(value: Any, description: str | None = None) -> _Assertion:
    """Begin a fluent assertion on *value*.

    Returns a :class:`_Assertion` object whose methods (``equals``,
    ``greater_than``, ``contains``, ...) raise :class:`AssertionError`
    on failure.

    Usage::

        assert_that(result).equals(42)
        assert_that(items).contains('key').has_length(3)
        assert_that(status, "VM status").equals('running')
    """
    return _Assertion(value, description=description)


@contextlib.contextmanager
def assert_raises(
    expected_exc: Type[BaseException] | tuple[Type[BaseException], ...],
    message: str | re.Pattern | None = None,
    description: str | None = None,
):
    """Context manager that asserts an exception is raised.

    Usage::

        with assert_raises(ValueError, message="invalid"):
            do_something()
    """
    exc_names = (
        ", ".join(e.__name__ for e in expected_exc)
        if isinstance(expected_exc, tuple)
        else expected_exc.__name__
    )
    try:
        yield
    except Exception as e:
        if not isinstance(e, expected_exc):
            actual_name = type(e).__name__
            raise AssertionError(
                _diff_message(
                    description or f"Expected {exc_names}, got {actual_name}",
                    exc_names, actual_name,
                ),
                expected=exc_names,
                actual=actual_name,
            ) from e
        if message is not None:
            if isinstance(message, re.Pattern):
                if not message.search(str(e)):
                    raise AssertionError(
                        _diff_message(
                            description or f"Exception message does not match pattern",
                            f"matches /{message.pattern}/", str(e),
                        ),
                        expected=f"matches /{message.pattern}/",
                        actual=str(e),
                    ) from e
            elif message not in str(e):
                raise AssertionError(
                    _diff_message(
                        description or f"Exception message does not contain expected text",
                        message, str(e),
                    ),
                    expected=message,
                    actual=str(e),
                ) from e
        return
    raise AssertionError(
        description or f"Expected {exc_names} but no exception was raised",
        expected=exc_names,
        actual="no exception",
    )
