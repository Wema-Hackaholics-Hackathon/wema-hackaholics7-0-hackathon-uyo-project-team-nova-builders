"""Face matching service — enrolment and 1:1 verification on top of liveness.

Every face goes through accept_face_record() first: it calls the SDK's
verify_face_record() (signature, expiry, session passed, PNG hash matches the
receipt), rejects a nonce that was already used, and rejects poor-quality faces.
Only then is the face embedded.

Recognition model: OpenCV Zoo SFace (Apache-2.0), run through cv2.FaceRecognizerSF.
The liveness face record is already a 112x112 crop aligned to the ArcFace template,
which is exactly what SFace expects, so no detection / re-alignment is done here.

Templates are biometric data: they are encrypted at rest (Fernet), kept
server-side only, and deletable by the user.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import faceliveness
import httpx
import numpy as np
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import get_settings
from app.models import UsedLivenessNonce
from app.services.liveness_service import get_public_key

MODEL_NAME = "sface_2021dec"
_SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/"
    "face_recognition_sface_2021dec.onnx"
)
_SFACE_SHA256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
_EMBEDDING_DIM = 128


# ---------------------------------------------------------------------------
# Model + crypto setup
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_sface_model() -> Path:
    """Return the SFace model path, downloading it once if missing. Verifies SHA-256."""
    path = Path(get_settings().SFACE_MODEL_PATH)
    if not path.exists():
        print(f"[face-match] downloading SFace model → {path}", flush=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        with httpx.stream("GET", _SFACE_URL, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        tmp.rename(path)
    digest = _sha256_file(path)
    if digest != _SFACE_SHA256:
        raise RuntimeError(f"SFace model checksum mismatch ({digest}) — delete {path} and retry")
    return path


@lru_cache
def _recognizer() -> cv2.FaceRecognizerSF:
    return cv2.FaceRecognizerSF.create(str(ensure_sface_model()), "")


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    if settings.FACE_TEMPLATE_KEY:
        return Fernet(settings.FACE_TEMPLATE_KEY.encode())
    if settings.ENV == "production":
        raise RuntimeError("FACE_TEMPLATE_KEY must be set in production")
    # Dev fallback: derive a stable key from SECRET_KEY so templates survive restarts.
    derived = hashlib.sha256(f"{settings.SECRET_KEY}:face-template".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


# ---------------------------------------------------------------------------
# Face record acceptance
# ---------------------------------------------------------------------------

@dataclass
class AcceptedFace:
    nonce: str
    face_png: bytes
    face_sha256: str
    quality: float
    real_score: float | None


async def accept_face_record(
    *,
    db: AsyncSession,
    user_id: str,
    purpose: str,
    receipt: str,
    face_png: bytes,
) -> AcceptedFace:
    """Gate every face before enrol/compare. Adds the nonce row; the caller commits."""
    try:
        r = faceliveness.verify_face_record(receipt, get_public_key(), face_png)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Liveness record rejected: {exc}",
        ) from exc

    # A receipt must work only once.
    db.add(UsedLivenessNonce(nonce=r.nonce, user_id=user_id, purpose=purpose))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This liveness result has already been used",
        ) from exc

    quality = r.face_quality or 0.0
    if quality < get_settings().FACE_MIN_QUALITY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Face image quality too low — face the camera in good light and try again",
        )

    return AcceptedFace(
        nonce=r.nonce,
        face_png=face_png,
        face_sha256=r.face_sha256 or "",
        quality=quality,
        real_score=r.real_score,
    )


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def embed(face_png: bytes) -> np.ndarray:
    """L2-normalised SFace embedding of an aligned face record (CPU-bound)."""
    # The PNG is RGB; cv2.imdecode returns BGR, which is what SFace expects.
    img = cv2.imdecode(np.frombuffer(face_png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("face record is not a valid PNG")
    if img.shape[:2] != (112, 112):
        img = cv2.resize(img, (112, 112), interpolation=cv2.INTER_AREA)
    feat = _recognizer().feature(img).astype(np.float32).reshape(-1)
    norm = float(np.linalg.norm(feat))
    if norm == 0.0:
        raise ValueError("empty face embedding")
    return feat / norm


def encrypt_template(embedding: np.ndarray) -> bytes:
    return _fernet().encrypt(embedding.astype(np.float32).tobytes())


def decrypt_template(blob: bytes) -> np.ndarray:
    raw = _fernet().decrypt(blob)
    vec = np.frombuffer(raw, dtype=np.float32)
    if vec.shape != (_EMBEDDING_DIM,):
        raise ValueError("stored face template is corrupt")
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def is_match(score: float) -> bool:
    return score >= get_settings().FACE_MATCH_THRESHOLD
