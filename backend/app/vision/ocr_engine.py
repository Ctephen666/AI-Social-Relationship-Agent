from __future__ import annotations

import inspect
import json
import os
import threading
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from app.core.runtime import data_directory
from app.vision.schemas import OCRBlock


class OCREngine(Protocol):
    def recognize(self, image_path: Path) -> list[OCRBlock]: ...

    def recognize_image(self, image: np.ndarray) -> list[OCRBlock]: ...


class RapidOCREngine:
    """Low-latency ONNX OCR for the visual fallback path."""

    def __init__(self, language: str = "ch") -> None:
        self.language = language
        self._engine: Any = None
        self._lock = threading.RLock()

    @property
    def engine(self) -> Any:
        if self._engine is None:
            with self._lock:
                if self._engine is None:
                    from rapidocr import RapidOCR

                    self._engine = RapidOCR()
        return self._engine

    def recognize(self, image_path: Path) -> list[OCRBlock]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"无法读取图片：{image_path}")
        return self.recognize_image(image)

    def recognize_image(self, image: np.ndarray) -> list[OCRBlock]:
        if image.size == 0:
            return []
        with self._lock:
            output = self.engine(image)
        boxes = getattr(output, "boxes", None)
        texts = getattr(output, "txts", None) or getattr(output, "texts", None)
        scores = getattr(output, "scores", None)
        if boxes is not None and texts is not None and scores is not None:
            return self._from_columns(boxes, texts, scores)

        # RapidOCR 1/2 compatibility: (results, elapsed), with each result
        # represented as [box, text, score].
        payload = output[0] if isinstance(output, tuple) else output
        blocks: list[OCRBlock] = []
        for item in payload or []:
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
            box, text, score = item[0], item[1], item[2]
            points = _normalise_box(box)
            if points:
                blocks.append(OCRBlock(text=str(text), confidence=float(score), box=points))
        return blocks

    @staticmethod
    def _from_columns(boxes: Any, texts: Any, scores: Any) -> list[OCRBlock]:
        blocks: list[OCRBlock] = []
        for box, text, score in zip(boxes, texts, scores):
            points = _normalise_box(box)
            if points:
                blocks.append(OCRBlock(text=str(text), confidence=float(score), box=points))
        return blocks


class PaddleOCREngine:
    """Optional compatibility fallback. Paddle imports lazily and never affect fast startup."""

    def __init__(self, language: str = "ch") -> None:
        self.language = language
        self._ocr: Any = None
        self._major_version = 3

    @property
    def engine(self) -> Any:
        if self._ocr is None:
            cache = data_directory() / "paddlex"
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache))
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
            import paddleocr
            from paddleocr import PaddleOCR

            self._major_version = int(getattr(paddleocr, "__version__", "3").split(".", maxsplit=1)[0])
            parameters = inspect.signature(PaddleOCR).parameters
            if "show_log" in parameters:
                self._ocr = PaddleOCR(use_angle_cls=False, lang=self.language, show_log=False)
            else:
                self._ocr = PaddleOCR(
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    text_recognition_model_name="PP-OCRv5_mobile_rec",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
        return self._ocr

    def recognize(self, image_path: Path) -> list[OCRBlock]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"无法读取图片：{image_path}")
        return self.recognize_image(image)

    def recognize_image(self, image: np.ndarray) -> list[OCRBlock]:
        return self._recognize_v3(image) if self._major_version >= 3 else self._recognize_v2(image)

    def _recognize_v2(self, image: np.ndarray) -> list[OCRBlock]:
        result = self.engine.ocr(image, cls=False)
        blocks: list[OCRBlock] = []
        for page in result or []:
            for line in page or []:
                box, (text, confidence) = line
                blocks.append(OCRBlock(text=str(text), confidence=float(confidence), box=_normalise_box(box)))
        return blocks

    def _recognize_v3(self, image: np.ndarray) -> list[OCRBlock]:
        results = self.engine.predict(
            image,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        blocks: list[OCRBlock] = []
        for page in results:
            payload = _as_mapping(page)
            data = payload.get("res", payload.get("data", payload))
            texts = data.get("rec_texts", data.get("texts", [])) or []
            scores = data.get("rec_scores", data.get("scores", [])) or []
            boxes = data.get("rec_boxes", data.get("rec_polys", data.get("dt_polys", []))) or []
            for box, text, score in zip(boxes, texts, scores):
                points = _normalise_box(box)
                if points:
                    blocks.append(OCRBlock(text=str(text), confidence=float(score), box=points))
        return blocks


class ResilientOCREngine:
    """Use the configured engine and fail over once when an optional backend is absent."""

    def __init__(self, primary: OCREngine, fallback: OCREngine | None = None) -> None:
        self.primary = primary
        self.fallback = fallback

    def recognize(self, image_path: Path) -> list[OCRBlock]:
        try:
            return self.primary.recognize(image_path)
        except (ImportError, ModuleNotFoundError):
            if self.fallback is None:
                raise RuntimeError("OCR 后端未安装，请执行 pip install -r requirements.txt。")
            return self.fallback.recognize(image_path)

    def recognize_image(self, image: np.ndarray) -> list[OCRBlock]:
        try:
            return self.primary.recognize_image(image)
        except (ImportError, ModuleNotFoundError):
            if self.fallback is None:
                raise RuntimeError("OCR 后端未安装，请执行 pip install -r requirements.txt。")
            return self.fallback.recognize_image(image)


def _as_mapping(result: Any) -> Mapping[str, Any]:
    if isinstance(result, Mapping):
        return result
    if hasattr(result, "to_dict"):
        value = result.to_dict()
        if isinstance(value, Mapping):
            return value
    value = getattr(result, "json", None)
    value = value() if callable(value) else value
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"无法解析 PaddleOCR 结果类型：{type(result).__name__}")


def _normalise_box(box: Any) -> list[list[int]]:
    if hasattr(box, "tolist"):
        box = box.tolist()
    if box is None or len(box) == 0:
        return []
    if isinstance(box[0], (int, float)):
        if len(box) != 4:
            return []
        left, top, right, bottom = box
        return [[int(left), int(top)], [int(right), int(top)], [int(right), int(bottom)], [int(left), int(bottom)]]
    return [[int(point[0]), int(point[1])] for point in box if len(point) >= 2]


@lru_cache(maxsize=4)
def get_ocr_engine(language: str = "ch", backend: str = "rapid") -> OCREngine:
    backend = backend.casefold().strip()
    if backend == "paddle":
        return PaddleOCREngine(language)
    if backend != "rapid":
        raise ValueError(f"不支持的 OCR_BACKEND：{backend}")
    return ResilientOCREngine(RapidOCREngine(language), PaddleOCREngine(language))
