import argparse
import json
import math
import socket
import time
from pathlib import Path
import logging
import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions
from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode


LANDMARKS = {
    "left_hip": vision.PoseLandmark.LEFT_HIP,
    "right_hip": vision.PoseLandmark.RIGHT_HIP,
    "left_knee": vision.PoseLandmark.LEFT_KNEE,
    "right_knee": vision.PoseLandmark.RIGHT_KNEE,
    "left_ankle": vision.PoseLandmark.LEFT_ANKLE,
    "right_ankle": vision.PoseLandmark.RIGHT_ANKLE,
}

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"

class OneEuroFilter:
    """Adaptive low-pass filter: smooths jitter when still, stays responsive when moving."""

    def __init__(self, min_cutoff=1.0, beta=0.3, d_cutoff=1.0):
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        if not math.isfinite(x):
            # A single NaN from MediaPipe must never poison x_prev: every later
            # output would be NaN, producing invalid JSON that the Unity receiver
            # silently rejects — freezing the avatar on the last good packet.
            return self.x_prev if self.x_prev is not None else 0.0

        if self.x_prev is None or self.t_prev is None:
            self.x_prev = x
            self.t_prev = t
            return x

        dt = t - self.t_prev
        if dt <= 0.0:
            return self.x_prev

        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self.dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self.x_prev

        self.x_prev = x_hat
        self.dx_prev = dx_hat
        self.t_prev = t
        return x_hat


class LandmarkSmoother:
    """Holds one OneEuroFilter per (landmark, axis); z uses a lower cutoff (noisier)."""

    def __init__(self, min_cutoff=1.0, beta=0.3, d_cutoff=1.0, z_min_cutoff=0.6):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.z_min_cutoff = z_min_cutoff
        self._filters = {}

    def smooth(self, name, axis, value, timestamp):
        key = (name, axis)
        euro = self._filters.get(key)
        if euro is None:
            min_cutoff = self.z_min_cutoff if axis == "z" else self.min_cutoff
            euro = OneEuroFilter(min_cutoff=min_cutoff, beta=self.beta, d_cutoff=self.d_cutoff)
            self._filters[key] = euro
        return euro(value, timestamp)


def finite(value, fallback=0.0):
    return value if math.isfinite(value) else fallback


def build_packet(result, smoother):
    if not result.pose_landmarks:
        return {
            "timestamp": time.time(),
            "tracked": False,
            "coordinate_space": "none",
            "landmarks": [],
        }

    image_landmarks = result.pose_landmarks[0]
    world_landmarks = result.pose_world_landmarks[0] if result.pose_world_landmarks else None
    source_landmarks = world_landmarks if world_landmarks else image_landmarks
    filter_time = time.perf_counter()
    landmarks = []

    for name, landmark_id in LANDMARKS.items():
        landmark_index = int(landmark_id)
        landmark = source_landmarks[landmark_index]
        image_landmark = image_landmarks[landmark_index]
        landmarks.append(
            {
                "name": name,
                "x": finite(smoother.smooth(name, "x", landmark.x, filter_time)),
                "y": finite(smoother.smooth(name, "y", landmark.y, filter_time)),
                "z": finite(smoother.smooth(name, "z", landmark.z, filter_time)),
                "visibility": finite(image_landmark.visibility),
                "image_x": finite(image_landmark.x),
                "image_y": finite(image_landmark.y),
            }
        )

    return {
        "timestamp": time.time(),
        "tracked": True,
        "coordinate_space": "world" if world_landmarks else "image",
        "landmarks": landmarks,
    }


def draw_lower_body_landmarks(frame, packet):
    height, width = frame.shape[:2]

    for landmark in packet["landmarks"]:
        if landmark["visibility"] < 0.5:
            continue

        x = int(landmark["image_x"] * width)
        y = int(landmark["image_y"] * height)
        cv2.circle(frame, (x, y), 7, (0, 255, 0), -1)


def ensure_model_exists(model_path):
    if model_path.exists():
        return

    command = (
        "Invoke-WebRequest "
        f"-Uri \"{MODEL_URL}\" "
        f"-OutFile \"{model_path}\""
    )
    raise FileNotFoundError(
        f"Missing MediaPipe pose model:\n  {model_path}\n\n"
        "Download it with PowerShell:\n"
        f"  {command}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Send MediaPipe lower-body pose landmarks to Unity over UDP.")
    parser.add_argument("--host", default="127.0.0.1", help="Unity receiver host.")
    parser.add_argument("--port", type=int, default=5055, help="Unity receiver UDP port.")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--width", type=int, default=1280, help="Camera capture width.")
    parser.add_argument("--height", type=int, default=720, help="Camera capture height.")
    parser.add_argument("--model", default="Tools/pose_landmarker_lite.task", help="MediaPipe Pose Landmarker .task model path.")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.0, help="One-Euro min cutoff for x/y (lower = smoother, more lag).")
    parser.add_argument("--smooth-beta", type=float, default=0.3, help="One-Euro speed coefficient (higher = less lag on fast moves).")
    parser.add_argument("--smooth-z-min-cutoff", type=float, default=0.6, help="One-Euro min cutoff for the noisier z axis.")
    parser.add_argument("--no-preview", action="store_true", help="Run without an OpenCV preview window.")
    args = parser.parse_args()

    model_path = Path(args.model)
    ensure_model_exists(model_path)

    smoother = LandmarkSmoother(
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
        z_min_cutoff=args.smooth_z_min_cutoff,
    )

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    capture = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera index {args.camera}.")

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=VisionTaskRunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_segmentation_masks=False,
    )

    with vision.PoseLandmarker.create_from_options(options) as pose:
        print(f"Model:  {model_path}")
        print(f"Sending MediaPipe pose UDP to {args.host}:{args.port}. Press Q to quit.")
        cv2.namedWindow("MediaPipe Pose UDP", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("MediaPipe Pose UDP", 960, 540)

        last_packet_log_time = 0.0

        while True:
            ok, frame = capture.read()
            if not ok:
                print("Camera frame not available.")
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            timestamp_ms = int(time.time() * 1000)
            result = pose.detect_for_video(image, timestamp_ms)

            packet = build_packet(result, smoother)
            # allow_nan=False: crash loudly here rather than emit invalid JSON
            # that Unity would silently drop while keeping the last good pose.
            data = json.dumps(packet, separators=(",", ":"), allow_nan=False).encode("utf-8")
            sender.sendto(data, (args.host, args.port))

            now = time.time()
            if now - last_packet_log_time >= 2.0:
                last_packet_log_time = now
                if packet["tracked"]:
                    sent = " | ".join(
                        f"{lm['name']} ({lm['x']:.3f}, {lm['y']:.3f}, {lm['z']:.3f})"
                        for lm in packet["landmarks"])
                    print(f"sent: {sent}")
                else:
                    print("sent: not tracked")
            if not args.no_preview:
                if packet["tracked"]:
                    draw_lower_body_landmarks(frame, packet)


                cv2.imshow("MediaPipe Pose UDP", frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    capture.release()
    sender.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
