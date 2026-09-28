"""DK motion: → Rover JSON（protocol.md v1）."""

from __future__ import annotations

import time

SPEED = 50
TURN_OUTER = 50
TURN_INNER = 25
DURATION = 2
COOLDOWN_MS = 1500

_MOTION_PREFIX = "motion:"


def motion_to_rover_json(name: str) -> str | None:
    """Map motion name to Rover command line (with trailing newline)."""
    key = name.strip().lower()
    if key == "stop":
        return '{"type":"stop"}\n'
    if key == "come_here":
        return (
            f'{{"type":"drive","left":{SPEED},"right":{SPEED},'
            f'"duration":{DURATION}}}\n'
        )
    if key == "go_away":
        return (
            f'{{"type":"drive","left":{-SPEED},"right":{-SPEED},'
            f'"duration":{DURATION}}}\n'
        )
    if key == "right":
        return (
            f'{{"type":"drive","left":{TURN_OUTER},"right":{TURN_INNER},'
            f'"duration":{DURATION}}}\n'
        )
    if key == "left":
        return (
            f'{{"type":"drive","left":{TURN_INNER},"right":{TURN_OUTER},'
            f'"duration":{DURATION}}}\n'
        )
    return None


def parse_dk_line(line: str) -> str | None:
    """
    Return motion name if line is `motion: <name>`, else None.
    Landmark JSON and other lines are ignored.
    """
    s = line.strip()
    if not s.lower().startswith(_MOTION_PREFIX):
        return None
    name = s[len(_MOTION_PREFIX) :].strip()
    return name or None


class CooldownGate:
    """1.5s cooldown; stop always passes (protocol.md §5)."""

    def __init__(self, cooldown_ms: int = COOLDOWN_MS) -> None:
        self.cooldown_ms = cooldown_ms
        self._last_send_monotonic: float | None = None

    def allow(self, motion_name: str) -> bool:
        is_stop = motion_name.strip().lower() == "stop"
        now = time.monotonic()
        if is_stop:
            self._last_send_monotonic = now
            return True
        if self._last_send_monotonic is None:
            self._last_send_monotonic = now
            return True
        elapsed_ms = (now - self._last_send_monotonic) * 1000.0
        if elapsed_ms < self.cooldown_ms:
            return False
        self._last_send_monotonic = now
        return True
