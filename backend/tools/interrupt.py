"""Stub for hermes tools.interrupt."""

import threading

_interrupted = threading.Event()


def is_interrupted() -> bool:
    return _interrupted.is_set()


def interrupt():
    _interrupted.set()
