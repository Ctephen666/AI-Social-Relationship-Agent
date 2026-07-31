from datetime import datetime, timedelta
import re

from app.vision.schemas import ContactObservation, OCRBlock

TIME_PATTERN = re.compile(r"^(昨天|前天|\d{1,2}:\d{2}|\d{1,2}/\d{1,2}|星期[一二三四五六日天])$")


class ChatListParser:
    """基于 OCR 行序的保守解析器；平台适配可在此增加专用策略。"""

    def parse(self, blocks: list[OCRBlock]) -> list[ContactObservation]:
        ordered = sorted(blocks, key=lambda block: min(point[1] for point in block.box) if block.box else 0)
        contacts: list[ContactObservation] = []
        for index, block in enumerate(ordered):
            text = block.text.strip()
            if not text or TIME_PATTERN.match(text) or len(text) > 32:
                continue
            next_items = ordered[index + 1 : index + 4]
            time_text = next((item.text for item in next_items if TIME_PATTERN.match(item.text.strip())), "")
            preview = next((item.text for item in next_items if item.text != time_text and len(item.text) > 2), "")
            contacts.append(ContactObservation(
                nickname=text,
                last_message_time_text=time_text,
                last_message_preview=preview,
                interaction_days=self._to_days(time_text),
                status="active" if time_text else "unknown",
                confidence=block.confidence,
            ))
        return contacts

    @staticmethod
    def _to_days(text: str) -> int | None:
        if text == "昨天":
            return 1
        if text == "前天":
            return 2
        if re.match(r"^\d{1,2}:\d{2}$", text):
            return 0
        if re.match(r"^星期", text):
            return (datetime.now().weekday() - 0) % 7
        return None

