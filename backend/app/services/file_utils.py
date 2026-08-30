"""
ComplyFlow — File Validation Utilities

Centralised constants and helpers for secure remediation evidence upload handling.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt"}

# 10 MiB
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sanitize_filename(name: str) -> str:
    """
    Return a filesystem-safe version of *name*.

    * Strips leading / trailing whitespace.
    * Normalises unicode to ASCII (best-effort).
    * Removes directory traversal components (/ backslash and ..).
    * Replaces unsafe characters with underscores.
    * Collapses consecutive underscores.
    * Guarantees the result is non-empty (falls back to "upload").
    """
    if not name:
        return "upload"

    # Normalise unicode -> ASCII best-effort
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Strip null bytes
    name = name.replace("\x00", "")

    # Take only the basename -- kill any directory traversal
    name = Path(name).name

    # Replace unsafe characters with underscores
    name = re.sub(r"[^\w.\-]", "_", name)

    # Collapse consecutive underscores / dots (except leading dot for hidden files)
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"\.{2,}", ".", name)

    name = name.strip("_").strip()

    return name or "upload"


def get_extension(filename: str) -> str:
    """Return the lower-cased file extension including leading dot, e.g. ".pdf"."""
    return Path(filename).suffix.lower()


async def validate_upload(file: UploadFile, max_size: Optional[int] = None) -> bytes:
    """
    Read *file* fully into memory, validate size and extension.

    Returns the raw bytes on success.
    Raises HTTPException(400) for validation failures.
    Raises HTTPException(413) when the file exceeds *max_size*.
    """
    limit = max_size if max_size is not None else MAX_UPLOAD_SIZE

    ext = get_extension(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed. Allowed types: {allowed}",
        )

    # Read in chunks to avoid loading an unbounded stream into memory
    chunks: list[bytes] = []
    total = 0
    chunk_size = 64 * 1024  # 64 KiB

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {limit // (1024 * 1024)} MiB.",
            )
        chunks.append(chunk)

    if total == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return b"".join(chunks)
