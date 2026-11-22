"""EPISODIC MEMORY — Bandit contextual que aprende quais ações/reações agradam o usuário em cada contexto."""

from datetime import datetime
import json
import math
import random
import time

from ..log import log
from ..store import append_line, read_json, read_lines, write_json, write_lines

ACTIONS = ("whisper", "sparkle_fx", "pose_wave", "outfit_shift", "quiet_company")

PRIOR = 0.12
PRIOR_WEIGHT = 2.0
GLOBAL_WEIGHT = 3.0
RECENCY_HALF_LIFE = 150
MAX_COUNT = 40
KEEP_EPISODES = 500


def _no_nan(val):
    raise ValueError(f"constante inválida: {val}")


def _valid_episode(ep) -> bool:
    if not isinstance(ep, dict):
        return False
    if not isinstance(ep.get("contexto"), str) or not isinstance(ep.get("acao"), str) or not ep.get("acao"):
        return False
    v = ep.get("valencia")
    return type(v) in (int, float) and math.isfinite(v) and -1.0 <= v <= 1.0


def _valid_stats(pair) -> list[float]:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ValueError("par inválido")
    n, mean = pair
    if type(n) not in (int, float) or type(mean) not in (int, float):
        raise ValueError("tipo inválido")
    n, mean = float(n), float(mean)
    if not (math.isfinite(n) and math.isfinite(mean)) or n < 0 or not (-1.0 <= mean <= 1.0):
        raise ValueError("intervalo inválido")
    return [n, mean]


def _valid_table(raw, by_context: bool) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    try:
        if by_context:
            for ctx, acts in raw.items():
                if isinstance(ctx, str) and isinstance(acts, dict):
                    out[ctx] = {a: _valid_stats(v) for a, v in acts.items() if isinstance(a, str)}
        else:
            out = {a: _valid_stats(v) for a, v in raw.items() if isinstance(a, str)}
    except (TypeError, ValueError):
        return {}
    return out


class EpisodicMemory:
    """Aprende qual reação sutil funciona melhor por (atividade|período|clima|emoção)."""

    def __init__(self, episodes_path, prefs_path):
        self.episodes_path = episodes_path
        self.prefs_path = prefs_path
        self.open: list[dict] = []
        self.recent: list[dict] = []
        self.table: dict[str, dict[str, list[float]]] = {}
        self.totals: dict[str, list[float]] = {}
        self.last_choice: tuple[str, str, str] | None = None
        self._seq = 0

    @staticmethod
    def context(activity: str, period: str, weather: str, emotion: str) -> str:
        return f"{activity}|{period}|{weather}|{emotion}"

    def estimate(self, ctx: str, action: str) -> float:
        n, mean = self.table.get(ctx, {}).get(action, [0.0, 0.0])
        gn, gmean = self.totals.get(action, [0.0, 0.0])
        base = (PRIOR * PRIOR_WEIGHT + gmean * min(gn, GLOBAL_WEIGHT)) / (PRIOR_WEIGHT + min(gn, GLOBAL_WEIGHT))
        return (n * mean + GLOBAL_WEIGHT * base) / (n + GLOBAL_WEIGHT)

    def choose(self, ctx: str, allowed: list[str] | tuple[str, ...], epsilon: float = 0.15) -> str | None:
        if not allowed:
            return None
        if random.random() < epsilon:
            action = random.choice(list(allowed))
            self.last_choice = (ctx, action, "explorando")
            return action
        scored = sorted(((self.estimate(ctx, a), a) for a in allowed), reverse=True)
        best = scored[0][0]
        ties = [a for sc, a in scored if sc >= best - 1e-9]
        action = random.choice(ties)
        self.last_choice = (ctx, action, f"estimativa {best:+.2f}")
        return action

    def start(self, ctx: str, action: str, now: float | None = None) -> dict:
        self._seq += 1
        ep = {
            "id": f"{time.time_ns()}-{self._seq}",
            "quando": datetime.now().isoformat(timespec="seconds"),
            "contexto": ctx,
            "acao": action,
            "inicio": time.monotonic() if now is None else now,
            "positive": False,
        }
        self.open.append(ep)
        return ep

    def on_positive_feedback(self) -> None:
        for ep in self.open:
            ep["positive"] = True

    def on_dismiss(self, now: float | None = None) -> None:
        now_t = time.monotonic() if now is None else now
        for ep in list(self.open):
            elapsed = max(0.0, now_t - ep["inicio"])
            val = -0.75 + 0.50 * min(elapsed / 20.0, 1.0)
            self._resolve(ep, f"dispensado em {elapsed:.1f}s", val)

    def tick(self, now: float, window: float = 18.0) -> None:
        for ep in list(self.open):
            if now - ep["inicio"] >= window:
                if ep["positive"]:
                    self._resolve(ep, "usuário respondeu com carinho", 0.72)
                else:
                    self._resolve(ep, "aceito tranquilamente", 0.22)

    def shift_clock(self, seconds: float) -> None:
        for ep in self.open:
            ep["inicio"] += seconds

    def _resolve(self, ep: dict, result: str, valence: float) -> None:
        if ep in self.open:
            self.open.remove(ep)
        record = {
            "id": ep["id"],
            "quando": ep["quando"],
            "contexto": ep["contexto"],
            "acao": ep["acao"],
            "resultado": result,
            "valencia": round(float(valence), 3),
        }
        self.recent.append(record)
        self.recent = self.recent[-KEEP_EPISODES:]
        self._learn(record["contexto"], record["acao"], record["valencia"])
        if self.episodes_path is not None:
            try:
                append_line(self.episodes_path, json.dumps(record, ensure_ascii=False))
            except OSError as err:
                log(f"[memória] erro ao gravar episódio: {err}")

    def _learn(self, ctx: str, action: str, valence: float) -> None:
        for stats in (
            self.table.setdefault(ctx, {}).setdefault(action, [0.0, 0.0]),
            self.totals.setdefault(action, [0.0, 0.0]),
        ):
            stats[0] = min(stats[0] + 1.0, float(MAX_COUNT))
            stats[1] += (valence - stats[1]) / stats[0]

    def consolidate(self) -> list[tuple[str, str, float, float]]:
        """Consolidação durante o sono: repondera episódios dando mais peso aos recentes."""
        episodes = self._read_episodes()
        if not episodes:
            return []
        table: dict = {}
        totals: dict = {}
        newest = len(episodes)
        for i, ep in enumerate(episodes):
            w = 0.5 ** ((newest - 1 - i) / RECENCY_HALF_LIFE)
            for st in (
                table.setdefault(ep["contexto"], {}).setdefault(ep["acao"], [0.0, 0.0]),
                totals.setdefault(ep["acao"], [0.0, 0.0]),
            ):
                st[0] += w
                st[1] += w * ep["valencia"]
        self.table = {c: {a: [min(n, MAX_COUNT), s / n] for a, (n, s) in acts.items()} for c, acts in table.items()}
        self.totals = {a: [min(n, MAX_COUNT), s / n] for a, (n, s) in totals.items()}
        if self.episodes_path is not None and len(episodes) > KEEP_EPISODES:
            try:
                write_lines(self.episodes_path, [json.dumps(ep, ensure_ascii=False) for ep in episodes[-KEEP_EPISODES:]])
            except OSError:
                pass
        self.save()
        return self.preferences()

    def preferences(self, top: int = 6) -> list[tuple[str, str, float, float]]:
        rows = [(c, a, mean, n) for c, acts in self.table.items() for a, (n, mean) in acts.items() if n >= 0.2]
        return sorted(rows, key=lambda r: -abs(r[2]) * min(r[3], 5.0))[:top]

    def _read_episodes(self) -> list[dict]:
        if self.episodes_path is None or not self.episodes_path.exists():
            return list(self.recent)
        out = []
        for line in read_lines(self.episodes_path):
            try:
                rec = json.loads(line, parse_constant=_no_nan)
            except ValueError:
                continue
            if _valid_episode(rec):
                out.append(rec)
        return out

    def save(self) -> None:
        if self.prefs_path is None:
            return
        try:
            write_json(self.prefs_path, {"tabela": self.table, "geral": self.totals, "saved_at": time.time()}, indent=2)
        except OSError as err:
            log(f"[memória] erro ao salvar preferências: {err}")

    def load(self) -> None:
        if self.prefs_path is not None:
            data = read_json(self.prefs_path, default=None)
            if isinstance(data, dict):
                self.table = _valid_table(data.get("tabela"), by_context=True)
                self.totals = _valid_table(data.get("geral"), by_context=False)
        self.recent = self._read_episodes()[-KEEP_EPISODES:]
