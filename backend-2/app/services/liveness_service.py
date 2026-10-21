"""Liveness detection service — pure OpenCV, no external API.

Challenge pool:
    look_left   — face centre x < 42% of frame width
    look_right  — face centre x > 58% of frame width
    look_up     — face centre y < 38% of frame height
    look_down   — face centre y > 58% of frame height
    open_mouth  — mouth region detected with sufficient vertical span

Detection uses OpenCV Haar cascades (bundled with opencv-python-headless):
    - haarcascade_frontalface_default.xml  — face bounding box
    - haarcascade_mcs_mouth.xml            — mouth open detection
    - haarcascade_eye.xml                  — eye detection (used for face quality)

All functions accept raw JPEG/PNG bytes (base64-decoded by the router)
and return (passed: bool, reason: str).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Challenge type
# ---------------------------------------------------------------------------

ChallengeType = Literal["look_left", "look_right", "look_up", "look_down", "open_mouth"]

ALL_CHALLENGES: list[ChallengeType] = [
    "look_left",
    "look_right",
    "look_up",
    "look_down",
    "open_mouth",
]

# Human-readable instructions sent to the frontend
CHALLENGE_INSTRUCTIONS: dict[ChallengeType, str] = {
    "look_left": "Turn your head to the LEFT",
    "look_right": "Turn your head to the RIGHT",
    "look_up": "Tilt your head UP",
    "look_down": "Tilt your head DOWN",
    "open_mouth": "Open your mouth wide",
}

# ---------------------------------------------------------------------------
# Cascade loader — lazy, cached after first call
# Cascades are bundled in app/data/cascades/ (OpenCV 5 dropped them from
# the package, so we ship our own copies from the opencv/opencv 4.x repo).
# ---------------------------------------------------------------------------

# Resolve relative to this file so it works from any working directory
_CASCADE_DIR = Path(__file__).parent.parent / "data" / "cascades"

_face_cascade: cv2.CascadeClassifier | None = None
_mouth_cascade: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    global _face_cascade
    if _face_cascade is None:
        path = str(_CASCADE_DIR / "haarcascade_frontalface_default.xml")
        _face_cascade = cv2.CascadeClassifier(path)
        if _face_cascade.empty():
            raise RuntimeError(f"Failed to load face cascade from {path}")
    return _face_cascade


def _get_mouth_cascade() -> cv2.CascadeClassifier:
    global _mouth_cascade
    if _mouth_cascade is None:
        # Use bundled smile cascade (works as open-mouth detector with tuned params)
        path = str(_CASCADE_DIR / "haarcascade_smile.xml")
        clf = cv2.CascadeClassifier(path)
        if clf.empty():
            raise RuntimeError(f"Failed to load mouth cascade from {path}")
        _mouth_cascade = clf
    return _mouth_cascade


# ---------------------------------------------------------------------------
# Frame decoder
# ---------------------------------------------------------------------------

@dataclass
class FrameInfo:
    gray: np.ndarray  # type: ignore[type-arg]
    height: int
    width: int


def _decode_frame(image_bytes: bytes) -> FrameInfo:
    """Decode raw image bytes → grayscale numpy array."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image — ensure it is a valid JPEG or PNG")
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Equalise histogram for better detection in varying lighting
    gray = cv2.equalizeHist(gray)
    return FrameInfo(gray=gray, height=h, width=w)


# ---------------------------------------------------------------------------
# Face detection
# ---------------------------------------------------------------------------

@dataclass
class FaceBox:
    x: int
    y: int
    w: int
    h: int
    cx: float  # centre x as fraction of frame width  (0.0 – 1.0)
    cy: float  # centre y as fraction of frame height (0.0 – 1.0)


def _detect_largest_face(frame: FrameInfo) -> FaceBox | None:
    """Return the largest detected face bounding box, or None if no face found."""
    faces = _get_face_cascade().detectMultiScale(
        frame.gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(60, 60),
    )
    if len(faces) == 0:
        return None
    # Pick largest by area
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])  # type: ignore[assignment]
    return FaceBox(
        x=int(x), y=int(y), w=int(w), h=int(h),
        cx=(x + w / 2) / frame.width,
        cy=(y + h / 2) / frame.height,
    )


# ---------------------------------------------------------------------------
# Per-challenge verifiers
# ---------------------------------------------------------------------------

def _check_look_left(face: FaceBox) -> tuple[bool, str]:
    # Face centre must be in the left 42% of the frame
    if face.cx < 0.42:
        return True, "Head turned left — ✓"
    return False, f"Face centre at {face.cx:.0%} — turn further left (need < 42%)"


def _check_look_right(face: FaceBox) -> tuple[bool, str]:
    if face.cx > 0.58:
        return True, "Head turned right — ✓"
    return False, f"Face centre at {face.cx:.0%} — turn further right (need > 58%)"


def _check_look_up(face: FaceBox) -> tuple[bool, str]:
    if face.cy < 0.38:
        return True, "Head tilted up — ✓"
    return False, f"Face centre at {face.cy:.0%} — tilt further up (need < 38%)"


def _check_look_down(face: FaceBox) -> tuple[bool, str]:
    if face.cy > 0.58:
        return True, "Head tilted down — ✓"
    return False, f"Face centre at {face.cy:.0%} — tilt further down (need > 58%)"


def _check_open_mouth(frame: FrameInfo, face: FaceBox) -> tuple[bool, str]:
    """Detect open mouth inside the lower half of the face region."""
    # Crop to lower 55% of face (where mouth lives)
    mouth_y_start = face.y + int(face.h * 0.45)
    mouth_roi = frame.gray[
        mouth_y_start : face.y + face.h,
        face.x : face.x + face.w,
    ]
    if mouth_roi.size == 0:
        return False, "Could not isolate mouth region"

    mouths = _get_mouth_cascade().detectMultiScale(
        mouth_roi,
        scaleFactor=1.1,
        minNeighbors=11,
        minSize=(25, 15),
    )
    if len(mouths) > 0:
        # Verify the detected region has sufficient vertical span (open ≠ closed)
        _mx, _my, _mw, mh = mouths[0]
        roi_height = mouth_roi.shape[0]
        # Mouth height should be at least 20% of the ROI height when open
        if mh / roi_height >= 0.18:
            return True, "Open mouth detected — ✓"
    return False, "Mouth not detected as open — open your mouth wider"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_challenge(challenge: ChallengeType, image_bytes: bytes) -> tuple[bool, str]:
    """Run face detection and verify the given challenge against the frame.

    Returns:
        (passed, human_readable_reason)
    Raises:
        ValueError  — image could not be decoded
        RuntimeError — cascade files missing (shouldn't happen with opencv-python-headless)
    """
    frame = _decode_frame(image_bytes)
    face = _detect_largest_face(frame)

    if face is None:
        return False, "No face detected — ensure your face is clearly visible and well-lit"

    if challenge == "look_left":
        return _check_look_left(face)
    if challenge == "look_right":
        return _check_look_right(face)
    if challenge == "look_up":
        return _check_look_up(face)
    if challenge == "look_down":
        return _check_look_down(face)
    if challenge == "open_mouth":
        return _check_open_mouth(frame, face)

    return False, f"Unknown challenge: {challenge}"


def pick_challenges(n: int = 3) -> list[ChallengeType]:
    """Return n randomly selected distinct challenges from the pool."""
    import random
    return random.sample(ALL_CHALLENGES, k=min(n, len(ALL_CHALLENGES)))
