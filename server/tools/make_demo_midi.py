"""Generate a public-domain multi-track demo MIDI: Pachelbel's Canon in D.

Four real parts (lead, string harmony, bass, drums) over the canonical 8-bar
progression — exactly the material the conductor-shaping engine needs to show
what it does: gestures thin/open the arrangement, drop drums to the kick,
shift the register, solo a part, and it all reverts. Also seed data for
build_bar_dataset --midi-dir.

Run:  python server/tools/make_demo_midi.py   -> songs/canon.mid
"""
from __future__ import annotations

import pathlib
import sys

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
TPB = 480                              # ticks per beat; bar = 4 beats = 1920

# The canon ground: D A Bm F#m G D G A (roots as MIDI, bass register)
BASS = [50, 45, 47, 42, 43, 38, 43, 45]
# Triads (D major) voiced near octave 4 for the string pad
CHORDS = [[62, 66, 69], [61, 64, 69], [62, 66, 71], [61, 66, 69],
          [62, 67, 71], [62, 66, 69], [62, 67, 71], [61, 64, 69]]
# The famous descending line, two half-notes per bar
MELODY = [(78, 76), (74, 73), (71, 69), (71, 73),
          (74, 71), (69, 66), (67, 71), (69, 73)]


def main() -> int:
    mid = MidiFile(ticks_per_beat=TPB)

    lead = MidiTrack()
    mid.tracks.append(lead)
    lead.append(MetaMessage("track_name", name="Lead", time=0))
    lead.append(MetaMessage("set_tempo", tempo=bpm2tempo(100), time=0))
    lead.append(Message("program_change", channel=0, program=40, time=0))   # violin
    for (a, b) in MELODY:
        for p in (a, b):
            lead.append(Message("note_on", channel=0, note=p, velocity=92, time=0))
            lead.append(Message("note_off", channel=0, note=p, velocity=0, time=TPB * 2))

    pad = MidiTrack()
    mid.tracks.append(pad)
    pad.append(MetaMessage("track_name", name="Strings", time=0))
    pad.append(Message("program_change", channel=1, program=48, time=0))
    for chord in CHORDS:
        for p in chord:
            pad.append(Message("note_on", channel=1, note=p, velocity=58, time=0))
        for j, p in enumerate(chord):
            pad.append(Message("note_off", channel=1, note=p, velocity=0,
                               time=TPB * 4 if j == 0 else 0))

    bass = MidiTrack()
    mid.tracks.append(bass)
    bass.append(MetaMessage("track_name", name="Bass", time=0))
    bass.append(Message("program_change", channel=2, program=33, time=0))
    for root in BASS:                   # root half-note, fifth half-note
        for p in (root, root + 7):
            bass.append(Message("note_on", channel=2, note=p, velocity=78, time=0))
            bass.append(Message("note_off", channel=2, note=p, velocity=0, time=TPB * 2))

    drums = MidiTrack()
    mid.tracks.append(drums)
    drums.append(MetaMessage("track_name", name="Drums", time=0))
    for _bar in range(8):
        for eighth in range(8):        # hats on 8ths, kick 1&3, snare 2&4
            hits = [42]
            if eighth in (0, 4):
                hits.append(36)
            if eighth in (2, 6):
                hits.append(38)
            for p in hits:
                drums.append(Message("note_on", channel=9, note=p, velocity=84, time=0))
            drums.append(Message("note_off", channel=9, note=hits[0], velocity=0, time=TPB // 2))
            for p in hits[1:]:
                drums.append(Message("note_off", channel=9, note=p, velocity=0, time=0))

    out = REPO / "songs"
    out.mkdir(exist_ok=True)
    path = out / "canon.mid"
    mid.save(path)
    print(f"wrote {path}")

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from engine.midi_load import load_midi_bytes
    song, parts = load_midi_bytes(path.read_bytes(), "canon.mid")
    print(f"loader sees: key={song.key_root} bpm={song.bpm:.0f} bars={len(song.bars)} "
          f"parts={[(p['name'], p['instrument'], 'melody' if p['is_melody'] else '') for p in parts]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
