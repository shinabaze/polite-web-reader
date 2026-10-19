"""A disk cache: one JSON file per URL, with the validators needed to ask "has it changed?"."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile


class DiskCache:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)

    def _path(self, url: str) -> str:
        return os.path.join(self.folder, hashlib.sha256(url.encode()).hexdigest() + ".json")

    def get(self, url: str) -> dict | None:
        try:
            with open(self._path(url), encoding="utf-8") as fh:
                entry = json.load(fh)
        except (OSError, ValueError):
            return None
        return entry if entry.get("url") == url else None

    def put(self, url: str, entry: dict) -> None:
        # Write to a temporary file and rename it, so a crash never leaves half an entry behind.
        fd, tmp = tempfile.mkstemp(dir=self.folder, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({**entry, "url": url}, fh)
        os.replace(tmp, self._path(url))
