from app.vision.chat_ui_detector import ChatUIDetector
from app.vision.schemas import OCRBlock


def test_detector_returns_chat_and_spark_bounds() -> None:
    blocks = [
        OCRBlock(text="张三", confidence=0.99, box=[[10, 10], [50, 10], [50, 30], [10, 30]]),
        OCRBlock(text="昨天", confidence=0.98, box=[[260, 10], [300, 10], [300, 30], [260, 30]]),
        OCRBlock(text="游戏通关了吗", confidence=0.95, box=[[10, 36], [150, 36], [150, 54], [10, 54]]),
    ]

    result = ChatUIDetector().detect(blocks, image_width=400, image_height=700)

    assert result.rows[0].contact.nickname == "张三"
    assert result.chat_list_bounds == [10, 10, 400, 54]
    assert result.rows[0].spark_bounds == [10, 0, 400, 68]
