"""Correct tests that only look suspicious: none of these should be flagged."""
from unittest import mock

import pytest

from src.cart import apply_discount, cart_total, notify


def assert_total(prices, expected):
    assert cart_total(prices) == expected, f"{prices} should total {expected}"


def test_uses_helper():
    assert_total([1, 2], 3)


def test_rejects_negative():
    with pytest.raises(ValueError):
        apply_discount(100, -1)


class TestSmallCarts:
    def test_one(self):
        assert cart_total([5]) == 5


class TestLargeCarts:
    def test_one(self):
        assert cart_total([5] * 100) == 500


def test_bad_input_then_good():
    try:
        apply_discount(100, 200)
    except ValueError:
        pass
    assert apply_discount(100, 50) == 50


@pytest.mark.skip(reason="the payment sandbox is down until the vendor fixes it")
def test_payment_sandbox():
    assert False


def test_message_form():
    assert cart_total([2, 2]) == 4, "two twos make four"


def test_notify_sends():
    sender = mock.Mock()
    notify(sender, 10)
    sender.send.assert_called_once_with("Your total is 10")


def test_unexpected_error_fails_loudly():
    try:
        cart_total([1, 2])
    except Exception as e:
        pytest.fail(f"cart_total raised {e!r}")


class TestUnittestStyle(__import__("unittest").TestCase):
    def test_equal(self):
        self.assertEqual(cart_total([1, 1]), 2)

    def test_raises_context(self):
        with self.assertRaises(ValueError):
            apply_discount(1, 500)


def test_explicit_raise():
    if cart_total([3]) != 3:
        raise AssertionError("cart_total([3]) should be 3")


def test_tuple_variable():
    pair = (cart_total([1]), cart_total([2]))
    assert pair == (1, 2)


def test_inline_skip_with_reason():
    pytest.skip("needs a live payment provider")
    assert cart_total([1]) == 1


def test(name):
    def deco(fn):
        return fn
    return deco
