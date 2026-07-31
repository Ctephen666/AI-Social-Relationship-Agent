from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from app.vision.schemas import OCRBlock, StructuredChatObject

TIME_PATTERN = re.compile(
    r"^(?:刚刚|今天|昨天|前天|\d{1,2}:\d{2}|\d{1,2}[/-]\d{1,2}|\d{4}[/-]\d{1,2}[/-]\d{1,2}|星期[一二三四五六日天])$"
)


@dataclass(frozen=True)
class _PositionedBlock:
    block: OCRBlock
    left: int
    top: int
    right: int
    bottom: int


class VisionChatParser:
    """Convert OCR text boxes into chat-list records using spatial row grouping.

    The parser intentionally does not depend on a specific chat product. Product-specific
    strategies can subclass this parser without changing OCR or Agent contracts.
    """

    def parse(self, blocks: list[OCRBlock]) -> list[StructuredChatObject]:
        rows = self._group_rows(self._position(block) for block in blocks if block.text.strip())
        records: list[StructuredChatObject] = []
        for row in rows:
            record = self._parse_row(row)
            if record is not None:
                records.append(record)
        return records

    @staticmethod
    def _position(block: OCRBlock) -> _PositionedBlock:
        points = block.box or [[0, 0]]
        xs, ys = [point[0] for point in points], [point[1] for point in points]
        return _PositionedBlock(block, min(xs), min(ys), max(xs), max(ys))

    def _group_rows(self, positioned: list[_PositionedBlock] | object) -> list[list[_PositionedBlock]]:
        ordered = sorted(list(positioned), key=lambda item: (item.top, item.left))
        rows: list[list[_PositionedBlock]] = []
        for item in ordered:
            height = max(12, item.bottom - item.top)
            if not rows:
                rows.append([item])
                continue
            current = rows[-1]
            current_bottom = max(block.bottom for block in current)
            threshold = max(height * 1.4, 22)
            if item.top - current_bottom <= threshold:
                current.append(item)
            else:
                rows.append([item])
        return rows

    def _parse_row(self, row: list[_PositionedBlock]) -> StructuredChatObject | None:
        ordered = sorted(row, key=lambda item: item.left)
        texts = [item.block.text.strip() for item in ordered]
        time_index = next((index for index, value in enumerate(texts) if TIME_PATTERN.match(value)), None)
        name_candidates = [
            (index, value) for index, value in enumerate(texts)
            if index != time_index and self._is_nickname_candidate(value)
        ]
        if not name_candidates:
            return None
        name_index, nickname = name_candidates[0]
        preview_candidates = [
            value for index, value in enumerate(texts)
            if index != name_index and index != time_index and value
        ]
        time_text = texts[time_index] if time_index is not None else ""
        confidence = sum(item.block.confidence for item in ordered) / len(ordered)
        return StructuredChatObject(
            nickname=nickname,
            last_message_time_text=time_text,
            last_message_preview=" ".join(preview_candidates[:2]),
            interaction_days=self._interaction_days(time_text),
            status="active" if time_text else "unknown",
            confidence=round(confidence, 4),
            bounds=[min(item.left for item in ordered), min(item.top for item in ordered), max(item.right for item in ordered), max(item.bottom for item in ordered)],
            raw_text=texts,
        )

    @staticmethod
    def _is_nickname_candidate(value: str) -> bool:
        if not value or len(value) > 32 or TIME_PATTERN.match(value):
            return False
        return not re.fullmatch(r"[\d\W_]+", value)

    @staticmethod
    def _interaction_days(time_text: str) -> int | None:
        if time_text in {"刚刚", "今天"} or re.fullmatch(r"\d{1,2}:\d{2}", time_text):
            return 0
        if time_text == "昨天":
            return 1
        if time_text == "前天":
            return 2
        if time_text.startswith("星期"):
            weekday = "一二三四五六日天".index(time_text[-1]) % 7
            return (datetime.now().weekday() - weekday) % 7
        return None
