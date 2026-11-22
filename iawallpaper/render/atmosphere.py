"""ATMOSPHERE — Paleta de cores, iluminação de borda (rim light) e gradação climática em tempo real."""

from dataclasses import dataclass

from ..mathutil import clamp, lerp
from ..sense.circadian import CircadianState
from ..sense.weather import WeatherState

RGB = tuple[int, int, int]


def _mix_rgb(a: RGB, b: RGB, t: float) -> RGB:
    k = clamp(t, 0.0, 1.0)
    return (
        int(round(lerp(a[0], b[0], k))),
        int(round(lerp(a[1], b[1], k))),
        int(round(lerp(a[2], b[2], k))),
    )


def _desaturate(c: RGB, amount: float, darken: float = 0.0) -> RGB:
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    r = lerp(c[0], lum, amount) * (1.0 - darken)
    g = lerp(c[1], lum, amount) * (1.0 - darken)
    b = lerp(c[2], lum, amount) * (1.0 - darken)
    return (int(clamp(r, 0, 255)), int(clamp(g, 0, 255)), int(clamp(b, 0, 255)))


@dataclass(frozen=True)
class AtmospherePalette:
    sky_top: RGB
    sky_mid: RGB
    sky_horizon: RGB
    celestial_core: RGB
    celestial_glow: RGB
    cloud_light: RGB
    cloud_shadow: RGB
    mountain_far: RGB
    mountain_mid: RGB
    mountain_near: RGB
    water_top: RGB
    water_bottom: RGB
    window_light: RGB
    rim_light: RGB
    avatar_tint: RGB
    avatar_tint_alpha: float
    window_glow_alpha: float
    fog_alpha: float
    star_alpha: float


# Keyframes de paleta ao longo de 24h: (hora, sky_top, sky_mid, sky_horizon, m_far, m_mid, m_near, rim)
_KEYFRAMES: list[tuple[float, RGB, RGB, RGB, RGB, RGB, RGB, RGB]] = [
    (0.0,  (8, 12, 32),    (16, 24, 58),   (28, 42, 86),   (20, 28, 56),   (14, 20, 44),   (9, 13, 28),    (140, 185, 255)),
    (5.5,  (24, 28, 68),   (78, 56, 108),  (215, 125, 130),(52, 46, 86),   (36, 32, 66),   (22, 20, 44),   (255, 178, 155)),
    (7.0,  (56, 118, 198), (125, 176, 232),(255, 206, 168),(96, 124, 172), (66, 92, 138),  (42, 62, 98),   (255, 224, 182)),
    (12.0, (42, 128, 224), (108, 184, 246),(206, 236, 255),(110, 152, 204),(76, 118, 168), (44, 78, 118),  (242, 248, 255)),
    (16.5, (52, 118, 208), (128, 174, 230),(238, 218, 198),(104, 128, 172),(72, 94, 138),  (44, 62, 96),   (255, 232, 198)),
    (18.0, (44, 48, 104),  (148, 76, 114), (255, 152, 98), (78, 56, 96),   (54, 38, 72),   (30, 22, 46),   (255, 176, 118)),
    (19.6, (20, 24, 62),   (56, 42, 98),   (138, 76, 118), (38, 34, 72),   (26, 24, 54),   (15, 14, 34),   (198, 150, 255)),
    (21.5, (10, 15, 40),   (20, 30, 68),   (38, 52, 98),   (24, 34, 66),   (16, 24, 48),   (10, 15, 32),   (148, 194, 255)),
    (24.0, (8, 12, 32),    (16, 24, 58),   (28, 42, 86),   (20, 28, 56),   (14, 20, 44),   (9, 13, 28),    (140, 185, 255)),
]


def _sample_keyframes(hour: float):
    h = hour % 24.0
    for i in range(len(_KEYFRAMES) - 1):
        k0 = _KEYFRAMES[i]
        k1 = _KEYFRAMES[i + 1]
        if k0[0] <= h <= k1[0]:
            span = max(k1[0] - k0[0], 1e-4)
            t = (h - k0[0]) / span
            return tuple(_mix_rgb(k0[j], k1[j], t) for j in range(1, 8))
    return _KEYFRAMES[0][1:]


def compute_atmosphere(circadian: CircadianState, weather: WeatherState, lightning: float = 0.0) -> AtmospherePalette:
    """Calcula paleta completa harmonizada entre hora do dia, clima e relâmpagos."""
    sky_top, sky_mid, sky_hor, m_far, m_mid, m_near, rim = _sample_keyframes(circadian.hour)

    cond = weather.condition
    w_int = weather.intensity
    fog_alpha = 0.0
    star_mult = 1.0

    if cond == "cloudy":
        desat, dark = 0.35 * w_int, 0.14 * w_int
        sky_top = _desaturate(sky_top, desat, dark)
        sky_mid = _desaturate(sky_mid, desat, dark * 0.8)
        sky_hor = _desaturate(sky_hor, desat, dark * 0.6)
        star_mult = 0.35
    elif cond == "rain":
        desat, dark = 0.48, 0.28
        slate = (52, 72, 102)
        sky_top = _mix_rgb(_desaturate(sky_top, desat, dark), slate, 0.38)
        sky_mid = _mix_rgb(_desaturate(sky_mid, desat, dark), (76, 98, 128), 0.38)
        sky_hor = _mix_rgb(_desaturate(sky_hor, desat, dark * 0.7), (108, 128, 152), 0.35)
        m_far = _desaturate(m_far, 0.45, 0.22)
        m_mid = _desaturate(m_mid, 0.45, 0.22)
        m_near = _desaturate(m_near, 0.40, 0.20)
        rim = _mix_rgb(rim, (160, 210, 245), 0.5)
        fog_alpha = 0.22
        star_mult = 0.1
    elif cond == "storm":
        sky_top = _mix_rgb(_desaturate(sky_top, 0.65, 0.48), (22, 28, 52), 0.55)
        sky_mid = _mix_rgb(_desaturate(sky_mid, 0.60, 0.42), (38, 48, 78), 0.55)
        sky_hor = _mix_rgb(_desaturate(sky_hor, 0.55, 0.36), (62, 74, 104), 0.50)
        m_far = _desaturate(m_far, 0.60, 0.38)
        m_mid = _desaturate(m_mid, 0.60, 0.38)
        m_near = _desaturate(m_near, 0.55, 0.35)
        rim = (175, 205, 255)
        fog_alpha = 0.32
        star_mult = 0.0
    elif cond == "snow":
        ice = (205, 222, 242)
        sky_top = _mix_rgb(sky_top, ice, 0.26 * circadian.daylight + 0.10)
        sky_mid = _mix_rgb(sky_mid, ice, 0.35 * circadian.daylight + 0.12)
        sky_hor = _mix_rgb(sky_hor, (232, 242, 255), 0.45 * circadian.daylight + 0.15)
        rim = (225, 242, 255)
        fog_alpha = 0.18
        star_mult = 0.25
    elif cond == "fog":
        mist = _mix_rgb((175, 190, 210), (70, 82, 110), circadian.night_factor)
        sky_mid = _mix_rgb(sky_mid, mist, 0.48)
        sky_hor = _mix_rgb(sky_hor, mist, 0.65)
        m_far = _mix_rgb(m_far, mist, 0.55)
        fog_alpha = 0.48
        star_mult = 0.15

    # Flash de relâmpago ilumina céu e rim-light instantaneamente
    if lightning > 0.01:
        lt = clamp(lightning, 0.0, 1.0)
        flash = (235, 244, 255)
        sky_top = _mix_rgb(sky_top, flash, lt * 0.65)
        sky_mid = _mix_rgb(sky_mid, flash, lt * 0.72)
        sky_hor = _mix_rgb(sky_hor, flash, lt * 0.55)
        rim = _mix_rgb(rim, flash, lt * 0.9)

    is_day = circadian.daylight >= 0.35
    celestial_core = (255, 248, 220) if is_day else (238, 244, 255)
    celestial_glow = _mix_rgb((255, 208, 130), (255, 135, 95), circadian.warmth) if is_day else (140, 182, 255)

    cloud_light = _mix_rgb((250, 252, 255), sky_hor, 0.45) if is_day else _mix_rgb((66, 82, 128), sky_hor, 0.4)
    cloud_shadow = _mix_rgb(sky_mid, m_far, 0.55)

    water_top = _mix_rgb(sky_hor, m_mid, 0.35)
    water_bottom = _mix_rgb(sky_top, m_near, 0.65)

    window_glow = clamp((circadian.night_factor - 0.25) / 0.55, 0.0, 1.0)
    window_light = (255, 216, 138)

    # Tonalização sutil do avatar para integrar perfeitamente no cenário
    avatar_tint = _mix_rgb(sky_hor, rim, 0.55)
    avatar_tint_alpha = clamp(0.06 + 0.16 * circadian.night_factor + 0.10 * circadian.warmth, 0.05, 0.26)

    return AtmospherePalette(
        sky_top=sky_top,
        sky_mid=sky_mid,
        sky_horizon=sky_hor,
        celestial_core=celestial_core,
        celestial_glow=celestial_glow,
        cloud_light=cloud_light,
        cloud_shadow=cloud_shadow,
        mountain_far=m_far,
        mountain_mid=m_mid,
        mountain_near=m_near,
        water_top=water_top,
        water_bottom=water_bottom,
        window_light=window_light,
        rim_light=rim,
        avatar_tint=avatar_tint,
        avatar_tint_alpha=avatar_tint_alpha,
        window_glow_alpha=window_glow,
        fog_alpha=fog_alpha,
        star_alpha=clamp(circadian.star_visibility * star_mult, 0.0, 1.0),
    )
