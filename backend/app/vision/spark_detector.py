from __future__ import annotations

from typing import Literal

import cv2
import numpy as np
from pydantic import BaseModel


class SparkDetection(BaseModel):
    status: Literal["active", "gray", "none"]
    confidence: float
    warm_ratio: float = 0.0
    gray_ratio: float = 0.0
    colorful_ratio: float = 0.0
    component_score: float = 0.0


class SparkDetector:
    """Connected-component HSV classifier tuned for tiny Douyin status icons.

    Requiring a compact saturated component is substantially less sensitive to
    anti-aliased white text and dark-theme background than a global pixel ratio.
    """

    def detect(self, image: np.ndarray | None) -> SparkDetection:
        if image is None or image.size == 0 or image.shape[0] < 3 or image.shape[1] < 3:
            return SparkDetection(status="none", confidence=0.0)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        warm = cv2.inRange(hsv, np.array([3, 105, 115]), np.array([43, 255, 255]))
        cyan = cv2.inRange(hsv, np.array([78, 105, 110]), np.array([112, 255, 255]))
        magenta = cv2.inRange(hsv, np.array([125, 95, 110]), np.array([175, 255, 255]))
        colorful = cv2.bitwise_or(warm, cv2.bitwise_or(cyan, magenta))
        colorful = cv2.morphologyEx(colorful, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

        pixels = float(hsv.shape[0] * hsv.shape[1])
        warm_ratio = cv2.countNonZero(warm) / pixels
        colorful_ratio = cv2.countNonZero(colorful) / pixels
        component_score = self._component_score(colorful, pixels)
        if component_score >= 0.22 or colorful_ratio >= 0.012:
            confidence = min(0.995, 0.58 + component_score * 0.34 + min(colorful_ratio, 0.20) * 2.0)
            return SparkDetection(
                status="active",
                confidence=round(confidence, 3),
                warm_ratio=round(warm_ratio, 4),
                gray_ratio=0.0,
                colorful_ratio=round(colorful_ratio, 4),
                component_score=round(component_score, 4),
            )

        # Gray detection considers only mid-tone compact shapes. Near-white text
        # and the dark panel background are excluded before component scoring.
        gray = cv2.inRange(hsv, np.array([0, 0, 72]), np.array([180, 42, 185]))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        gray_ratio = cv2.countNonZero(gray) / pixels
        gray_component = self._component_score(gray, pixels)
        if gray_component >= 0.34 and 0.006 <= gray_ratio <= 0.28:
            return SparkDetection(
                status="gray",
                confidence=round(min(0.92, 0.52 + gray_component * 0.38), 3),
                warm_ratio=round(warm_ratio, 4),
                gray_ratio=round(gray_ratio, 4),
                colorful_ratio=round(colorful_ratio, 4),
                component_score=round(gray_component, 4),
            )
        return SparkDetection(
            status="none",
            confidence=round(max(0.5, min(0.96, 0.92 - max(colorful_ratio, gray_ratio) * 1.5)), 3),
            warm_ratio=round(warm_ratio, 4),
            gray_ratio=round(gray_ratio, 4),
            colorful_ratio=round(colorful_ratio, 4),
            component_score=round(max(component_score, gray_component), 4),
        )

    @staticmethod
    def _component_score(mask: np.ndarray, pixels: float) -> float:
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best = 0.0
        min_area = max(3, int(pixels * 0.0006))
        for index in range(1, count):
            x, y, width, height, area = stats[index]
            if area < min_area or width < 2 or height < 2:
                continue
            if width > mask.shape[1] * 0.55 or height > mask.shape[0] * 0.95:
                continue
            fill = area / float(width * height)
            size = min(1.0, area / max(10.0, pixels * 0.025))
            shape = min(width, height) / max(width, height)
            best = max(best, size * 0.55 + fill * 0.25 + shape * 0.20)
        return best
