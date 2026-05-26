from __future__ import annotations

from typing import Iterable, Optional, Tuple

import cv2

from metrics import TechniqueSnapshot


def draw_wrist_path(frame_bgr, wrist_path: Iterable[Tuple[float, float]]) -> None:
    height, width = frame_bgr.shape[:2]
    pixel_points = [
        (int(x * width), int(y * height))
        for x, y in wrist_path
    ]
    for i in range(1, len(pixel_points)):
        cv2.line(frame_bgr, pixel_points[i - 1], pixel_points[i], (0, 255, 255), 2)


def draw_metrics(frame_bgr, snapshot: TechniqueSnapshot) -> None:
    overlays = [
        f"Bow arm angle: {snapshot.bow_arm_angle_deg:.1f} deg",
        f"Shoulder elevation: {snapshot.shoulder_elevation:.3f}",
        f"Smoothness score: {snapshot.smoothness_score:.4f}",
        f"Wrist speed: {snapshot.wrist_speed:.4f}",
    ]

    for idx, text in enumerate(overlays):
        y = 35 + idx * 30
        cv2.putText(
            frame_bgr,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
        )

    for idx, text in enumerate(snapshot.feedback):
        y = 170 + idx * 28
        cv2.putText(
            frame_bgr,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (80, 255, 80),
            2,
        )


def draw_bow_line(frame_bgr, line: Optional[Tuple[int, int, int, int]]) -> None:
    if line is None:
        return
    x1, y1, x2, y2 = line
    cv2.line(frame_bgr, (x1, y1), (x2, y2), (0, 165, 255), 2)
    cv2.putText(
        frame_bgr,
        "Candidate bow line",
        (x1, max(20, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 165, 255),
        2,
    )
