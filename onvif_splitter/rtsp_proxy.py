from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def _handle_connection(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    remote_host: str,
    remote_port: int,
):
    peer = client_writer.get_extra_info("peername")
    log.debug("RTSP proxy connection from %s", peer)
    try:
        remote_reader, remote_writer = await asyncio.open_connection(
            remote_host, remote_port
        )
    except Exception:
        log.warning("Failed to connect to RTSP backend %s:%d", remote_host, remote_port)
        client_writer.close()
        return

    await asyncio.gather(
        _pipe(client_reader, remote_writer),
        _pipe(remote_reader, client_writer),
    )
    log.debug("RTSP proxy connection closed from %s", peer)


async def start_rtsp_proxy(
    local_host: str,
    local_port: int,
    remote_host: str,
    remote_port: int,
) -> asyncio.Server:
    server = await asyncio.start_server(
        lambda r, w: _handle_connection(r, w, remote_host, remote_port),
        local_host,
        local_port,
    )
    log.info(
        "RTSP proxy %s:%d -> %s:%d",
        local_host,
        local_port,
        remote_host,
        remote_port,
    )
    return server
