def total(prices):
    return sum(prices)


def discounted(total_, percent):
    return max(0, total_ * (100 - percent) / 100)
