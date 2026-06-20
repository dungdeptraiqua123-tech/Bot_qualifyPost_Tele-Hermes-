from __future__ import annotations

import json
from pathlib import Path
from threading import Lock


class AllowedChannelStore:
    def __init__(self, path: Path, *, initial_channel_ids: set[int] | None = None) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if initial_channel_ids and not self.path.exists():
            self._save(sorted(initial_channel_ids))

    def list_channel_ids(self) -> list[int]:
        with self._lock:
            return self._load()

    def is_allowed(self, channel_id: int) -> bool:
        channel_ids = self.list_channel_ids()
        return not channel_ids or channel_id in channel_ids

    def add_channel(self, channel_id: int) -> bool:
        with self._lock:
            channel_ids = self._load()
            if channel_id in channel_ids:
                return False
            channel_ids.append(channel_id)
            channel_ids.sort()
            self._save(channel_ids)
            return True

    def remove_channel(self, channel_id: int) -> bool:
        with self._lock:
            channel_ids = self._load()
            if channel_id not in channel_ids:
                return False
            channel_ids.remove(channel_id)
            self._save(channel_ids)
            return True

    def _load(self) -> list[int]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        if isinstance(raw, dict):
            raw_ids = raw.get("allowed_channel_ids", [])
        else:
            raw_ids = raw
        return sorted({int(channel_id) for channel_id in raw_ids})

    def _save(self, channel_ids: list[int]) -> None:
        payload = {"allowed_channel_ids": [str(channel_id) for channel_id in channel_ids]}
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(self.path)
