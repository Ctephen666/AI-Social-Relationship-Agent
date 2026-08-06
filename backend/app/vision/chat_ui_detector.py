from __future__ import annotations

from pydantic import BaseModel, Field

from app.vision.parser import TIME_PATTERN, VisionChatParser
from app.vision.schemas import OCRBlock, StructuredChatObject


class DetectedChatRow(BaseModel):
    contact: StructuredChatObject
    spark_bounds: list[int] = Field(min_length=4, max_length=4)


class ChatUIDetection(BaseModel):
    chat_list_bounds: list[int] = Field(default_factory=list)
    rows: list[DetectedChatRow] = Field(default_factory=list)


class ChatUIDetector:
    """Map OCR records to chat-list rows and per-row firework candidate regions."""

    def __init__(self, parser: VisionChatParser | None = None) -> None:
        self.parser = parser or VisionChatParser()

    @staticmethod
    def douyin_chat_list_bounds(image_width: int, image_height: int) -> list[int]:
        return [int(image_width * 0.545), int(image_height * 0.055), int(image_width * 0.705), int(image_height * 0.78)]

    def detect(self, blocks: list[OCRBlock], image_width: int, image_height: int) -> ChatUIDetection:
        contacts = self.parser.parse(blocks)
        if not contacts:
            return ChatUIDetection()
        all_bounds = [contact.bounds for contact in contacts if len(contact.bounds) == 4]
        chat_bounds = [
            min(bounds[0] for bounds in all_bounds),
            min(bounds[1] for bounds in all_bounds),
            min(image_width, max(bounds[2] for bounds in all_bounds) + 110),
            max(bounds[3] for bounds in all_bounds),
        ]
        rows = [DetectedChatRow(contact=contact, spark_bounds=self._spark_bounds(contact.bounds, chat_bounds, image_width, image_height)) for contact in contacts]
        return ChatUIDetection(chat_list_bounds=chat_bounds, rows=rows)

    def is_douyin_message_panel_open(self, blocks: list[OCRBlock], image_width: int, image_height: int) -> bool:
        left, top, right, bottom = self.douyin_chat_list_bounds(image_width, image_height)
        texts = [block.text.replace(" ", "").strip() for block in blocks if self._block_center_inside(block, left, top, right, bottom)]
        # Generic feed text may also fall inside the future panel rectangle.
        # Require controls that only exist when the conversation panel is open.
        return "搜索" in texts or "收起会话" in texts

    def detect_douyin(self, blocks: list[OCRBlock], image_width: int, image_height: int) -> ChatUIDetection:
        """Parse only the Douyin conversation-list column, excluding feed/chat content."""
        left, top, right, bottom = self.douyin_chat_list_bounds(image_width, image_height)
        content_top = top + int(image_height * 0.055)
        excluded = {"搜索", "消息", "收起会话", "发送消息"}
        filtered = [
            block for block in blocks
            if self._block_center_inside(block, left, content_top, right, bottom)
            and block.text.replace(" ", "").strip() not in excluded
        ]
        rows: list[DetectedChatRow] = []
        row_height = max(72, int(image_height * 0.066))
        grouped: dict[int, list[OCRBlock]] = {}
        for block in filtered:
            center_y = self._center(block)[1]
            row_index = max(0, int((center_y - content_top) // row_height))
            grouped.setdefault(row_index, []).append(block)

        for row_index, row_blocks in sorted(grouped.items()):
            row_top = content_top + row_index * row_height
            row_bottom = min(bottom, row_top + row_height)
            title_limit = row_top + int(row_height * 0.57)
            title_blocks = [block for block in row_blocks if self._center(block)[1] <= title_limit]
            ordered_title = sorted(title_blocks, key=lambda block: self._bounds(block)[0])
            name_block = next((block for block in ordered_title if self.parser._is_nickname_candidate(block.text.strip())), None)
            if name_block is None:
                continue
            name_left, name_top, name_right, name_bottom = self._bounds(name_block)
            time_block = next((block for block in reversed(ordered_title) if TIME_PATTERN.match(block.text.strip())), None)
            time_text = time_block.text.strip() if time_block else ""
            preview = [
                block.text.strip() for block in sorted(row_blocks, key=lambda item: (self._center(item)[1], self._bounds(item)[0]))
                if block is not name_block and block is not time_block and self._center(block)[1] > title_limit
            ]
            contact = StructuredChatObject(
                nickname=name_block.text.strip(),
                last_message_time_text=time_text,
                last_message_preview=" ".join(preview[:2]),
                interaction_days=self.parser._interaction_days(time_text),
                status="active" if time_text else "unknown",
                confidence=round(sum(block.confidence for block in row_blocks) / len(row_blocks), 4),
                bounds=[min(self._bounds(block)[0] for block in row_blocks), row_top, max(self._bounds(block)[2] for block in row_blocks), row_bottom],
                raw_text=[block.text.strip() for block in row_blocks],
            )
            time_left = self._bounds(time_block)[0] if time_block else right
            spark_left = min(right, name_right + 3)
            spark_right = min(right, max(spark_left + 28, time_left - 3))
            spark_top = max(row_top, name_top - 5)
            spark_bottom = min(row_bottom, name_bottom + 5)
            rows.append(DetectedChatRow(contact=contact, spark_bounds=[spark_left, spark_top, spark_right, spark_bottom]))
        return ChatUIDetection(chat_list_bounds=[left, content_top, right, bottom], rows=rows)

    @staticmethod
    def _block_center_inside(block: OCRBlock, left: int, top: int, right: int, bottom: int) -> bool:
        if not block.box:
            return False
        xs, ys = [point[0] for point in block.box], [point[1] for point in block.box]
        return left <= sum(xs) / len(xs) <= right and top <= sum(ys) / len(ys) <= bottom

    @staticmethod
    def _bounds(block: OCRBlock) -> tuple[int, int, int, int]:
        xs, ys = [point[0] for point in block.box], [point[1] for point in block.box]
        return min(xs), min(ys), max(xs), max(ys)

    @classmethod
    def _center(cls, block: OCRBlock) -> tuple[float, float]:
        left, top, right, bottom = cls._bounds(block)
        return (left + right) / 2, (top + bottom) / 2

    @staticmethod
    def _spark_bounds(bounds: list[int], chat_bounds: list[int], image_width: int, image_height: int) -> list[int]:
        left, top, right, bottom = bounds
        row_height = max(24, bottom - top)
        # The icon normally sits in the same list row. Include a small area around
        # text so layouts with a leading or trailing spark icon are both covered.
        return [
            max(chat_bounds[0], left - 48),
            max(0, top - row_height // 3),
            min(image_width, max(right + 76, chat_bounds[2])),
            min(image_height, bottom + row_height // 3),
        ]
