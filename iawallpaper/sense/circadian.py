"""CIRCADIAN — Ciclo solar e circadiano contínuo (24h) para iluminação do cenário e energia da avatar."""

from dataclasses import dataclass
from datetime import datetime
import math

from ..mathutil import clamp, smoothstep


@dataclass(frozen=True)
class CircadianState:
    hour: float             # 0.0 .. 24.0
    period: str             # dawn | morning | afternoon | golden_hour | twilight | night | late_night
    label_pt: str
    sun_elevation: float    # -1.0 (meia-noite) .. +1.0 (meio-dia)
    daylight: float         # 0.0 .. 1.0
    night_factor: float     # 0.0 .. 1.0
    warmth: float           # 0.0 .. 1.0 (pico na alvorada e pôr do sol)
    star_visibility: float  # 0.0 .. 1.0
    sun_x_norm: float       # 0.0 .. 1.0 posição horizontal do sol/lua


PERIOD_LABELS_PT = {
    "dawn": "Alvorada",
    "morning": "Manhã",
    "afternoon": "Tarde",
    "golden_hour": "Pôr do Sol",
    "twilight": "Crepúsculo",
    "night": "Noite",
    "late_night": "Madrugada",
}


def classify_period(hour: float) -> str:
    h = hour % 24.0
    if 5.0 <= h < 7.5:
        return "dawn"
    if 7.5 <= h < 12.0:
        return "morning"
    if 12.0 <= h < 17.0:
        return "afternoon"
    if 17.0 <= h < 19.0:
        return "golden_hour"
    if 19.0 <= h < 20.5:
        return "twilight"
    if 20.5 <= h < 24.0:
        return "night"
    return "late_night"


def compute_circadian(override_hour: float | None = None, now: datetime | None = None) -> CircadianState:
    """Calcula parâmetros contínuos de iluminação e período do dia."""
    if override_hour is not None:
        hour = float(override_hour) % 24.0
    else:
        dt = now or datetime.now()
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0

    period = classify_period(hour)
    # Elevação solar senoidal com pico às 12h30 e vale às 00h30
    angle = ((hour - 6.5) / 24.0) * 2.0 * math.pi
    sun_elev = math.sin(angle)

    daylight = smoothstep(-0.18, 0.28, sun_elev)
    night_factor = 1.0 - daylight
    star_vis = smoothstep(0.35, 0.92, night_factor)

    # Calor dourado na alvorada (~6h15) e golden hour (~18h00)
    dawn_warmth = math.exp(-((hour - 6.25) ** 2) / 1.8)
    sunset_warmth = math.exp(-((hour - 18.0) ** 2) / 2.2)
    warmth = clamp(max(dawn_warmth, sunset_warmth), 0.0, 1.0)

    # Posição horizontal do astro principal no céu
    if daylight >= 0.35:
        sun_x = clamp((hour - 5.5) / 13.5, 0.08, 0.92)
    else:
        moon_h = (hour - 19.0) % 24.0
        sun_x = clamp(moon_h / 11.0, 0.12, 0.88)

    return CircadianState(
        hour=hour,
        period=period,
        label_pt=PERIOD_LABELS_PT[period],
        sun_elevation=sun_elev,
        daylight=daylight,
        night_factor=night_factor,
        warmth=warmth,
        star_visibility=star_vis,
        sun_x_norm=sun_x,
    )
