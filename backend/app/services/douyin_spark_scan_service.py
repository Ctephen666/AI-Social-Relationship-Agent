from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import time

import cv2
import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import DesktopSparkScan, SparkStatus, User
from app.desktop_agent.douyin_agent import DesktopCaptureResult, DouyinDesktopVisionAgent
from app.desktop_agent.uia_backend import DouyinUIABackend, UIAChatRow, UIAChatSnapshot
from app.desktop_agent.windows_controller import DouyinWindowsController
from app.vision.chat_ui_detector import ChatUIDetection, ChatUIDetector, DetectedChatRow
from app.vision.frame_fingerprint import difference_hash, hash_similarity
from app.vision.ocr_engine import get_ocr_engine
from app.vision.spark_detector import SparkDetector


@dataclass(frozen=True)
class FullScanSummary:
    window_title: str
    pages_scanned: int
    results: list[DesktopSparkScan]
    scan_mode: str = "hybrid"
    elapsed_ms: int = 0
    ocr_pages: int = 0


class DouyinSparkScanService:
    """Low-latency UIA-first scan with a bounded local OCR fallback.

    The only mutating desktop actions remain opening the message panel and
    scrolling inside the verified conversation-list rectangle.
    """

    def __init__(self, uia: DouyinUIABackend | None = None) -> None:
        self.settings = get_settings()
        self.ui_detector = ChatUIDetector()
        self.spark_detector = SparkDetector()
        self.uia = uia or DouyinUIABackend(self.settings.uia_timeout_seconds)

    def run(self, db: Session) -> tuple[str, str, list[DesktopSparkScan]]:
        summary = self.run_full_scan(db, max_pages=1)
        screenshot = summary.results[0].screenshot_path if summary.results else ""
        return summary.window_title, screenshot, summary.results

    def run_full_scan(
        self,
        db: Session,
        max_pages: int = 30,
        progress: Callable[[str], None] | None = None,
        controller: DouyinWindowsController | None = None,
    ) -> FullScanSummary:
        started = time.perf_counter()
        report = progress or (lambda _: None)
        control = controller or DouyinWindowsController()
        report("正在启动并激活抖音…")
        window = control.ensure_ready()
        capture_agent = DouyinDesktopVisionAgent(self.settings.screenshot_path / "douyin")

        report("正在读取 Windows UI Automation 控件…")
        use_uia = self.settings.scan_backend.casefold() in {"hybrid", "uia"}
        snapshot = self.uia.inspect(window) if use_uia else self._empty_snapshot(window.bounds.width, window.bounds.height)
        if not snapshot.panel_open:
            report("正在打开消息面板…")
            opened = use_uia and self.uia.click_message_entry(window)
            if not opened:
                # The fixed point is constrained to the verified Douyin top bar;
                # unlike the old implementation it does not need full-screen OCR.
                control.open_message_panel(window, [])
            time.sleep(0.45)
            snapshot = self.uia.inspect(window) if use_uia else self._empty_snapshot(window.bounds.width, window.bounds.height)

        # If Chromium does not expose its accessibility tree, visual confirmation
        # is performed only on the narrow list ROI.
        if snapshot.panel_open:
            chat_bounds = snapshot.chat_list_bounds
            initial_mode = "uia"
        else:
            if self.settings.scan_backend.casefold() == "uia":
                raise RuntimeError("当前抖音版本未暴露 UIA 聊天控件；请设置 SCAN_BACKEND=hybrid 使用局部视觉兜底。")
            capture, image = self._capture_image(capture_agent)
            visual = self._ocr_detection(image)
            if not visual.rows:
                raise RuntimeError("消息面板已打开，但 UIA 和局部 OCR 均未读取到聊天列表。请最大化抖音后重试。")
            chat_bounds = visual.chat_list_bounds
            initial_mode = "rapidocr"

        report("正在快速定位聊天列表顶部…")
        control.scroll_chat_list(window, chat_bounds, "up", steps=80)
        time.sleep(self.settings.scroll_settle_ms / 1000)

        seen: set[str] = set()
        saved: list[DesktopSparkScan] = []
        pages_scanned = 0
        ocr_pages = 0
        uia_pages = 0
        previous_hash: int | None = None
        no_new_pages = 0

        for page_index in range(max(1, min(max_pages, 100))):
            capture, image = self._capture_image(capture_agent)
            list_crop = self._crop(image, chat_bounds)
            current_hash = difference_hash(list_crop)
            if previous_hash is not None and hash_similarity(previous_hash, current_hash) >= 0.992:
                report("聊天列表画面未变化，已经到达底部")
                break

            snapshot = self.uia.inspect(window) if use_uia else self._empty_snapshot(window.bounds.width, window.bounds.height)
            if snapshot.rows:
                detection = self._from_uia(snapshot.rows, snapshot.chat_list_bounds)
                uia_pages += 1
            else:
                detection = self._ocr_detection(image)
                ocr_pages += 1
            if not detection.rows:
                no_new_pages += 1
            else:
                chat_bounds = detection.chat_list_bounds

            new_count = 0
            for row in detection.rows:
                nickname = row.contact.nickname.strip()
                identity = self._identity(nickname)
                if not identity or identity in seen:
                    continue
                seen.add(identity)
                new_count += 1
                record = self._build_record(
                    db,
                    capture.image_path,
                    capture.window.title,
                    image,
                    detection.chat_list_bounds,
                    row,
                    "uia" if snapshot.rows else "rapidocr",
                )
                db.add(record)
                saved.append(record)
            db.commit()
            pages_scanned = page_index + 1
            report(f"已扫描 {pages_scanned} 屏，发现 {len(seen)} 位好友")
            no_new_pages = no_new_pages + 1 if new_count == 0 else 0
            if no_new_pages >= 2:
                break

            previous_hash = current_hash
            control.scroll_chat_list(window, chat_bounds, "down", steps=7)
            time.sleep(self.settings.scroll_settle_ms / 1000)

        for record in saved:
            db.refresh(record)
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        if ocr_pages == 0 and uia_pages:
            mode = "uia"
        elif uia_pages and ocr_pages:
            mode = "hybrid"
        else:
            mode = initial_mode
        report(f"扫描完成：{elapsed_ms / 1000:.2f}s，模式 {mode}，OCR {ocr_pages} 屏")
        return FullScanSummary(window.title, pages_scanned, saved, mode, elapsed_ms, ocr_pages)

    def _ocr_detection(self, image: np.ndarray) -> ChatUIDetection:
        left, top, right, bottom = self.ui_detector.douyin_chat_list_bounds(image.shape[1], image.shape[0])
        roi = image[top:bottom, left:right]
        blocks = get_ocr_engine(self.settings.ocr_lang, self.settings.ocr_backend).recognize_image(roi)
        translated = [
            block.model_copy(update={"box": [[point[0] + left, point[1] + top] for point in block.box]})
            for block in blocks
        ]
        return self.ui_detector.detect_douyin(translated, image.shape[1], image.shape[0])

    @staticmethod
    def _from_uia(rows: list[UIAChatRow], bounds: list[int]) -> ChatUIDetection:
        return ChatUIDetection(
            chat_list_bounds=bounds,
            rows=[DetectedChatRow(contact=row.contact, spark_bounds=row.spark_bounds) for row in rows],
        )

    @staticmethod
    def _empty_snapshot(width: int, height: int) -> UIAChatSnapshot:
        return UIAChatSnapshot(False, DouyinUIABackend.default_chat_bounds(width, height), [], 0)

    @staticmethod
    def _capture_image(agent: DouyinDesktopVisionAgent) -> tuple[DesktopCaptureResult, np.ndarray]:
        capture = agent.capture()
        image = cv2.imread(str(capture.image_path))
        if image is None:
            raise RuntimeError("抖音窗口截图保存失败。")
        return capture, image

    @staticmethod
    def _crop(image: np.ndarray, bounds: list[int]) -> np.ndarray:
        if len(bounds) != 4:
            return image
        left, top, right, bottom = bounds
        return image[max(0, top):max(top, bottom), max(0, left):max(left, right)]

    @staticmethod
    def _identity(nickname: str) -> str:
        return "".join(nickname.casefold().split())

    def _build_record(
        self,
        db: Session,
        image_path: Path,
        window_title: str,
        image: np.ndarray,
        chat_bounds: list[int],
        row: DetectedChatRow,
        scan_mode: str,
    ) -> DesktopSparkScan:
        x1, y1, x2, y2 = row.spark_bounds
        detection = self.spark_detector.detect(image[y1:y2, x1:x2])
        user = db.scalar(select(User).where(User.nickname == row.contact.nickname))
        relative_path = image_path.relative_to(self.settings.screenshot_path).as_posix()
        return DesktopSparkScan(
            user_id=user.id if user else None,
            nickname=row.contact.nickname,
            spark_status=SparkStatus(detection.status),
            confidence=detection.confidence,
            screenshot_path=relative_path,
            chat_list_bounds=chat_bounds,
            spark_bounds=row.spark_bounds,
            ocr_payload={
                "contact": row.contact.model_dump(),
                "warm_ratio": detection.warm_ratio,
                "gray_ratio": detection.gray_ratio,
                "window_title": window_title,
                "scan_mode": scan_mode,
                "detector": detection.model_dump(),
            },
        )
