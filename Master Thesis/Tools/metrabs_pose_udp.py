"""Send MeTRAbs lower-body 3D pose landmarks to Unity over UDP.

Drop-in alternative to mediapipe_pose_udp.py: emits the BYTE-IDENTICAL JSON packet
(same 6 landmark names, meters, hip-centered, same axis convention) so the Unity
MediaPipePoseReceiver needs no changes -- just run this script instead of the
MediaPipe one. Only the model and coordinate-conversion differ.

Run inside the dedicated conda env (has torch+cu121 and the MeTRAbs deps):
    conda activate metrabs
    python Tools/metrabs_pose_udp.py

Requires the cloned MeTRAbs repo + PyTorch model (see --repo / --model-dir defaults).
"""

import argparse
import json
import math
import os
import socket
import sys
import time

import cv2
import numpy as np

# --- MeTRAbs repo / model locations (cloned outside the Unity project) --------
DEFAULT_REPO = r"C:\Users\Meta_Mobile_2\Documents\metrabs"
DEFAULT_MODEL_DIR = os.path.join(DEFAULT_REPO, "metrabs_eff2l_384px_800k_28ds_pytorch")

# The 6 lower-body landmarks, in the exact names the Unity receiver matches on,
# mapped to their smpl_24 joint indices from the MeTRAbs model.
SMPL24_INDEX = {
    "left_hip": 1,
    "right_hip": 2,
    "left_knee": 4,
    "right_knee": 5,
    "left_ankle": 7,
    "right_ankle": 8,
}
LANDMARK_ORDER = ["left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"]


class OneEuroFilter:
    """Adaptive low-pass filter: smooths jitter when still, stays responsive when moving.

    Copied verbatim from mediapipe_pose_udp.py so both sources smooth identically.
    """

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


def load_metrabs_model(repo, model_dir):
    """Assemble the MeTRAbs PyTorch multiperson model (mirrors the repo demo)."""
    os.environ.setdefault("DATA_ROOT", repo)  # dummy; datasets unused at inference
    sys.path.insert(0, repo)

    import torch
    import simplepyutils as spu
    import posepile.joint_info
    import metrabs_pytorch.backbones.efficientnet as effnet_pt
    import metrabs_pytorch.models.metrabs as metrabs_pt
    from metrabs_pytorch.multiperson import multiperson_model
    from metrabs_pytorch.util import get_config

    get_config(os.path.join(model_dir, "config.yaml"))
    cfg = get_config()

    ji_np = np.load(os.path.join(model_dir, "joint_info.npz"))
    ji = posepile.joint_info.JointInfo(ji_np["joint_names"], ji_np["joint_edges"])
    backbone_raw = getattr(effnet_pt, f"efficientnet_v2_{cfg.efficientnet_size}")()
    backbone = torch.nn.Sequential(effnet_pt.PreprocLayer(), backbone_raw.features)
    crop_model = metrabs_pt.Metrabs(backbone, ji)
    crop_model.eval()
    crop_model((torch.zeros((1, 3, cfg.proc_side, cfg.proc_side)), torch.eye(3)[np.newaxis]))
    crop_model.load_state_dict(torch.load(os.path.join(model_dir, "ckpt.pt")))

    skel_infos = spu.load_pickle(os.path.join(model_dir, "skeleton_infos.pkl"))
    jtm = np.load(os.path.join(model_dir, "joint_transform_matrix.npy"))
    with torch.device("cuda"):
        model = multiperson_model.Pose3dEstimator(crop_model.cuda(), skel_infos, jtm).cuda()
    return model


def build_packet(poses3d_mm, poses2d_px, frame_w, frame_h, smoother):
    """Convert one person's MeTRAbs output to the MediaPipe-compatible UDP packet.

    poses3d_mm: (24, 3) millimetres, camera frame (+X right, +Y down, +Z away).
    poses2d_px: (24, 2) pixel coords in the (already horizontally flipped) frame.
    """
    if poses3d_mm is None:
        return {"timestamp": time.time(), "tracked": False,
                "coordinate_space": "none", "landmarks": []}

    # Hip-midpoint origin, millimetres -> metres. This matches MediaPipe world space:
    # hip-centered, +X right, +Y down, +Z away from camera. If the avatar ends up
    # mirrored / facing away / upside down in Unity, flip the receiver's
    # mirrorX / invertZ / invertY / swapLeftRight toggles (no code change needed).
    hip_mid = (poses3d_mm[SMPL24_INDEX["left_hip"]] + poses3d_mm[SMPL24_INDEX["right_hip"]]) * 0.5
    filter_time = time.perf_counter()
    landmarks = []
    for name in LANDMARK_ORDER:
        idx = SMPL24_INDEX[name]
        rel_m = (poses3d_mm[idx] - hip_mid) / 1000.0
        px, py = poses2d_px[idx]
        landmarks.append({
            "name": name,
            "x": finite(smoother.smooth(name, "x", float(rel_m[0]), filter_time)),
            "y": finite(smoother.smooth(name, "y", float(rel_m[1]), filter_time)),
            "z": finite(smoother.smooth(name, "z", float(rel_m[2]), filter_time)),
            "visibility": 1.0,
            "image_x": finite(float(px) / frame_w),
            "image_y": finite(float(py) / frame_h),
        })
    return {"timestamp": time.time(), "tracked": True,
            "coordinate_space": "world", "landmarks": landmarks}


def draw_lower_body_landmarks(frame, packet):
    h, w = frame.shape[:2]
    for lm in packet["landmarks"]:
        if lm["visibility"] < 0.5:
            continue
        x = int(lm["image_x"] * w)
        y = int(lm["image_y"] * h)
        cv2.circle(frame, (x, y), 7, (0, 255, 0), -1)


def main():
    parser = argparse.ArgumentParser(description="Send MeTRAbs lower-body pose landmarks to Unity over UDP.")
    parser.add_argument("--host", default="127.0.0.1", help="Unity receiver host.")
    parser.add_argument("--port", type=int, default=5055, help="Unity receiver UDP port.")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index.")
    parser.add_argument("--width", type=int, default=1280, help="Camera capture width.")
    parser.add_argument("--height", type=int, default=720, help="Camera capture height.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Path to the cloned MeTRAbs repo.")
    parser.add_argument("--model-dir", default=DEFAULT_MODEL_DIR, help="MeTRAbs PyTorch model dir.")
    parser.add_argument("--fov", type=float, default=55.0, help="Assumed camera vertical field-of-view (deg).")
    parser.add_argument("--num-aug", type=int, default=2,
                        help="Test-time augmentations: higher = more accurate depth, lower = faster.")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.0)
    parser.add_argument("--smooth-beta", type=float, default=0.3)
    parser.add_argument("--smooth-z-min-cutoff", type=float, default=0.6)
    parser.add_argument("--no-preview", action="store_true", help="Run without an OpenCV preview window.")
    args = parser.parse_args()

    import torch  # imported after arg parsing so --help stays fast

    print("Loading MeTRAbs model (first run also downloads the YOLO detector)...")
    model = load_metrabs_model(args.repo, args.model_dir)
    print("Model ready.")

    smoother = LandmarkSmoother(
        min_cutoff=args.smooth_min_cutoff, beta=args.smooth_beta,
        z_min_cutoff=args.smooth_z_min_cutoff)

    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    capture = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera index {args.camera}.")

    print(f"Sending MeTRAbs pose UDP to {args.host}:{args.port}. Press Q to quit.")
    if not args.no_preview:
        cv2.namedWindow("MeTRAbs Pose UDP", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("MeTRAbs Pose UDP", 960, 540)

    last_log = 0.0
    with torch.inference_mode(), torch.device("cuda"):
        while True:
            ok, frame = capture.read()
            if not ok:
                print("Camera frame not available.")
                break

            # Mirror like mediapipe_pose_udp.py so the coordinate handedness matches.
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_t = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1))).cuda()

            try:
                pred = model.detect_poses(
                    img_t, skeleton="smpl_24", num_aug=args.num_aug,
                    default_fov_degrees=args.fov, detector_threshold=0.3, max_detections=1)
                poses3d = pred["poses3d"].cpu().numpy()
                poses2d = pred["poses2d"].cpu().numpy()
            except Exception:
                # No person detected this frame (you stepped out of view / a blurry
                # frame) -> MeTRAbs runs torch.cat on an empty batch and raises.
                # Treat it as "not tracked" and keep the loop alive instead of dying.
                poses3d, poses2d = [], []

            if len(poses3d) > 0:
                packet = build_packet(poses3d[0], poses2d[0], w, h, smoother)
            else:
                packet = build_packet(None, None, w, h, smoother)

            data = json.dumps(packet, separators=(",", ":"), allow_nan=False).encode("utf-8")
            sender.sendto(data, (args.host, args.port))

            now = time.time()
            if now - last_log >= 2.0:
                last_log = now
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
                cv2.imshow("MeTRAbs Pose UDP", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    capture.release()
    sender.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
