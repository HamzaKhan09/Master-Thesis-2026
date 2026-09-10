# Master Thesis

Unity prototype for modular full-body tracking in XR.

This project builds on the previous HYTRACK Kinect + Meta Quest prototype and extends it toward the master thesis goal: replacing the Kinect lower-body tracking component with an RGB-camera pose-estimation source while keeping the avatar tracking pipeline modular.

## Current Direction

- Baseline: Meta Quest + Kinect v2 hybrid tracking
- Thesis prototype: Meta Quest + MediaPipe RGB pose tracking
- Main Unity scene: `Assets/Scenes/LegTrackingSystem.unity`
- Target comparison: Kinect baseline, MediaPipe RGB source, and Quest-only baseline
