#!/usr/bin/env python3
"""Phase 4 Bridge: DK USB serial → motion: → Rover NUS（設定・常駐・メトリクス）。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .config import BridgeConfig, load_config, resolve_config_path
from .metrics import BridgeMetrics
from .nus_central import NusCentral
from .protocol import CooldownGate, motion_to_rover_json, parse_dk_line
from .serial_bridge import SerialBridge

log = logging.getLogger("bridge")


def _install_stop_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass


async def _metrics_loop(
    metrics: BridgeMetrics, interval: float, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            log.info("%s", metrics.format_line())


async def _read_serial(
    serial: SerialBridge,
    handle_motion,
    verbose_json: bool,
) -> None:
    async for line in serial.lines():
        motion = parse_dk_line(line)
        if motion is None:
            if verbose_json and line.lstrip().startswith("{"):
                log.debug("ignore json: %s", line.strip()[:80])
            continue
        await handle_motion(motion)


async def run(args: argparse.Namespace, cfg: BridgeConfig) -> int:
    metrics = BridgeMetrics()
    gate = CooldownGate(cfg.cooldown_ms)
    serial = SerialBridge(args.port, args.baud, metrics=metrics)

    def on_nus_line(line: str) -> None:
        if args.echo_nus:
            try:
                serial.write_line(line.rstrip("\n"))
            except Exception as exc:
                log.debug("echo to DK failed: %s", exc)

    nus = NusCentral(
        name=None if args.address else args.name,
        address=args.address,
        scan_timeout=args.scan_timeout,
        retry_min=cfg.retry_min,
        retry_max=cfg.retry_max,
        on_line=on_nus_line if args.echo_nus else None,
        metrics=metrics,
    )

    stop = asyncio.Event()
    _install_stop_signals(stop)

    ble_task = asyncio.create_task(nus.maintain(), name="nus-maintain")
    metrics_task: asyncio.Task | None = None
    if args.metrics_interval > 0:
        metrics_task = asyncio.create_task(
            _metrics_loop(metrics, args.metrics_interval, stop),
            name="metrics",
        )

    async def handle_motion(motion: str) -> None:
        log.info("motion: %s", motion)
        cmd = motion_to_rover_json(motion)
        if cmd is None:
            metrics.record_unknown()
            log.info("unknown motion, skip: %r", motion)
            return
        if not gate.allow(motion):
            metrics.record_cooldown()
            log.info("cooldown, skip: %s", motion)
            return
        ok = await nus.write_line(cmd)
        if not ok:
            log.warning("command not sent: %s", cmd.strip())

    try:
        for _ in range(int(args.scan_timeout) + 5):
            if stop.is_set():
                break
            if nus.connected:
                break
            await asyncio.sleep(1.0)
        if not nus.connected and not stop.is_set():
            log.warning("BLE not ready yet; will send when connected")

        if args.inject and not stop.is_set():
            for name in args.inject:
                await handle_motion(name)
                await asyncio.sleep(0.3)
            if args.inject_only:
                return 0

        log.info("reading DK serial; SIGTERM/Ctrl+C to stop")
        read_task = asyncio.create_task(
            _read_serial(serial, handle_motion, args.verbose_json),
            name="serial",
        )
        stop_task = asyncio.create_task(stop.wait(), name="stop")
        _done, pending = await asyncio.wait(
            {read_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if read_task.done() and not read_task.cancelled():
            exc = read_task.exception()
            if exc is not None:
                raise exc
        log.info("stopped")
        return 0
    except asyncio.CancelledError:
        raise
    finally:
        stop.set()
        log.info("%s", metrics.format_line())
        for task in (metrics_task, ble_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        serial.close()


def _build_parser(cfg: BridgeConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="tenomi-bridge: DK USB serial to Rover NUS"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="TOML config path (default: cwd, then ~/.config/tenomi-bridge, then /etc)",
    )
    parser.add_argument("--port", default=cfg.serial_port)
    parser.add_argument("--baud", type=int, default=cfg.serial_baud)
    parser.add_argument("--name", default=cfg.ble_name or "micro:bit2_UART")
    parser.add_argument("--address", default=cfg.ble_address)
    parser.add_argument("--scan-timeout", type=float, default=cfg.scan_timeout)
    parser.add_argument(
        "--echo-nus",
        action="store_true",
        default=cfg.echo_nus,
        help="Forward Rover Notify lines back to DK serial",
    )
    parser.add_argument(
        "--verbose-json",
        action="store_true",
        default=cfg.verbose_json,
        help="Log ignored landmark JSON lines (debug)",
    )
    parser.add_argument(
        "--log-level",
        default=cfg.log_level,
        help="DEBUG / INFO / WARNING / ERROR (overridden by -v)",
    )
    parser.add_argument(
        "--metrics-interval",
        type=float,
        default=cfg.metrics_interval,
        help="Seconds between metrics log lines; 0 disables",
    )
    parser.add_argument(
        "--inject",
        nargs="+",
        default=[],
        metavar="MOTION",
        help="Send synthetic motion names after BLE connect (e.g. stop come_here)",
    )
    parser.add_argument(
        "--inject-only",
        action="store_true",
        help="Exit after --inject (do not read serial)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    pre_args, _ = pre.parse_known_args()
    path = resolve_config_path(pre_args.config)
    if pre_args.config and (path is None or not path.is_file()):
        raise SystemExit(f"config not found: {pre_args.config}")
    try:
        cfg = load_config(path)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    parser = _build_parser(cfg)
    args = parser.parse_args()
    if path is not None:
        log_boot = f"config {path}"
    else:
        log_boot = "config (built-in defaults)"

    level_name = "DEBUG" if args.verbose else str(args.log_level).upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log.info("%s; log_level=%s", log_boot, logging.getLevelName(level))

    try:
        raise SystemExit(asyncio.run(run(args, cfg)))
    except KeyboardInterrupt:
        log.info("stopped")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
