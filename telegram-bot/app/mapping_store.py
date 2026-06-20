from __future__ import annotations

import json
from pathlib import Path
from threading import Lock


class MappingStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_mappings(self) -> dict[int, list[int]]:
        with self._lock:
            return self._load()

    def get_targets(self, source_channel_id: int) -> list[int]:
        return self.list_mappings().get(source_channel_id, [])

    def add_mapping(self, source_channel_id: int, target_channel_id: int) -> bool:
        with self._lock:
            mappings = self._load()
            targets = mappings.setdefault(source_channel_id, [])
            if target_channel_id in targets:
                return False
            targets.append(target_channel_id)
            targets.sort()
            self._save(mappings)
            return True

    def remove_mapping(self, source_channel_id: int, target_channel_id: int) -> bool:
        with self._lock:
            mappings = self._load()
            targets = mappings.get(source_channel_id)
            if not targets or target_channel_id not in targets:
                return False
            targets.remove(target_channel_id)
            if targets:
                mappings[source_channel_id] = targets
            else:
                mappings.pop(source_channel_id, None)
            self._save(mappings)
            return True

    def _load(self) -> dict[int, list[int]]:
        if not self.path.exists():
            return {}

        with self.path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        mappings: dict[int, list[int]] = {}
        for source, targets in raw.items():
            source_id = int(source)
            mappings[source_id] = sorted({int(target) for target in targets})
        return mappings

    def _save(self, mappings: dict[int, list[int]]) -> None:
        payload = {
            str(source): [str(target) for target in targets]
            for source, targets in sorted(mappings.items())
        }
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        tmp_path.replace(self.path)
