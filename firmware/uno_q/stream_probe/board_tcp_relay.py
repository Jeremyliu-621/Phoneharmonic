"""Small board-host TCP relay for IPv6-only hotspot deployments.

Arduino App containers currently have an IPv4 Docker network even when the UNO
Q host has working IPv6.  The container connects to the host's WiFi IPv4
address; this process forwards that stream to the laptop's IPv6 server.
"""
from __future__ import annotations

import argparse
import asyncio
import logging


log = logging.getLogger("phoneharmonic_relay")


async def copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except OSError as exc:
        log.warning("target connection failed for %s: %s", peer, exc)
        writer.close()
        await writer.wait_closed()
        return

    log.info("relaying %s to [%s]:%d", peer, target_host, target_port)
    upstream = asyncio.create_task(copy_stream(reader, target_writer))
    downstream = asyncio.create_task(copy_stream(target_reader, writer))
    await asyncio.wait((upstream, downstream), return_when=asyncio.FIRST_COMPLETED)
    upstream.cancel()
    downstream.cancel()
    await asyncio.gather(upstream, downstream, return_exceptions=True)


async def run(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: handle_client(reader, writer, target_host, target_port),
        listen_host,
        listen_port,
    )
    addresses = ", ".join(str(sock.getsockname()) for sock in server.sockets or ())
    log.info("listening on %s; forwarding to [%s]:%d", addresses, target_host, target_port)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", required=True, type=int)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", required=True, type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(run(args.listen_host, args.listen_port, args.target_host, args.target_port))


if __name__ == "__main__":
    main()
