from __future__ import annotations

from datetime import datetime
import ctypes
from pathlib import Path

import mss
import mss.tools

from app.desktop_agent.window_locator import DesktopWindow


class WindowScreenshotCapture:
    """Capture pixels inside a discovered window; it never interacts with the window."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def capture(self, window: DesktopWindow) -> Path:
        if int(ctypes.windll.user32.GetForegroundWindow()) != window.handle:
            raise RuntimeError("抖音窗口不在前台，已停止截图以避免误识别其他应用。")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"douyin_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
        path = self.output_dir / filename
        monitor = {
            "left": window.bounds.left,
            "top": window.bounds.top,
            "width": window.bounds.width,
            "height": window.bounds.height,
        }
        with mss.mss() as sct:
            image = sct.grab(monitor)
            mss.tools.to_png(image.rgb, image.size, output=str(path))
        return path
