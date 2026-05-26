from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import numpy as np


def angle_between(p1, p2) -> float:
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    return math.degrees(math.atan2(dy, dx))


@dataclass
class TechniqueSnapshot:
    bow_arm_angle_deg: float
    shoulder_elevation: float
    smoothness_score: float
    wrist_speed: float
    feedback: List[str] = field(default_factory=list)


class MotionAnalyzer:
    """Tracks short-term technique metrics from pose landmarks."""

    def __init__(
        self,
        history_size: int = 30,
        shoulder_raise_threshold: float = 0.03,
        smoothness_warning_threshold: float = 0.025,
    ) -> None:
        self.history_size = history_size
        self.shoulder_raise_threshold = shoulder_raise_threshold
        self.smoothness_warning_threshold = smoothness_warning_threshold
        self.shoulder_baseline_y: Optional[float] = None
        self.wrist_history: Deque[Tuple[float, float]] = deque(maxlen=history_size)
        self.speed_history: Deque[float] = deque(maxlen=history_size)

    def update(self, shoulder, elbow, wrist) -> TechniqueSnapshot:
        if self.shoulder_baseline_y is None:
            self.shoulder_baseline_y = shoulder.y

        shoulder_elevation = max(0.0, self.shoulder_baseline_y - shoulder.y)
        bow_arm_angle_deg = angle_between(elbow, wrist)

        wrist_point = (wrist.x, wrist.y)
        wrist_speed = 0.0
        if self.wrist_history:
            prev_x, prev_y = self.wrist_history[-1]
            wrist_speed = math.dist((prev_x, prev_y), wrist_point)
        self.wrist_history.append(wrist_point)
        self.speed_history.append(wrist_speed)

        smoothness_score = self._compute_smoothness()
        feedback = self._generate_feedback(
            shoulder_elevation=shoulder_elevation,
            smoothness_score=smoothness_score,
            wrist_speed=wrist_speed,
        )

        return TechniqueSnapshot(
            bow_arm_angle_deg=bow_arm_angle_deg,
            shoulder_elevation=shoulder_elevation,
            smoothness_score=smoothness_score,
            wrist_speed=wrist_speed,
            feedback=feedback,
        )

    def get_wrist_path(self) -> List[Tuple[float, float]]:
        return list(self.wrist_history)

    def _compute_smoothness(self) -> float:
        if len(self.speed_history) < 3:
            return 0.0
        speeds = np.array(self.speed_history, dtype=np.float32)
        return float(np.std(np.diff(speeds)))

    def _generate_feedback(
        self,
        shoulder_elevation: float,
        smoothness_score: float,
        wrist_speed: float,
    ) -> List[str]:
        feedback: List[str] = []

        if shoulder_elevation > self.shoulder_raise_threshold:
            feedback.append("Shoulder looks elevated")
        else:
            feedback.append("Shoulder posture looks relaxed")

        if smoothness_score > self.smoothness_warning_threshold:
            feedback.append("Bowing motion may be jerky")
        else:
            feedback.append("Bowing motion looks smooth")

        if wrist_speed < 0.002:
            feedback.append("Very little wrist movement detected")

        return feedback
