from __future__ import annotations

import numpy as np

from app.vision.ocr_engine import RapidOCREngine


class FakeOutput:
    boxes = np.array([[[1, 2], [11, 2], [11, 12], [1, 12]]])
    txts = ["张三"]
    scores = [0.98]


def test_rapidocr_adapter_accepts_v3_output() -> None:
    engine = RapidOCREngine()
    engine._engine = lambda _: FakeOutput()
    blocks = engine.recognize_image(np.zeros((20, 20, 3), dtype=np.uint8))
    assert blocks[0].text == "张三"
    assert blocks[0].box[2] == [11, 12]
