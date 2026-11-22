"""WEATHER — Serviço de clima em tempo real via Open-Meteo (sem API key), cache local e overrides manuais."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request

from ..log import log
from ..mathutil import clamp
from ..store import read_json, write_json

WEATHER_LABELS_PT = {
    "clear": "Céu Limpo",
    "cloudy": "Nublado",
    "rain": "Chuva",
    "storm": "Tempestade",
    "snow": "Neve",
    "fog": "Neblina",
}


def map_wmo_code(code: int) -> tuple[str, float]:
    """Traduz código WMO da Open-Meteo para (condição, intensidade 0..1)."""
    c = int(code)
    if c in (0, 1):
        return "clear", 0.0
    if c in (2, 3):
        return "cloudy", 0.55 if c == 2 else 0.85
    if c in (45, 48):
        return "fog", 0.75
    if c in (51, 53, 55, 56, 57):
        return "rain", 0.45
    if c in (61, 63, 80, 81):
        return "rain", 0.72
    if c in (65, 66, 67, 82):
        return "rain", 0.95
    if c in (71, 73, 75, 77, 85, 86):
        return "snow", 0.75
    if c in (95, 96, 99):
        return "storm", 0.95
    return "clear", 0.0


@dataclass
class WeatherState:
    condition: str = "clear"       # clear | cloudy | rain | storm | snow | fog
    intensity: float = 0.0         # 0..1
    temperature_c: float = 22.0
    wind_speed: float = 6.0        # km/h
    city: str = "Local"
    source: str = "fallback"       # live | cache | override | fallback
    updated_at: float = 0.0

    @property
    def label_pt(self) -> str:
        return WEATHER_LABELS_PT.get(self.condition, "Céu Limpo")

    def channels(self) -> dict[str, float]:
        """Converte clima em canais sensoriais 0..1 para a rede neural."""
        rain = 0.0
        storm = 0.0
        if self.condition == "rain":
            rain = clamp(0.45 + 0.55 * self.intensity)
        elif self.condition == "storm":
            rain = 0.9
            storm = clamp(0.65 + 0.35 * self.intensity)
        elif self.condition in ("snow", "fog"):
            rain = 0.35  # gera sensação acolhedora/cozy semelhante
        return {"RAIN": rain, "STORM": storm}


def _http_get_json(url: str, timeout: float = 5.0) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "IAWallpaper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)


class WeatherService:
    """Busca clima real em background (Open-Meteo) com fallback offline instantâneo."""

    def __init__(self, cache_path: Path | None = None):
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._state = WeatherState()
        self._fetching = False
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_path:
            return
        data = read_json(self.cache_path, default=None)
        if not isinstance(data, dict):
            return
        cond = data.get("condition", "clear")
        if cond not in WEATHER_LABELS_PT:
            cond = "clear"
        self._state = WeatherState(
            condition=cond,
            intensity=clamp(float(data.get("intensity", 0.0))),
            temperature_c=float(data.get("temperature_c", 22.0)),
            wind_speed=max(0.0, float(data.get("wind_speed", 6.0))),
            city=str(data.get("city", "Local")),
            source="cache",
            updated_at=float(data.get("updated_at", 0.0)),
        )

    def current(self, override_mode: str = "auto") -> WeatherState:
        """Retorna clima efetivo (respeitando override manual da Central de Controle)."""
        with self._lock:
            base = self._state
        if override_mode and override_mode != "auto" and override_mode in WEATHER_LABELS_PT:
            intensity = 0.0 if override_mode == "clear" else 0.8
            wind = 22.0 if override_mode == "storm" else (12.0 if override_mode == "rain" else 6.0)
            return WeatherState(
                condition=override_mode,
                intensity=intensity,
                temperature_c=base.temperature_c,
                wind_speed=wind,
                city=base.city,
                source="override",
                updated_at=time.time(),
            )
        return base

    def refresh_async(self, city: str = "", lat: float | None = None, lon: float | None = None) -> None:
        """Atualiza o clima em thread daemon sem bloquear a interface."""
        with self._lock:
            if self._fetching:
                return
            self._fetching = True

        def worker():
            try:
                state = self.fetch_sync(city=city, lat=lat, lon=lon)
                if state is not None:
                    with self._lock:
                        self._state = state
                    if self.cache_path:
                        try:
                            write_json(self.cache_path, asdict(state), indent=2)
                        except OSError:
                            pass
                    log(f"[weather] {state.city}: {state.label_pt} ({state.temperature_c:.1f}°C, vento {state.wind_speed:.0f} km/h)")
            finally:
                with self._lock:
                    self._fetching = False

        threading.Thread(target=worker, daemon=True, name="iawallpaper-weather").start()

    def fetch_sync(self, city: str = "", lat: float | None = None, lon: float | None = None) -> WeatherState | None:
        """Consulta Open-Meteo (geocodificando cidade ou usando IP se lat/lon ausentes)."""
        resolved_city = city.strip() if city else ""
        try:
            if lat is None or lon is None:
                if resolved_city:
                    q = urllib.parse.quote(resolved_city)
                    geo = _http_get_json(f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=pt&format=json")
                    results = (geo or {}).get("results") or []
                    if results:
                        lat = float(results[0]["latitude"])
                        lon = float(results[0]["longitude"])
                        resolved_city = str(results[0].get("name", resolved_city))
                if lat is None or lon is None:
                    ip_info = _http_get_json("https://ipwho.is/", timeout=4.0)
                    if isinstance(ip_info, dict) and ip_info.get("success", True) and "latitude" in ip_info:
                        lat = float(ip_info["latitude"])
                        lon = float(ip_info["longitude"])
                        resolved_city = str(ip_info.get("city") or resolved_city or "Local")
            if lat is None or lon is None:
                return None

            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat:.4f}&longitude={lon:.4f}"
                f"&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto"
            )
            data = _http_get_json(url, timeout=5.0)
            cur = (data or {}).get("current") or {}
            cond, intensity = map_wmo_code(cur.get("weather_code", 0))
            return WeatherState(
                condition=cond,
                intensity=intensity,
                temperature_c=float(cur.get("temperature_2m", 22.0)),
                wind_speed=max(0.0, float(cur.get("wind_speed_10m", 5.0))),
                city=resolved_city or "Local",
                source="live",
                updated_at=time.time(),
            )
        except Exception as err:
            log(f"[weather] consulta offline/falha (mantendo cache): {err}")
            return None
