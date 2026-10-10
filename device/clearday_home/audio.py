"""Audio output: a synthesized chime and downloaded announcement/briefing audio.

Plays through the USB sound card with whatever player the board has
(ffplay, mpg123, or aplay for WAV). If none works, it logs and the team
plays the audio from a laptop instead (hardware doc, Fallbacks).
"""

from __future__ import annotations

import logging
import math
import shutil
import struct
import subprocess  # noqa: S404 - fixed argv lists, no shell
import tempfile
import threading
import wave
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("clearday_home.audio")


def write_chime(path: Path, rate: int = 22050) -> Path:
    """Two soft rising sine tones with a fade, written as 16-bit mono WAV."""
    frames = bytearray()
    for freq, seconds in ((880.0, 0.18), (1318.5, 0.32)):
        n = int(rate * seconds)
        for i in range(n):
            envelope = min(1.0, i / 200) * (1 - i / n)
            sample = int(9000 * envelope * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def _player_argv(path: Path) -> list[str] | None:
    if shutil.which("ffplay"):
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
    if path.suffix == ".mp3" and shutil.which("mpg123"):
        return ["mpg123", "-q", str(path)]
    if path.suffix == ".wav" and shutil.which("aplay"):
        return ["aplay", "-q", str(path)]
    return None


class Audio:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._chime: Path | None = None
        self._lock = threading.Lock()  # one clip at a time

    def chime(self) -> None:
        if self._chime is None:
            self._chime = write_chime(Path(tempfile.gettempdir()) / "clearday-chime.wav")
        self.play(self._chime, delete=False)

    def play(self, path: Path, delete: bool = True, on_done: Callable[[], None] | None = None) -> None:
        """Play in the background; `on_done` runs when playback ends (or fails)."""
        threading.Thread(target=self._play, args=(path, delete, on_done), name="audio", daemon=True).start()

    def _play(self, path: Path, delete: bool, on_done: Callable[[], None] | None) -> None:
        try:
            argv = _player_argv(path) if self.enabled else None
            if argv is None:
                log.info("audio playback unavailable; play it from the laptop (%s)", path.suffix)
                return
            with self._lock:
                subprocess.run(argv, check=False, timeout=120)  # noqa: S603 - fixed player argv
        except Exception as exc:  # noqa: BLE001 - audio is a Should, never fatal
            log.warning("audio playback failed (%s)", type(exc).__name__)
        finally:
            if delete:
                path.unlink(missing_ok=True)
            if on_done is not None:
                on_done()
