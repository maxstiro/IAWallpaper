"""CONDICIONAMENTO (Rescorla-Wagner) — Aprende a antecipar carinho, retorno do usuário e padrões de uso."""

import math

from ..mathutil import clamp
from ..store import read_json, write_json

DEFAULT_WINDOW = 2.0
CUE_WINDOWS = {
    "APPROACH": 2.0,     # cursor se aproximando do avatar -> carinho ou cutucada
    "RETURN": 8.0,       # usuário voltou da ausência -> saudação / carinho
    "MUSIC_START": 6.0,  # música começou -> clima relaxado/animado
    "RAIN_START": 10.0,  # começou a chover -> ambiente aconchegante
}


class Conditioning:
    """Modelo Rescorla-Wagner: V <- V + rate * (lambda - V)."""

    def __init__(self, path=None, rate: float = 0.14):
        self.path = path
        self.rate = rate
        self.V: dict[str, float] = {cue: 0.0 for cue in CUE_WINDOWS}
        self.active: dict[str, dict] = {}
        self.ended: list[list] = []

    def set_cue(self, cue: str, on: bool, now: float) -> None:
        if cue not in self.V:
            return
        if on and cue not in self.active:
            self.active[cue] = {"start": now, "hit": False}
        elif not on and cue in self.active:
            info = self.active.pop(cue)
            self.ended.append([cue, now, info["hit"]])

    def outcome(self, now: float, cues: tuple[str, ...] = ("APPROACH", "RETURN")) -> None:
        """Marca desfecho reforçador para pistas ativas ou recém-encerradas."""
        for cue, info in self.active.items():
            if cue in cues:
                info["hit"] = True
        for ep in self.ended:
            if ep[0] in cues and now - ep[1] <= CUE_WINDOWS.get(ep[0], DEFAULT_WINDOW):
                ep[2] = True

    def tick(self, now: float) -> None:
        still = []
        for ep in self.ended:
            cue, end, hit = ep
            if now - end < CUE_WINDOWS.get(cue, DEFAULT_WINDOW):
                still.append(ep)
                continue
            lam = 1.0 if hit else 0.0
            v = self.V.get(cue, 0.0)
            self.V[cue] = clamp(v + self.rate * (lam - v), 0.0, 1.0)
        self.ended = still

    def shift_clock(self, seconds: float) -> None:
        for info in self.active.values():
            info["start"] += seconds
        for ep in self.ended:
            ep[1] += seconds

    def expectancy(self) -> dict[str, float]:
        return {cue: self.V.get(cue, 0.0) for cue in self.active}

    def strength(self, cues: tuple[str, ...] | None = None) -> float:
        exp = self.expectancy()
        if cues is None:
            return max(exp.values(), default=0.0)
        return max((v for c, v in exp.items() if c in cues), default=0.0)

    def save(self) -> None:
        if self.path is None:
            return
        write_json(self.path, {"V": {k: round(v, 5) for k, v in self.V.items()}})

    def load(self) -> None:
        if self.path is None:
            return
        data = read_json(self.path, default=None)
        if isinstance(data, dict) and isinstance(data.get("V"), dict):
            for cue, v in data["V"].items():
                if cue in self.V and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                    self.V[cue] = clamp(float(v), 0.0, 1.0)
