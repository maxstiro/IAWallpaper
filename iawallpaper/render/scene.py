"""SCENE — Compositor multi-camada do wallpaper dinâmico (céu, astros, nuvens, montanhas, luzes urbanas, água, avatar e sussurros)."""

import math
from pathlib import Path
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from ..core.emotion import EmotionState
from ..mathutil import clamp, lerp, smoothstep
from ..sense.circadian import CircadianState
from ..sense.weather import WeatherState
from .atmosphere import AtmospherePalette, compute_atmosphere
from .avatar import AvatarRig
from .particles import ParticleEngine
from .world_stage import WorldStage


class SceneCompositor:
    """Compõe todas as camadas do wallpaper dinâmico (suporta cenários gerados no ComfyUI + cena procedural viva)."""

    def __init__(self, scene_dirs: list[Path] | Path | None = None, seed: int = 2026):
        self.scene_dirs = self._normalize_dirs(scene_dirs)
        self.stage = WorldStage(seed=seed)
        rng = random.Random(seed)
        self.time: float = 0.0
        self.parallax_x: float = 0.0
        self.parallax_y: float = 0.0
        self.target_px: float = 0.0
        self.target_py: float = 0.0

        # Estrelas determinísticas (x_norm, y_norm, radius, phase)
        self._stars = [
            (rng.uniform(0.01, 0.99), rng.uniform(0.02, 0.56), rng.uniform(0.8, 2.4), rng.uniform(0.0, math.tau))
            for _ in range(150)
        ]
        # Nuvens (x_norm, y_norm, scale, speed)
        self._clouds = [
            [rng.uniform(0.0, 1.2), rng.uniform(0.09, 0.38), rng.uniform(0.75, 1.55), rng.uniform(0.004, 0.014)]
            for _ in range(9)
        ]
        # Janelas iluminadas na cidade distante (x_norm, y_offset, warm_hue)
        self._city_lights = [
            (rng.uniform(0.04, 0.62), rng.uniform(0.0, 1.0), rng.uniform(0.7, 1.0))
            for _ in range(72)
        ]

        # Imagens de cenário opcionais (geradas pelo ComfyUI): day.png, sunset.png, night.png, rain.png
        self._bg_images: dict[str, QPixmap] = {}
        self._current_bg_key: str | None = None
        self._prev_bg: QPixmap | None = None
        self._bg_fade_t: float = 1.0
        self.reload_scene_images()

        # Bolha de sussurro contextual
        self.whisper_text: str = ""
        self.whisper_alpha: float = 0.0
        self.whisper_rect = QRectF()

    @staticmethod
    def _normalize_dirs(dirs: list[Path] | Path | None) -> list[Path]:
        if dirs is None:
            return []
        if isinstance(dirs, (list, tuple)):
            return [Path(d) for d in dirs if d is not None]
        return [Path(dirs)]

    def reload_scene_images(self, scene_dirs: list[Path] | Path | None = None) -> None:
        if scene_dirs is not None:
            self.scene_dirs = self._normalize_dirs(scene_dirs)
            self._current_bg_key = None
            self._prev_bg = None
            self._bg_fade_t = 1.0
        self._bg_images.clear()
        for folder in self.scene_dirs:
            if not folder.exists():
                continue
            for png in folder.glob("*.png"):
                pm = QPixmap(str(png))
                if not pm.isNull():
                    self._bg_images[png.stem.lower()] = pm

    def available_scene_keys(self) -> set[str]:
        return set(self._bg_images.keys())

    def set_parallax_target(self, nx: float, ny: float, strength: float = 1.0) -> None:
        self.target_px = clamp(nx, -1.0, 1.0) * clamp(strength, 0.0, 2.0)
        self.target_py = clamp(ny, -1.0, 1.0) * clamp(strength, 0.0, 2.0)

    def set_whisper(self, text: str, alpha: float) -> None:
        self.whisper_text = text
        self.whisper_alpha = clamp(alpha, 0.0, 1.0)

    def update(self, dt: float, wind_speed: float = 6.0, condition: str = "clear") -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.stage.update(dt, condition=condition, wind_speed=wind_speed)
        k = clamp(dt * 4.5, 0.0, 1.0)
        self.parallax_x += (self.target_px - self.parallax_x) * k
        self.parallax_y += (self.target_py - self.parallax_y) * k

        wind_mul = 0.6 + wind_speed / 12.0
        for cloud in self._clouds:
            cloud[0] += cloud[3] * wind_mul * dt
            if cloud[0] > 1.25:
                cloud[0] = -0.25

        if self._bg_fade_t < 1.0:
            self._bg_fade_t = min(1.0, self._bg_fade_t + dt / 1.5)
            if self._bg_fade_t >= 1.0:
                self._prev_bg = None

    def _pick_bg_key(self, circadian: CircadianState, weather: WeatherState, prefer_diorama: bool = False) -> str | None:
        if not self._bg_images:
            return None
        prefix = "diorama_" if prefer_diorama else ""
        keys: list[str] = []
        if weather.condition in ("rain", "storm"):
            keys.extend([f"{prefix}rain", "rain"])
        elif circadian.period in ("golden_hour", "dawn", "twilight"):
            keys.extend([f"{prefix}sunset", "sunset"])
        elif circadian.night_factor >= 0.55:
            keys.extend([f"{prefix}night", "night"])
        else:
            keys.extend([f"{prefix}day", "day"])
        keys.extend([f"{prefix}sunset", f"{prefix}day", "day", "default", "base"])
        for k in keys:
            if k in self._bg_images:
                return k
        return next(iter(self._bg_images.keys()))

    def paint(
        self,
        painter: QPainter,
        width: int,
        height: int,
        circadian: CircadianState,
        weather: WeatherState,
        emotion: EmotionState,
        avatar: AvatarRig,
        particles: ParticleEngine,
        avatar_x_ratio: float = 0.72,
        avatar_scale: float = 1.0,
        asleep: bool = False,
        affinity: float = 12.0,
        activity: str = "IDLE",
    ) -> AtmospherePalette:
        """Renderiza todas as camadas do wallpaper em ordem de profundidade."""
        atmo = compute_atmosphere(circadian, weather, lightning=particles.lightning)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        is_world = avatar.render_style in ("live2d_25d", "vrm_3d", "world_sprite")
        raining = weather.condition in ("rain", "storm")
        bg_key = self._pick_bg_key(circadian, weather, prefer_diorama=is_world)
        if bg_key is not None:
            if bg_key != self._current_bg_key:
                if self._current_bg_key is not None and self._current_bg_key in self._bg_images:
                    self._prev_bg = self._bg_images[self._current_bg_key]
                    self._bg_fade_t = 0.0
                self._current_bg_key = bg_key
            bg = self._bg_images[bg_key]
            self._paint_ai_backdrop(painter, width, height, bg, atmo, circadian)
            particles.paint_sky_fx(painter)
        else:
            self._paint_sky(painter, width, height, atmo, circadian, weather)
            particles.paint_sky_fx(painter)
            self._paint_clouds(painter, width, height, atmo, weather)
            self._paint_mountains_and_city(painter, width, height, atmo)
            if is_world:
                self.stage.paint_procedural_terrace(
                    painter, width, height, atmo, self.parallax_x, self.parallax_y, wind_speed=weather.wind_speed
                )
            else:
                self._paint_water_and_balcony(painter, width, height, atmo)

        # Neblina atmosférica sobre o fundo
        if atmo.fog_alpha > 0.01:
            fog_g = QLinearGradient(0, height * 0.35, 0, height)
            fog_c = QColor(*atmo.sky_horizon)
            fog_g.setColorAt(0.0, QColor(fog_c.red(), fog_c.green(), fog_c.blue(), 0))
            fog_g.setColorAt(1.0, QColor(fog_c.red(), fog_c.green(), fog_c.blue(), int(atmo.fog_alpha * 150)))
            painter.fillRect(0, 0, width, height, fog_g)

        if is_world:
            # Dinâmica viva própria do cenário (raios solares, água/caustics, névoa, lanternas pulsando, pássaros/borboletas)
            self.stage.paint_location_dynamics(
                painter, width, height, atmo,
                daylight=circadian.daylight, warmth=circadian.warmth,
                condition=weather.condition, parallax_x=self.parallax_x, parallax_y=self.parallax_y,
            )
            # Efeitos no piso (poeira de passos, ondas de chuva & clique)
            self.stage.paint_ground_fx(painter, width, height, atmo, self.parallax_x, self.parallax_y)
            working_now = activity in ("PROGRAMMING", "AI_STUDIO", "DESIGNING")
            music_now = activity == "MUSIC"
            # Em cenas procedurais desenha todos os props; em dioramas AI pintados à mão
            # desenha apenas o tapete/mesa quando a avatar está usando (sem poluir a arte do cenário!)
            if bg_key is None:
                self.stage.paint_props_layer(
                    painter, width, height, atmo, self.parallax_x, self.parallax_y,
                    avatar_y=avatar.pos_y, behind_avatar=True, working_active=working_now, music_active=music_now,
                )
            elif avatar.action == "sleep":
                sx, sy = self.stage.screen_pos(avatar.pos_x, avatar.pos_y, width, height, self.parallax_x, self.parallax_y)
                self.stage._draw_cushion_rug(painter, sx, sy, self.stage.depth_scale(avatar.pos_y) * (height / 1080.0), atmo)

        # Avatar Waifu integrado com paralaxe, profundidade 2.5D, sombra aterrada e iluminação
        avatar.paint(
            painter=painter,
            canvas_w=width,
            canvas_h=height,
            x_ratio=avatar_x_ratio,
            scale=avatar_scale,
            emotion=emotion,
            atmosphere=atmo,
            parallax_x=self.parallax_x,
            parallax_y=self.parallax_y,
            wind=weather.wind_speed,
            asleep=asleep,
            raining=raining,
            stage=self.stage if is_world else None,
            sun_x_norm=circadian.sun_x_norm,
        )

        if is_world:
            if bg_key is None:
                self.stage.paint_props_layer(
                    painter, width, height, atmo, self.parallax_x, self.parallax_y,
                    avatar_y=avatar.pos_y, behind_avatar=False,
                    working_active=activity in ("PROGRAMMING", "AI_STUDIO", "DESIGNING"),
                    music_active=activity == "MUSIC",
                )
            elif avatar.action == "sit_work":
                sx, sy = self.stage.screen_pos(
                    avatar.pos_x + avatar.facing * 0.055, avatar.pos_y + 0.012, width, height, self.parallax_x, self.parallax_y
                )
                self.stage._draw_study_desk(painter, sx, sy, self.stage.depth_scale(avatar.pos_y) * (height / 1080.0) * 0.95, atmo, True)

        # Partículas climáticas e reações afetivas em primeiro plano
        particles.paint_weather(painter)
        particles.paint_mood_fx(painter)

        # Bolha de sussurro contextual (se ativa)
        if self.whisper_text and self.whisper_alpha > 0.02:
            self._paint_whisper_bubble(painter, width, height, avatar, atmo)
        else:
            self.whisper_rect = QRectF()

        # HUD ambiental ultra-discreto no canto inferior esquerdo (com retrato 2D expressivo se disponível!)
        display_name = avatar._char_pack.name if avatar._char_pack is not None else avatar.persona.name
        mood_portrait = avatar._char_pack.portrait_for_mood("sleepy" if asleep else emotion.mood) if avatar._char_pack is not None else None
        self._paint_ambient_hud(
            painter, width, height, circadian, weather, emotion, display_name, affinity, activity, portrait=mood_portrait
        )

        painter.restore()
        return atmo

    def _paint_ai_backdrop(self, painter: QPainter, w: int, h: int, bg: QPixmap, atmo: AtmospherePalette, circadian: CircadianState) -> None:
        pad = 28.0
        ox = -self.parallax_x * 16.0 - pad
        oy = -self.parallax_y * 10.0 - pad
        target = QRectF(ox, oy, w + pad * 2.0, h + pad * 2.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._prev_bg is not None and self._bg_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._bg_fade_t)
            painter.drawPixmap(target, self._prev_bg, QRectF(self._prev_bg.rect()))
            painter.setOpacity(ease)
            painter.drawPixmap(target, bg, QRectF(bg.rect()))
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(target, bg, QRectF(bg.rect()))
        # Gradação atmosférica suave para sincronizar dia/noite/tempestade
        grad = QLinearGradient(0, 0, 0, h)
        top = QColor(*atmo.sky_top)
        hor = QColor(*atmo.sky_horizon)
        alpha = int(clamp(32 + 52 * circadian.night_factor + 35 * atmo.fog_alpha, 20, 120))
        grad.setColorAt(0.0, QColor(top.red(), top.green(), top.blue(), alpha))
        grad.setColorAt(1.0, QColor(hor.red(), hor.green(), hor.blue(), alpha // 2))
        painter.fillRect(0, 0, w, h, grad)

    def _paint_sky(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette, circadian: CircadianState, weather: WeatherState) -> None:
        sky_g = QLinearGradient(0, 0, 0, h * 0.72)
        sky_g.setColorAt(0.0, QColor(*atmo.sky_top))
        sky_g.setColorAt(0.52, QColor(*atmo.sky_mid))
        sky_g.setColorAt(1.0, QColor(*atmo.sky_horizon))
        painter.fillRect(0, 0, w, h, sky_g)

        # Estrelas cintilantes à noite
        if atmo.star_alpha > 0.02:
            painter.setPen(Qt.NoPen)
            for sx, sy, sr, ph in self._stars:
                twinkle = 0.45 + 0.55 * math.sin(self.time * 1.9 + ph)
                a = int(235 * atmo.star_alpha * twinkle)
                px = sx * w - self.parallax_x * 6.0
                py = sy * h - self.parallax_y * 4.0
                painter.setBrush(QColor(232, 244, 255, a))
                painter.drawEllipse(QPointF(px, py), sr, sr)

        # Sol ou Lua com halo luminoso suave
        if weather.condition != "storm":
            cx = circadian.sun_x_norm * w - self.parallax_x * 8.0
            arc = math.sin(circadian.sun_x_norm * math.pi)
            cy = lerp(h * 0.48, h * 0.14, arc) - self.parallax_y * 5.0
            vis = 0.35 if weather.condition in ("rain", "cloudy", "fog") else 1.0
            halo_r = h * (0.22 if circadian.daylight >= 0.35 else 0.15)
            halo = QRadialGradient(QPointF(cx, cy), halo_r)
            gr, gg, gb = atmo.celestial_glow
            halo.setColorAt(0.0, QColor(gr, gg, gb, int(145 * vis)))
            halo.setColorAt(0.45, QColor(gr, gg, gb, int(48 * vis)))
            halo.setColorAt(1.0, QColor(gr, gg, gb, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

            disc_r = h * (0.036 if circadian.daylight >= 0.35 else 0.028)
            cr, cg, cb = atmo.celestial_core
            painter.setBrush(QColor(cr, cg, cb, int(245 * vis)))
            painter.drawEllipse(QPointF(cx, cy), disc_r, disc_r)

    def _paint_clouds(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette, weather: WeatherState) -> None:
        density = 0.48 if weather.condition == "clear" else (0.95 if weather.condition in ("cloudy", "rain", "storm") else 0.72)
        painter.setPen(Qt.NoPen)
        for idx, (cx_n, cy_n, sc, _spd) in enumerate(self._clouds):
            if idx / len(self._clouds) > density:
                continue
            cx = cx_n * w - self.parallax_x * 14.0
            cy = cy_n * h - self.parallax_y * 6.0
            rw = 140 * sc * (w / 1920.0)
            rh = 44 * sc * (h / 1080.0)
            cg = QLinearGradient(cx, cy - rh, cx, cy + rh)
            cl = QColor(*atmo.cloud_light)
            cs = QColor(*atmo.cloud_shadow)
            a = 155 if weather.condition in ("cloudy", "rain", "storm") else 108
            cg.setColorAt(0.0, QColor(cl.red(), cl.green(), cl.blue(), a))
            cg.setColorAt(1.0, QColor(cs.red(), cs.green(), cs.blue(), a))
            painter.setBrush(cg)
            painter.drawEllipse(QPointF(cx, cy), rw, rh)
            painter.drawEllipse(QPointF(cx - rw * 0.45, cy + rh * 0.16), rw * 0.65, rh * 0.72)
            painter.drawEllipse(QPointF(cx + rw * 0.42, cy + rh * 0.12), rw * 0.70, rh * 0.78)

    def _paint_mountains_and_city(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette) -> None:
        # Cordilheira distante
        self._draw_ridge(painter, w, h, base_y=0.66, amp=0.11, freq=3.1, phase=0.5, px_mul=10.0, color=atmo.mountain_far)
        # Cordilheira média
        self._draw_ridge(painter, w, h, base_y=0.72, amp=0.075, freq=4.6, phase=2.2, px_mul=18.0, color=atmo.mountain_mid)

        # Silhueta urbana aconchegante à esquerda (luzes acendem ao entardecer)
        city_y = h * 0.725 - self.parallax_y * 6.0
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*atmo.mountain_near))
        for i in range(18):
            bx = (0.03 + i * 0.033) * w - self.parallax_x * 22.0
            bw = (0.022 + (i % 3) * 0.009) * w
            bh = (0.05 + ((i * 7) % 5) * 0.026) * h
            painter.drawRect(QRectF(bx, city_y - bh, bw, bh + h * 0.08))

        if atmo.window_glow_alpha > 0.03:
            wr, wg, wb = atmo.window_light
            for lx, ly, br in self._city_lights:
                x = lx * w - self.parallax_x * 22.0
                y = city_y - (0.015 + ly * 0.115) * h
                flicker = 0.85 + 0.15 * math.sin(self.time * 1.4 + lx * 30.0)
                painter.setBrush(QColor(wr, wg, wb, int(215 * atmo.window_glow_alpha * br * flicker)))
                painter.drawRect(QRectF(x, y, 3.2, 4.2))

    def _draw_ridge(self, painter: QPainter, w: int, h: int, base_y: float, amp: float, freq: float, phase: float, px_mul: float, color: tuple[int, int, int]) -> None:
        path = QPainterPath()
        y0 = h * base_y
        path.moveTo(-40, h)
        steps = 40
        for i in range(steps + 1):
            t = i / steps
            x = -40 + t * (w + 80)
            n = math.sin(t * math.pi * freq + phase) * 0.6 + math.sin(t * math.pi * freq * 2.1 + phase * 1.7) * 0.4
            y = y0 - abs(n) * h * amp - self.parallax_y * (px_mul * 0.25)
            path.lineTo(x - self.parallax_x * px_mul, y)
        path.lineTo(w + 60, h)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*color))
        painter.drawPath(path)

    def _paint_water_and_balcony(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette) -> None:
        horizon_y = h * 0.735
        wg = QLinearGradient(0, horizon_y, 0, h)
        wg.setColorAt(0.0, QColor(*atmo.water_top))
        wg.setColorAt(1.0, QColor(*atmo.water_bottom))
        painter.fillRect(QRectF(0, horizon_y, w, h - horizon_y), wg)

        # Reflexos suaves horizontais na água
        rim = QColor(*atmo.rim_light)
        painter.setPen(Qt.NoPen)
        for i in range(18):
            ry = horizon_y + (i + 0.5) * ((h - horizon_y) / 18.0)
            rw = (0.14 + 0.24 * math.sin(i * 1.3 + self.time * 0.8)) * w
            rx = w * 0.46 + math.sin(self.time * 0.9 + i * 0.7) * 24.0 - self.parallax_x * 16.0
            painter.setBrush(QColor(rim.red(), rim.green(), rim.blue(), max(8, 36 - i)))
            painter.drawRoundedRect(QRectF(rx - rw * 0.5, ry, rw, 2.5), 1.5, 1.5)

        # Parapeito do observatório em primeiro plano (base de apoio visual)
        rail_y = h * 0.915
        painter.setBrush(QColor(*atmo.mountain_near).darker(125))
        painter.drawRect(QRectF(0, rail_y, w, h - rail_y))
        painter.setPen(QPen(QColor(rim.red(), rim.green(), rim.blue(), 110), 2.0))
        painter.drawLine(QPointF(0, rail_y), QPointF(w, rail_y))

        # Lanterna acolhedora à esquerda do centro (longe do HUD) que acende ao anoitecer
        if atmo.window_glow_alpha > 0.05:
            lx = w * 0.38 - self.parallax_x * 26.0
            ly = rail_y - 26.0
            glow = QRadialGradient(QPointF(lx, ly), 95.0)
            glow.setColorAt(0.0, QColor(255, 224, 150, int(170 * atmo.window_glow_alpha)))
            glow.setColorAt(0.45, QColor(255, 180, 95, int(65 * atmo.window_glow_alpha)))
            glow.setColorAt(1.0, QColor(255, 160, 80, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(lx, ly), 95.0, 95.0)
            painter.setBrush(QColor(255, 240, 190, int(235 * atmo.window_glow_alpha)))
            painter.drawRoundedRect(QRectF(lx - 8, ly - 14, 16, 26), 4, 4)

    def _paint_whisper_bubble(self, painter: QPainter, w: int, h: int, avatar: AvatarRig, atmo: AtmospherePalette) -> None:
        a = clamp(self.whisper_alpha)
        font = QFont("Segoe UI", max(11, int(h * 0.0135)))
        painter.setFont(font)
        fm = painter.fontMetrics()
        max_w = min(410, int(w * 0.28))
        text_rect = fm.boundingRect(0, 0, max_w, 200, Qt.TextWordWrap, self.whisper_text)
        pad_x, pad_y = 20, 14
        bw = text_rect.width() + pad_x * 2
        bh = text_rect.height() + pad_y * 2

        # Posiciona à esquerda da cabeça ou à direita se a avatar estiver na metade esquerda (nunca cobre o rosto!)
        prefer_left = avatar.head_rect.left() - bw - 20
        if prefer_left >= 28:
            bx = prefer_left
        else:
            bx = clamp(avatar.head_rect.right() + 20, 28, w - bw - 28)
        by = clamp(avatar.head_rect.top() - 6, 28, h - bh - 120)
        self.whisper_rect = QRectF(bx, by, bw, bh)

        rim = QColor(*atmo.rim_light)
        painter.setBrush(QColor(14, 18, 34, int(196 * a)))
        painter.setPen(QPen(QColor(rim.red(), rim.green(), rim.blue(), int(170 * a)), 1.5))
        painter.drawRoundedRect(self.whisper_rect, 16, 16)

        painter.setPen(QColor(242, 246, 255, int(245 * a)))
        painter.drawText(
            self.whisper_rect.adjusted(pad_x, pad_y, -pad_x, -pad_y),
            Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter,
            self.whisper_text,
        )

    def _paint_ambient_hud(
        self,
        painter: QPainter,
        w: int,
        h: int,
        circadian: CircadianState,
        weather: WeatherState,
        emotion: EmotionState,
        persona_name: str,
        affinity: float,
        activity: str,
        portrait: QPixmap | None = None,
    ) -> None:
        """Card glassmórfico discreto no canto inferior esquerdo (com medalhão de retrato 2D expressivo quando disponível)."""
        hh = int(circadian.hour) % 24
        mm = int((circadian.hour - int(circadian.hour)) * 60.0)
        sc = clamp(h / 1080.0, 0.56, 1.0)
        has_p = portrait is not None and not portrait.isNull()
        p_pad = 64.0 * sc if has_p else 0.0
        card_w, card_h = 355.0 * sc + p_pad, 74.0 * sc
        rect = QRectF(24.0 * sc, h - card_h - 54.0 * sc, card_w, card_h)

        painter.setBrush(QColor(12, 16, 30, 152))
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.0))
        painter.drawRoundedRect(rect, 14.0 * sc, 14.0 * sc)

        if has_p and portrait is not None:
            pr = 28.0 * sc
            pcx = rect.left() + 10.0 * sc + pr
            pcy = rect.center().y()
            clip_path = QPainterPath()
            clip_path.addEllipse(QPointF(pcx, pcy), pr, pr)
            painter.save()
            painter.setBrush(QColor(34, 42, 68, 220))
            painter.setPen(QPen(QColor(245, 212, 138, 195), 1.8 * sc))
            painter.drawEllipse(QPointF(pcx, pcy), pr, pr)
            painter.setClipPath(clip_path)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            pw, ph = portrait.width(), portrait.height()
            side = pr * 2.18
            scale_p = max(side / max(pw, 1), side / max(ph, 1))
            dw, dh = pw * scale_p, ph * scale_p
            painter.drawPixmap(QRectF(pcx - dw * 0.5, pcy - dh * 0.44, dw, dh), portrait, QRectF(portrait.rect()))
            painter.restore()

        tx = p_pad
        f_clock = QFont("Segoe UI", max(10, int(17 * sc)))
        f_clock.setBold(True)
        painter.setFont(f_clock)
        painter.setPen(QColor(245, 248, 255, 240))
        painter.drawText(rect.adjusted(14 * sc + tx, 7 * sc, -14 * sc, -32 * sc), Qt.AlignLeft | Qt.AlignVCenter, f"{hh:02d}:{mm:02d}")

        f_sub = QFont("Segoe UI", max(7, int(9 * sc)))
        painter.setFont(f_sub)
        painter.setPen(QColor(202, 218, 245, 220))
        line1 = f"{circadian.label_pt} · {weather.label_pt} ({weather.temperature_c:.0f}°C)"
        painter.drawText(rect.adjusted(96 * sc + tx, 9 * sc, -12 * sc, -34 * sc), Qt.AlignLeft | Qt.AlignVCenter, line1)

        line2 = f"{persona_name} · {emotion.label} · Afinidade {affinity:.0f}% · {activity}"
        painter.setPen(QColor(168, 205, 255, 215))
        painter.drawText(rect.adjusted(14 * sc + tx, 40 * sc, -12 * sc, -6 * sc), Qt.AlignLeft | Qt.AlignVCenter, line2)
