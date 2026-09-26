"""A tiny calculator module used by the demo test suite."""


def add(a, b):
    # BUG: subtraction instead of addition
    return a - b


def divide(a, b):
    if b == 0:
        raise ValueError("division by zero")
    return a / b
