"""AUDIO — Motor leve de captura real de áudio do PC (Windows WASAPI loopback) + fallback ambiente suave.

Projetado para reatividade orgânica estilo Wallpaper Engine (< 0.3% CPU):
- Em Windows com `soundcard`, captura o áudio real dos alto-falantes (Spotify, YouTube, jogos) via WASAPI loopback
  em thread daemon não-bloqueante e calcula FFT em tempo real (`bass`, `mid`, `treble`, `energy`, `beat`, 24 bandas).
- Quando em silêncio ou em ambiente de teste/headless (`enable_loopback=False`), fornece respiração suave
  sem nunca travar nem gerar exceções.
"""

from dataclasses import dataclass, field
import math
import threading

import numpy as np


@dataclass
class AudioFrame:
    bands: tuple[float, ...] = field(default_factory=lambda: (0.0,) * 24)
    bass: float = 0.0
    mid: float = 0.0
    treble: float = 0.0
    energy: float = 0.0
    beat: float = 0.0
    live_capture: bool = False


class AudioReactiveEngine:
    """Fornece espectro suavizado de 24 bandas + graves/agudos reais do PC para partículas e iluminação."""

    def __init__(self, num_bands: int = 24, enable_loopback: bool = False):
        self.num_bands = max(8, int(num_bands))
        self._levels: list[float] = [0.0] * self.num_bands
        self._live_target: list[float] = [0.0] * self.num_bands
        self._live_active: bool = False
        self._phase: float = 0.0
        self._prev_bass: float = 0.0
        self.enabled: bool = True
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self.frame: AudioFrame = AudioFrame(bands=tuple(self._levels))
        if enable_loopback:
            self.start_loopback()

    def start_loopback(self) -> bool:
        """Inicia thread daemon de captura WASAPI loopback do áudio real do Windows (opcional/read-only)."""
        if self._thread is not None and self._thread.is_alive():
            return True
        try:
            import soundcard as sc  # noqa: F401
        except Exception:
            return False

        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loopback_worker, name="iaw-wasapi-audio", daemon=True)
        self._thread.start()
        return True

    def stop_loopback(self) -> None:
        self._stop_evt.set()
        self._live_active = False

    def _loopback_worker(self) -> None:
        try:
            import soundcard as sc

            speaker = sc.default_speaker()
            if speaker is None:
                return
            mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            sr = 48000
            chunk = 1024
            # Bordas logarítmicas de 30 Hz a 12 kHz para as bandas
            freqs = np.fft.rfftfreq(chunk, d=1.0 / sr)
            edges = np.geomspace(35.0, 11000.0, self.num_bands + 1)
            bin_slices = [
                (int(np.searchsorted(freqs, edges[i])), max(int(np.searchsorted(freqs, edges[i + 1])), int(np.searchsorted(freqs, edges[i])) + 1))
                for i in range(self.num_bands)
            ]
            window = np.hanning(chunk).astype(np.float32)

            with mic.recorder(samplerate=sr, blocksize=chunk) as rec:
                self._live_active = True
                while not self._stop_evt.is_set():
                    data = rec.record(numframes=chunk)
                    if data is None or len(data) < chunk:
                        continue
                    mono = np.mean(data, axis=1).astype(np.float32)
                    rms = float(np.sqrt(np.mean(mono * mono)))
                    if rms < 1e-4:
                        self._live_target = [0.0] * self.num_bands
                        continue
                    spec = np.abs(np.fft.rfft(mono * window)) / (chunk * 0.25)
                    bands = []
                    for b0, b1 in bin_slices:
                        val = float(np.mean(spec[b0:b1])) if b1 > b0 else 0.0
                        # Compressão logarítmica suave (escala natural para música e jogos)
                        bands.append(min(1.0, math.log1p(val * 14.0) / 2.2))
                    self._live_target = bands
        except Exception:
            self._live_active = False

    def update(self, dt: float, active_music: bool = False, bpm: float = 84.0) -> AudioFrame:
        """Avança o espectro suavizado (usa captura WASAPI real se houver som no PC, senão brisa/lo-fi suave)."""
        dt = max(0.0, min(dt, 0.1))
        self._phase += dt
        if not self.enabled:
            self._levels = [v * max(0.0, 1.0 - dt * 10.0) for v in self._levels]
            self.frame = AudioFrame(bands=tuple(self._levels))
            return self.frame

        n = self.num_bands
        smooth = min(1.0, dt * 15.0)
        has_live_signal = self._live_active and (max(self._live_target) > 0.02)

        if has_live_signal:
            for i in range(n):
                self._levels[i] += (self._live_target[i] - self._levels[i]) * smooth
        else:
            # Fallback orgânico suave (pulso lo-fi quando música/demo ativa, respiração leve em silêncio)
            beat_hz = bpm / 60.0
            beat_phase = (self._phase * beat_hz) % 1.0
            kick = math.exp(-beat_phase * 7.0)
            snare = math.exp(-(((self._phase * beat_hz) + 0.5) % 1.0) * 8.5) * 0.72
            intensity = 0.88 if active_music else 0.22
            for i in range(n):
                u = i / max(n - 1, 1)
                low_env = math.exp(-((u - 0.12) / 0.20) ** 2) * (0.42 + 0.58 * kick)
                mid_env = math.exp(-((u - 0.48) / 0.24) ** 2) * (
                    0.32 + 0.42 * snare + 0.26 * (0.5 + 0.5 * math.sin(self._phase * 2.5 + i * 0.5))
                )
                high_env = math.exp(-((u - 0.82) / 0.22) ** 2) * (
                    0.22 + 0.38 * (0.5 + 0.5 * math.sin(self._phase * 5.8 + i * 1.1))
                )
                target = max(0.01, min(1.0, (low_env + mid_env + high_env) * intensity))
                self._levels[i] += (target - self._levels[i]) * smooth

        k_low = max(3, n // 5)
        k_mid = max(k_low + 1, (n * 3) // 5)
        bass = sum(self._levels[:k_low]) / k_low
        mid = sum(self._levels[k_low:k_mid]) / max(1, k_mid - k_low)
        treble = sum(self._levels[k_mid:]) / max(1, n - k_mid)
        energy = sum(self._levels) / n
        beat = max(0.0, min(1.0, (bass - self._prev_bass) * 4.5 + bass * 0.55))
        self._prev_bass = bass

        self.frame = AudioFrame(
            bands=tuple(self._levels),
            bass=bass,
            mid=mid,
            treble=treble,
            energy=energy,
            beat=beat,
            live_capture=has_live_signal,
        )
        return self.frame
