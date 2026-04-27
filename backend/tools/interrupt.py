"""Stub for hermes tools.interrupt."""

import threading

_interrupted = threading.Event()
_interrupt_event = _interrupted


def is_interrupted() -> bool:
    return _interrupted.is_set()


def interrupt() -> None:
    _interrupted.set()


def set_interrupt() -> None:
    _interrupted.set()


def clear_interrupt() -> None:
    _interrupted.clear()
