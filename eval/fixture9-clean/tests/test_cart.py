from src.cart import discounted, total


def test_total():  # REQ-1
    assert total([1, 2]) == 3


def test_discount_floor():  # covers REQ-2
    assert discounted(10, 150) == 0


def test_rounding():  # REQ-3: two decimals
    assert f"{total([0.1, 0.2]):.2f}" == "0.30"


def test_empty_checkout():  # REQ-4
    assert total([]) == 0
