class Product:
    def __init__(self, name, price):
        self.name = name
        self.price = price

    def apply_discount(self, percent):
        discount = calculate_discount(self.price, percent)
        return self.price - discount


def calculate_discount(price, percent):
    return price * percent / 100