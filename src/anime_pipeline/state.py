"""Small resumable pipeline-state store."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, load_json


class PipelineState:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"version": 1, "stages": {}}
        if path.is_file():
            try:
                self.data = load_json(path)
            except (OSError, ValueError):
                pass

    def complete(self, stage: str, outputs: list[Path]) -> None:
        self.data.setdefault("stages", {})[stage] = {
            "status": "completed", "completed_at": datetime.now(timezone.utc).isoformat(),
            "outputs": [str(path) for path in outputs],
        }
        atomic_write_json(self.path, self.data)

    def can_resume(self, stage: str) -> bool:
        record = self.data.get("stages", {}).get(stage, {})
        return record.get("status") == "completed" and all(Path(p).is_file() for p in record.get("outputs", []))

