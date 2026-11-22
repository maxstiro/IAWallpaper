"""HOMEOSTASIS — Variáveis internas (energia, estimulação, contato) + Afinidade (Bond) de longo prazo."""

import time

from ..mathutil import clamp, valor_real
from ..store import read_json, write_json

SLEEP_BELOW = 0.20
WAKE_ABOVE = 0.65
BORED_BELOW = 0.35
LONELY_ABOVE = 0.55
TIRED_BELOW = 0.50

STIMULUS_GAIN = {
    "app": 0.08,
    "novelty": 0.18,
    "poke": 0.15,
    "caress": 0.09,
    "gift": 0.25,
    "weather": 0.12,
    "whisper": 0.10,
}

CONTACT_RELIEF = {
    "poke": 0.14,
    "caress": 0.28,
    "gift": 0.35,
    "dismiss": 0.04,
}

AFFINITY_GAIN = {
    "caress": 0.45,
    "gift": 1.20,
    "poke": 0.15,
    "shared_minute": 0.06,
}


class Drives:
    """Necessidades homeostáticas acopladas ao ritmo circadiano + nível de afinidade (0..100)."""

    def __init__(self):
        self.energy: float = 0.92
        self.stimulation: float = 0.62
        self.contact: float = 0.12
        self.affinity: float = 12.0   # 0..100 (cresce com convivência e carinho)
        self.total_caresses: int = 0
        self.days_together: float = 0.0

    def stimulate(self, kind: str, scale: float = 1.0) -> None:
        self.stimulation = clamp(self.stimulation + STIMULUS_GAIN.get(kind, 0.0) * scale)

    def touched(self, kind: str, scale: float = 1.0) -> None:
        self.contact = clamp(self.contact - CONTACT_RELIEF.get(kind, 0.0) * scale)
        gain = AFFINITY_GAIN.get(kind, 0.0) * scale
        if gain > 0.0:
            self.affinity = clamp(self.affinity + gain, 0.0, 100.0)
        if kind == "caress":
            self.total_caresses += 1

    def update(
        self,
        dt: float,
        asleep: bool,
        arousal: float,
        user_away: bool,
        engaged: bool = False,
        night_factor: float = 0.0,
        energy_span: float = 7200.0,
        sleep_recover: float = 900.0,
        stim_decay: float = 1800.0,
        contact_span: float = 2400.0,
    ) -> None:
        """Atualiza drives por dt segundos. night_factor (0..1) acelera cansaço na madrugada."""
        dt = clamp(float(dt), 0.0, 10.0)
        if asleep:
            self.energy = clamp(self.energy + dt / max(sleep_recover, 60.0))
        else:
            circadian_drain = 1.0 + 0.85 * clamp(night_factor, 0.0, 1.0)
            effort = (1.0 + 0.6 * max(0.0, arousal)) * circadian_drain
            self.energy = clamp(self.energy - dt * effort / max(energy_span, 120.0))

        if engaged and not asleep:
            target = 0.65
            self.stimulation += (target - self.stimulation) * min(1.0, dt / 25.0)
        else:
            self.stimulation = clamp(self.stimulation - dt / max(stim_decay, 120.0))

        loneliness_rate = 0.25 if user_away else 1.0
        self.contact = clamp(self.contact + dt * loneliness_rate / max(contact_span, 120.0))

        if not user_away:
            self.days_together += dt / 86400.0
            self.affinity = clamp(self.affinity + (dt / 60.0) * AFFINITY_GAIN["shared_minute"], 0.0, 100.0)

    def channels(self) -> dict[str, float]:
        """Canais interoceptivos (0..1) alimentados diretamente na rede LIF."""
        return {
            "BOREDOM": clamp((BORED_BELOW - self.stimulation) / BORED_BELOW),
            "LONELY": clamp((self.contact - LONELY_ABOVE) / (1.0 - LONELY_ABOVE)),
            "FATIGUE": clamp((TIRED_BELOW - self.energy) / TIRED_BELOW),
        }

    def sleepy(self) -> bool:
        return self.energy < SLEEP_BELOW

    def rested(self) -> bool:
        return self.energy >= WAKE_ABOVE

    @property
    def bond_stage(self) -> str:
        """Estágio afetivo crescente conforme a afinidade."""
        if self.affinity >= 80.0:
            return "devota"
        if self.affinity >= 55.0:
            return "íntima"
        if self.affinity >= 30.0:
            return "próxima"
        if self.affinity >= 15.0:
            return "amigável"
        return "curiosa"

    def save(self, path) -> None:
        write_json(
            path,
            {
                "energy": round(self.energy, 4),
                "stimulation": round(self.stimulation, 4),
                "contact": round(self.contact, 4),
                "affinity": round(self.affinity, 3),
                "total_caresses": self.total_caresses,
                "days_together": round(self.days_together, 5),
                "saved_at": time.time(),
            },
        )

    def load(self, path, sleep_recover: float = 900.0, stim_decay: float = 1800.0, contact_span: float = 2400.0) -> bool:
        data = read_json(path, default=None)
        if not isinstance(data, dict):
            return False
        try:
            elapsed = max(0.0, time.time() - valor_real(data.get("saved_at", time.time()), 0.0, 1e13))
            energy = valor_real(data.get("energy", 0.9), 0.0, 1.0)
            stimulation = valor_real(data.get("stimulation", 0.6), 0.0, 1.0)
            contact = valor_real(data.get("contact", 0.1), 0.0, 1.0)
            affinity = valor_real(data.get("affinity", 12.0), 0.0, 100.0)
            days = valor_real(data.get("days_together", 0.0), 0.0, 100000.0)
        except ValueError:
            return False

        self.energy = clamp(energy + elapsed / max(sleep_recover, 60.0))
        self.stimulation = clamp(stimulation - elapsed / max(stim_decay, 120.0))
        self.contact = clamp(contact + 0.25 * elapsed / max(contact_span, 120.0))
        # Afinidade nunca despenca quando o PC fica desligado (perda mínima só após semanas)
        self.affinity = clamp(affinity, 0.0, 100.0)
        self.days_together = days
        caresses = data.get("total_caresses", 0)
        if isinstance(caresses, int) and caresses >= 0:
            self.total_caresses = caresses
        return True
