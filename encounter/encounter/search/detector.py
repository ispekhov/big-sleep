"""Object detection stage.

Production uses Grounding DINO / Florence-2 to localise the design object in a
busy real-world scene (a lamp in a hotel lobby) and crop it before embedding,
which dramatically improves recognition. The default detector is a no-op that
treats the whole frame as a single object, so the pipeline runs without a GPU.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Detection:
    image_bytes: bytes
    label: str | None = None
    score: float = 1.0
    # bbox as (x0, y0, x1, y1) in pixels; None for whole-image.
    bbox: tuple[int, int, int, int] | None = None


class ObjectDetector(abc.ABC):
    @abc.abstractmethod
    def detect(self, image_bytes: bytes) -> list[Detection]:
        """Return one Detection per candidate object (largest first)."""


class WholeImageDetector(ObjectDetector):
    """Fallback: the whole image is the object."""

    def detect(self, image_bytes: bytes) -> list[Detection]:
        return [Detection(image_bytes=image_bytes, label="object", score=1.0)]


@lru_cache
def get_detector() -> ObjectDetector:
    # A GroundingDinoDetector can be selected here via config in the future.
    return WholeImageDetector()
