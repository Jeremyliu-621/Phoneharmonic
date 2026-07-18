"""Gesture feature extraction from a completed grab->release window.

Two input modalities converge on the same 5-feature vector:
  - "imu"  : phone/ESP32 frames [tw, ax,ay,az, gx,gy,gz]  (accel m/s^2 incl. gravity, gyro deg/s)
  - "pose" : webcam frames       [tw, x, y, z, roll_deg]   (normalised hand position + roll)

Features (all roughly normalised): energy, size, vertical (-1..1), rotation, duration(s).

The scaling constants are deliberate rough guesses for the slice — plain-Python,
no numpy/scipy. P3 replaces this with gravity filtering + percentile normalisation
calibrated from recorded data; the interface stays identical.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from engine_api import GestureWindow


@dataclass
class GestureFeatures:
    energy: float = 0.0      # 0..1 vigor
    size: float = 0.0        # 0..1 spatial extent
    vertical: float = 0.0    # -1 (down) .. +1 (up)
    rotation: float = 0.0    # 0..1 twist / swirl
    duration: float = 0.0    # seconds

    def as_dict(self) -> dict:
        return {"energy": self.energy, "size": self.size, "vertical": self.vertical,
                "rotation": self.rotation, "duration": self.duration}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _duration_s(frames: list[list[float]]) -> float:
    if len(frames) < 2:
        return 0.0
    return max(0.0, (frames[-1][0] - frames[0][0]) / 1000.0)


def _extract_imu(frames: list[list[float]]) -> GestureFeatures:
    dur = _duration_s(frames)
    lin, gyro, ay_vals = [], [], []
    for f in frames:
        _, ax, ay, az, gx, gy, gz = f[:7]
        lin.append(abs(math.sqrt(ax * ax + ay * ay + az * az) - 9.8))  # remove ~1g
        gyro.append(math.sqrt(gx * gx + gy * gy + gz * gz))
        ay_vals.append(ay)
    speed = sum(lin) / len(lin)
    rot = sum(gyro) / len(gyro)
    return GestureFeatures(
        energy=_clamp(speed / 12.0, 0, 1),
        size=_clamp(speed * dur / 6.0, 0, 1),
        vertical=_clamp((sum(ay_vals) / len(ay_vals)) / 9.8, -1, 1),
        rotation=_clamp(rot / 200.0, 0, 1),
        duration=dur,
    )


def _extract_pose(frames: list[list[float]]) -> GestureFeatures:
    dur = _duration_s(frames)
    path = 0.0
    rolls = []
    for a, b in zip(frames, frames[1:]):
        dx, dy, dz = b[1] - a[1], b[2] - a[2], b[3] - a[3]
        path += math.sqrt(dx * dx + dy * dy + dz * dz)
        rolls.append(b[4])
    if not rolls:
        rolls = [frames[0][4]] if frames else [0.0]
    speed = path / dur if dur > 0 else 0.0
    y0, y1 = frames[0][2], frames[-1][2]
    roll_range = max(rolls) - min(rolls)
    return GestureFeatures(
        energy=_clamp(speed / 2.0, 0, 1),        # normalised units/s
        size=_clamp(path / 2.0, 0, 1),
        vertical=_clamp(-(y1 - y0) * 3.0, -1, 1),  # screen y grows downward -> up is negative
        rotation=_clamp(roll_range / 180.0, 0, 1),
        duration=dur,
    )


def extract_features(window: GestureWindow) -> GestureFeatures:
    frames = window.frames
    if len(frames) < 3 or _duration_s(frames) < 0.1:
        return GestureFeatures()  # too short -> treated as a tiny/neutral gesture
    if window.modality == "pose":
        return _extract_pose(frames)
    return _extract_imu(frames)
