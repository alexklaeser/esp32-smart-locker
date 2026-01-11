class _GeneratorContextManager:
    def __init__(self, gen):
        self._gen = gen

    def __enter__(self):
        return next(self._gen)

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            try:
                next(self._gen)
            except StopIteration:
                return False
            else:
                raise RuntimeError
        else:
            try:
                self._gen.throw(exc_type, exc, tb)
            except StopIteration:
                return True
            else:
                return False


def contextmanager(func):
    def wrapper(*args, **kwargs):
        return _GeneratorContextManager(func(*args, **kwargs))

    return wrapper
