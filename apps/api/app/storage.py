"""Audio blob storage.

Hackathon default: write bytes to `apps/api/media/`. The DB stores only a
`file_uri` reference, so swapping this for S3 later is a one-file change.
"""
from pathlib import Path
from uuid import uuid4

_MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

# Container extension -> what we tell downstream tools the blob is.
_DEFAULT_EXT = ".m4a"


def save_audio(data: bytes, filename: str | None = None) -> tuple[str, int]:
    """Persist audio bytes. Returns (file_uri, size_bytes)."""
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix if filename and Path(filename).suffix else _DEFAULT_EXT
    path = _MEDIA_DIR / f"{uuid4()}{ext}"
    path.write_bytes(data)
    return str(path), len(data)


def read_audio(file_uri: str) -> bytes:
    return Path(file_uri).read_bytes()
