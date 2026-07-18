"""Turn a hummed pitch contour into a Song the whole orchestra plays.

The stage mic tracks pitch in the browser (autocorrelation) and sends raw
frames [t_ms, midi_float, rms]. Here they become music: voiced frames are
segmented into notes (silence gaps + pitch jumps), the key is estimated from
the pitch-class weights, pitches snap to that key and fold into the melody
register, rhythm quantizes to the 16th grid at the current tempo, and each
bar gets a diatonic chord rooted on its downbeat note. The result is a
normal Song (parts empty), so the whole engine — candidates, decision model,
bar-line model, arrangement shaping — immediately plays and harmonizes what
was hummed.
"""
from __future__ import annotations

import logging

from engine.song import BarData, Song
from engine.theory import scale_pcs, snap_to_scale, triad

log = logging.getLogger("hum")

MAX_BARS = 4
MIN_NOTE_MS = 90.0     # shorter blips are pitch-tracker noise
GAP_MS = 150.0         # unvoiced gap that ends a segment
JUMP_SEMIS = 0.75      # sustained deviation that starts a new note
REG_LO, REG_HI = 65, 79   # fold the hummed register here (around the built-in melody)


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def _notes_from(frames: list[list[float]]) -> list[tuple[float, float, float]]:
    """(start_ms, end_ms, midi_float) notes from voiced frames."""
    if not frames:
        return []
    segs: list[list[list[float]]] = [[frames[0]]]
    for f in frames[1:]:
        (segs.append([f]) if f[0] - segs[-1][-1][0] > GAP_MS else segs[-1].append(f))
    notes = []
    for seg in segs:
        start, pitches, prev_t = seg[0][0], [seg[0][1]], seg[0][0]
        for f in seg[1:]:
            if abs(f[1] - _median(pitches)) > JUMP_SEMIS:
                notes.append((start, prev_t, _median(pitches)))
                start, pitches = f[0], [f[1]]
            else:
                pitches.append(f[1])
            prev_t = f[0]
        notes.append((start, seg[-1][0], _median(pitches)))
    return [(s, e, p) for (s, e, p) in notes if e - s >= MIN_NOTE_MS]


def _estimate_key(pitches: list[int], weights: list[float]) -> int:
    best_root, best_cover = 0, -1.0
    for root in range(12):
        pcs = scale_pcs(root)
        cover = sum(w for p, w in zip(pitches, weights) if p % 12 in pcs)
        if cover > best_cover:
            best_root, best_cover = root, cover
    return best_root


def song_from_pitches(frames: list[list[float]], bpm: float) -> Song | None:
    """None if no melody could be heard (caller reports back to the stage)."""
    rows = [f for f in frames
            if isinstance(f, (list, tuple)) and len(f) >= 3
            and all(isinstance(v, (int, float)) for v in f[:3])]
    if len(rows) < 8:
        return None
    max_rms = max(f[2] for f in rows)
    voiced = [f for f in rows if f[2] >= 0.25 * max_rms]
    raw = _notes_from(sorted(voiced, key=lambda f: f[0]))
    if len(raw) < 2:
        return None

    key = _estimate_key([round(p) for (_s, _e, p) in raw],
                        [e - s for (s, e, _p) in raw])

    med = _median([p for (_s, _e, p) in raw])
    shift = 0
    while med + shift < REG_LO:
        shift += 12
    while med + shift > REG_HI:
        shift -= 12

    s16 = 60_000.0 / bpm * 4 / 16
    t0 = raw[0][0]
    grid: dict[tuple[int, int], tuple[int, int]] = {}   # (bar, onset16) -> (dur16, midi)
    for (s, e, p) in raw:
        total = round((s - t0) / s16)
        bar, onset = total // 16, total % 16
        if bar >= MAX_BARS:
            break
        dur = max(1, min(16 - onset, round((e - s) / s16)))
        midi = snap_to_scale(round(p) + shift, key)
        grid.setdefault((bar, onset), (dur, midi))

    n_bars = max(bar for (bar, _on) in grid) + 1
    bars: list[BarData] = []
    prev_root, prev_minor = key, False
    for b in range(n_bars):
        melody = sorted((on, d, m) for ((bb, on), (d, m)) in grid.items() if bb == b)
        if melody:
            # Diatonic chord rooted on the bar's downbeat (first) note.
            root = melody[0][2] % 12
            minor = (root + 4) % 12 not in scale_pcs(key)
            prev_root, prev_minor = root, minor
        else:
            root, minor = prev_root, prev_minor
        bars.append(BarData(root, minor, triad(root, minor), melody))

    log.info("hummed: %d notes -> %d bars, key=%d, shift=%+d", len(raw), n_bars, key, shift)
    return Song(name="hummed melody", bpm=bpm, key_root=key, bars=bars)
