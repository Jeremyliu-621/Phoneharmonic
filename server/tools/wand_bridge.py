"""Bluetooth-serial -> WebSocket bridge for the hardware wand.

The UNO Q (or ESP32) pairs with the laptop over Bluetooth Serial and prints
ONE JSON message PER LINE — exactly the wire messages from
docs/hardware-wand.md (wand.imu / wand.grab / wand.touch / wand.range /
wand.mode / wand.recal / wand.feedback). This bridge opens the serial port,
speaks the hello handshake to the server as role "wand", and forwards every
line verbatim. Firmware never needs a WiFi stack or a WebSocket client.

  python server/tools/wand_bridge.py --port /dev/tty.WandMaestro --baud 115200

Reconnects both sides forever; malformed lines are dropped with a note.
Requires pyserial (in requirements.txt).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # server/ on path

try:
    import serial  # pyserial
except ImportError:
    print("pyserial missing:  venv/bin/pip install pyserial")
    sys.exit(1)

from websockets.asyncio.client import connect

ALLOWED = {"wand.imu", "wand.pose", "wand.grab", "wand.touch", "wand.range",
           "wand.mode", "wand.recal", "wand.feedback"}


async def pump(port: str, baud: int, url: str) -> None:
    client_id = None
    while True:
        try:
            ser = serial.Serial(port, baud, timeout=0.25)
        except serial.SerialException as e:
            print(f"serial: {e} — retrying in 2s")
            await asyncio.sleep(2)
            continue
        print(f"serial open: {port} @ {baud}")
        try:
            async with connect(url) as ws:
                await ws.send(json.dumps({"t": "hello", "v": 1, "role": "wand",
                                          "session": "lol1", "client_id": client_id}))
                welcome = json.loads(await ws.recv())
                client_id = welcome.get("client_id", client_id)
                print(f"bridged to {url} as wand ({client_id[:8] if client_id else '?'})")
                n = 0
                while True:
                    line = await asyncio.to_thread(ser.readline)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8", "replace").strip())
                    except ValueError:
                        print(f"  dropped non-JSON line: {line[:60]!r}")
                        continue
                    if not isinstance(msg, dict) or msg.get("t") not in ALLOWED:
                        print(f"  dropped unexpected message: {str(msg)[:60]}")
                        continue
                    await ws.send(json.dumps(msg))
                    n += 1
                    if n % 200 == 0:
                        print(f"  {n} messages bridged")
        except Exception as e:  # noqa: BLE001 - keep bridging through anything
            print(f"bridge dropped ({type(e).__name__}: {e}) — reconnecting in 1s")
            await asyncio.sleep(1)
        finally:
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", required=True, help="serial device, e.g. /dev/tty.WandMaestro")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--url", default="ws://127.0.0.1:8080/ws")
    args = ap.parse_args()
    try:
        asyncio.run(pump(args.port, args.baud, args.url))
    except KeyboardInterrupt:
        print("bridge stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
