"""Async USB serial reader for DK (ST-Link VCP)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

import serial
from serial import SerialException

from .metrics import BridgeMetrics

log = logging.getLogger(__name__)


class SerialBridge:
    def __init__(
        self,
        port: str,
        baud: int = 115200,
        *,
        read_timeout: float = 0.2,
        metrics: BridgeMetrics | None = None,
    ) -> None:
        self.port = port
        self.baud = baud
        self.read_timeout = read_timeout
        self.metrics = metrics
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.read_timeout,
        )
        log.info("serial open %s @ %d", self.port, self.baud)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            log.info("serial closed")
        self._ser = None

    def write_line(self, text: str) -> None:
        if not self._ser or not self._ser.is_open:
            raise SerialException("serial not open")
        data = text if text.endswith("\n") else text + "\n"
        self._ser.write(data.encode("utf-8"))

    async def lines(self) -> AsyncIterator[str]:
        """Yield decoded lines until cancelled. Reopens on error with backoff."""
        buf = bytearray()
        while True:
            try:
                if self._ser is None or not self._ser.is_open:
                    await asyncio.to_thread(self.open)
                chunk = await asyncio.to_thread(self._read_chunk)
                if not chunk:
                    await asyncio.sleep(0.01)
                    continue
                buf.extend(chunk)
                while True:
                    idx = buf.find(b"\n")
                    if idx < 0:
                        break
                    raw = bytes(buf[: idx + 1])
                    del buf[: idx + 1]
                    yield raw.decode("utf-8", errors="replace")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("serial read error: %s; reopen in 1s", exc)
                if self.metrics:
                    self.metrics.record_serial_reopen()
                try:
                    await asyncio.to_thread(self.close)
                except Exception:
                    pass
                await asyncio.sleep(1.0)

    def _read_chunk(self) -> bytes:
        assert self._ser is not None
        waiting = self._ser.in_waiting
        return self._ser.read(waiting or 1)
