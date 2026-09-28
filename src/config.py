"""Load Bridge settings from TOML (code の外へ出す)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass
class BridgeConfig:
    serial_port: str = "/dev/ttyACM0"
    serial_baud: int = 115200
    ble_name: str | None = "micro:bit2_UART"
    ble_address: str | None = None
    scan_timeout: float = 15.0
    retry_min: float = 1.0
    retry_max: float = 30.0
    echo_nus: bool = False
    log_level: str = "INFO"
    metrics_interval: float = 60.0
    cooldown_ms: int = 1500
    verbose_json: bool = False


def default_config_path() -> Path:
    """CWD の config.toml（開発時・install.sh の WorkingDirectory）。"""
    return Path.cwd() / "config.toml"


def resolve_config_path(cli_path: str | None) -> Path | None:
    """CLI > TENOMI_BRIDGE_CONFIG > cwd / XDG / /etc（無ければ None）。"""
    if cli_path:
        return Path(cli_path).expanduser().resolve()
    env = os.environ.get("TENOMI_BRIDGE_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    for candidate in _search_paths():
        if candidate.is_file():
            return candidate.resolve()
    return None


def _search_paths() -> list[Path]:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg:
        user_cfg = Path(xdg) / "tenomi-bridge" / "config.toml"
    else:
        user_cfg = Path.home() / ".config" / "tenomi-bridge" / "config.toml"
    return [
        Path.cwd() / "config.toml",
        user_cfg,
        Path("/etc/tenomi-bridge/config.toml"),
    ]


def load_config(path: Path | None) -> BridgeConfig:
    cfg = BridgeConfig()
    if path is None:
        return cfg
    if not path.is_file():
        raise FileNotFoundError(f"config not found: {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    _apply_toml(cfg, data)
    return cfg


def _apply_toml(cfg: BridgeConfig, data: dict) -> None:
    serial = data.get("serial") or {}
    ble = data.get("ble") or {}
    bridge = data.get("bridge") or {}

    if "port" in serial:
        cfg.serial_port = str(serial["port"])
    if "baud" in serial:
        cfg.serial_baud = int(serial["baud"])

    if "name" in ble:
        cfg.ble_name = _opt_str(ble["name"])
    if "address" in ble:
        cfg.ble_address = _opt_str(ble["address"])
    if "scan_timeout" in ble:
        cfg.scan_timeout = float(ble["scan_timeout"])
    if "retry_min" in ble:
        cfg.retry_min = float(ble["retry_min"])
    if "retry_max" in ble:
        cfg.retry_max = float(ble["retry_max"])

    if "echo_nus" in bridge:
        cfg.echo_nus = bool(bridge["echo_nus"])
    if "log_level" in bridge:
        cfg.log_level = _log_level(str(bridge["log_level"]))
    if "metrics_interval" in bridge:
        cfg.metrics_interval = float(bridge["metrics_interval"])
    if "cooldown_ms" in bridge:
        cfg.cooldown_ms = int(bridge["cooldown_ms"])
    if "verbose_json" in bridge:
        cfg.verbose_json = bool(bridge["verbose_json"])


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _log_level(raw: str) -> str:
    key = raw.strip().upper()
    if key not in _LEVELS:
        return "INFO"
    return key
