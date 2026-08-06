from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

from sqlalchemy.orm import Session

from app.database.models import OutboundMessageAudit
from app.desktop_agent.uia_backend import DouyinUIABackend
from app.desktop_agent.windows_controller import DouyinWindowsController, MessageDeliveryError


@dataclass(frozen=True)
class RenewalRecipient:
    nickname: str
    message: str


@dataclass(frozen=True)
class RenewalSummary:
    sent: int
    failed: int
    not_found: int
    aborted: bool
    elapsed_ms: int


class DouyinSparkRenewService:
    """Traverse visible Douyin rows and send through allow-listed geometry.

    This service intentionally has no generic click/type primitive. Every
    mutation is constrained to a visible chat row, the bottom editor ROI and
    the right-side send arrow while Douyin remains foreground.
    """

    def __init__(self, uia: DouyinUIABackend | None = None) -> None:
        self.uia = uia or DouyinUIABackend(timeout_seconds=1.8)

    def send_all(
        self,
        db: Session,
        plan_id: str,
        message_template: str,
        delay_seconds: float,
        max_pages: int,
        max_recipients: int,
        progress: Callable[[str], None] | None = None,
        controller: DouyinWindowsController | None = None,
    ) -> RenewalSummary:
        """Open Messages and send once to every unique row in a single pass."""
        started = time.perf_counter()
        report = progress or (lambda _message: None)
        control = controller or DouyinWindowsController()
        window = control.ensure_ready()
        report("正在打开抖音右上角消息面板…")
        snapshot = self.uia.inspect(window)
        if not snapshot.panel_open:
            opened = self.uia.click_message_entry(window)
            if not opened:
                control.open_message_panel(window, [])
            time.sleep(0.22)
            snapshot = self.uia.inspect(window)
        if not snapshot.panel_open or not snapshot.rows:
            raise RuntimeError("未能打开右上角消息面板，或抖音未暴露聊天列表 UIA 控件。")

        chat_bounds = snapshot.chat_list_bounds
        control.scroll_chat_list(window, chat_bounds, "up", steps=80)
        time.sleep(0.18)

        sent = 0
        failed = 0
        aborted = False
        seen: set[str] = set()
        previous_signature: tuple[str, ...] | None = None
        stagnant_pages = 0
        recipient_limit = max(1, min(max_recipients, 300))

        for page_index in range(max(1, min(max_pages, 100))):
            snapshot = self.uia.inspect(window)
            if not snapshot.rows:
                raise RuntimeError("发送过程中聊天列表 UIA 控件消失，已立即停止。")
            signature = tuple(self._identity(row.contact.nickname) for row in snapshot.rows)
            stagnant_pages = stagnant_pages + 1 if signature == previous_signature else 0
            if stagnant_pages >= 1:
                break
            previous_signature = signature

            for row in snapshot.rows:
                nickname = row.contact.nickname.strip()
                identity = self._identity(nickname)
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                if sent + failed >= recipient_limit:
                    break
                if control.emergency_stop_requested():
                    aborted = True
                    report("检测到 Ctrl+Shift+Q，已紧急停止发送")
                    break
                recipient = RenewalRecipient(nickname, message_template.replace("{nickname}", nickname))
                try:
                    report(f"正在发送给 {nickname}（第 {page_index + 1} 屏）…")
                    control.click_chat_row(window, row.row_bounds)
                    time.sleep(0.10)
                    editor = control.default_message_editor_bounds(window)
                    control.send_message(window, editor, recipient.message)
                except Exception as exc:
                    failed += 1
                    self._audit(db, plan_id, recipient, "failed", str(exc))
                    if isinstance(exc, MessageDeliveryError):
                        report(f"{nickname} 输入失败，已停止整个任务：{exc}")
                        raise
                    report(f"{nickname} 发送失败，已跳过：{exc}")
                    continue
                sent += 1
                self._audit(db, plan_id, recipient, "sent", "")
                time.sleep(max(0.15, min(delay_seconds, 3.0)))
            if aborted or sent + failed >= recipient_limit:
                break
            chat_bounds = snapshot.chat_list_bounds
            control.scroll_chat_list(window, chat_bounds, "down", steps=7)
            time.sleep(0.14)

        return RenewalSummary(sent, failed, 0, aborted, round((time.perf_counter() - started) * 1000))

    def send(
        self,
        db: Session,
        plan_id: str,
        recipients: list[RenewalRecipient],
        delay_seconds: float,
        max_pages: int,
        progress: Callable[[str], None] | None = None,
        controller: DouyinWindowsController | None = None,
    ) -> RenewalSummary:
        started = time.perf_counter()
        report = progress or (lambda _message: None)
        control = controller or DouyinWindowsController()
        window = control.ensure_ready()
        snapshot = self.uia.inspect(window)
        if not snapshot.panel_open:
            opened = self.uia.click_message_entry(window)
            if not opened:
                control.open_message_panel(window, [])
            time.sleep(0.5)
            snapshot = self.uia.inspect(window)
        if not snapshot.rows:
            raise RuntimeError("发送功能要求抖音暴露 UIA 聊天控件；为避免误发，当前不会使用 OCR 坐标发送。")

        chat_bounds = snapshot.chat_list_bounds
        control.scroll_chat_list(window, chat_bounds, "up", steps=80)
        time.sleep(0.5)

        pending = {self._identity(item.nickname): item for item in recipients if self._identity(item.nickname)}
        sent = 0
        failed = 0
        aborted = False
        previous_signature: tuple[str, ...] | None = None
        stagnant_pages = 0

        for _page in range(max(1, min(max_pages, 100))):
            if not pending:
                break
            snapshot = self.uia.inspect(window)
            if not snapshot.rows:
                raise RuntimeError("发送过程中聊天列表 UIA 控件消失，已立即停止。")
            signature = tuple(self._identity(row.contact.nickname) for row in snapshot.rows)
            stagnant_pages = stagnant_pages + 1 if signature == previous_signature else 0
            if stagnant_pages >= 1:
                break
            previous_signature = signature

            for row in snapshot.rows:
                identity = self._identity(row.contact.nickname)
                recipient = pending.pop(identity, None)
                if recipient is None:
                    continue
                if control.emergency_stop_requested():
                    aborted = True
                    report("检测到 Ctrl+Shift+Q，已紧急停止发送")
                    break
                try:
                    report(f"正在校验 {recipient.nickname} 的会话…")
                    control.click_chat_row(window, row.row_bounds)
                    time.sleep(0.35)
                    if not self.uia.conversation_matches(window, recipient.nickname):
                        raise RuntimeError("会话标题与目标好友不一致")
                    editor = self.uia.message_editor_bounds(window)
                    if editor is None:
                        raise RuntimeError("未找到已验证的消息输入框")
                    report(f"正在发送给 {recipient.nickname}（Ctrl+Shift+Q 可停止）")
                    control.send_message(window, editor, recipient.message)
                except Exception as exc:
                    failed += 1
                    self._audit(db, plan_id, recipient, "failed", str(exc))
                    report(f"{recipient.nickname} 发送失败，已跳过：{exc}")
                    continue
                sent += 1
                self._audit(db, plan_id, recipient, "sent", "")
                time.sleep(max(0.8, min(delay_seconds, 10.0)))
            if aborted:
                break
            chat_bounds = snapshot.chat_list_bounds
            control.scroll_chat_list(window, chat_bounds, "down", steps=7)
            time.sleep(0.35)

        return RenewalSummary(
            sent=sent,
            failed=failed,
            not_found=len(pending),
            aborted=aborted,
            elapsed_ms=round((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _audit(db: Session, plan_id: str, recipient: RenewalRecipient, status: str, error: str) -> None:
        db.add(
            OutboundMessageAudit(
                plan_id=plan_id,
                platform="douyin",
                nickname=recipient.nickname,
                content=recipient.message,
                status=status,
                error=error,
            )
        )
        db.commit()

    @staticmethod
    def _identity(value: str) -> str:
        return "".join(value.replace("…", "").replace(".", "").casefold().split())
