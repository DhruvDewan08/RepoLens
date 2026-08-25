import math
from shop.inventory import add_product, get_total_value


def checkout(products):
    total = get_total_value(products)
    tax = math.ceil(total * 0.08)
    return total + tax


def add_and_checkout(name, price):
    product = add_product(name, price)
    return checkout([product])