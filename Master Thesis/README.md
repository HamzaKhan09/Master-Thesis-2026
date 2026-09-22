# Master Thesis — Modular Full-Body Tracking in XR

Unity prototype for modular full-body tracking in XR. It builds on the earlier HYTRACK
Kinect + Meta Quest prototype and replaces the Kinect lower-body component with an
RGB-camera pose-estimation source, keeping the avatar retargeting pipeline modular so the
leg-pose provider can be swapped without touching the rest of the rig.

Unity **6000.0.37f1**.

## Tracking conditions

The upper body is always driven by the Meta Quest headset and controllers. The conditions
differ only in what drives the **legs**:

| Condition | Leg pose source | Scene |
| --- | --- | --- |
| RGB | Monocular RGB camera, 3D pose over UDP | `Assets/Scenes/RGBFullBodyTrackingSystem.unity` |
| MetaOnly | Quest's own generated lower body | `Assets/Scenes/RGBFullBodyTrackingSystem.unity` (runtime toggle) |
| OptiTrack | Marker-based mocap, used as ground truth | `Assets/Scenes/OptiTrackFullBody.unity` |

RGB and MetaOnly live in the same scene and are switched at runtime by
`Assets/Scripts/UserStudy/TrackingManager.cs`. The RGB provider is deliberately left
running in MetaOnly — only its influence on the legs is cut — so switching back is instant.

`Assets/Scenes/Kinect_VR.unity` and `Assets/Scenes/Meta tracking.unity` are the earlier
baseline scenes, kept for reference.

## Running the RGB condition

The pose estimator runs as a Python process outside Unity and streams leg landmarks over
UDP as JSON. Start the bridge first, then enter play mode.

**MeTRAbs (the prototype's pose source):**

```
python "Master Thesis/Tools/metrabs_pose_udp.py" --repo <path-to-metrabs-clone>
```

`--repo` defaults to a hard-coded local path, so pass your own clone location. The model
directory defaults to `metrabs_eff2l_384px_800k_28ds_pytorch` inside that repo; override
with `--model-dir`.

**MediaPipe (drop-in alternative):**

```
python "Master Thesis/Tools/mediapipe_pose_udp.py"
```

It emits a byte-identical packet — same six landmark names, meters, hip-centered, same
axis convention — so the Unity receiver needs no changes. The `.task` model is downloaded
on first run if missing.

Both scripts share `--host` (default `127.0.0.1`), `--port` (default `5055`), `--camera`,
`--width`, `--height`, the One-Euro smoothing flags, and `--no-preview`. The port must
match `port` on the `MediaPipePoseReceiver` component in the scene.

Dependencies: `opencv-python`, `numpy`, plus `mediapipe` for the MediaPipe bridge and a
local MeTRAbs checkout with its PyTorch model for the MeTRAbs bridge.

## Running the OptiTrack condition

`Assets/Scenes/OptiTrackFullBody.unity` uses the OptiTrack Unity plugin under
`Assets/optitrack-unity/`. `OptitrackLegPoseUdpSender.cs` re-emits the tracked skeleton's
leg pose in the same packet format the RGB bridge uses, so the same retargeting path
drives the avatar. It sends to port **5057** by default — point a second
`MediaPipePoseReceiver` at that port and keep it distinct from the RGB receiver's.

## Layout

- `Assets/Scripts/` — avatar control, IK, and the UDP pose receiver
- `Assets/Scripts/UserStudy/` — condition switching, retargeting, and data logging
- `Assets/optitrack-unity/` — OptiTrack plugin
- `Tools/` — the two Python pose bridges

## Not in the repository

Model weights and captured session data are kept out of version control and are not needed
to open or build the project: the MediaPipe `.task` file downloads on first run, the
MeTRAbs model comes from its own repo, and the recorded study data stays local.
