"""The server's authoritative clock.

One monotonic timebase, established at process start. Every scheduled event
time and every clock.pong `ts` is expressed as milliseconds on this clock.
Never wall-clock (`time.time()`) — that can jump and would corrupt sync.
"""
from __future__ import annotations

import time

_T0 = time.monotonic()


def server_time_ms() -> float:
    """Milliseconds since process start, on the monotonic clock."""
    return (time.monotonic() - _T0) * 1000.0
