from pathlib import Path

import cv2
import numpy as np


def preprocess_for_ocr(image_path: Path) -> np.ndarray:
    """轻量预处理，保留聊天 UI 中的中英文文本边缘。"""
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"无法读取图片：{image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enlarged = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    return cv2.fastNlMeansDenoising(enlarged, None, h=7, templateWindowSize=7, searchWindowSize=21)

