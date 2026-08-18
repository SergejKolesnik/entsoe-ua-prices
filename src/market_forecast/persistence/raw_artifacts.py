"""Content-addressed storage for immutable source responses."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """Metadata for one content-addressed raw source file."""

    sha256: str
    path: Path
    byte_count: int


class RawArtifactStore:
    """Persist raw bytes atomically without overwriting existing content."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def save(
        self,
        content: bytes,
        source: str,
        delivery_date: date,
        extension: str,
    ) -> StoredArtifact:
        """Store content under its SHA-256 digest and return stable metadata."""

        if not content:
            raise ValueError("Raw artifact content must not be empty")
        if not source or any(char in source for char in "/\\"):
            raise ValueError("Source must be a safe path segment")
        suffix = extension.lower().lstrip(".")
        if not suffix.isalnum():
            raise ValueError("Artifact extension must be alphanumeric")

        digest = hashlib.sha256(content).hexdigest()
        directory = self.root / source / delivery_date.strftime("%Y/%m/%d")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.{suffix}"
        if not path.exists():
            temporary = directory / f".{path.name}.{uuid.uuid4().hex}.tmp"
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return StoredArtifact(sha256=digest, path=path, byte_count=len(content))
