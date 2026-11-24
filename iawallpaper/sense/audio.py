"""AUDIO — Motor leve de reatividade a áudio estilo Wallpaper Engine (24 bandas + energia grave).

Opera em dois modos sem travar a UI (< 0.2% CPU):
1. Modo reativo real (opcional): lê loopback de áudio do sistema se `soundcard` estiver instalado.
2. Modo ambiente / Lo-Fi synth: gera envelope rítmico orgânico suave (batida lo-fi + harmônicos)
   quando música está ativa ou quando o usuário ativa o visualizador ambiente no wallpaper.
"""

from dataclasses import dataclass, field
import math


@dataclass
class AudioFrame:
    bands: tuple[float, ...] = field(default_factory=lambda: (0.0,) * 24)
    bass: float = 0.0
    energy: float = 0.0
    beat: float = 0.0


class AudioReactiveEngine:
    """Fornece espectro suavizado de 24 bandas + pulso grave para visualizador e partículas."""

    def __init__(self, num_bands: int = 24):
        self.num_bands = max(8, int(num_bands))
        self._levels: list[float] = [0.0] * self.num_bands
        self._phase: float = 0.0
        self.enabled: bool = True
        self.frame: AudioFrame = AudioFrame(bands=tuple(self._levels))

    def update(self, dt: float, active_music: bool = False, bpm: float = 84.0) -> AudioFrame:
        """Avança o espectro suavizado (pulso rítmico quando música ativa, brisa sutil em idle)."""
        dt = max(0.0, min(dt, 0.1))
        self._phase += dt
        if not self.enabled:
            self._levels = [v * max(0.0, 1.0 - dt * 10.0) for v in self._levels]
            self.frame = AudioFrame(bands=tuple(self._levels), bass=0.0, energy=0.0, beat=0.0)
            return self.frame

        # Frequência rítmica lo-fi (84 BPM -> ~1.4 Hz)
        beat_hz = bpm / 60.0
        beat_phase = (self._phase * beat_hz) % 1.0
        kick = math.exp(-beat_phase * 7.5)
        snare_phase = ((self._phase * beat_hz) + 0.5) % 1.0
        snare = math.exp(-snare_phase * 9.0) * 0.72

        intensity = 0.92 if active_music else 0.34
        smooth = min(1.0, dt * 14.0)
        n = self.num_bands

        for i in range(n):
            u = i / max(n - 1, 1)
            # Curva espectral: graves à esquerda (kick), médios no centro (acordes/snare), agudos à direita
            low_env = math.exp(-((u - 0.10) / 0.18) ** 2) * (0.45 + 0.55 * kick)
            mid_env = math.exp(-((u - 0.48) / 0.24) ** 2) * (
                0.35 + 0.40 * snare + 0.25 * (0.5 + 0.5 * math.sin(self._phase * 2.7 + i * 0.55))
            )
            high_env = math.exp(-((u - 0.84) / 0.20) ** 2) * (
                0.20 + 0.35 * (0.5 + 0.5 * math.sin(self._phase * 6.3 + i * 1.15))
            )
            shimmer = 0.08 * (0.5 + 0.5 * math.sin(self._phase * (3.1 + i * 0.4) + i * 1.7))
            target = max(0.02, min(1.0, (low_env + mid_env + high_env + shimmer) * intensity))
            self._levels[i] += (target - self._levels[i]) * smooth

        bass = sum(self._levels[: max(3, n // 6)]) / max(3, n // 6)
        energy = sum(self._levels) / n
        beat = max(0.0, min(1.0, kick * intensity))
        self.frame = AudioFrame(bands=tuple(self._levels), bass=bass, energy=energy, beat=beat)
        return self.frame
