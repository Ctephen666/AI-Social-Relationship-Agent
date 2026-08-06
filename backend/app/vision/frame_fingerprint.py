from __future__ import annotations

import cv2
import numpy as np


def difference_hash(image: np.ndarray, hash_size: int = 16) -> int:
    """Return a compact perceptual hash used to detect an unchanged scroll page."""
    if image.size == 0:
        return 0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    bits = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in bits.flat:
        value = (value << 1) | int(bit)
    return value


def hash_similarity(first: int, second: int, bits: int = 256) -> float:
    return 1.0 - ((first ^ second).bit_count() / bits)
