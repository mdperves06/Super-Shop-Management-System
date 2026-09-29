import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import ValidationFailed

# Content is identified from magic bytes; the client-supplied filename/content-type is never trusted.
_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"%PDF-", "application/pdf", ".pdf"),
]

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
DOCUMENT_TYPES = IMAGE_TYPES | {"application/pdf"}


def sniff(data: bytes) -> tuple[str, str] | None:
    for sig, mime, ext in _SIGNATURES:
        if data.startswith(sig):
            return mime, ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def upload_root() -> Path:
    root = Path(settings.upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def save_upload(file: UploadFile, *, subdir: str, allowed: set[str]) -> tuple[str, str, str, int]:
    """Validate and store an upload. Returns (stored_relative_path, original_name, content_type, size)."""
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if not data:
        raise ValidationFailed("The uploaded file is empty")
    if len(data) > limit:
        raise ValidationFailed(f"File is too large (max {settings.max_upload_mb} MB)", code="file_too_large")
    detected = sniff(data)
    if detected is None or detected[0] not in allowed:
        raise ValidationFailed("Unsupported file type. Allowed: " + ", ".join(sorted(t.split("/")[1] for t in allowed)))
    mime, ext = detected
    name = f"{uuid.uuid4().hex}{ext}"
    folder = upload_root() / subdir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    original = Path(file.filename or "upload").name[:200]
    return f"{subdir}/{name}", original, mime, len(data)


def resolve_stored(path: str) -> Path:
    """Map a stored relative path to disk, refusing anything that escapes the upload root."""
    root = upload_root().resolve()
    full = (root / path).resolve()
    if root not in full.parents:
        raise ValidationFailed("Invalid file path")
    return full
