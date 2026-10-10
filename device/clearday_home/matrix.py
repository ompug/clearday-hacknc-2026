"""Link to the MCU sketch that draws the LED matrix.

Commands are the plain strings from the hardware doc's bridge protocol:
`matrix:sun`, `matrix:cloud`, `matrix:count:3`, `matrix:dash` (plus
`matrix:mic` for the Listening stretch state). The sketch registers one
Bridge function, "matrix", that takes the whole string.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

log = logging.getLogger("clearday_home.matrix")

COMMAND_RE = re.compile(r"^matrix:(sun|cloud|dash|mic|count:\d{1,2})$")


class MatrixLink(Protocol):
    def send(self, command: str) -> None: ...


def validate(command: str) -> str:
    if not COMMAND_RE.match(command):
        raise ValueError(f"not a matrix command: {command!r}")
    return command


class LogMatrix:
    """Logs commands; used off-board and in tests."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, command: str) -> None:
        self.sent.append(validate(command))
        log.info("matrix %s", command)


class BridgeMatrix:
    """Sends commands to the sketch over the UNO Q's Arduino Router Bridge.

    `arduino.app_utils` is provided by Arduino App Lab on the board. If the
    import fails we log and fall back to LogMatrix behaviour.
    """

    def __init__(self) -> None:
        from arduino.app_utils import Bridge  # type: ignore[import-not-found]  # board only

        self._bridge = Bridge

    def send(self, command: str) -> None:
        validate(command)
        try:
            self._bridge.call("matrix", command)
        except Exception as exc:  # noqa: BLE001 - a matrix hiccup must not stop the bulb or audio
            log.warning("bridge call failed (%s)", type(exc).__name__)


def make_matrix(kind: str) -> MatrixLink:
    if kind.lower() == "bridge":
        try:
            return BridgeMatrix()
        except ImportError:
            log.warning("arduino.app_utils not available; logging matrix commands instead")
    return LogMatrix()
