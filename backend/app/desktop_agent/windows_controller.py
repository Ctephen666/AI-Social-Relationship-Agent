from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import time
from typing import Literal

from app.desktop_agent.window_locator import DesktopWindow, DouyinWindowLocator
from app.vision.schemas import OCRBlock


_ULONG_PTR = getattr(wintypes, "ULONG_PTR", wintypes.WPARAM)


class MessageDeliveryError(RuntimeError):
    """Raised when text or the send action cannot be delivered reliably."""


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    # INPUT's union must include its largest member. On 64-bit Windows
    # MOUSEINPUT is 32 bytes, making INPUT 40 bytes. A keyboard-only union is
    # only 24 bytes and causes SendInput to reject cbSize with ERROR_INVALID_PARAMETER.
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


class DouyinWindowsController:
    """Allow-listed Douyin controls with strict coordinate and focus checks."""

    SW_MAXIMIZE = 3
    SW_RESTORE = 9
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_WHEEL = 0x0800
    WHEEL_DELTA = 120
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    VK_RETURN = 0x0D
    VK_CONTROL = 0x11
    VK_SHIFT = 0x10
    VK_Q = 0x51

    def __init__(self, locator: DouyinWindowLocator | None = None) -> None:
        self.locator = locator or DouyinWindowLocator()
        self.user32 = ctypes.windll.user32

    def ensure_ready(self, timeout: float = 20.0) -> DesktopWindow:
        window = self.locator.find_optional()
        if window is None:
            self._launch_douyin()
            window = self.locator.wait_for_window(timeout)
        self.user32.ShowWindow(window.handle, self.SW_RESTORE)
        self.user32.ShowWindow(window.handle, self.SW_MAXIMIZE)
        for _ in range(4):
            self.user32.BringWindowToTop(window.handle)
            self.user32.SetForegroundWindow(window.handle)
            if int(self.user32.GetForegroundWindow()) == window.handle:
                break
            time.sleep(0.12)
        time.sleep(0.35)
        ready = self.locator.find()
        if int(self.user32.GetForegroundWindow()) != ready.handle:
            raise RuntimeError("Windows 未允许抖音切换到前台。请手动点击抖音窗口后重试，程序已拒绝截取其他应用。")
        return ready

    def open_message_panel(self, window: DesktopWindow, blocks: list[OCRBlock]) -> None:
        point = self._message_entry_point(window, blocks)
        self._click_allowed(window, point[0], point[1], action="message_entry")
        time.sleep(0.45)

    def scroll_chat_list(self, window: DesktopWindow, bounds: list[int], direction: Literal["up", "down"], steps: int = 7) -> None:
        if len(bounds) != 4:
            raise ValueError("聊天列表区域无效，已拒绝滚动。")
        left, top, right, bottom = bounds
        width, height = window.bounds.width, window.bounds.height
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("聊天列表越出抖音窗口，已拒绝滚动。")
        if right > int(width * 0.82) or top < int(height * 0.03):
            raise ValueError("目标不符合聊天列表安全区域，已拒绝滚动。")
        x = window.bounds.left + (left + right) // 2
        y = window.bounds.top + (top + bottom) // 2
        self.user32.SetCursorPos(x, y)
        delta = self.WHEEL_DELTA if direction == "up" else -self.WHEEL_DELTA
        for _ in range(max(1, min(steps, 80))):
            self.user32.mouse_event(self.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
            time.sleep(0.012)

    def click_chat_row(self, window: DesktopWindow, bounds: list[int]) -> None:
        """Open one visible conversation row after validating the list ROI."""
        if len(bounds) != 4:
            raise ValueError("聊天行区域无效。")
        left, top, right, bottom = bounds
        width, height = window.bounds.width, window.bounds.height
        safe_left, safe_top = int(width * 0.50), int(height * 0.08)
        safe_right, safe_bottom = int(width * 0.80), int(height * 0.90)
        if not (safe_left <= left < right <= safe_right and safe_top <= top < bottom <= safe_bottom):
            raise PermissionError("聊天行坐标未通过安全检查。")
        self._assert_foreground(window)
        self._click(window.bounds.left + (left + right) // 2, window.bounds.top + (top + bottom) // 2)

    def send_message(self, window: DesktopWindow, editor_bounds: list[int], message: str) -> None:
        """Type into the bottom editor and click Douyin's right-side arrow."""
        cleaned = " ".join(message.replace("\r", " ").replace("\n", " ").split()).strip()
        if not cleaned or len(cleaned) > 120:
            raise ValueError("消息必须为 1-120 个字符，且不能包含换行。")
        if len(editor_bounds) != 4:
            raise ValueError("消息输入框区域无效。")
        left, top, right, bottom = editor_bounds
        width, height = window.bounds.width, window.bounds.height
        if not (
            int(width * 0.68) <= left < right <= width
            and int(height * 0.48) <= top < bottom <= int(height * 0.98)
        ):
            raise PermissionError("消息输入框坐标未通过安全检查。")
        self._assert_foreground(window)
        self._click(window.bounds.left + (left + right) // 2, window.bounds.top + (top + bottom) // 2)
        time.sleep(0.04)
        self._send_unicode(cleaned)
        time.sleep(0.06)
        arrow_x, arrow_y = self.message_send_button_point(window)
        self._assert_foreground(window)
        self._click(arrow_x, arrow_y)

    @staticmethod
    def default_message_editor_bounds(window: DesktopWindow) -> list[int]:
        """Return the stable bottom-right editor ROI used by current Douyin."""
        width, height = window.bounds.width, window.bounds.height
        return [int(width * 0.70), int(height * 0.64), int(width * 0.925), int(height * 0.76)]

    @staticmethod
    def message_send_button_point(window: DesktopWindow) -> tuple[int, int]:
        """Return the allow-listed center of Douyin's message send arrow."""
        width, height = window.bounds.width, window.bounds.height
        return window.bounds.left + int(width * 0.958), window.bounds.top + int(height * 0.70)

    def emergency_stop_requested(self) -> bool:
        """Ctrl+Shift+Q is an always-available stop chord during batch send."""
        return all(
            self.user32.GetAsyncKeyState(key) & 0x8000
            for key in (self.VK_CONTROL, self.VK_SHIFT, self.VK_Q)
        )

    def _message_entry_point(self, window: DesktopWindow, blocks: list[OCRBlock]) -> tuple[int, int]:
        width, height = window.bounds.width, window.bounds.height
        for block in blocks:
            text = block.text.replace(" ", "").strip()
            if text != "消息" or not block.box:
                continue
            xs = [point[0] for point in block.box]
            ys = [point[1] for point in block.box]
            local_x, local_y = sum(xs) // len(xs), sum(ys) // len(ys)
            if local_y <= int(height * 0.16) and local_x >= int(width * 0.55):
                return window.bounds.left + local_x, window.bounds.top + local_y
        return window.bounds.left + int(width * 0.84), window.bounds.top + int(height * 0.035)

    def _click_allowed(self, window: DesktopWindow, screen_x: int, screen_y: int, action: Literal["message_entry"]) -> None:
        if action != "message_entry":
            raise PermissionError("未列入白名单的桌面动作。")
        local_x = screen_x - window.bounds.left
        local_y = screen_y - window.bounds.top
        if not (int(window.bounds.width * 0.55) <= local_x <= window.bounds.width and 0 <= local_y <= int(window.bounds.height * 0.16)):
            raise PermissionError("消息入口坐标未通过安全检查，已拒绝点击。")
        self._click(screen_x, screen_y)

    def _assert_foreground(self, window: DesktopWindow) -> None:
        if int(self.user32.GetForegroundWindow()) != window.handle:
            raise RuntimeError("抖音不在前台，已停止发送以避免操作其他应用。")

    def _click(self, screen_x: int, screen_y: int) -> None:
        self.user32.SetCursorPos(screen_x, screen_y)
        self.user32.mouse_event(self.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.user32.mouse_event(self.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _send_unicode(self, text: str) -> None:
        units = [int.from_bytes(text.encode("utf-16-le")[index:index + 2], "little") for index in range(0, len(text.encode("utf-16-le")), 2)]
        events = (_INPUT * (len(units) * 2))()
        for index, unit in enumerate(units):
            events[index * 2].type = self.INPUT_KEYBOARD
            events[index * 2].ki = _KEYBDINPUT(0, unit, self.KEYEVENTF_UNICODE, 0, 0)
            events[index * 2 + 1].type = self.INPUT_KEYBOARD
            events[index * 2 + 1].ki = _KEYBDINPUT(0, unit, self.KEYEVENTF_UNICODE | self.KEYEVENTF_KEYUP, 0, 0)
        send_input = self.user32.SendInput
        send_input.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
        send_input.restype = wintypes.UINT
        sent = send_input(len(events), events, ctypes.sizeof(_INPUT))
        if sent != len(events):
            error_code = int(ctypes.windll.kernel32.GetLastError())
            raise MessageDeliveryError(
                f"Windows 未能完整输入消息（{sent}/{len(events)}，错误码 {error_code}），已停止整个任务。"
            )

    def _launch_douyin(self) -> None:
        shortcuts = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "抖音.lnk",
            Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "抖音.lnk",
        ]
        for shortcut in shortcuts:
            if shortcut.is_file():
                os.startfile(shortcut)  # type: ignore[attr-defined]
                return
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Douyin" / "Douyin.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Douyin" / "Douyin.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                os.startfile(candidate)  # type: ignore[attr-defined]
                return
        raise RuntimeError("无法定位抖音启动入口，请重新安装 Windows 抖音客户端或创建开始菜单快捷方式。")
