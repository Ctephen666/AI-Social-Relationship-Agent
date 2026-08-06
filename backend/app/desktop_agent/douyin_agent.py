from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.desktop_agent.screenshot import WindowScreenshotCapture
from app.desktop_agent.window_locator import DesktopWindow, DouyinWindowLocator


@dataclass(frozen=True)
class DesktopCaptureResult:
    window: DesktopWindow
    image_path: Path


class DouyinDesktopVisionAgent:
    """Read-only capture stage of the Douyin spark scanning pipeline."""

    def __init__(self, screenshot_dir: Path, locator: DouyinWindowLocator | None = None) -> None:
        self.locator = locator or DouyinWindowLocator()
        self.capture_service = WindowScreenshotCapture(screenshot_dir)

    def capture(self) -> DesktopCaptureResult:
        window = self.locator.find()
        return DesktopCaptureResult(window=window, image_path=self.capture_service.capture(window))
