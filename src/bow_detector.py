from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


Line = Tuple[int, int, int, int]


class BowDetector:
    """Experimental straight-line detector that can later be tuned for bow tracking."""

    def __init__(
        self,
        canny_threshold1: int = 50,
        canny_threshold2: int = 150,
        hough_threshold: int = 80,
        min_line_length: int = 120,
        max_line_gap: int = 20,
    ) -> None:
        self.canny_threshold1 = canny_threshold1
        self.canny_threshold2 = canny_threshold2
        self.hough_threshold = hough_threshold
        self.min_line_length = min_line_length
        self.max_line_gap = max_line_gap

    def detect(self, frame_bgr) -> Optional[Line]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, self.canny_threshold1, self.canny_threshold2)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=self.hough_threshold,
            minLineLength=self.min_line_length,
            maxLineGap=self.max_line_gap,
        )
        if lines is None:
            return None

        longest_line = max(lines[:, 0], key=self._line_length)
        return tuple(int(v) for v in longest_line)

    @staticmethod
    def _line_length(line: np.ndarray) -> float:
        x1, y1, x2, y2 = line
        return float(np.hypot(x2 - x1, y2 - y1))
