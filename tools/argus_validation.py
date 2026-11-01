"""Input and proof checks that remain active under optimized Python."""


def require(condition, message=None):
    """Preserve the harnesses' AssertionError contract without assert removal."""
    if not condition:
        if message is None:
            raise AssertionError
        raise AssertionError(message)
