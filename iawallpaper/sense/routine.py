"""ROUTINE — Aprende o perfil horário de atividades do usuário (24h) para contextualizar a avatar."""

from datetime import datetime
from pathlib import Path

from ..store import read_json, write_json


class RoutineTracker:
    """Histograma de atividades por hora do dia (0..23)."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self.hours: dict[str, dict[str, int]] = {str(h): {} for h in range(24)}
        self._samples = 0

    def record(self, activity: str, hour: int | None = None) -> None:
        if not activity or activity == "AWAY":
            return
        h = str((datetime.now().hour if hour is None else int(hour)) % 24)
        bucket = self.hours.setdefault(h, {})
        bucket[activity] = int(bucket.get(activity, 0)) + 1
        self._samples += 1

    def usual_activity(self, hour: int | None = None) -> str | None:
        h = str((datetime.now().hour if hour is None else int(hour)) % 24)
        bucket = self.hours.get(h) or {}
        if not bucket:
            return None
        act, count = max(bucket.items(), key=lambda kv: kv[1])
        return act if count >= 3 else None

    def summary(self) -> dict[str, str]:
        out = {}
        for h in range(24):
            act = self.usual_activity(h)
            if act:
                out[f"{h:02d}h"] = act
        return out

    def save(self) -> None:
        if self.path is None:
            return
        write_json(self.path, {"hours": self.hours, "samples": self._samples}, indent=2)

    def load(self) -> None:
        if self.path is None:
            return
        data = read_json(self.path, default=None)
        if isinstance(data, dict) and isinstance(data.get("hours"), dict):
            for h in range(24):
                k = str(h)
                raw = data["hours"].get(k)
                if isinstance(raw, dict):
                    self.hours[k] = {
                        str(act): int(cnt)
                        for act, cnt in raw.items()
                        if isinstance(act, str) and isinstance(cnt, int) and cnt >= 0
                    }
            if isinstance(data.get("samples"), int):
                self._samples = data["samples"]
