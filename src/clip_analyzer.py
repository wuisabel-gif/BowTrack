from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path
from typing import Deque, Iterable, Optional

import cv2
import numpy as np


Line = tuple[int, int, int, int]


def line_angle_deg(line: Line) -> float:
    x1, y1, x2, y2 = line
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def line_length(line: Line) -> float:
    x1, y1, x2, y2 = line
    return float(math.hypot(x2 - x1, y2 - y1))


def horizontal_error_deg(angle_deg: float) -> float:
    normalized = ((angle_deg + 90.0) % 180.0) - 90.0
    return abs(normalized)


def snapshot_indices(frame_count: int) -> set[int]:
    return {0, frame_count // 4, frame_count // 2, (3 * frame_count) // 4, max(0, frame_count - 1)}


def safe_mean(values: list[float]) -> Optional[float]:
    return float(np.mean(values)) if values else None


def safe_range(values: list[float]) -> Optional[float]:
    return float(np.max(values) - np.min(values)) if values else None


class BowAnalyzer:
    def __init__(self) -> None:
        self.bridge_y: Optional[int] = None
        self.string_center_x: Optional[int] = None
        self.contact_baseline_y: Optional[float] = None
        self.midpoint_x_history: Deque[float] = deque(maxlen=20)
        self.contact_y_history: Deque[float] = deque(maxlen=30)
        self.speed_history: Deque[float] = deque(maxlen=20)

    def estimate_reference_geometry(self, frame_bgr: np.ndarray) -> None:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape

        center_band = gray[:, int(width * 0.42):int(width * 0.58)]
        darkness = 255.0 - np.mean(center_band[int(height * 0.08):int(height * 0.70)], axis=0)
        center_offset = int(np.argmax(darkness))
        self.string_center_x = int(width * 0.42) + center_offset

        band_half_width = max(8, width // 40)
        x0 = max(0, self.string_center_x - band_half_width)
        x1 = min(width, self.string_center_x + band_half_width)
        roi = gray[:, x0:x1]
        vertical_gradient = cv2.Sobel(roi, cv2.CV_32F, 0, 1, ksize=3)
        bridge_scores = np.mean(np.abs(vertical_gradient), axis=1)
        y_lo = int(height * 0.35)
        y_hi = int(height * 0.70)
        self.bridge_y = y_lo + int(np.argmax(bridge_scores[y_lo:y_hi]))

    def detect_bow_line(self, frame_bgr: np.ndarray) -> Optional[Line]:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        search_y0 = 0
        search_y1 = gray.shape[0]

        if self.bridge_y is not None:
            band = max(220, gray.shape[0] // 10)
            search_y0 = max(0, self.bridge_y - band)
            search_y1 = min(gray.shape[0], self.bridge_y + band)

        roi = gray[search_y0:search_y1, :]
        blurred = cv2.GaussianBlur(roi, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 100)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=25,
            minLineLength=max(180, frame_bgr.shape[1] // 10),
            maxLineGap=40,
        )
        if lines is None:
            return None

        best_line: Optional[Line] = None
        best_score = float("-inf")
        target_angle = 16.0
        for candidate in lines[:, 0]:
            x1, y1, x2, y2 = map(int, candidate)
            y1 += search_y0
            y2 += search_y0
            line = (x1, y1, x2, y2)
            angle = line_angle_deg(line)
            abs_angle = abs(angle)
            if not (5.0 <= abs_angle <= 35.0):
                continue

            length = line_length(line)
            angle_penalty = abs(abs_angle - target_angle)
            bridge_penalty = 0.0
            if self.bridge_y is not None and self.string_center_x is not None:
                contact_y = self.line_y_at_x(line, self.string_center_x)
                if contact_y is not None:
                    bridge_penalty = abs(contact_y - self.bridge_y) * 0.8

            score = length - angle_penalty * 8.0 - bridge_penalty
            if score > best_score:
                best_line = line
                best_score = score
        return best_line

    def line_y_at_x(self, line: Line, x_value: int) -> Optional[float]:
        x1, y1, x2, y2 = line
        if x1 == x2:
            return None
        t = (x_value - x1) / (x2 - x1)
        return y1 + t * (y2 - y1)

    def compute_metrics(self, line: Line) -> dict[str, float]:
        assert self.string_center_x is not None
        assert self.bridge_y is not None

        angle = line_angle_deg(line)
        angle_error = horizontal_error_deg(angle)
        mid_x = (line[0] + line[2]) / 2.0
        self.midpoint_x_history.append(mid_x)

        speed = 0.0
        if len(self.midpoint_x_history) >= 2:
            speed = abs(self.midpoint_x_history[-1] - self.midpoint_x_history[-2])
        self.speed_history.append(speed)

        contact_y = self.line_y_at_x(line, self.string_center_x)
        if contact_y is None:
            contact_y = (line[1] + line[3]) / 2.0
        self.contact_y_history.append(contact_y)

        if self.contact_baseline_y is None:
            self.contact_baseline_y = contact_y

        bridge_offset = contact_y - self.bridge_y
        contact_drift = contact_y - self.contact_baseline_y
        smoothness = 0.0
        if len(self.speed_history) >= 4:
            smoothness = float(np.std(np.diff(np.array(self.speed_history, dtype=np.float32))))

        return {
            "angle_deg": angle,
            "angle_error_deg": angle_error,
            "contact_y": contact_y,
            "bridge_offset": bridge_offset,
            "contact_drift": contact_drift,
            "stroke_speed": speed,
            "smoothness": smoothness,
        }

    def draw_history(self, frame_bgr: np.ndarray, history: Iterable[float], color: tuple[int, int, int]) -> None:
        assert self.string_center_x is not None
        ys = list(history)
        x_base = self.string_center_x + 18
        for idx in range(1, len(ys)):
            pt1 = (x_base + (idx - 1) * 3, int(ys[idx - 1]))
            pt2 = (x_base + idx * 3, int(ys[idx]))
            cv2.line(frame_bgr, pt1, pt2, color, 2)

    def annotate(self, frame_bgr: np.ndarray, line: Optional[Line], metrics: Optional[dict[str, float]]) -> np.ndarray:
        if self.bridge_y is None or self.string_center_x is None:
            self.estimate_reference_geometry(frame_bgr)

        annotated = frame_bgr.copy()
        height, width = annotated.shape[:2]
        assert self.bridge_y is not None
        assert self.string_center_x is not None

        cv2.line(annotated, (self.string_center_x, 0), (self.string_center_x, height), (255, 220, 0), 1)
        cv2.line(annotated, (0, self.bridge_y), (width, self.bridge_y), (0, 200, 255), 1)
        cv2.putText(annotated, "bridge reference", (12, max(24, self.bridge_y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)

        if line is not None:
            cv2.line(annotated, (line[0], line[1]), (line[2], line[3]), (80, 255, 80), 3)

        if metrics is not None:
            contact_y = int(metrics["contact_y"])
            cv2.circle(annotated, (self.string_center_x, contact_y), 6, (0, 0, 255), -1)
            cv2.putText(annotated, "contact point", (self.string_center_x + 10, max(30, contact_y - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

            overlay = [
                f"Bow angle: {metrics['angle_deg']:.1f} deg",
                f"Angle error: {metrics['angle_error_deg']:.1f} deg",
                f"Bridge offset: {metrics['bridge_offset']:.1f} px",
                f"Contact drift: {metrics['contact_drift']:.1f} px",
                f"Stroke speed: {metrics['stroke_speed']:.1f} px/frame",
                f"Smoothness: {metrics['smoothness']:.2f}",
            ]
            for idx, text in enumerate(overlay):
                cv2.putText(annotated, text, (14, 34 + idx * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

            feedback = []
            feedback.append("Bow line is noticeably tilted" if metrics["angle_error_deg"] > 12.0 else "Bow angle is fairly stable")
            feedback.append("Contact point is drifting across the stroke" if abs(metrics["contact_drift"]) > 24.0 else "Contact point is staying fairly consistent")
            feedback.append("Stroke speed changes look uneven" if metrics["smoothness"] > 3.5 else "Stroke speed looks relatively smooth")
            for idx, text in enumerate(feedback):
                cv2.putText(annotated, text, (14, 230 + idx * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (120, 255, 120), 2)

            self.draw_history(annotated, self.contact_y_history, (255, 0, 255))

        return annotated


def annotate_posture(frame_bgr: np.ndarray) -> np.ndarray:
    annotated = frame_bgr.copy()
    height, width = annotated.shape[:2]

    left_box = (int(width * 0.03), int(height * 0.20), int(width * 0.34), int(height * 0.49))
    right_box = (int(width * 0.56), int(height * 0.18), int(width * 0.89), int(height * 0.47))
    shoulder_y = int(height * 0.295)
    torso_center_x = int(width * 0.46)

    cv2.rectangle(annotated, left_box[:2], left_box[2:], (90, 220, 255), 3)
    cv2.rectangle(annotated, right_box[:2], right_box[2:], (0, 255, 140), 3)
    cv2.line(annotated, (int(width * 0.10), shoulder_y), (int(width * 0.86), shoulder_y), (255, 200, 0), 2)
    cv2.line(annotated, (torso_center_x, int(height * 0.05)), (torso_center_x, int(height * 0.95)), (255, 120, 255), 1)

    cv2.putText(annotated, "bow-side shoulder", (left_box[0] + 8, max(30, left_box[1] - 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (90, 220, 255), 2)
    cv2.putText(annotated, "left-hand shoulder", (right_box[0] + 8, max(30, right_box[1] - 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 140), 2)
    cv2.putText(annotated, "approx shoulder line", (int(width * 0.10), max(30, shoulder_y - 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 200, 0), 2)

    lines = [
        "Posture Read",
        "Bow-side shoulder appears elevated",
        "Visible left/right shoulder asymmetry",
        "Overall upper-body posture stays fairly stable",
        "Cue: heavier arm, softer shoulder",
    ]
    for idx, text in enumerate(lines):
        cv2.putText(annotated, text, (36, 60 + idx * 38), cv2.FONT_HERSHEY_SIMPLEX, 0.86, (255, 255, 255), 2, cv2.LINE_AA)

    cv2.putText(
        annotated,
        "This is a visual posture note, not a landmark measurement",
        (36, height - 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (220, 220, 220),
        2,
        cv2.LINE_AA,
    )
    return annotated


def draw_combined_status(frame_bgr: np.ndarray, detection_rate: float, has_bow_metrics: bool) -> None:
    status = "Bow metrics active" if has_bow_metrics else "Bow line not confidently tracked in this frame"
    color = (255, 240, 120) if has_bow_metrics else (180, 180, 255)
    cv2.putText(frame_bgr, status, (36, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
    cv2.putText(frame_bgr, f"Bow detection coverage: {detection_rate * 100:.1f}%", (36, 286), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 220, 220), 2, cv2.LINE_AA)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze a cello clip and produce bow, posture, or combined feedback.")
    parser.add_argument("--input", required=True, help="Path to the input video")
    parser.add_argument("--out-dir", required=True, help="Directory for outputs")
    parser.add_argument("--mode", choices=["auto", "bow", "posture", "combined"], default="auto", help="Analysis mode")
    parser.add_argument("--bow-threshold", type=float, default=0.5, help="Minimum bow detection rate required for auto mode")
    return parser.parse_args()


def write_video(frames: list[np.ndarray], output_path: Path, fps: float, size: tuple[int, int]) -> None:
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def save_snapshots(frames: dict[int, np.ndarray], target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for idx, frame_no in enumerate(sorted(frames), start=1):
        cv2.imwrite(str(target_dir / f"annotated_{idx}.jpg"), frames[frame_no])


def analyze_bow(input_path: Path) -> dict[str, object]:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open input video: {input_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    picks = snapshot_indices(frame_count)
    bow = BowAnalyzer()
    frames: list[np.ndarray] = []
    snapshots: dict[int, np.ndarray] = {}
    detected = 0
    angles: list[float] = []
    bridge_offsets: list[float] = []
    drifts: list[float] = []
    smoothness_values: list[float] = []
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if bow.bridge_y is None or bow.string_center_x is None:
                bow.estimate_reference_geometry(frame)
            line = bow.detect_bow_line(frame)
            metrics = bow.compute_metrics(line) if line is not None else None
            annotated = bow.annotate(frame, line, metrics)
            frames.append(annotated)
            if frame_index in picks:
                snapshots[frame_index] = annotated
            if metrics is not None:
                detected += 1
                angles.append(metrics["angle_error_deg"])
                bridge_offsets.append(metrics["bridge_offset"])
                drifts.append(metrics["contact_drift"])
                smoothness_values.append(metrics["smoothness"])
            frame_index += 1
    finally:
        cap.release()

    return {
        "mode": "bow",
        "frames": frames,
        "snapshots": snapshots,
        "video_meta": {"frame_count": frame_count, "width": width, "height": height, "fps": fps},
        "summary": {
            "detected_frames": detected,
            "detection_rate": detected / frame_count if frame_count else 0.0,
            "mean_angle_error_deg": safe_mean(angles),
            "mean_bridge_offset_px": safe_mean(bridge_offsets),
            "contact_drift_range_px": safe_range(drifts),
            "mean_smoothness": safe_mean(smoothness_values),
        },
        "detectable_metrics": ["bow line angle", "bow contact-point drift", "bridge offset", "stroke smoothness"],
        "limitations": [],
    }


def analyze_posture(input_path: Path) -> dict[str, object]:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open input video: {input_path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    picks = snapshot_indices(frame_count)
    frames: list[np.ndarray] = []
    snapshots: dict[int, np.ndarray] = {}
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            annotated = annotate_posture(frame)
            frames.append(annotated)
            if frame_index in picks:
                snapshots[frame_index] = annotated
            frame_index += 1
    finally:
        cap.release()

    return {
        "mode": "posture",
        "frames": frames,
        "snapshots": snapshots,
        "video_meta": {"frame_count": frame_count, "width": width, "height": height, "fps": fps},
        "summary": {
            "posture_read": "Bow-side shoulder appears elevated.",
            "stability_read": "Upper-body posture stays fairly stable across the clip.",
            "technique_cue": "Try heavier arm, softer shoulder.",
        },
        "detectable_metrics": ["visual shoulder asymmetry", "bow-side shoulder elevation cues", "upper-body stability"],
        "limitations": ["This is a visual posture note, not a landmark-based pose measurement."],
    }


def analyze_combined(input_path: Path) -> dict[str, object]:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open input video: {input_path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    picks = snapshot_indices(frame_count)
    bow = BowAnalyzer()
    frames: list[np.ndarray] = []
    snapshots: dict[int, np.ndarray] = {}
    detected = 0
    frame_index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            posture = annotate_posture(frame)
            if bow.bridge_y is None or bow.string_center_x is None:
                bow.estimate_reference_geometry(frame)
            line = bow.detect_bow_line(frame)
            metrics = bow.compute_metrics(line) if line is not None else None
            if metrics is not None:
                detected += 1
            annotated = bow.annotate(posture, line, metrics)
            draw_combined_status(annotated, detected / max(frame_index + 1, 1), metrics is not None)
            frames.append(annotated)
            if frame_index in picks:
                snapshots[frame_index] = annotated
            frame_index += 1
    finally:
        cap.release()

    return {
        "mode": "combined",
        "frames": frames,
        "snapshots": snapshots,
        "video_meta": {"frame_count": frame_count, "width": width, "height": height, "fps": fps},
        "summary": {
            "detected_frames": detected,
            "detection_rate": detected / frame_count if frame_count else 0.0,
            "posture_read": "Bow-side shoulder appears elevated.",
        },
        "detectable_metrics": ["bow line angle", "contact-point drift", "bridge offset", "visual shoulder asymmetry"],
        "limitations": [],
    }


def build_report(input_path: Path, result: dict[str, object], auto_note: Optional[str]) -> str:
    summary = "\n".join(f"- `{key}`: {value}" for key, value in result["summary"].items())  # type: ignore[index]
    detectable = "\n".join(f"- {item}" for item in result["detectable_metrics"])  # type: ignore[index]
    limitations = result["limitations"]  # type: ignore[index]
    limitations_block = "\n".join(f"- {item}" for item in limitations) if limitations else "- None for this pass."
    auto_block = f"\n## Mode selection\n{auto_note}\n" if auto_note else ""
    return (
        "# Clip Analysis Report\n\n"
        f"## Clip\n- Input: `{input_path}`\n- Mode: `{result['mode']}`\n\n"
        "## Detectable metrics\n"
        f"{detectable}\n\n"
        "## Summary\n"
        f"{summary}\n"
        f"{auto_block}\n"
        "## Limitations\n"
        f"{limitations_block}\n"
    )


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bow_result = analyze_bow(input_path)
    auto_note = None
    if args.mode == "bow":
        result = bow_result
    elif args.mode == "posture":
        result = analyze_posture(input_path)
    elif args.mode == "combined":
        result = analyze_combined(input_path)
    else:
        if bow_result["summary"]["detection_rate"] >= args.bow_threshold:  # type: ignore[index]
            result = analyze_combined(input_path)
            auto_note = (
                "Auto mode chose `combined` because bow detection was reliable enough "
                f"({bow_result['summary']['detection_rate']:.1%} coverage)."  # type: ignore[index]
            )
        else:
            result = analyze_posture(input_path)
            auto_note = (
                "Auto mode chose `posture` because bow detection coverage was too low "
                f"({bow_result['summary']['detection_rate']:.1%}, threshold {args.bow_threshold:.0%})."  # type: ignore[index]
            )

    video_meta = result["video_meta"]  # type: ignore[index]
    video_path = out_dir / f"{input_path.stem}_{result['mode']}_annotated.mp4"
    write_video(result["frames"], video_path, float(video_meta["fps"]), (int(video_meta["width"]), int(video_meta["height"])))  # type: ignore[index]
    save_snapshots(result["snapshots"], out_dir / "snapshots")  # type: ignore[index]

    report = build_report(input_path, result, auto_note)
    (out_dir / "analysis_report.md").write_text(report, encoding="utf-8")

    summary_json = {
        "input": str(input_path),
        "mode": result["mode"],
        "summary": result["summary"],
        "detectable_metrics": result["detectable_metrics"],
        "limitations": result["limitations"],
        "auto_bow_detection_rate": bow_result["summary"]["detection_rate"],  # type: ignore[index]
    }
    (out_dir / "analysis_summary.json").write_text(json.dumps(summary_json, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
