"""EMOTION — Decodifica taxas de disparo dos motores LIF em estado emocional contínuo e estável."""

from dataclasses import dataclass

from ..mathutil import clamp

MOTOR_TO_MOOD = {
    "HAPPY": "happy",
    "AFFECTIONATE": "affectionate",
    "FOCUSED": "focused",
    "CURIOUS_LOOK": "curious",
    "COZY_RELAX": "cozy",
    "SLEEPY": "sleepy",
    "SHY_BLUSH": "shy",
    "POUTY": "pouty",
    "SURPRISED": "surprised",
}

MOOD_LABELS_PT = {
    "calm": "Serena",
    "happy": "Radiante",
    "affectionate": "Carinhosa",
    "focused": "Concentrada",
    "curious": "Curiosa",
    "cozy": "Aconchegada",
    "sleepy": "Sonolenta",
    "shy": "Corada",
    "pouty": "Emburradinha",
    "surprised": "Surpresa",
}


@dataclass
class EmotionState:
    mood: str = "calm"
    label: str = "Serena"
    valence: float = 0.2      # -1 (emburrada) .. +1 (feliz/carinhosa)
    arousal: float = 0.3      # 0 (sonolenta) .. 1 (empolgada/surpresa)
    blush: float = 0.0        # 0..1 intensidade do rubor
    confidence: float = 0.5   # 0..1 força do estado dominante


class EmotionDecoder:
    """Traduz taxas motoras (Hz) com histerese suave para evitar oscilação brusca de expressão."""

    def __init__(self):
        self.state = EmotionState()
        self._scores: dict[str, float] = {m: 0.0 for m in MOTOR_TO_MOOD.values()}

    def update(self, expression_rates: dict[str, float], dt: float, asleep: bool = False) -> EmotionState:
        dt = clamp(float(dt), 0.0, 2.0)
        alpha = clamp(dt * 2.4, 0.05, 0.65)

        for motor, mood in MOTOR_TO_MOOD.items():
            hz = float(expression_rates.get(motor, 0.0))
            norm = clamp(hz / 18.0, 0.0, 1.0)
            self._scores[mood] += (norm - self._scores[mood]) * alpha

        if asleep:
            dominant = "sleepy"
            conf = 1.0
        else:
            best_mood, best_val = max(self._scores.items(), key=lambda kv: kv[1])
            if best_val < 0.14:
                dominant = "calm"
                conf = 0.45
            else:
                # Histerese: só troca se superar o atual com pequena margem
                curr_val = self._scores.get(self.state.mood, 0.0)
                if self.state.mood in self._scores and best_val < curr_val + 0.05:
                    dominant = self.state.mood
                    conf = curr_val
                else:
                    dominant = best_mood
                    conf = best_val

        pos = (
            self._scores["happy"] * 1.0
            + self._scores["affectionate"] * 1.1
            + self._scores["cozy"] * 0.7
            + self._scores["curious"] * 0.4
        )
        neg = self._scores["pouty"] * 1.0 + self._scores["sleepy"] * 0.15
        valence = clamp((pos - neg) / 1.8, -1.0, 1.0)

        high_arousal = (
            self._scores["surprised"] * 1.2
            + self._scores["happy"] * 0.8
            + self._scores["curious"] * 0.6
            + self._scores["shy"] * 0.5
        )
        low_arousal = self._scores["sleepy"] * 1.1 + self._scores["cozy"] * 0.5
        arousal = clamp(0.35 + (high_arousal - low_arousal) * 0.55, 0.0, 1.0)

        blush = clamp(self._scores["shy"] * 0.95 + self._scores["affectionate"] * 0.55, 0.0, 1.0)

        self.state = EmotionState(
            mood=dominant,
            label=MOOD_LABELS_PT.get(dominant, dominant.title()),
            valence=valence,
            arousal=arousal,
            blush=blush,
            confidence=clamp(conf, 0.0, 1.0),
        )
        return self.state
