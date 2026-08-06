import pytest
import cv2
import numpy as np

from app.desktop_agent.uia_backend import AccessibleElement, DouyinUIABackend
from app.desktop_agent.window_locator import DesktopWindow, WindowBounds
from app.desktop_agent.windows_controller import DouyinWindowsController
from app.vision.chat_ui_detector import ChatUIDetector
from app.vision.schemas import OCRBlock
from app.vision.frame_fingerprint import difference_hash, hash_similarity
from app.vision.spark_detector import SparkDetector


def block(text: str, left: int, top: int, right: int, bottom: int) -> OCRBlock:
    return OCRBlock(text=text, confidence=0.98, box=[[left, top], [right, top], [right, bottom], [left, bottom]])


def test_douyin_detector_ignores_feed_and_parses_chat_column() -> None:
    blocks = [
        block("视频标题", 200, 300, 400, 340),
        block("搜索", 1150, 80, 1220, 108),
        block("张三", 1200, 160, 1260, 184),
        block("660", 1270, 160, 1310, 184),
        block("15:36", 1360, 160, 1400, 184),
        block("昨天聊的游戏", 1200, 194, 1320, 216),
    ]
    result = ChatUIDetector().detect_douyin(blocks, 2048, 1222)
    assert result.chat_list_bounds == [1116, 134, 1443, 953]
    assert result.rows
    assert result.rows[0].contact.nickname == "张三"
    assert all(row.contact.nickname != "视频标题" for row in result.rows)


def test_message_panel_detection() -> None:
    blocks = [block("搜索", 1150, 80, 1220, 108)]
    assert ChatUIDetector().is_douyin_message_panel_open(blocks, 2048, 1222)


def test_controller_rejects_click_outside_top_navigation() -> None:
    controller = DouyinWindowsController.__new__(DouyinWindowsController)
    controller.user32 = None
    window = DesktopWindow(1, "抖音", WindowBounds(0, 0, 2000, 1200))
    with pytest.raises(PermissionError):
        controller._click_allowed(window, 1700, 1000, action="message_entry")


def test_uia_parser_builds_rows_without_ocr() -> None:
    elements = [
        AccessibleElement("搜索", "Edit", (1150, 80, 1390, 110)),
        AccessibleElement("张三", "Text", (1200, 150, 1260, 177)),
        AccessibleElement("15:36", "Text", (1360, 150, 1402, 177)),
        AccessibleElement("昨天聊的游戏", "Text", (1200, 185, 1340, 210)),
        AccessibleElement("李四", "Text", (1200, 232, 1260, 259)),
        AccessibleElement("周六", "Text", (1360, 232, 1402, 259)),
        AccessibleElement("分享了视频", "Text", (1200, 267, 1320, 291)),
    ]
    rows, bounds = DouyinUIABackend.parse_chat_rows(elements, 2048, 1222)
    assert bounds == [1116, 134, 1443, 953]
    assert [row.contact.nickname for row in rows] == ["张三", "李四"]
    assert rows[0].spark_bounds[0] >= 1262


def test_uia_parser_anchors_nickname_to_right_aligned_time_after_scroll() -> None:
    elements = [
        AccessibleElement("分享[视频]", "Text", (1523, 191, 1605, 216)),
        AccessibleElement("沈文溪", "Text", (1523, 254, 1586, 285)),
        AccessibleElement("424", "Text", (1620, 256, 1656, 286)),
        AccessibleElement("昨天 13:05", "Text", (1672, 259, 1744, 281)),
        AccessibleElement("[嗨]", "Text", (1523, 295, 1554, 320)),
        AccessibleElement("冷漠无情葱花", "Text", (1523, 355, 1648, 386)),
        AccessibleElement("周六", "Text", (1714, 359, 1744, 381)),
        AccessibleElement("[表情]", "Text", (1523, 392, 1571, 417)),
    ]

    rows, _bounds = DouyinUIABackend.parse_chat_rows(elements, 2582, 1550)

    assert [row.contact.nickname for row in rows] == ["沈文溪", "冷漠无情葱花"]


def test_frame_hash_detects_unchanged_page() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(image, (10, 10), (80, 30), (255, 255, 255), -1)
    same = image.copy()
    changed = image.copy()
    cv2.rectangle(changed, (20, 60), (90, 85), (255, 255, 255), -1)
    assert hash_similarity(difference_hash(image), difference_hash(same)) == 1.0
    assert hash_similarity(difference_hash(image), difference_hash(changed)) < 0.99


def test_spark_detector_uses_compact_color_component() -> None:
    detector = SparkDetector()
    active = np.zeros((36, 100, 3), dtype=np.uint8)
    cv2.circle(active, (20, 18), 7, (0, 120, 255), -1)
    gray = np.zeros((36, 100, 3), dtype=np.uint8)
    cv2.circle(gray, (20, 18), 7, (135, 135, 135), -1)
    none = np.zeros((36, 100, 3), dtype=np.uint8)
    assert detector.detect(active).status == "active"
    assert detector.detect(gray).status == "gray"
    assert detector.detect(none).status == "none"
