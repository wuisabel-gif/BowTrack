from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Dict, Optional, Tuple

import cv2

# Avoid MediaPipe/Matplotlib cache warnings in sandboxed environments.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import mediapipe as mp


@dataclass
class PoseFrame:
    pose_landmarks: object
    pose_world_landmarks: object
    named_landmarks: Dict[str, object]


class PoseTracker:
    """Wrapper around MediaPipe Pose for upper-body tracking."""

    def __init__(
        self,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        if not hasattr(mp, "solutions"):
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "This project currently uses the MediaPipe Solutions API, "
                f"but the installed mediapipe {version} build does not expose "
                "'mediapipe.solutions'. Use Python 3.10-3.12 with a compatible "
                "MediaPipe build, or migrate the tracker to the newer Tasks API."
            )
        self.mp_pose = mp.solutions.pose
        self.mp_draw = mp.solutions.drawing_utils
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=model_complexity,
            enable_segmentation=False,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(self, frame_bgr) -> Optional[PoseFrame]:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        if not results.pose_landmarks:
            return None

        landmarks = results.pose_landmarks.landmark
        named_landmarks = {
            "right_shoulder": landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER],
            "right_elbow": landmarks[self.mp_pose.PoseLandmark.RIGHT_ELBOW],
            "right_wrist": landmarks[self.mp_pose.PoseLandmark.RIGHT_WRIST],
        }
        return PoseFrame(
            pose_landmarks=results.pose_landmarks,
            pose_world_landmarks=results.pose_world_landmarks,
            named_landmarks=named_landmarks,
        )

    def draw(self, frame_bgr, pose_frame: PoseFrame) -> None:
        self.mp_draw.draw_landmarks(
            frame_bgr,
            pose_frame.pose_landmarks,
            self.mp_pose.POSE_CONNECTIONS,
        )

    def close(self) -> None:
        self.pose.close()

    @staticmethod
    def to_pixel_coordinates(landmark, frame_shape) -> Tuple[int, int]:
        height, width = frame_shape[:2]
        return int(landmark.x * width), int(landmark.y * height)
