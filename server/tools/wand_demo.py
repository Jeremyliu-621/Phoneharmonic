"""wand_demo.py — a fake UNO Q for demos and laptop testing.

Connects to the server as role "wand" and behaves like a person holding the
hardware wand: slowly sweeps the pointing beam left <-> right across the room,
and every few seconds "squishes" (grab) while waving energetically, releasing
after ~1s — so the console shows the live beam, cards glow as it passes, the
beam turns green during grabs, and the camera hub flashes what each gesture did.

Usage (server running):
    python server/tools/wand_demo.py            # ws://127.0.0.1:8080/ws
    WM_HTTP_PORT=8098 python server/tools/wand_demo.py
    python server/tools/wand_demo.py --seconds 120
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import websockets

PORT = os.environ.get("WM_HTTP_PORT", "8080")
WS = os.environ.get("WM_WS_URL", f"ws://127.0.0.1:{PORT}/ws")

RATE_HZ = 50          # IMU sample rate
BATCH = 5             # frames per wand.imu (like the board)
SWEEP_PERIOD_S = 9.0  # one full left->right->left sweep
SWEEP_DEG = 70.0      # sweep amplitude: ±70° covers the whole room
GRAB_EVERY_S = 7.0    # squish cadence
GRAB_LEN_S = 1.1


async def main(seconds: float) -> None:
    async with websockets.connect(WS) as ws:
        await ws.send(json.dumps({"t": "hello", "v": 1, "role": "wand", "session": "lol1"}))
        welcome = json.loads(await ws.recv())
        print(f"fake wand connected as {welcome.get('client_id', '?')[:8]} -> {WS}")
        print("watch the console: the beam sweeps the room; green = grabbing")

        async def drain() -> None:
            # the server pushes roster/engine.state/wand.cmd at us; if nobody
            # reads them the receive queue fills and the socket chokes on
            # keepalive — exactly what the real board's _downlink task is for
            async for _ in ws:
                pass
        drain_task = asyncio.create_task(drain())

        t0 = time.perf_counter()
        seq, frames = 0, []
        grabbed, next_grab, grab_until = False, GRAB_EVERY_S, 0.0
        # target yaw follows a sine; we emit the RATE (deg/s) the IMU would see
        prev_yaw = 0.0

        while (t := time.perf_counter() - t0) < seconds:
            yaw = SWEEP_DEG * math.sin(2 * math.pi * t / SWEEP_PERIOD_S)
            gz = (yaw - prev_yaw) * RATE_HZ          # deg/s to move to the new yaw
            prev_yaw = yaw
            wave = 25.0 * math.sin(2 * math.pi * t * 2.2) if grabbed else 0.0
            tw = round(t * 1000)
            frames.append([tw, wave * 0.3, 9.81, wave * 0.2, wave, wave * 0.6, gz])
            if len(frames) >= BATCH:
                seq += 1
                await ws.send(json.dumps({"t": "wand.imu", "seq": seq, "frames": frames}))
                frames = []

            if not grabbed and t >= next_grab:
                grabbed, grab_until = True, t + GRAB_LEN_S
                await ws.send(json.dumps({"t": "wand.grab", "state": "start", "tw": tw}))
                print(f"  squish  (t={t:5.1f}s, yaw {yaw:+.0f}°)")
            elif grabbed and t >= grab_until:
                grabbed, next_grab = False, t + GRAB_EVERY_S
                await ws.send(json.dumps({"t": "wand.grab", "state": "end", "tw": tw}))
                print(f"  release (t={t:5.1f}s)")

            await asyncio.sleep(1.0 / RATE_HZ)
        drain_task.cancel()
        print("demo done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()
    asyncio.run(main(args.seconds))
