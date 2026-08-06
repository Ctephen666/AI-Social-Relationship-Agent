import numpy as np

from app.vision.spark_detector import SparkDetector


def test_orange_spark_is_classified_as_active() -> None:
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    image[:, :] = (0, 165, 255)  # BGR orange

    result = SparkDetector().detect(image)

    assert result.status == "active"
    assert result.confidence >= 0.9


def test_empty_crop_is_classified_as_none() -> None:
    result = SparkDetector().detect(None)

    assert result.status == "none"
    assert result.confidence == 0.0
