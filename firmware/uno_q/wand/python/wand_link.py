"""wand_link.py — the WiFi WebSocket link between the UNO Q and the laptop.

Runs on the board's Linux side. Bidirectional:
  UPLINK   Bridge topic "imu" (CSV from the MCU) -> batch ~5 -> wand.imu JSON.
  DOWNLINK server wand.cmd -> WandState -> Bridge topic "cmd" (CSV to the MCU),
           plus phone-select + ai-mode hooks.

Mirrors the handshake/forward logic of server/tools/wand_bridge.py, but lives on
the board and is two-way. Reconnects forever, echoing the cached client_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
import threading
import time
from collections import deque

import websockets
from websockets.asyncio.client import connect

import config
from state import WandState

log = logging.getLogger("wand.link")


# ── zero-config server discovery ─────────────────────────────────────────────
# Order: env override -> cached last-good URL -> listen/probe for the server's
# UDP beacon -> default gateway (covers a laptop-hosted hotspot). The result:
# App Lab "Run" is the only human action on the board, on any network.

def _cached_url() -> str | None:
    try:
        with open(config.CACHE_FILE, encoding="utf-8") as f:
            return json.load(f).get("ws") or None
    except (OSError, ValueError):
        return None


def _save_cache(url: str) -> None:
    try:
        with open(config.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ws": url}, f)
    except OSError:
        pass


def _discover_beacon(wait_s: float) -> str | None:
    """Listen for the server's discovery beacon while poking it with probes.
    Our own probe also lands in our socket (we bind the same port) — the
    'phoneharmonic' key filters it out."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", config.DISCOVERY_PORT))
        sock.settimeout(1.0)
    except OSError as e:
        log.warning("discovery socket failed: %s", e)
        return None
    try:
        deadline = time.monotonic() + wait_s
        last_probe = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() - last_probe > 2.0:
                last_probe = time.monotonic()
                for dst in ("255.255.255.255", "<broadcast>"):
                    try:
                        sock.sendto(b"maestro?", (dst, config.DISCOVERY_PORT))
                    except OSError:
                        pass
            try:
                data, _addr = sock.recvfrom(512)
            except socket.timeout:
                continue
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except ValueError:
                continue
            if msg.get("phoneharmonic") and msg.get("ws"):
                return str(msg["ws"])
        return None
    finally:
        sock.close()


def _gateway_url() -> str | None:
    """On the board's Linux, the default gateway is the hotspot host — which
    IS the laptop when the laptop hosts. Free fallback."""
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw = socket.inet_ntoa(struct.pack("<L", int(parts[2], 16)))
                    return f"ws://{gw}:{config.WS_PORT}/ws"
    except (OSError, ValueError):
        pass
    return None


def resolve_ws_url(skip_cache: bool = False) -> str | None:
    if config.WS_URL:                       # WAND_LAPTOP_IP override always wins
        return config.WS_URL
    if not skip_cache:
        url = _cached_url()
        if url:
            log.info("using cached server url %s", url)
            return url
    url = _discover_beacon(config.DISCOVERY_WAIT_S)
    if url:
        log.info("discovered server via beacon: %s", url)
        return url
    url = _gateway_url()
    if url:
        log.info("falling back to gateway: %s", url)
    return url

# Bridge (MCU<->Linux). Optional import so this module stays testable off-board.
try:
    from arduino.app_utils import Bridge   # type: ignore
except Exception:  # noqa: BLE001
    Bridge = None
    log.warning("arduino.app_utils.Bridge unavailable — running off-board (no MCU I/O)")


class WandLink:
    def __init__(self, state: WandState, ai_mode=None, phone_select=None):
        self.state = state
        self.ai_mode = ai_mode
        self.phone_select = phone_select
        self._buf: deque[list[float]] = deque()
        self._lock = threading.Lock()
        self._seq = 0
        self._range: float | None = None    # latest ToF mm from the MCU, if new
        self._ws = None                      # live socket; None between reconnects
        self._grabbed = False               # squeeze-to-conduct state (ToF-derived)

    # --- MCU uplink ingress (Bridge callback; may fire off-thread) ---
    def _on_imu(self, payload) -> None:
        row = _parse_imu_csv(payload)
        if row is not None:
            with self._lock:
                self._buf.append(row)

    def _drain(self, n: int) -> list[list[float]] | None:
        with self._lock:
            if len(self._buf) < n:
                return None
            return [self._buf.popleft() for _ in range(n)]

    # --- MCU range ingress (ToF) ---
    def _on_range(self, payload) -> None:
        mm = _parse_range(payload)
        if mm is not None:
            with self._lock:
                self._range = mm

    def _take_range(self) -> float | None:
        with self._lock:
            mm, self._range = self._range, None
            return mm

    # --- MCU downlink egress ---
    def _push_to_mcu(self) -> None:
        if Bridge is not None:
            Bridge.notify("cmd", self.state.to_mcu_csv())

    async def send(self, obj: dict) -> None:
        """Used by helpers (e.g. phone_select.recal) to reach the server."""
        if self._ws is not None:
            await self._ws.send(json.dumps(obj))

    def register_bridge(self) -> None:
        """Register the MCU uplink providers. Call once on the main thread before
        App.run() — the Arduino Bridge runtime services these callbacks."""
        if Bridge is not None:
            Bridge.provide("imu", self._on_imu)
            Bridge.provide("range", self._on_range)

    # --- main loop: discover + reconnect forever ---
    async def run(self) -> None:
        self._ws = None
        from_cache = False
        skip_cache = False
        while True:
            url = await asyncio.to_thread(resolve_ws_url, skip_cache)
            skip_cache = False
            if url is None:
                log.warning("no server found (beacon quiet, no gateway); retrying")
                await asyncio.sleep(config.RECONNECT_BACKOFF_S)
                continue
            from_cache = (not config.WS_URL) and url == _cached_url()
            try:
                async with connect(url) as ws:
                    self._ws = ws
                    self._grabbed = False   # a reconnect must not strand a grab
                    await self._handshake(ws)
                    _save_cache(url)        # it worked: instant reconnects next time
                    log.info("wand link up -> %s (client_id=%s)", url, self.state.client_id)
                    await asyncio.gather(self._uplink(ws), self._downlink(ws))
            except (OSError, websockets.ConnectionClosed) as e:
                log.warning("link down (%s); reconnecting", type(e).__name__)
                if from_cache:
                    skip_cache = True       # stale cache (new network?): rediscover
            except Exception:  # noqa: BLE001
                log.exception("link error; reconnecting")
            finally:
                self._ws = None
            await asyncio.sleep(config.RECONNECT_BACKOFF_S)

    async def _handshake(self, ws) -> None:
        await ws.send(json.dumps({
            "t": "hello", "v": config.PROTOCOL_VERSION, "role": "wand",
            "session": config.SESSION, "client_id": self.state.client_id,
        }))
        welcome = json.loads(await ws.recv())
        self.state.client_id = welcome.get("client_id", self.state.client_id)

    async def _uplink(self, ws) -> None:
        while True:
            sent = False
            frames = self._drain(config.BATCH)
            if frames is not None:
                self._seq += 1
                await ws.send(json.dumps({"t": "wand.imu", "seq": self._seq, "frames": frames}))
                sent = True
            mm = self._take_range()
            if mm is not None:
                await ws.send(json.dumps({"t": "wand.range", "mm": mm}))
                await self._squish_grab(ws, mm)
                sent = True
            if not sent:
                await asyncio.sleep(0.005)

    # Squeeze-to-conduct: covering the ToF (< GRAB_ON_MM) = grab start, so the
    # server buffers the IMU that follows into a gesture window; uncovering
    # (> GRAB_OFF_MM) releases it. Without this the hardware wand can wave
    # forever and the engine never hears a gesture.
    async def _squish_grab(self, ws, mm: float) -> None:
        tw = int(time.monotonic() * 1000)
        if not self._grabbed and 0 < mm < config.GRAB_ON_MM:
            self._grabbed = True
            await ws.send(json.dumps({"t": "wand.grab", "state": "start", "tw": tw}))
            log.info("squish grab START (%.0fmm)", mm)
        elif self._grabbed and mm > config.GRAB_OFF_MM:
            self._grabbed = False
            await ws.send(json.dumps({"t": "wand.grab", "state": "end", "tw": tw}))
            log.info("squish grab END (%.0fmm)", mm)

    async def _downlink(self, ws) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            t = msg.get("t")
            if t == "wand.cmd":
                self.state.update_from_cmd(msg)
                self._push_to_mcu()
                if self.phone_select is not None:
                    self.phone_select.on_state(self.state)
                if self.ai_mode is not None:
                    self.ai_mode.on_state(self.state)
            elif t == "err":
                log.warning("server err: %s", msg.get("msg"))
            # welcome / clock.pong: ignored


def _parse_imu_csv(payload) -> list[float] | None:
    """Parse the MCU's "tw,ax,ay,az,gx,gy,gz" into 7 floats."""
    try:
        parts = payload.split(",") if isinstance(payload, str) else list(payload)
        if len(parts) != 7:
            return None
        return [float(x) for x in parts]
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_range(payload) -> float | None:
    """Parse the MCU's distance payload ("mm") into a float, dropping NaN."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    try:
        mm = float(payload)
    except (ValueError, TypeError):
        return None
    return mm if mm == mm else None
