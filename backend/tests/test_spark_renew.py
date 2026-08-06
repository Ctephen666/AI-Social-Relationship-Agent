from __future__ import annotations

import ctypes
import pytest

from app.desktop_agent.uia_backend import UIAChatRow, UIAChatSnapshot
from app.desktop_agent.window_locator import DesktopWindow, WindowBounds
from app.desktop_agent.windows_controller import MessageDeliveryError, _INPUT
from app.services.douyin_spark_renew_service import DouyinSparkRenewService, RenewalRecipient
from app.vision.schemas import StructuredChatObject


class FakeDB:
    def __init__(self) -> None:
        self.rows = []
        self.commits = 0

    def add(self, row) -> None:
        self.rows.append(row)

    def commit(self) -> None:
        self.commits += 1


def test_windows_input_structure_has_native_size() -> None:
    assert ctypes.sizeof(_INPUT) == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)


class FakeController:
    def __init__(self, fail_input: bool = False) -> None:
        self.window = DesktopWindow(7, "抖音", WindowBounds(0, 0, 2000, 1200), "douyin.exe")
        self.messages: list[str] = []
        self.fail_input = fail_input

    def ensure_ready(self):
        return self.window

    def scroll_chat_list(self, *_args, **_kwargs) -> None:
        return None

    def emergency_stop_requested(self) -> bool:
        return False

    def click_chat_row(self, _window, _bounds) -> None:
        return None

    def send_message(self, _window, _bounds, message: str) -> None:
        if self.fail_input:
            raise MessageDeliveryError("simulated input failure")
        self.messages.append(message)

    @staticmethod
    def default_message_editor_bounds(_window):
        return [1400, 768, 1850, 912]


class FakeUIA:
    def __init__(self, matches: bool = True, panel_open: bool = True, nicknames: tuple[str, ...] = ("张三",)) -> None:
        rows = []
        for index, nickname in enumerate(nicknames):
            top = 150 + index * 90
            contact = StructuredChatObject(nickname=nickname, bounds=[1100, top, 1400, top + 80])
            rows.append(UIAChatRow(contact, [1100, top, 1400, top + 80], [1250, top, 1380, top + 30]))
        self.rows = rows
        self.panel_open = panel_open
        self.message_entry_clicks = 0
        self.matches = matches

    def inspect(self, _window):
        return UIAChatSnapshot(self.panel_open, [1090, 120, 1420, 950], self.rows if self.panel_open else [], 2)

    def click_message_entry(self, _window) -> bool:
        self.message_entry_clicks += 1
        self.panel_open = True
        return True

    def conversation_matches(self, _window, _nickname) -> bool:
        return self.matches

    def message_editor_bounds(self, _window):
        return [1450, 850, 1900, 920]

    def verified_message_editor(self, _window, _nickname):
        return [1450, 850, 1900, 920] if self.matches else None


def test_renew_service_sends_only_after_conversation_verification() -> None:
    db = FakeDB()
    controller = FakeController()
    summary = DouyinSparkRenewService(uia=FakeUIA()).send(
        db=db,
        plan_id="plan",
        recipients=[RenewalRecipient("张三", "来续个火花～")],
        delay_seconds=0.8,
        max_pages=2,
        controller=controller,
    )
    assert summary.sent == 1
    assert summary.failed == 0
    assert controller.messages == ["来续个火花～"]
    assert db.rows[0].status == "sent"


def test_renew_service_fails_closed_on_header_mismatch() -> None:
    db = FakeDB()
    controller = FakeController()
    summary = DouyinSparkRenewService(uia=FakeUIA(matches=False)).send(
        db=db,
        plan_id="plan",
        recipients=[RenewalRecipient("张三", "来续个火花～")],
        delay_seconds=0.8,
        max_pages=1,
        controller=controller,
    )
    assert summary.sent == 0
    assert summary.failed == 1
    assert controller.messages == []
    assert db.rows[0].status == "failed"


def test_single_pass_opens_messages_then_sends_each_visible_conversation() -> None:
    db = FakeDB()
    controller = FakeController()
    uia = FakeUIA(panel_open=False, nicknames=("张三", "李四"))

    summary = DouyinSparkRenewService(uia=uia).send_all(
        db=db,
        plan_id="plan-fast",
        message_template="{nickname}，来续个火花～",
        delay_seconds=0.15,
        max_pages=2,
        max_recipients=20,
        controller=controller,
    )

    assert uia.message_entry_clicks == 1
    assert summary.sent == 2
    assert summary.failed == 0
    assert controller.messages == ["张三，来续个火花～", "李四，来续个火花～"]
    assert [row.status for row in db.rows] == ["sent", "sent"]


def test_single_pass_stops_immediately_on_input_failure() -> None:
    db = FakeDB()
    controller = FakeController(fail_input=True)

    with pytest.raises(MessageDeliveryError):
        DouyinSparkRenewService(uia=FakeUIA(nicknames=("张三", "李四"))).send_all(
            db=db,
            plan_id="plan-fast",
            message_template="来续个火花～",
            delay_seconds=0.15,
            max_pages=1,
            max_recipients=20,
            controller=controller,
        )

    assert controller.messages == []
    assert len(db.rows) == 1
    assert db.rows[0].nickname == "张三"
    assert db.rows[0].status == "failed"
