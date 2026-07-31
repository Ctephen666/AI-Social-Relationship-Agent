from functools import lru_cache
from pathlib import Path

from paddleocr import PaddleOCR

from app.vision.image_preprocessor import preprocess_for_ocr
from app.vision.schemas import OCRBlock


class PaddleOCREngine:
    """延迟加载 OCR 模型，避免 API 服务启动时阻塞。"""

    def __init__(self, language: str = "ch") -> None:
        self.language = language
        self._ocr: PaddleOCR | None = None

    @property
    def engine(self) -> PaddleOCR:
        if self._ocr is None:
            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.language, show_log=False)
        return self._ocr

    def recognize(self, image_path: Path) -> list[OCRBlock]:
        image = preprocess_for_ocr(image_path)
        result = self.engine.ocr(image, cls=True)
        blocks: list[OCRBlock] = []
        for page in result or []:
            for line in page or []:
                box, (text, confidence) = line
                blocks.append(OCRBlock(text=text, confidence=float(confidence), box=[[int(x), int(y)] for x, y in box]))
        return blocks


@lru_cache
def get_ocr_engine(language: str) -> PaddleOCREngine:
    return PaddleOCREngine(language)

