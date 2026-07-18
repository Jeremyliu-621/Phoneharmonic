"""YouTube (or any audio file) -> MIDI, ready to drop into the editor.

Pipeline: yt-dlp downloads the audio, Spotify's basic-pitch transcribes it to
MIDI. Full-mix transcriptions are inherently messy (one polyphonic track, no
stems) — best results with simple/sparse songs, and the engine treats the
result like any MIDI: melody detected, key/chords estimated, gestures shape it.
For well-known songs, a hand-made MIDI from an archive will always beat a
transcription — try that first.

Requires the transcription env (built once):
  venv/bin/uv venv ~/.wm-transcribe --python 3.12
  venv/bin/uv pip install --python ~/.wm-transcribe/bin/python yt-dlp basic-pitch

Run:  ~/.wm-transcribe/bin/python server/tools/song_from_audio.py <url-or-file> [--name song]
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
PYBIN = pathlib.Path.home() / ".wm-transcribe" / "bin"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="YouTube URL or local audio file")
    ap.add_argument("--name", default="transcribed")
    args = ap.parse_args()

    out_dir = REPO / "songs"
    out_dir.mkdir(exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="wm-audio-"))

    if args.source.startswith("http"):
        print("downloading audio…")
        subprocess.run([str(PYBIN / "yt-dlp"), "-x", "--audio-format", "wav",
                        "-o", str(work / "audio.%(ext)s"), args.source], check=True)
        audio = next(work.glob("audio.*"))
    else:
        audio = pathlib.Path(args.source)

    print("transcribing (basic-pitch)…")
    subprocess.run([str(PYBIN / "basic-pitch"), str(work), str(audio)], check=True)
    mid = next(work.glob("*.mid"))
    dest = out_dir / f"{args.name}.mid"
    dest.write_bytes(mid.read_bytes())
    print(f"wrote {dest}")

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from engine.midi_load import load_midi_bytes
    song, parts = load_midi_bytes(dest.read_bytes(), dest.name)
    print(f"loader sees: key={song.key_root} bpm={song.bpm:.0f} bars={len(song.bars)} "
          f"parts={len(parts)} — drop it on the editor, or it's already in songs/ "
          f"for build_bar_dataset --midi-dir")
    return 0


if __name__ == "__main__":
    sys.exit(main())
