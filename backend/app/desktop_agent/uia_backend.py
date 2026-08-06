from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Any

from app.desktop_agent.window_locator import DesktopWindow
from app.vision.parser import TIME_PATTERN
from app.vision.schemas import StructuredChatObject


_IGNORED_TEXTS = {
    "搜索", "消息", "通知", "投稿", "收起会话", "发送消息", "朋友", "关注",
    "直播", "放映厅", "短剧", "小游戏", "精选", "推荐", "我的", "全部",
}
_SPARK_SUFFIX = re.compile(r"\s*[🔥💧✨]\s*(?:\d+|重燃中\s*\d+/\d+)?\s*$")
_UNREAD = re.compile(r"^\d{1,3}$")
_CHAT_TIME = re.compile(
    r"^(?:(?:刚刚|今天|昨天|前天)(?:\s+\d{1,2}:\d{2})?|周[一二三四五六日天]|"
    r"\d+\s*(?:分钟|小时|天)前|\d{1,2}:\d{2}|\d{1,2}[/-]\d{1,2}|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2})$"
)


@dataclass(frozen=True)
class AccessibleElement:
    """Small, testable projection of a UI Automation element."""

    name: str
    control_type: str
    bounds: tuple[int, int, int, int]


@dataclass(frozen=True)
class UIAChatRow:
    contact: StructuredChatObject
    row_bounds: list[int]
    spark_bounds: list[int]


@dataclass(frozen=True)
class UIAChatSnapshot:
    panel_open: bool
    chat_list_bounds: list[int]
    rows: list[UIAChatRow]
    elapsed_ms: int


class DouyinUIABackend:
    """Fast Windows UIA reader; it never opens a conversation or sends input."""

    def __init__(self, timeout_seconds: float = 1.5) -> None:
        self.timeout_seconds = max(0.2, timeout_seconds)
        self._unavailable = False

    def inspect(self, window: DesktopWindow) -> UIAChatSnapshot:
        started = time.perf_counter()
        if self._unavailable:
            return UIAChatSnapshot(False, self.default_chat_bounds(window.bounds.width, window.bounds.height), [], 0)
        elements = self._read_elements(window)
        if not elements:
            # Chromium builds without an accessibility tree can take seconds to
            # answer once. Remember the negative capability for the scan process.
            self._unavailable = True
        local = [self._to_local(item, window) for item in elements]
        local = [item for item in local if item is not None]
        rows, bounds = self.parse_chat_rows(local, window.bounds.width, window.bounds.height)
        names = {item.name.replace(" ", "") for item in local}
        panel_open = bool(rows) or "收起会话" in names or (
            "搜索" in names and sum(self._inside(item, bounds) for item in local) >= 3
        )
        return UIAChatSnapshot(
            panel_open=panel_open,
            chat_list_bounds=bounds,
            rows=rows,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    def click_message_entry(self, window: DesktopWindow) -> bool:
        """Click only an accessible element named 消息 inside the safe top bar."""
        if self._unavailable:
            return False
        for wrapper in self._read_wrappers(window):
            name = str(getattr(wrapper.element_info, "name", "")).replace(" ", "").strip()
            if name != "消息":
                continue
            rect = wrapper.rectangle()
            center_x = (rect.left + rect.right) // 2
            center_y = (rect.top + rect.bottom) // 2
            local_x = center_x - window.bounds.left
            local_y = center_y - window.bounds.top
            if local_x >= int(window.bounds.width * 0.55) and local_y <= int(window.bounds.height * 0.16):
                wrapper.click_input()
                return True
        return False

    def conversation_matches(self, window: DesktopWindow, nickname: str) -> bool:
        """Verify the selected conversation header before any external write."""
        expected = self._identity(nickname)
        if not expected:
            return False
        for item in (self._to_local(value, window) for value in self._read_elements(window)):
            if item is None:
                continue
            left, top, right, bottom = item.bounds
            if left < int(window.bounds.width * 0.68) or top > int(window.bounds.height * 0.20):
                continue
            actual = self._identity(item.name)
            prefix = min(len(expected), len(actual))
            if prefix >= 2 and (actual.startswith(expected[:prefix]) or expected.startswith(actual[:prefix])):
                return True
        return False

    def message_editor_bounds(self, window: DesktopWindow) -> list[int] | None:
        """Locate the visible message editor in the lower-right conversation pane."""
        candidates: list[AccessibleElement] = []
        for item in (self._to_local(value, window) for value in self._read_elements(window)):
            if item is None:
                continue
            left, top, right, bottom = item.bounds
            name = item.name.replace(" ", "").strip()
            is_editor = item.control_type.casefold() in {"edit", "document"} or name == "发送消息"
            if (
                is_editor
                and left >= int(window.bounds.width * 0.68)
                and top >= int(window.bounds.height * 0.48)
                and right > left
                and bottom > top
            ):
                candidates.append(item)
        if not candidates:
            return None
        best = max(candidates, key=lambda item: (item.bounds[2] - item.bounds[0]) * (item.bounds[3] - item.bounds[1]))
        return list(best.bounds)

    def verified_message_editor(self, window: DesktopWindow, nickname: str) -> list[int] | None:
        """Verify conversation header and editor with one accessibility-tree read."""
        expected = self._identity(nickname)
        if not expected:
            return None
        width, height = window.bounds.width, window.bounds.height
        header_matches = False
        editors: list[AccessibleElement] = []
        for item in (self._to_local(value, window) for value in self._read_elements(window)):
            if item is None:
                continue
            left, top, right, bottom = item.bounds
            actual = self._identity(item.name)
            prefix = min(len(expected), len(actual))
            if (
                left >= int(width * 0.68)
                and top <= int(height * 0.20)
                and prefix >= 2
                and (actual.startswith(expected[:prefix]) or expected.startswith(actual[:prefix]))
            ):
                header_matches = True
            name = item.name.replace(" ", "").strip()
            is_editor = item.control_type.casefold() in {"edit", "document"} or name == "发送消息"
            if (
                is_editor
                and left >= int(width * 0.68)
                and top >= int(height * 0.48)
                and right > left
                and bottom > top
            ):
                editors.append(item)
        if not header_matches or not editors:
            return None
        best = max(editors, key=lambda item: (item.bounds[2] - item.bounds[0]) * (item.bounds[3] - item.bounds[1]))
        return list(best.bounds)

    def _read_elements(self, window: DesktopWindow) -> list[AccessibleElement]:
        output: list[AccessibleElement] = []
        for wrapper in self._read_wrappers(window):
            try:
                info = wrapper.element_info
                name = str(getattr(info, "name", "") or "").strip()
                if not name:
                    continue
                rect = wrapper.rectangle()
                if rect.right <= rect.left or rect.bottom <= rect.top:
                    continue
                output.append(AccessibleElement(name, str(getattr(info, "control_type", "")), (rect.left, rect.top, rect.right, rect.bottom)))
            except Exception:
                continue
        return output

    def _read_wrappers(self, window: DesktopWindow) -> list[Any]:
        try:
            from pywinauto import Desktop

            root = Desktop(backend="uia").window(handle=window.handle)
            root.wait("exists visible", timeout=self.timeout_seconds, retry_interval=0.1)
            return list(root.descendants())
        except Exception:
            return []

    @classmethod
    def parse_chat_rows(
        cls,
        elements: list[AccessibleElement],
        width: int,
        height: int,
    ) -> tuple[list[UIAChatRow], list[int]]:
        left, top, right, bottom = cls.default_chat_bounds(width, height)
        candidates = [item for item in elements if cls._inside(item, [left, top, right, bottom])]
        row_height = max(64, int(height * 0.066))
        anchored = cls._parse_time_anchored_rows(candidates, left, top, right, bottom, row_height, width)
        if anchored:
            return anchored, [left, top, right, bottom]
        grouped: dict[int, list[AccessibleElement]] = {}
        for item in candidates:
            center_y = (item.bounds[1] + item.bounds[3]) / 2
            grouped.setdefault(max(0, int((center_y - top) // row_height)), []).append(item)

        rows: list[UIAChatRow] = []
        for index, items in sorted(grouped.items()):
            row_top = top + index * row_height
            row_bottom = min(bottom, row_top + row_height)
            nickname = cls._nickname_from_group(items, left, right, row_top, row_height)
            if not nickname:
                continue
            texts = [item.name.strip() for item in sorted(items, key=lambda item: (item.bounds[1], item.bounds[0]))]
            time_text = next((text for text in texts if TIME_PATTERN.match(text)), "")
            preview = next((text for text in texts if text != nickname and text != time_text and text not in _IGNORED_TEXTS and len(text) > 2), "")
            title_left = left + max(46, int(width * 0.032))
            nickname_item = next((item for item in items if nickname in item.name and item.bounds[2] - item.bounds[0] < (right - left) * 0.65), None)
            spark_left = max(title_left, nickname_item.bounds[2] + 2) if nickname_item else title_left
            # Exclude avatar and right-aligned time. The icon sits on the title line.
            spark = [spark_left, row_top + 2, right - max(24, int(width * 0.018)), min(row_bottom, row_top + int(row_height * 0.48))]
            contact = StructuredChatObject(
                nickname=nickname,
                last_message_time_text=time_text,
                last_message_preview=preview,
                status="active" if time_text else "unknown",
                confidence=0.99,
                bounds=[left, row_top, right, row_bottom],
                raw_text=texts,
            )
            rows.append(UIAChatRow(contact, [left, row_top, right, row_bottom], spark))
        return rows, [left, top, right, bottom]

    @classmethod
    def _parse_time_anchored_rows(
        cls,
        candidates: list[AccessibleElement],
        left: int,
        top: int,
        right: int,
        bottom: int,
        row_height: int,
        width: int,
    ) -> list[UIAChatRow]:
        """Anchor rows on right-aligned timestamps instead of a fixed scroll grid."""
        time_items = [
            item
            for item in candidates
            if _CHAT_TIME.match(item.name.replace(" ", " ").strip())
            and item.bounds[0] >= left + int((right - left) * 0.55)
        ]
        rows: list[UIAChatRow] = []
        used_centers: list[float] = []
        for time_item in sorted(time_items, key=lambda item: item.bounds[1]):
            center_y = (time_item.bounds[1] + time_item.bounds[3]) / 2
            if any(abs(center_y - value) < row_height * 0.45 for value in used_centers):
                continue
            title_items = [
                item
                for item in candidates
                if item.bounds[0] < time_item.bounds[0]
                and abs(((item.bounds[1] + item.bounds[3]) / 2) - center_y) <= max(18, row_height * 0.22)
            ]
            nickname = next(
                (
                    _SPARK_SUFFIX.sub("", item.name.replace("\n", " ").strip()).strip()[:100]
                    for item in sorted(title_items, key=lambda item: item.bounds[0])
                    if cls._nickname_candidate(_SPARK_SUFFIX.sub("", item.name).strip())
                ),
                "",
            )
            if not nickname:
                continue
            row_top = max(top, round(center_y - row_height * 0.36))
            row_bottom = min(bottom, round(center_y + row_height * 0.64))
            items = [
                item
                for item in candidates
                if row_top <= (item.bounds[1] + item.bounds[3]) / 2 <= row_bottom
            ]
            texts = [item.name.strip() for item in sorted(items, key=lambda item: (item.bounds[1], item.bounds[0]))]
            preview = next(
                (
                    text
                    for text in texts
                    if text != nickname and text != time_item.name and text not in _IGNORED_TEXTS and len(text) > 2
                ),
                "",
            )
            title_item = next((item for item in title_items if nickname in item.name), None)
            title_left = left + max(46, int(width * 0.032))
            spark_left = max(title_left, title_item.bounds[2] + 2) if title_item else title_left
            spark = [spark_left, row_top + 2, right - max(24, int(width * 0.018)), min(row_bottom, row_top + int(row_height * 0.48))]
            contact = StructuredChatObject(
                nickname=nickname,
                last_message_time_text=time_item.name.strip(),
                last_message_preview=preview,
                status="active",
                confidence=0.99,
                bounds=[left, row_top, right, row_bottom],
                raw_text=texts,
            )
            rows.append(UIAChatRow(contact, [left, row_top, right, row_bottom], spark))
            used_centers.append(center_y)
        return rows

    @staticmethod
    def default_chat_bounds(width: int, height: int) -> list[int]:
        return [int(width * 0.545), int(height * 0.11), int(width * 0.705), int(height * 0.78)]

    @staticmethod
    def _inside(item: AccessibleElement, bounds: list[int]) -> bool:
        x = (item.bounds[0] + item.bounds[2]) / 2
        y = (item.bounds[1] + item.bounds[3]) / 2
        return bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]

    @classmethod
    def _nickname_from_group(
        cls,
        items: list[AccessibleElement],
        left: int,
        right: int,
        row_top: int,
        row_height: int,
    ) -> str:
        ordered = sorted(items, key=lambda item: (item.bounds[1], item.bounds[0]))
        for item in ordered:
            text = item.name.replace("\n", " ").strip()
            if item.bounds[1] > row_top + row_height * 0.6:
                continue
            for part in re.split(r"\s{2,}|[,，|]", text):
                value = _SPARK_SUFFIX.sub("", part).strip()
                if cls._nickname_candidate(value):
                    return value[:100]
        return ""

    @staticmethod
    def _nickname_candidate(text: str) -> bool:
        compact = text.replace(" ", "")
        return bool(
            1 <= len(compact) <= 32
            and compact not in _IGNORED_TEXTS
            and not TIME_PATTERN.match(compact)
            and not _UNREAD.match(compact)
            and not compact.startswith("[")
        )

    @staticmethod
    def _to_local(item: AccessibleElement, window: DesktopWindow) -> AccessibleElement | None:
        left, top, right, bottom = item.bounds
        local = (left - window.bounds.left, top - window.bounds.top, right - window.bounds.left, bottom - window.bounds.top)
        if local[2] <= 0 or local[3] <= 0 or local[0] >= window.bounds.width or local[1] >= window.bounds.height:
            return None
        return AccessibleElement(item.name, item.control_type, local)

    @staticmethod
    def _identity(value: str) -> str:
        return re.sub(r"[\s…\.·🔥💧✨]", "", value).casefold()
