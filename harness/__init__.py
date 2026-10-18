"""Harness package. The Retention Console engine is loaded lazily so that
importing harness.* submodules does not pull in the console."""

__all__ = ["build_console"]


def build_console(*args, **kwargs):
    from harness.engine import build_console as _build_console
    return _build_console(*args, **kwargs)
