"""UDP discovery beacon — the wand finds the laptop with zero typed commands.

On a phone-hosted hotspot the laptop's IP changes every session, so the board
can't hardcode it. Instead the server announces itself two ways on one UDP
port (WM_DISCOVERY_PORT, default 41234):

  * every 2s, a broadcast datagram:  {"phoneharmonic": 1, "ws": "ws://ip:8080/ws"}
  * any datagram containing b"maestro?" gets the same JSON unicast back to the
    sender (covers hotspots that gate broadcast in one direction).

The board (firmware/uno_q/wand/python/wand_link.py) listens for either. Set
WM_DISCOVERY_OFF=1 to disable (e.g. multiple servers on one machine).
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket

log = logging.getLogger("disco")

BEACON_INTERVAL_S = 2.0


class _Responder(asyncio.DatagramProtocol):
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport) -> None:  # type: ignore[override]
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
        if b"maestro?" in data and self.transport is not None:
            self.transport.sendto(self._payload, addr)


async def start_beacon(ws_url: str, port: int) -> None:
    """Fire-and-forget: binds the port, answers probes, broadcasts forever.
    Failure to bind (another server already announcing) is a warning, not a
    crash — the show must go on without discovery."""
    payload = json.dumps({"phoneharmonic": 1, "ws": ws_url}).encode()
    loop = asyncio.get_running_loop()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
        sock.setblocking(False)
        transport, _proto = await loop.create_datagram_endpoint(
            lambda: _Responder(payload), sock=sock)
    except OSError as e:
        log.warning("discovery beacon disabled (:%d busy? %s)", port, e)
        return

    async def blast() -> None:
        while True:
            try:
                transport.sendto(payload, ("255.255.255.255", port))
                transport.sendto(payload, ("<broadcast>", port))
            except OSError:
                pass                      # interface down mid-broadcast: retry next tick
            await asyncio.sleep(BEACON_INTERVAL_S)

    asyncio.get_running_loop().create_task(blast())
    log.info("discovery beacon on udp:%d -> %s", port, ws_url)
