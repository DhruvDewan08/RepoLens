from shop.models import Product


def add_product(name, price):
    product = Product(name, price)
    return product


def get_total_value(products):
    total = 0
    for p in products:
        total = total + p.price
    return total