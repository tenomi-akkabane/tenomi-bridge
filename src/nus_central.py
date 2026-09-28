"""BLE NUS Central for Rover (BlueZ + Bleak)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from .metrics import BridgeMetrics

log = logging.getLogger(__name__)

NUS_SERVICE = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_WRITE_STD = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_NOTIFY_STD = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"


class NusCentral:
    def __init__(
        self,
        *,
        name: str | None = "micro:bit2_UART",
        address: str | None = None,
        scan_timeout: float = 12.0,
        retry_min: float = 1.0,
        retry_max: float = 30.0,
        on_line: Callable[[str], None] | None = None,
        metrics: BridgeMetrics | None = None,
    ) -> None:
        self.name = name
        self.address = address
        self.scan_timeout = scan_timeout
        self.retry_min = retry_min
        self.retry_max = retry_max
        self.on_line = on_line
        self.metrics = metrics
        self._client: BleakClient | None = None
        self._write_uuid: str | None = None
        self._notify_uuid: str | None = None
        self._notify_buf = bytearray()
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    async def connect(self) -> None:
        address = self.address
        if not address:
            if not self.name:
                raise ValueError("name or address required")
            log.info("scanning for %r ...", self.name)
            device = await BleakScanner.find_device_by_name(
                self.name, timeout=self.scan_timeout
            )
            if device is None:
                if self.metrics:
                    self.metrics.record_scan_fail()
                raise BleakError(f"device not found: {self.name!r}")
            address = device.address
            log.info("found %r [%s]", device.name, address)

        client = BleakClient(address, timeout=20.0)
        await client.connect()
        write_uuid, notify_uuid = self._resolve_uuids(client)
        await client.start_notify(notify_uuid, self._on_notify)
        self._client = client
        self._write_uuid = write_uuid
        self._notify_uuid = notify_uuid
        if self.metrics:
            self.metrics.record_connect()
        log.info(
            "NUS connected write=%s notify=%s", write_uuid, notify_uuid
        )

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        # Call even if Bleak already reports disconnected (link lost).
        if self.metrics:
            self.metrics.record_disconnect()
        if client is None:
            return
        try:
            if client.is_connected and self._notify_uuid:
                await client.stop_notify(self._notify_uuid)
        except Exception as exc:
            log.debug("stop_notify: %s", exc)
        try:
            await client.disconnect()
        except Exception as exc:
            log.debug("disconnect: %s", exc)
        log.info("NUS disconnected")

    async def write_line(self, text: str) -> bool:
        """Write one Rover command. Returns False if not connected."""
        async with self._lock:
            if not self.connected or not self._write_uuid or not self._client:
                log.warning("drop command (BLE down): %r", text.strip())
                if self.metrics:
                    self.metrics.record_write_drop()
                return False
            payload = text.encode("utf-8")
            try:
                await self._client.write_gatt_char(
                    self._write_uuid, payload, response=True
                )
            except Exception as exc:
                log.error("NUS write failed: %s", exc)
                if self.metrics:
                    self.metrics.record_write_drop()
                return False
            log.info("NUS tx %r", text.strip())
            if self.metrics:
                self.metrics.record_write_ok()
            return True

    async def maintain(self) -> None:
        """Keep connection alive; reconnect with backoff on drop."""
        delay = self.retry_min
        while True:
            try:
                if not self.connected:
                    await self.connect()
                    delay = self.retry_min
                await asyncio.sleep(1.0)
                if self._client and not self._client.is_connected:
                    raise BleakError("link lost")
            except asyncio.CancelledError:
                await self.disconnect()
                raise
            except Exception as exc:
                log.warning("NUS maintain: %s; retry in %.1fs", exc, delay)
                try:
                    await self.disconnect()
                except Exception:
                    pass
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, self.retry_max)

    def _resolve_uuids(self, client: BleakClient) -> tuple[str, str]:
        write_uuid: str | None = None
        notify_uuid: str | None = None
        for service in client.services:
            if service.uuid.lower() != NUS_SERVICE.lower():
                continue
            for char in service.characteristics:
                props = set(char.properties)
                if "notify" in props or "indicate" in props:
                    notify_uuid = char.uuid
                if "write" in props or "write-without-response" in props:
                    write_uuid = char.uuid
        if write_uuid and notify_uuid:
            return write_uuid, notify_uuid
        return NUS_WRITE_STD, NUS_NOTIFY_STD

    def _on_notify(
        self, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        self._notify_buf.extend(data)
        while True:
            idx = self._notify_buf.find(b"\n")
            if idx < 0:
                break
            raw = bytes(self._notify_buf[: idx + 1])
            del self._notify_buf[: idx + 1]
            text = raw.decode("utf-8", errors="replace")
            log.info("NUS rx %r", text.strip())
            if self.on_line:
                self.on_line(text)
