"""Configurações persistentes do IAWallpaper com validação de domínio."""

from dataclasses import asdict, dataclass
from pathlib import Path

from .mathutil import clamp, valor_real
from .store import read_json, write_json

VALID_MODES = ("wallpaper", "preview")
VALID_RENDER_STYLES = ("world_sprite", "live2d_25d", "vrm_3d", "portrait")
VALID_WEATHER_MODES = ("auto", "clear", "cloudy", "rain", "storm", "snow", "fog")
VALID_OUTFITS = (None, "base", "cozy_shirt", "casual", "cozy", "rainy", "focus", "nightwear", "starlight")


@dataclass
class Settings:
    persona_id: str = "mira"
    character_id: str = "arya"
    scene_id: str = "cozy_loft_arya"
    mode: str = "wallpaper"
    render_style: str = "world_sprite"
    vrm_model: str = "elfa_loira"
    vrm_dynamic_recolor: bool = False
    fps_cap: int = 60
    auto_pause_fullscreen: bool = True
    parallax_strength: float = 1.0
    particle_density: float = 1.0
    avatar_scale: float = 1.0
    avatar_x_ratio: float = 0.72
    whispers_enabled: bool = True
    weather_mode: str = "auto"
    weather_city: str = ""
    weather_lat: float | None = None
    weather_lon: float | None = None
    time_override_hour: float | None = None
    outfit_override: str | None = None
    comfyui_url: str = "http://127.0.0.1:8188"
    comfyui_preset: str = "RawSexyGlowingGemPencil(TOP)"
    comfyui_enabled: bool = True
    start_with_windows: bool = False
    test_mode: bool = False

    def sanitized(self) -> "Settings":
        """Retorna uma cópia validada dentro dos domínios seguros."""
        mode = self.mode if self.mode in VALID_MODES else "wallpaper"
        render_style = self.render_style if self.render_style in VALID_RENDER_STYLES else "world_sprite"
        weather_mode = self.weather_mode if self.weather_mode in VALID_WEATHER_MODES else "auto"
        outfit = self.outfit_override if self.outfit_override in VALID_OUTFITS else None
        fps_cap = 30 if int(self.fps_cap) <= 30 else 60
        time_override = None
        if self.time_override_hour is not None:
            try:
                time_override = valor_real(self.time_override_hour, 0.0, 24.0) % 24.0
            except ValueError:
                time_override = None
        lat = None
        lon = None
        if self.weather_lat is not None and self.weather_lon is not None:
            try:
                lat = valor_real(self.weather_lat, -90.0, 90.0)
                lon = valor_real(self.weather_lon, -180.0, 180.0)
            except ValueError:
                lat, lon = None, None
        return Settings(
            persona_id=str(self.persona_id or "mira").strip().lower(),
            character_id=str(self.character_id or "arya").strip().lower(),
            scene_id=str(self.scene_id or "sky_sanctuary").strip().lower(),
            mode=mode,
            render_style=render_style,
            vrm_model=str(self.vrm_model or "").strip(),
            vrm_dynamic_recolor=bool(self.vrm_dynamic_recolor),
            fps_cap=fps_cap,
            auto_pause_fullscreen=bool(self.auto_pause_fullscreen),
            parallax_strength=clamp(float(self.parallax_strength), 0.0, 2.0),
            particle_density=clamp(float(self.particle_density), 0.0, 2.0),
            avatar_scale=clamp(float(self.avatar_scale), 0.5, 1.6),
            avatar_x_ratio=clamp(float(self.avatar_x_ratio), 0.15, 0.88),
            whispers_enabled=bool(self.whispers_enabled),
            weather_mode=weather_mode,
            weather_city=str(self.weather_city or "").strip(),
            weather_lat=lat,
            weather_lon=lon,
            time_override_hour=time_override,
            outfit_override=outfit,
            comfyui_url=str(self.comfyui_url or "http://127.0.0.1:8188").strip().rstrip("/"),
            comfyui_preset=str(self.comfyui_preset or "RawSexyGlowingGemPencil(TOP)").strip(),
            comfyui_enabled=bool(self.comfyui_enabled),
            start_with_windows=bool(self.start_with_windows),
            test_mode=bool(self.test_mode),
        )

    def save(self, path: str | Path) -> None:
        write_json(path, asdict(self.sanitized()), indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        raw = read_json(path, default=None)
        if not isinstance(raw, dict):
            return cls()
        allowed = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in raw.items() if k in allowed}
        try:
            return cls(**filtered).sanitized()
        except Exception:
            return cls()
