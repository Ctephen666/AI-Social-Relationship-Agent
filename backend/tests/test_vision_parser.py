from app.vision.parser import VisionChatParser
from app.vision.schemas import OCRBlock


def test_parser_groups_spatial_row_into_structured_chat_object() -> None:
    blocks = [
        OCRBlock(text="张三", confidence=0.99, box=[[10, 10], [50, 10], [50, 30], [10, 30]]),
        OCRBlock(text="昨天", confidence=0.98, box=[[260, 10], [300, 10], [300, 30], [260, 30]]),
        OCRBlock(text="那个游戏通关了吗", confidence=0.95, box=[[10, 36], [160, 36], [160, 54], [10, 54]]),
        OCRBlock(text="李四", confidence=0.98, box=[[10, 95], [50, 95], [50, 115], [10, 115]]),
        OCRBlock(text="12:30", confidence=0.98, box=[[260, 95], [305, 95], [305, 115], [260, 115]]),
    ]

    records = VisionChatParser().parse(blocks)

    assert [record.nickname for record in records] == ["张三", "李四"]
    assert records[0].interaction_days == 1
    assert records[0].last_message_preview == "那个游戏通关了吗"
    assert records[0].model_dump()["bounds"] == [10, 10, 300, 54]
