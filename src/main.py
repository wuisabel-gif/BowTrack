from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import cv2

from bow_detector import BowDetector
from metrics import MotionAnalyzer
from pose_tracker import PoseTracker
from visualize import draw_bow_line, draw_metrics, draw_wrist_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cello bow motion and posture tracker")
    parser.add_argument("--input", type=str, help="Path to an input video file")
    parser.add_argument("--camera", type=int, default=None, help="Webcam index")
    parser.add_argument("--output", type=str, help="Optional output video path")
    parser.add_argument(
        "--show-bow-line",
        action="store_true",
        help="Run experimental straight-line detection",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Disable preview window",
    )
    return parser.parse_args()


def open_capture(input_path: Optional[str], camera_index: Optional[int]) -> cv2.VideoCapture:
    if input_path:
        return cv2.VideoCapture(input_path)
    if camera_index is not None:
        return cv2.VideoCapture(camera_index)
    return cv2.VideoCapture(0)


def build_writer(output_path: str, capture: cv2.VideoCapture) -> Optional[cv2.VideoWriter]:
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(str(output_file), fourcc, fps, (width, height))


def main() -> None:
    args = parse_args()
    capture = open_capture(args.input, args.camera)
    if not capture.isOpened():
        raise RuntimeError("Unable to open video source")

    writer = build_writer(args.output, capture) if args.output else None
    pose_tracker = PoseTracker()
    motion_analyzer = MotionAnalyzer()
    bow_detector = BowDetector() if args.show_bow_line else None

    try:
        while capture.isOpened():
            ret, frame = capture.read()
            if not ret:
                break

            pose_frame = pose_tracker.process(frame)
            if pose_frame:
                pose_tracker.draw(frame, pose_frame)
                landmarks = pose_frame.named_landmarks
                snapshot = motion_analyzer.update(
                    landmarks["right_shoulder"],
                    landmarks["right_elbow"],
                    landmarks["right_wrist"],
                )
                draw_metrics(frame, snapshot)
                draw_wrist_path(frame, motion_analyzer.get_wrist_path())

            if bow_detector is not None:
                draw_bow_line(frame, bow_detector.detect(frame))

            if writer:
                writer.write(frame)

            if not args.no_display:
                cv2.imshow("Jetson Cello Bow Motion Tracker", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        capture.release()
        if writer:
            writer.release()
        pose_tracker.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
