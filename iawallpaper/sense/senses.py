"""SENSES — Classificação de atividades do PC e tradução para canais 0..1 da rede neural."""

import math
import time

from ..mathutil import clamp
from .circadian import CircadianState
from .weather import WeatherState

ACTIVITY_APPS: dict[str, set[str]] = {
    "PROGRAMMING": {
        "code", "devenv", "pycharm64", "pycharm", "cursor", "windsurf", "zed",
        "windowsterminal", "wt", "powershell", "pwsh", "cmd", "idea64", "webstorm64",
        "rider64", "clion64", "sublime_text", "notepad++", "antigravity", "studio64",
    },
    "AI_STUDIO": {
        "comfyui", "studio_service", "ollama", "lm studio", "lmstudio",
    },
    "DESIGNING": {
        "blender", "figma", "photoshop", "illustrator", "afterfx", "premiere",
        "resolve", "capcut", "krita", "inkscape", "aseprite", "gimp",
    },
    "GAMING": {
        "steam", "valorant", "cs2", "league of legends", "robloxplayerbeta",
        "minecraft.windows", "fortniteclient-win64-shipping", "eldenring",
        "cyberpunk2077", "genshinimpact", "starrail", "zenlesszonezero",
        "dota2", "overwatch", "gta5", "rocketleague", "hollow_knight",
    },
    "BROWSING": {
        "chrome", "chromium", "firefox", "msedge", "opera", "brave", "vivaldi", "zen",
    },
    "SOCIAL": {
        "discord", "telegram", "whatsapp", "teams", "slack",
    },
    "MUSIC": {
        "spotify", "foobar2000", "musicbee", "aimp", "vlc", "tidal",
    },
}

ACTIVITY_CHANNEL = {
    "PROGRAMMING": "WORK",
    "DESIGNING": "WORK",
    "AI_STUDIO": "AI_CRAFT",
    "GAMING": "PLAY",
    "MUSIC": "MUSIC",
    "SOCIAL": "SOCIAL",
    "BROWSING": "WEB",
}


def normalize_app_name(app: str) -> str:
    name = (app or "").strip().lower()
    return name[:-4] if name.endswith(".exe") else name


def detect_activity(app: str, idle_seconds: float, away_after: float = 180.0, comfy_busy: bool = False) -> str:
    """Classifica o momento do usuário em uma atividade de alto nível."""
    if idle_seconds >= away_after:
        return "AWAY"
    name = normalize_app_name(app)
    for activity, apps in ACTIVITY_APPS.items():
        if name in apps:
            return activity
    if comfy_busy and name in ("desktop", "chrome", "msedge", "firefox", "brave", "python"):
        return "AI_STUDIO"
    return "IDLE"


class ActivityTracker:
    """Detecta transições: APP_CHANGED, ACTIVITY_CHANGED, USER_LEFT, USER_RETURNED."""

    def __init__(self):
        self.app: str | None = None
        self.activity: str = "IDLE"
        self.session_start: float = time.monotonic()

    def observe(self, app: str, activity: str) -> list[str]:
        events: list[str] = []
        if self.app is not None:
            if activity != self.activity:
                if activity == "AWAY":
                    events.append("USER_LEFT")
                elif self.activity == "AWAY":
                    events.append("USER_RETURNED")
                    self.session_start = time.monotonic()
                else:
                    events.append("ACTIVITY_CHANGED")
            if app != self.app and activity != "AWAY":
                events.append("APP_CHANGED")
        self.app = app
        self.activity = activity
        return events

    @property
    def session_seconds(self) -> float:
        return time.monotonic() - self.session_start


class ContextSenses:
    """Converte PC + ambiente (dia/noite + clima) + interação em canais [0..1] para a rede LIF."""

    PULSE_TAU = {
        "MOTION": 2.0,
        "NOVELTY": 3.5,
        "POKE": 1.6,
        "GIFT": 4.0,
        "DISMISS": 5.5,
    }

    def __init__(self):
        self.pulse = {k: 0.0 for k in self.PULSE_TAU}
        self.level = {k: 0.0 for k in ("WORK", "AI_CRAFT", "PLAY", "MUSIC", "SOCIAL", "WEB")}
        self.typing = 0.0
        self.caress = 0.0
        self.last = time.monotonic()

    def kick(self, channel: str, amount: float) -> None:
        if channel in self.pulse:
            self.pulse[channel] = clamp(self.pulse[channel] + amount, 0.0, 1.0)

    def on_events(self, events: list[str]) -> None:
        for ev in events:
            if ev == "APP_CHANGED":
                self.kick("MOTION", 0.70)
            elif ev in ("ACTIVITY_CHANGED", "USER_RETURNED"):
                self.kick("NOVELTY", 0.95)

    def update(
        self,
        activity: str,
        idle_seconds: float,
        drives_channels: dict[str, float],
        circadian: CircadianState,
        weather: WeatherState,
        telemetry: dict[str, float],
        caressing: bool = False,
        mouse_moving: bool = False,
        anticipate: float = 0.0,
    ) -> dict[str, float]:
        now = time.monotonic()
        dt = clamp(now - self.last, 0.0, 1.0)
        self.last = now

        for k, tau in self.PULSE_TAU.items():
            self.pulse[k] *= math.exp(-dt / tau)

        active_ch = ACTIVITY_CHANNEL.get(activity)
        for ch in self.level:
            target = 1.0 if ch == active_ch else 0.0
            self.level[ch] += (target - self.level[ch]) * (1.0 - math.exp(-dt / 3.0))

        typing_now = 1.0 if (idle_seconds < 0.35 and not mouse_moving and not caressing) else 0.0
        self.typing += (typing_now - self.typing) * (1.0 - math.exp(-dt / 1.8))

        caress_now = 1.0 if caressing else 0.0
        self.caress += (caress_now - self.caress) * (1.0 - math.exp(-dt / 0.6))

        sys_load = clamp((telemetry.get("cpu", 0.0) - 0.35) / 0.65)
        silence = clamp((idle_seconds - 6.0) / 60.0)

        out: dict[str, float] = {}
        out.update(self.level)
        out.update(self.pulse)
        out["TYPING"] = self.typing
        out["CARESS"] = self.caress
        out["SILENCE"] = silence
        out["SYS_LOAD"] = sys_load
        out["DAYLIGHT"] = circadian.daylight
        out["NIGHT"] = circadian.night_factor
        out.update(weather.channels())
        out.update(drives_channels)
        out["ANTICIPATE"] = clamp(anticipate)
        return out
