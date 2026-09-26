from calculator import add, divide


def test_add_negative_numbers():
    assert add(-2, 3) == 1


def test_add_positive_numbers():
    assert add(2, 3) == 5


def test_divide():
    assert divide(6, 3) == 2


def test_divide_by_zero_raises():
    try:
        divide(1, 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
