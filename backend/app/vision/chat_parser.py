from app.vision.parser import VisionChatParser
from app.vision.schemas import ContactObservation, OCRBlock


class ChatListParser:
    """Compatibility adapter for scan service consumers."""

    def __init__(self) -> None:
        self.parser = VisionChatParser()

    def parse(self, blocks: list[OCRBlock]) -> list[ContactObservation]:
        return list(self.parser.parse(blocks))
