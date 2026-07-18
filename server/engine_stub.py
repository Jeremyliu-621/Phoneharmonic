"""P1 stub engine: a metronome that clicks on every section at once.

This exists so the entire realtime layer — clock sync, scheduler, section
scheduling — can be built and measured before the real music engine exists.
The metronome is deliberately the hardest case for the skew measurement:
every device is asked to make the same sound at the same instant, so any
inter-device disagreement is directly audible/recordable.

Implements the MusicEngine Protocol from engine_api.py.
"""
from __future__ import annotations

import itertools

from config import METRONOME_BEATS_PER_BAR, METRONOME_BPM
from engine_api import CancelSpec, GestureWindow, NoteEvent, SectionInfo
from protocol import SECTION_ALL

_ids = itertools.count(1)


class MetronomeEngine:
    def __init__(self) -> None:
        self._playing = False
        self._t0_ms: float | None = None          # server-time of beat 0
        self._beat_ms = 60_000.0 / METRONOME_BPM   # ms per beat
        self._next_beat = 0                         # index of the next beat to emit
        self._cancels: list[CancelSpec] = []

    # --- transport ---
    def on_transport(self, cmd: str, t0_ms: float | None) -> None:
        if cmd in ("start", "clicktest"):
            self._playing = True
            self._t0_ms = t0_ms
            self._next_beat = 0
        elif cmd == "stop":
            self._playing = False
            self._cancels.append(CancelSpec(allnotesoff=True))
        elif cmd == "allnotesoff":
            self._cancels.append(CancelSpec(allnotesoff=True))
        # "resync" is a client-side concept; nothing to do server-side.

    # --- event pull ---
    def get_events(self, now_ms: float, until_ms: float) -> list[NoteEvent]:
        if not self._playing or self._t0_ms is None:
            return []
        events: list[NoteEvent] = []
        # Emit every beat whose time falls in the lookahead window and hasn't
        # been emitted yet. Skip beats already in the past (missed lead time).
        while True:
            beat_time = self._t0_ms + self._next_beat * self._beat_ms
            if beat_time > until_ms:
                break
            if beat_time >= now_ms:
                beat_in_bar = self._next_beat % METRONOME_BEATS_PER_BAR
                downbeat = beat_in_bar == 0
                events.append(NoteEvent(
                    id=f"m{next(_ids)}",
                    section=SECTION_ALL,
                    at=beat_time,
                    dur=60.0,
                    note="C6" if downbeat else "C5",   # accent the downbeat by pitch
                    vel=1.0 if downbeat else 0.7,
                    art="click",
                ))
            self._next_beat += 1
        return events

    def get_cancels(self) -> list[CancelSpec]:
        out, self._cancels = self._cancels, []
        return out

    # --- unused-in-P1 protocol surface (no-ops until the real engine) ---
    def on_sections_changed(self, sections: list[SectionInfo]) -> None: ...
    def on_gesture(self, window: GestureWindow) -> None: ...
    def on_grab(self, kind: str, server_ms: float) -> None: ...
    def on_aim(self, section_id: str | None) -> None: ...
    def on_feedback(self, value: int) -> None: ...
