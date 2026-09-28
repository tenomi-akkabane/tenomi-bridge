"""Connection and command counters for ops logs."""

from __future__ import annotations

import threading
import time


class BridgeMetrics:
    """Process-lifetime counters. Safe to bump from Bleak notify threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self.connected = False
        self.connects = 0
        self.disconnects = 0
        self.scan_fail = 0
        self.write_ok = 0
        self.write_drop = 0
        self.cooldown_skip = 0
        self.unknown_motion = 0
        self.serial_reopen = 0
        self._connected_since: float | None = None

    def record_connect(self) -> None:
        with self._lock:
            self.connected = True
            self.connects += 1
            self._connected_since = time.monotonic()

    def record_disconnect(self) -> None:
        with self._lock:
            was = self.connected
            self.connected = False
            self._connected_since = None
            if was:
                self.disconnects += 1

    def record_scan_fail(self) -> None:
        with self._lock:
            self.scan_fail += 1

    def record_write_ok(self) -> None:
        with self._lock:
            self.write_ok += 1

    def record_write_drop(self) -> None:
        with self._lock:
            self.write_drop += 1

    def record_cooldown(self) -> None:
        with self._lock:
            self.cooldown_skip += 1

    def record_unknown(self) -> None:
        with self._lock:
            self.unknown_motion += 1

    def record_serial_reopen(self) -> None:
        with self._lock:
            self.serial_reopen += 1

    def format_line(self) -> str:
        with self._lock:
            uptime = int(time.monotonic() - self._started)
            link_s = (
                int(time.monotonic() - self._connected_since)
                if self.connected and self._connected_since is not None
                else 0
            )
            ble = "up" if self.connected else "down"
            return (
                "metrics"
                f" ble={ble}"
                f" link_s={link_s}"
                f" uptime_s={uptime}"
                f" connects={self.connects}"
                f" disconnects={self.disconnects}"
                f" scan_fail={self.scan_fail}"
                f" write_ok={self.write_ok}"
                f" write_drop={self.write_drop}"
                f" cooldown_skip={self.cooldown_skip}"
                f" unknown={self.unknown_motion}"
                f" serial_reopen={self.serial_reopen}"
            )
