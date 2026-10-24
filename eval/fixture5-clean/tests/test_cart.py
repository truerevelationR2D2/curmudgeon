import pytest

from src.cart import apply_discount, cart_total


def test_total_runs():
    assert cart_total([1, 2]) == 3


def test_total_single():
    assert cart_total([1]) == 1, "total of one item is wrong"


def test_discount():
    assert apply_discount(100, 10) == 90


def test_discount_zero():
    assert apply_discount(100, 0) == 100


def test_total_empty():
    assert cart_total([]) == 0


@pytest.mark.skip(reason="bounds are checked in the integration suite until the rewrite lands")
def test_discount_bounds():
    with pytest.raises(ValueError):
        apply_discount(100, 101)


class TestCartUnittest(__import__("unittest").TestCase):
    def test_total_positive(self):
        self.assertTrue(cart_total([1]) > 0, "total should be positive")

    def test_total_type(self):
        self.assertIsInstance(cart_total([1]), int)
