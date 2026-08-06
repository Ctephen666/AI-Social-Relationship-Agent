from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
import time


def _enable_dpi_awareness() -> None:
    """Keep Win32 window/mouse coordinates aligned with MSS physical pixels."""
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


_enable_dpi_awareness()


@dataclass(frozen=True)
class WindowBounds:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class DesktopWindow:
    handle: int
    title: str
    bounds: WindowBounds
    process_name: str = ""


class DouyinWindowLocator:
    """Find a visible Douyin top-level window without focusing or controlling it."""

    def __init__(self, title_hints: tuple[str, ...] = ("抖音", "Douyin")) -> None:
        self.title_hints = tuple(hint.casefold() for hint in title_hints)
        self.user32 = ctypes.windll.user32

    def find(self) -> DesktopWindow:
        window = self.find_optional()
        if window is None:
            raise RuntimeError("未找到可见的抖音客户端窗口。")
        return window

    def find_optional(self) -> DesktopWindow | None:
        matches: list[DesktopWindow] = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def enum_callback(hwnd: int, _: int) -> bool:
            if not self.user32.IsWindowVisible(hwnd):
                return True
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            title = title_buffer.value.strip()
            if title.casefold() not in self.title_hints:
                return True
            process_name = self._process_name(hwnd)
            if process_name != "douyin.exe":
                return True
            rect = wintypes.RECT()
            if not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width, height = rect.right - rect.left, rect.bottom - rect.top
            # A minimized Windows window is represented off-screen as roughly
            # 158x26. Process/title checks above are strong enough to retain it;
            # the controller restores/maximizes it before any capture.
            if width > 0 and height > 0:
                matches.append(DesktopWindow(int(hwnd), title, WindowBounds(rect.left, rect.top, width, height), process_name))
            return True

        self.user32.EnumWindows(enum_callback, 0)
        if not matches:
            return None
        return max(matches, key=lambda item: item.bounds.width * item.bounds.height)

    def wait_for_window(self, timeout: float = 20.0) -> DesktopWindow:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            window = self.find_optional()
            if window is not None:
                return window
            time.sleep(0.5)
        raise RuntimeError("启动抖音超时，请确认 Windows 抖音客户端已经安装。")

    def _process_name(self, hwnd: int) -> str:
        process_id = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id.value)
        if not process:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not ctypes.windll.kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return ""
            return Path(buffer.value).name.casefold()
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
