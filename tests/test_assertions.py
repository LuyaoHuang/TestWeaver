"""Tests for the fluent assertion API."""

from __future__ import annotations

import re

import pytest

from testweaver.assertions import AssertionError, assert_raises, assert_that
from testweaver.engine import _run_callable
from testweaver.env import Env


def _call(func, params=None, env=None):
    """Helper to invoke a callable through the engine's _run_callable."""
    if params is None:
        params = {}
    if env is None:
        env = Env()
    return _run_callable(func, params, env)


class TestAssertThat:
    def test_equals_pass(self):
        ok, _, _, _, is_assert = _call(lambda p, e: assert_that(42).equals(42))
        assert ok is True
        assert is_assert is False

    def test_equals_fail(self):
        ok, stdout, stderr, _, is_assert = _call(
            lambda p, e: assert_that(42).equals(43)
        )
        assert ok is False
        assert is_assert is True
        assert "expected: 43" in stderr
        assert "actual: 42" in stderr

    def test_not_equals_pass(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that(42).not_equals(43))
        assert ok is True

    def test_not_equals_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that(42).not_equals(42)
        )
        assert ok is False
        assert "unexpectedly" in stderr

    def test_is_true_pass(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that(True).is_true())
        assert ok is True

    def test_is_true_fail(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that([]).is_true())
        assert ok is False

    def test_is_false_pass(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that([]).is_false())
        assert ok is True

    def test_is_none_pass(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that(None).is_none())
        assert ok is True

    def test_is_none_fail(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that(42).is_none())
        assert ok is False

    def test_is_not_none_pass(self):
        ok, _, _, _, _ = _call(lambda p, e: assert_that(42).is_not_none())
        assert ok is True

    def test_is_not_none_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that(None).is_not_none()
        )
        assert ok is False
        assert "non-None" in stderr

    def test_greater_than_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that(10).greater_than(5)
        )
        assert ok is True

    def test_greater_than_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that(3).greater_than(5)
        )
        assert ok is False
        assert "> 5" in stderr

    def test_greater_than_or_equal_to_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that(5).greater_than_or_equal_to(5)
        )
        assert ok is True

    def test_greater_than_or_equal_to_fail(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that(4).greater_than_or_equal_to(5)
        )
        assert ok is False

    def test_less_than_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that(3).less_than(5)
        )
        assert ok is True

    def test_less_than_or_equal_to_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that(5).less_than_or_equal_to(5)
        )
        assert ok is True

    def test_contains_pass_list(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that([1, 2, 3]).contains(2)
        )
        assert ok is True

    def test_contains_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that([1, 2]).contains(3)
        )
        assert ok is False
        assert "contains" in stderr

    def test_not_contains_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that([1, 2]).not_contains(3)
        )
        assert ok is True

    def test_has_length_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that([1, 2, 3]).has_length(3)
        )
        assert ok is True

    def test_has_length_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that([1, 2]).has_length(3)
        )
        assert ok is False
        assert "length" in stderr

    def test_is_instance_of_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that("hello").is_instance_of(str)
        )
        assert ok is True

    def test_matches_pass(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that("abc123").matches(r"^\w+\d+$")
        )
        assert ok is True

    def test_matches_fail(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that("abc").matches(r"^\d+$")
        )
        assert ok is False
        assert "matches" in stderr

    def test_chained_assertions(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that([1, 2, 3])
            .is_not_none()
            .has_length(3)
            .contains(2)
        )
        assert ok is True

    def test_chained_fails_on_first_failure(self):
        ok, _, _, _, _ = _call(
            lambda p, e: assert_that([1, 2])
            .has_length(3)  # fails here
            .contains(2)  # never reached
        )
        assert ok is False

    def test_described_as_adds_context(self):
        ok, _, stderr, _, _ = _call(
            lambda p, e: assert_that(42, "The answer").equals(43)
        )
        assert ok is False
        assert "The answer" in stderr

    def test_exception_has_expected_actual_attrs(self):
        try:
            assert_that(42).equals(43)
        except AssertionError as e:
            assert e.expected == 43
            assert e.actual == 42
        else:
            pytest.fail("Expected AssertionError")


class TestAssertRaises:
    def test_correct_exception_raised(self):
        def raiser(p, e):
            with assert_raises(ValueError):
                raise ValueError("bad value")
        ok, _, _, _, _ = _call(raiser)
        assert ok is True

    def test_no_exception_raised(self):
        def noop(p, e):
            with assert_raises(ValueError):
                pass
        ok, _, stderr, _, is_assert = _call(noop)
        assert ok is False
        assert is_assert is True
        assert "no exception was raised" in stderr

    def test_wrong_exception_type(self):
        def wrong(p, e):
            with assert_raises(ValueError):
                raise TypeError("wrong type")
        ok, _, stderr, _, _ = _call(wrong)
        assert ok is False
        assert "ValueError" in stderr
        assert "TypeError" in stderr

    def test_message_substring_match(self):
        def raiser(p, e):
            with assert_raises(ValueError, message="bad value"):
                raise ValueError("something bad value happened")
        ok, _, _, _, _ = _call(raiser)
        assert ok is True

    def test_message_mismatch(self):
        def raiser(p, e):
            with assert_raises(ValueError, message="bad value"):
                raise ValueError("something else")
        ok, _, _, _, _ = _call(raiser)
        assert ok is False

    def test_message_regex_match(self):
        def raiser(p, e):
            with assert_raises(ValueError, message=re.compile(r"code \d+")):
                raise ValueError("error code 42 occurred")
        ok, _, _, _, _ = _call(raiser)
        assert ok is True


class TestFormatValue:
    def test_string_is_reprd(self):
        from testweaver.assertions import _format_value
        assert _format_value("hello") == "'hello'"

    def test_type_is_class_name(self):
        from testweaver.assertions import _format_value
        assert _format_value(int) == "int"
