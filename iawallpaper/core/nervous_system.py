"""NERVOUS SYSTEM — Rede neural pulsada (LIF) do avatar waifu no IAWallpaper.

Inspirada na arquitetura de rede pulsada do Pestinha, adaptada para um wallpaper vivo
sensível a contexto de PC, ciclo dia/noite, clima, carga do sistema e interações afetivas.

Mecanismos biológicos:
- Neurônios LIF (vazamento, limiar, período refratário, ruído de membrana)
- Adaptação de limiar (atividade sustentada cansa naturalmente)
- Habituação sináptica nos canais sensoriais com recuperação exponencial
- Inibição global (INHIB / QUIET) e inibição lateral entre motores do mesmo grupo
- Aprendizado de três fatores (elegibilidade pré-sináptica × recompensa × valência do interneurônio)
"""

from abc import ABC, abstractmethod
import math
import time

import numpy as np

from ..log import log
from ..mathutil import clamp, valor_real
from ..store import read_json, write_json

# ============================================================
# CANAIS SENSORIAIS: (n_neurônios, taxa_max_Hz, d_habituacao, tau_rec_s)
# ============================================================

SENSORY_SPEC: dict[str, tuple[int, float, float, float]] = {
    # Contexto do computador
    "WORK":       (6,  45.0, 0.00006, 1200.0),
    "AI_CRAFT":   (6,  50.0, 0.00008,  900.0),
    "PLAY":       (6,  60.0, 0.00010,  900.0),
    "MUSIC":      (6,  45.0, 0.00006, 1200.0),
    "SOCIAL":     (6,  50.0, 0.00008,  900.0),
    "WEB":        (6,  45.0, 0.00008,  900.0),
    "TYPING":     (6,  55.0, 0.00006, 1200.0),
    "MOTION":     (6, 100.0, 0.00040,  600.0),
    "NOVELTY":    (6,  95.0, 0.00035,  900.0),
    "SILENCE":    (6,  40.0, 0.0,        1.0),
    "SYS_LOAD":   (6,  50.0, 0.00010,  600.0),
    # Ambiente & Clima
    "DAYLIGHT":   (6,  35.0, 0.0,        1.0),
    "NIGHT":      (6,  35.0, 0.0,        1.0),
    "RAIN":       (6,  40.0, 0.0,        1.0),
    "STORM":      (6,  70.0, 0.00015,  600.0),
    # Interação do usuário
    "CARESS":     (6,  70.0, 0.0,        1.0),   # carinho não enjoa
    "POKE":       (6,  85.0, 0.00080,  180.0),   # cutucada habitua rápido
    "GIFT":       (6,  90.0, 0.00020,  600.0),   # troca de presente/outfit/mimo
    "DISMISS":    (6,  80.0, 0.00008, 1200.0),   # sussurro/reação dispensada
    # Interocepção & Antecipação
    "FATIGUE":    (6,  45.0, 0.0,        1.0),
    "BOREDOM":    (6,  55.0, 0.0,        1.0),
    "LONELY":     (6,  45.0, 0.0,        1.0),
    "ANTICIPATE": (6,  75.0, 0.0,        1.0),
}

# ============================================================
# INTERNEURÔNIOS: (nome, tipo, n, tau_m_ms, adapt_b, adapt_tau_s)
# ============================================================

INTER_SPEC: list[tuple[str, str, int, float, float, float]] = [
    ("ALERT",     "exc", 14,  22.0, 0.030, 1.5),
    ("FOCUS",     "exc", 14, 110.0, 0.020, 2.0),
    ("CURIOUS",   "exc", 14,  75.0, 0.020, 2.0),
    ("PLAYFUL",   "exc", 14,  60.0, 0.020, 2.0),
    ("AFFECTION", "exc", 14, 180.0, 0.012, 3.0),
    ("CALM",      "exc", 14, 260.0, 0.010, 3.0),
    ("COZY",      "exc", 14, 240.0, 0.010, 3.0),
    ("TIRED",     "exc", 12, 360.0, 0.010, 3.0),
    ("SHY",       "exc", 12, 120.0, 0.020, 2.5),
    ("POUT",      "exc", 12, 240.0, 0.012, 3.0),
    ("QUIET",     "inh", 12,  30.0, 0.000, 1.0),
    ("INHIB",     "inh", 18,  12.0, 0.000, 1.0),
]

# ============================================================
# MOTORES: (nome, grupo, n, tau_m_ms, adapt_b, adapt_tau_s)
# ============================================================

MOTOR_SPEC: list[tuple[str, str, int, float, float, float]] = [
    # Expressões (competem entre si por inibição lateral)
    ("HAPPY",        "expression", 10, 50.0, 0.035, 3.0),
    ("AFFECTIONATE", "expression", 10, 60.0, 0.030, 3.5),
    ("FOCUSED",      "expression", 10, 60.0, 0.030, 3.0),
    ("CURIOUS_LOOK", "expression", 10, 45.0, 0.040, 2.5),
    ("COZY_RELAX",   "expression", 10, 70.0, 0.025, 4.0),
    ("SLEEPY",       "expression", 10, 85.0, 0.020, 5.0),
    ("SHY_BLUSH",    "expression", 10, 50.0, 0.035, 3.0),
    ("POUTY",        "expression", 10, 60.0, 0.030, 3.5),
    ("SURPRISED",    "expression", 10, 25.0, 0.060, 1.2),
    # Decisões (competem entre si por inibição lateral)
    ("WHISPER",      "decision",   10, 60.0, 0.040, 4.0),
    ("CHANGE_POSE",  "decision",   10, 55.0, 0.040, 3.5),
    ("CHANGE_OUTFIT","decision",   10, 75.0, 0.035, 5.0),
    ("PLAY_FX",      "decision",   10, 50.0, 0.040, 3.0),
    ("DOZE_OFF",     "decision",   10, 90.0, 0.020, 5.0),
]

EXPRESSION_MOTORS = [m[0] for m in MOTOR_SPEC if m[1] == "expression"]
DECISION_MOTORS = [m[0] for m in MOTOR_SPEC if m[1] == "decision"]

# ============================================================
# CONEXÕES SINÁPTICAS: (pré, pós, peso_fração_limiar, densidade)
# ============================================================

CONNECTIONS: list[tuple[str, str, float, float]] = [
    # Sensores -> Interneurônios
    ("WORK",      "FOCUS",     0.15, 0.6),
    ("WORK",      "CALM",      0.04, 0.6),
    ("AI_CRAFT",  "FOCUS",     0.11, 0.6),
    ("AI_CRAFT",  "CURIOUS",   0.12, 0.6),
    ("PLAY",      "PLAYFUL",   0.11, 0.6),
    ("PLAY",      "ALERT",     0.05, 0.6),
    ("MUSIC",     "COZY",      0.09, 0.6),
    ("MUSIC",     "PLAYFUL",   0.06, 0.6),
    ("MUSIC",     "CALM",      0.06, 0.6),
    ("SOCIAL",    "CURIOUS",   0.07, 0.6),
    ("SOCIAL",    "PLAYFUL",   0.05, 0.6),
    ("WEB",       "CURIOUS",   0.07, 0.6),
    ("TYPING",    "FOCUS",     0.06, 0.6),
    ("TYPING",    "ALERT",     0.02, 0.6),
    ("MOTION",    "ALERT",     0.12, 0.6),
    ("NOVELTY",   "CURIOUS",   0.12, 0.6),
    ("NOVELTY",   "ALERT",     0.07, 0.6),
    ("SILENCE",   "CALM",      0.05, 0.6),
    ("SILENCE",   "TIRED",     0.05, 0.6),
    ("SILENCE",   "QUIET",     0.07, 0.6),
    ("SYS_LOAD",  "CURIOUS",   0.08, 0.6),
    ("SYS_LOAD",  "ALERT",     0.05, 0.6),

    # Ambiente -> Interneurônios
    ("DAYLIGHT",  "PLAYFUL",   0.04, 0.5),
    ("DAYLIGHT",  "CURIOUS",   0.03, 0.5),
    ("NIGHT",     "COZY",      0.07, 0.6),
    ("NIGHT",     "TIRED",     0.04, 0.5),
    ("NIGHT",     "CALM",      0.05, 0.5),
    ("RAIN",      "COZY",      0.11, 0.6),
    ("RAIN",      "CALM",      0.06, 0.6),
    ("STORM",     "ALERT",     0.10, 0.6),
    ("STORM",     "COZY",      0.05, 0.5),
    ("STORM",     "SHY",       0.06, 0.5),

    # Interação -> Interneurônios
    ("CARESS",    "AFFECTION", 0.16, 0.65),
    ("CARESS",    "CALM",      0.08, 0.6),
    ("CARESS",    "SHY",       0.07, 0.5),
    ("CARESS",    "POUT",     -0.12, 0.6),
    ("POKE",      "ALERT",     0.09, 0.6),
    ("POKE",      "PLAYFUL",   0.08, 0.6),
    ("POKE",      "SHY",       0.08, 0.6),
    ("GIFT",      "AFFECTION", 0.16, 0.65),
    ("GIFT",      "PLAYFUL",   0.10, 0.6),
    ("GIFT",      "POUT",     -0.14, 0.6),
    ("DISMISS",   "POUT",      0.14, 0.6),
    ("DISMISS",   "SHY",       0.04, 0.5),
    ("DISMISS",   "AFFECTION",-0.05, 0.5),

    # Homeostase & Antecipação -> Interneurônios
    ("FATIGUE",   "TIRED",     0.14, 0.65),
    ("FATIGUE",   "QUIET",     0.04, 0.5),
    ("BOREDOM",   "CURIOUS",   0.11, 0.6),
    ("BOREDOM",   "PLAYFUL",   0.08, 0.6),
    ("LONELY",    "POUT",      0.09, 0.6),
    ("LONELY",    "AFFECTION", 0.04, 0.5),
    ("ANTICIPATE","ALERT",     0.09, 0.6),
    ("ANTICIPATE","AFFECTION", 0.06, 0.5),

    # Interneurônios <-> Interneurônios
    ("ALERT",     "INHIB",     0.09, 0.5),
    ("FOCUS",     "INHIB",     0.06, 0.5),
    ("CURIOUS",   "INHIB",     0.05, 0.5),
    ("PLAYFUL",   "INHIB",     0.05, 0.5),
    ("AFFECTION", "CALM",      0.05, 0.5),
    ("AFFECTION", "POUT",     -0.08, 0.5),
    ("POUT",      "PLAYFUL",  -0.06, 0.5),
    ("POUT",      "CALM",     -0.05, 0.5),
    ("TIRED",     "PLAYFUL",  -0.06, 0.5),
    ("TIRED",     "ALERT",    -0.05, 0.5),
    ("COZY",      "ALERT",    -0.05, 0.5),
    ("CALM",      "ALERT",    -0.06, 0.5),
    ("QUIET",     "ALERT",    -0.05, 0.5),
    ("QUIET",     "CURIOUS",  -0.04, 0.5),
    ("INHIB",     "ALERT",    -0.04, 0.5),
    ("INHIB",     "FOCUS",    -0.03, 0.5),
    ("INHIB",     "CURIOUS",  -0.03, 0.5),
    ("INHIB",     "PLAYFUL",  -0.03, 0.5),

    # Interneurônios -> Motores de Expressão
    ("PLAYFUL",   "HAPPY",        0.58, 0.6),
    ("AFFECTION", "HAPPY",        0.18, 0.5),
    ("AFFECTION", "AFFECTIONATE", 0.65, 0.65),
    ("CALM",      "AFFECTIONATE", 0.14, 0.5),
    ("FOCUS",     "FOCUSED",      0.62, 0.65),
    ("CURIOUS",   "CURIOUS_LOOK", 0.58, 0.6),
    ("ALERT",     "CURIOUS_LOOK", 0.16, 0.5),
    ("COZY",      "COZY_RELAX",   0.58, 0.65),
    ("CALM",      "COZY_RELAX",   0.32, 0.6),
    ("TIRED",     "SLEEPY",       0.62, 0.65),
    ("COZY",      "SLEEPY",       0.12, 0.5),
    ("SHY",       "SHY_BLUSH",    0.64, 0.65),
    ("AFFECTION", "SHY_BLUSH",    0.15, 0.5),
    ("POUT",      "POUTY",        0.64, 0.65),
    ("ALERT",     "SURPRISED",    0.55, 0.6),
    ("INHIB",     "SURPRISED",   -0.09, 0.5),
    ("INHIB",     "HAPPY",       -0.06, 0.5),

    # Interneurônios -> Motores de Decisão
    ("AFFECTION", "WHISPER",      0.34, 0.6),
    ("CURIOUS",   "WHISPER",      0.30, 0.6),
    ("POUT",      "WHISPER",      0.26, 0.6),
    ("FOCUS",     "WHISPER",     -0.24, 0.6),  # respeita foco no trabalho
    ("TIRED",     "WHISPER",     -0.20, 0.5),
    ("PLAYFUL",   "CHANGE_POSE",  0.38, 0.6),
    ("CURIOUS",   "CHANGE_POSE",  0.26, 0.6),
    ("SHY",       "CHANGE_POSE",  0.22, 0.5),
    ("COZY",      "CHANGE_OUTFIT",0.28, 0.6),
    ("RAIN",      "CHANGE_OUTFIT",0.24, 0.6),
    ("NIGHT",     "CHANGE_OUTFIT",0.22, 0.6),
    ("DAYLIGHT",  "CHANGE_OUTFIT",0.18, 0.5),
    ("PLAYFUL",   "PLAY_FX",      0.40, 0.6),
    ("AFFECTION", "PLAY_FX",      0.34, 0.6),
    ("COZY",      "PLAY_FX",      0.20, 0.5),
    ("TIRED",     "DOZE_OFF",     0.55, 0.65),
    ("COZY",      "DOZE_OFF",     0.14, 0.5),
    ("ALERT",     "DOZE_OFF",    -0.35, 0.6),
]

PLASTIC_POSTS = {"AFFECTION": 1.0, "PLAYFUL": 0.8, "COZY": 0.7, "CALM": 0.6, "POUT": -0.9}
PLASTIC_DENSITY = 0.5
LEARN_MIN, LEARN_MAX = -0.05, 0.09
ELIGIBILITY_TAU = 5.0
BRAIN_VERSION = 1


class Brain(ABC):
    @abstractmethod
    def stimulate(self, intensities: dict[str, float]) -> None: ...

    @abstractmethod
    def step(self, dt_ms: float) -> None: ...

    @abstractmethod
    def motor_activity(self) -> dict[str, float]: ...

    @abstractmethod
    def learn(self, reward: float) -> None: ...

    @abstractmethod
    def snapshot(self) -> dict: ...

    @abstractmethod
    def save(self, path) -> None: ...

    @abstractmethod
    def load(self, path) -> bool: ...


class WaifuSpikingBrain(Brain):
    """Rede neural pulsada LIF em NumPy puro com habituação e plasticidade de três fatores."""

    def __init__(self, seed: int = 42, temperament: dict[str, float] | None = None):
        self.seed = int(seed)
        self.temperament = dict(temperament or {})
        self.rng = np.random.default_rng(self.seed)

        # Mapeamento de populações para fatias contíguas de índices
        self.pop_slices: dict[str, slice] = {}
        self.sensory_names = list(SENSORY_SPEC.keys())
        self.inter_names = [spec[0] for spec in INTER_SPEC]
        self.motor_names = [spec[0] for spec in MOTOR_SPEC]

        idx = 0
        for name, (n, _rate, _d, _tau) in SENSORY_SPEC.items():
            self.pop_slices[name] = slice(idx, idx + n)
            idx += n
        self.n_sensory = idx

        for name, _kind, n, _tau, _ab, _at in INTER_SPEC:
            self.pop_slices[name] = slice(idx, idx + n)
            idx += n
        self.n_inter_end = idx

        for name, _grp, n, _tau, _ab, _at in MOTOR_SPEC:
            self.pop_slices[name] = slice(idx, idx + n)
            idx += n
        self.n_total = idx

        # Parâmetros dos neurônios LIF (não-sensoriais)
        self.tau_m = np.full(self.n_total, 50.0, dtype=np.float64)
        self.adapt_b = np.zeros(self.n_total, dtype=np.float64)
        self.adapt_tau = np.ones(self.n_total, dtype=np.float64)
        for name, _kind, _n, tau_m, ab, at in INTER_SPEC:
            sl = self.pop_slices[name]
            self.tau_m[sl] = tau_m
            self.adapt_b[sl] = ab
            self.adapt_tau[sl] = at
        for name, _grp, _n, tau_m, ab, at in MOTOR_SPEC:
            sl = self.pop_slices[name]
            self.tau_m[sl] = tau_m
            self.adapt_b[sl] = ab
            self.adapt_tau[sl] = at

        # Estado dinâmico LIF
        self.v = np.zeros(self.n_total, dtype=np.float64)
        self.adapt = np.zeros(self.n_total, dtype=np.float64)
        self.refrac = np.zeros(self.n_total, dtype=np.float64)
        self.spikes = np.zeros(self.n_total, dtype=np.float64)

        # Taxa suavizada (EMA em Hz) de cada população
        self.pop_rates: dict[str, float] = {
            name: 0.0 for name in self.pop_slices
        }
        self.sensory_input: dict[str, float] = {name: 0.0 for name in self.sensory_names}
        self.habituation: dict[str, float] = {name: 1.0 for name in self.sensory_names}
        self.eligibility: dict[str, float] = {name: 0.0 for name in self.sensory_names}

        # Matriz de pesos fixos + pesos plásticos aprendidos
        self.W_base = np.zeros((self.n_total, self.n_total), dtype=np.float64)
        self.W_learned = np.zeros((self.n_total, self.n_total), dtype=np.float64)
        self.plastic_mask = np.zeros((self.n_total, self.n_total), dtype=np.float64)

        self._build_connectome()
        self.total_steps = 0
        self.learn_events = 0

    def _build_connectome(self) -> None:
        conn_rng = np.random.default_rng(self.seed + 1009)
        for pre_name, post_name, weight, density in CONNECTIONS:
            pre_sl = self.pop_slices[pre_name]
            post_sl = self.pop_slices[post_name]
            w_eff = weight
            if pre_name in self.sensory_names:
                w_eff *= float(self.temperament.get(pre_name, 1.0))
            rows = post_sl.stop - post_sl.start
            cols = pre_sl.stop - pre_sl.start
            mask = conn_rng.random((rows, cols)) < density
            jitter = conn_rng.uniform(0.85, 1.15, size=(rows, cols))
            self.W_base[post_sl, pre_sl] += mask * w_eff * jitter

        # Inibição lateral dentro de cada grupo motor
        for group in (EXPRESSION_MOTORS, DECISION_MOTORS):
            for i, m1 in enumerate(group):
                for j, m2 in enumerate(group):
                    if i == j:
                        continue
                    sl1 = self.pop_slices[m1]
                    sl2 = self.pop_slices[m2]
                    rows = sl2.stop - sl2.start
                    cols = sl1.stop - sl1.start
                    mask = conn_rng.random((rows, cols)) < 0.35
                    self.W_base[sl2, sl1] += mask * (-0.045)

        # Máscara plástica (canais sensoriais de contexto/ambiente -> interneurônios emocionais)
        for s_name in self.sensory_names:
            if s_name in ("CARESS", "POKE", "GIFT", "DISMISS"):
                continue
            pre_sl = self.pop_slices[s_name]
            for post_name, sign in PLASTIC_POSTS.items():
                post_sl = self.pop_slices[post_name]
                rows = post_sl.stop - post_sl.start
                cols = pre_sl.stop - pre_sl.start
                mask = (conn_rng.random((rows, cols)) < PLASTIC_DENSITY).astype(np.float64)
                self.plastic_mask[post_sl, pre_sl] = mask * sign

    def stimulate(self, intensities: dict[str, float]) -> None:
        """Atualiza intensidades sensoriais [0..1] para o próximo passo."""
        for name in self.sensory_names:
            if name in intensities:
                self.sensory_input[name] = clamp(float(intensities[name]), 0.0, 1.0)
            else:
                self.sensory_input[name] = 0.0

    def step(self, dt_ms: float) -> None:
        """Avança a rede em dt_ms (quebrando internamente em subpassos de 5ms para estabilidade)."""
        dt_ms = clamp(float(dt_ms), 0.0, 200.0)
        if dt_ms <= 0.0:
            return
        sub_ms = 5.0
        n_sub = max(1, int(math.ceil(dt_ms / sub_ms)))
        step_ms = dt_ms / n_sub
        step_s = step_ms / 1000.0

        W_total = self.W_base + self.W_learned
        s_end = self.n_sensory

        for _ in range(n_sub):
            self.total_steps += 1
            spikes = np.zeros(self.n_total, dtype=np.float64)

            # 1. Geradores Poisson sensoriais + habituação + traço de elegibilidade
            elig_decay = math.exp(-step_s / ELIGIBILITY_TAU)
            for name, (n, max_rate, d_hab, tau_rec) in SENSORY_SPEC.items():
                sl = self.pop_slices[name]
                inp = self.sensory_input[name]
                eff = self.habituation[name]
                prob = clamp(inp * eff * max_rate * step_s, 0.0, 0.95)
                fired = (self.rng.random(n) < prob).astype(np.float64)
                spikes[sl] = fired
                n_fired = float(fired.sum())
                if d_hab > 0.0:
                    eff = eff - d_hab * n_fired
                    eff = eff + (1.0 - eff) * (step_s / max(tau_rec, 1e-3))
                    self.habituation[name] = clamp(eff, 0.25, 1.0)
                self.eligibility[name] = clamp(
                    self.eligibility[name] * elig_decay + inp * step_s * 0.45,
                    0.0,
                    1.0,
                )

            # 2. Corrente sináptica (spikes anteriores nos inter/motores + spikes sensoriais atuais)
            active_pre = self.spikes.copy()
            active_pre[:s_end] = spikes[:s_end]
            syn_input = W_total @ active_pre

            # 3. Integração LIF para interneurônios e motores
            non_s = slice(s_end, self.n_total)
            v = self.v[non_s]
            ad = self.adapt[non_s]
            ref = self.refrac[non_s]

            ref = np.maximum(0.0, ref - step_ms)
            not_ref = (ref <= 0.0).astype(np.float64)
            leak = np.exp(-step_ms / self.tau_m[non_s])
            noise = self.rng.normal(0.0, 0.025 * math.sqrt(step_ms / 5.0), size=v.shape)

            v = v * leak + (syn_input[non_s] + noise) * not_ref
            v = np.clip(v, -0.6, 2.5)

            threshold = 1.0 + ad
            fired_non_s = (v >= threshold) & (ref <= 0.0)
            fired_f = fired_non_s.astype(np.float64)

            v = np.where(fired_non_s, 0.0, v)
            ref = np.where(fired_non_s, 4.0, ref)
            ad = ad * np.exp(-step_s / self.adapt_tau[non_s]) + fired_f * self.adapt_b[non_s]

            self.v[non_s] = v
            self.adapt[non_s] = ad
            self.refrac[non_s] = ref
            spikes[non_s] = fired_f
            self.spikes = spikes

            # 4. Taxas de disparo suavizadas (EMA, constante ~0.45s)
            alpha = 1.0 - math.exp(-step_s / 0.45)
            for name, sl in self.pop_slices.items():
                n_pop = sl.stop - sl.start
                inst_hz = float(spikes[sl].sum()) / (n_pop * step_s)
                self.pop_rates[name] += (inst_hz - self.pop_rates[name]) * alpha

    def learn(self, reward: float) -> None:
        """Regra de três fatores: fortalece ou enfraquece associações contexto -> emoção."""
        r = clamp(float(reward), -1.0, 1.0)
        if abs(r) < 1e-4:
            return
        lr = 0.012 * r
        changed = False
        for s_name in self.sensory_names:
            elig = self.eligibility.get(s_name, 0.0)
            if elig < 0.03:
                continue
            pre_sl = self.pop_slices[s_name]
            for post_name in PLASTIC_POSTS:
                post_sl = self.pop_slices[post_name]
                delta = self.plastic_mask[post_sl, pre_sl] * (lr * elig)
                if np.any(delta != 0.0):
                    self.W_learned[post_sl, pre_sl] = np.clip(
                        self.W_learned[post_sl, pre_sl] + delta,
                        LEARN_MIN,
                        LEARN_MAX,
                    )
                    changed = True
        if changed:
            self.learn_events += 1

    def motor_activity(self) -> dict[str, float]:
        """Retorna taxa de disparo atual (Hz) de todos os motores."""
        return {name: self.pop_rates[name] for name in self.motor_names}

    def expression_rates(self) -> dict[str, float]:
        return {name: self.pop_rates[name] for name in EXPRESSION_MOTORS}

    def decision_rates(self) -> dict[str, float]:
        return {name: self.pop_rates[name] for name in DECISION_MOTORS}

    def learned_summary(self, top: int = 6) -> list[tuple[str, str, float]]:
        """Retorna as associações aprendidas mais fortes: [(canal, interneurônio, média)]."""
        rows: list[tuple[str, str, float]] = []
        for s_name in self.sensory_names:
            pre_sl = self.pop_slices[s_name]
            for post_name in PLASTIC_POSTS:
                post_sl = self.pop_slices[post_name]
                mask = self.plastic_mask[post_sl, pre_sl] != 0.0
                if not np.any(mask):
                    continue
                mean_w = float(self.W_learned[post_sl, pre_sl][mask].mean())
                if abs(mean_w) >= 0.002:
                    rows.append((s_name, post_name, round(mean_w, 4)))
        rows.sort(key=lambda item: -abs(item[2]))
        return rows[:top]

    def snapshot(self) -> dict:
        """Estado instantâneo completo para o Monitor Neural."""
        return {
            "neurons": self.n_total,
            "synapses": int(np.count_nonzero(self.W_base)),
            "sensory": {k: round(self.sensory_input[k], 3) for k in self.sensory_names},
            "habituation": {k: round(self.habituation[k], 3) for k in self.sensory_names},
            "inter": {k: round(self.pop_rates[k], 2) for k in self.inter_names},
            "expression": {k: round(self.pop_rates[k], 2) for k in EXPRESSION_MOTORS},
            "decision": {k: round(self.pop_rates[k], 2) for k in DECISION_MOTORS},
            "learned_top": self.learned_summary(top=6),
            "learn_events": self.learn_events,
        }

    def save(self, path) -> None:
        """Salva pesos plásticos compactados por bloco e habituação."""
        blocks = {}
        for s_name in self.sensory_names:
            pre_sl = self.pop_slices[s_name]
            for post_name in PLASTIC_POSTS:
                post_sl = self.pop_slices[post_name]
                mask = self.plastic_mask[post_sl, pre_sl] != 0.0
                if not np.any(mask):
                    continue
                mean_w = float(self.W_learned[post_sl, pre_sl][mask].mean())
                if abs(mean_w) >= 1e-5:
                    blocks[f"{s_name}->{post_name}"] = round(mean_w, 6)
        data = {
            "version": BRAIN_VERSION,
            "seed": self.seed,
            "saved_at": time.time(),
            "habituation": {k: round(v, 5) for k, v in self.habituation.items()},
            "learned_blocks": blocks,
            "learn_events": self.learn_events,
        }
        try:
            write_json(path, data, indent=2)
        except OSError as err:
            log(f"[brain] falha ao salvar cérebro: {err}")

    def load(self, path) -> bool:
        """Restaura habituação (com recuperação pelo tempo offline) e pesos plásticos."""
        data = read_json(path, default=None)
        if not isinstance(data, dict) or data.get("version") != BRAIN_VERSION:
            return False
        try:
            saved_at = valor_real(data.get("saved_at", time.time()), 0.0, 1e13)
            elapsed = max(0.0, time.time() - saved_at)
        except ValueError:
            return False

        hab_raw = data.get("habituation")
        if isinstance(hab_raw, dict):
            for name, (_n, _r, d_hab, tau_rec) in SENSORY_SPEC.items():
                if name in hab_raw:
                    try:
                        val = valor_real(hab_raw[name], 0.25, 1.0)
                    except ValueError:
                        continue
                    if d_hab > 0.0 and tau_rec > 0.0:
                        val = 1.0 - (1.0 - val) * math.exp(-elapsed / tau_rec)
                    self.habituation[name] = clamp(val, 0.25, 1.0)

        blocks = data.get("learned_blocks")
        if isinstance(blocks, dict):
            for key, val in blocks.items():
                if not isinstance(key, str) or "->" not in key:
                    continue
                s_name, post_name = key.split("->", 1)
                if s_name not in self.sensory_names or post_name not in PLASTIC_POSTS:
                    continue
                try:
                    w = valor_real(val, LEARN_MIN, LEARN_MAX)
                except ValueError:
                    continue
                pre_sl = self.pop_slices[s_name]
                post_sl = self.pop_slices[post_name]
                mask = self.plastic_mask[post_sl, pre_sl] != 0.0
                self.W_learned[post_sl, pre_sl] = np.where(mask, w, 0.0)

        events = data.get("learn_events", 0)
        if isinstance(events, int) and events >= 0:
            self.learn_events = events
        return True
