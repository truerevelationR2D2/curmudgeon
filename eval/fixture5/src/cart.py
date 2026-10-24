"""A tiny cart for the tests-of-the-tests lens fixture (SC-48)."""


def cart_total(prices):
    return sum(prices)


def apply_discount(total, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round(total * (100 - percent) / 100, 2)


def notify(sender, total):
    sender.send(f"Your total is {total}")
