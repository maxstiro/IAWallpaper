"""AVATAR — Sprite vivo 2.5D de corpo inteiro com recorte exato na sola dos pés, sombra aterrada e animação multi-banda (Live2D/Spine).

Resolve flutuação e rigidez:
1. Auto-recorte por bounding box de alfa (`_trim_sprite_pixmap`): garante que y=altura é EXATAMENTE a sola dos sapatos/saltos!
2. Sombra dupla aterrada: oclusão escura colada aos pés + sombra direcional projetada oposta ao sol/lua + reflexo no piso molhado na chuva!
3. Deformação esquelética 2.5D em 3 bandas anatômicas sobrepostas (pernas, quadril/tronco, busto/cabeça/cabelo):
   - Pés plantados sem deslizar no idle; quadril balança, busto respira, cabeça acompanha o cursor!
   - Caminhada com cisalhamento de passo alternado, contra-balanço de quadril e cabelo acompanhando com atraso de fase!
   - Ações complexas: `walk`, `sit_work`, `stretch` (alongamento gracioso), `wave` (aceno), `admire_view`, `music_sway` (dança suave) e `sleep`!
"""

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from ..core.emotion import EmotionState
from ..core.persona import Persona
from ..mathutil import clamp, lerp, smoothstep
from .atmosphere import AtmospherePalette
from .world_stage import WorldStage


def trim_sprite_pixmap(pm: QPixmap, alpha_threshold: int = 14) -> QPixmap:
    """Recorta margens transparentes para que a base (y=height) encoste EXATAMENTE na sola dos pés."""
    if pm.isNull():
        return pm
    img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
    ys, xs = np.where(arr[:, :, 3] > alpha_threshold)
    if len(xs) == 0 or len(ys) == 0:
        return pm
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    # Mantém 2px laterais/topo para anti-aliasing e 0px abaixo da sola dos pés!
    rx0 = max(0, x0 - 2)
    ry0 = max(0, y0 - 2)
    rx1 = min(w - 1, x1 + 2)
    ry1 = min(h - 1, y1)
    return pm.copy(QRect(rx0, ry0, rx1 - rx0 + 1, ry1 - ry0 + 1))


class AvatarRig:
    """Personagem waifu madura e animada habitando o cenário 2.5D do wallpaper."""

    def __init__(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None, render_style: str = "world_sprite"):
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self.render_style: str = render_style  # "world_sprite" | "portrait"
        self.outfit: str = "casual"
        self.action: str = "idle"              # idle | walk | sit_work | stretch | wave | admire_view | music_sway | sleep

        # Posição e navegação no chão 2.5D (ancorada no plano caminhável inferior)
        self.pos_x: float = 0.56
        self.pos_y: float = 0.87
        self.target_x: float = 0.56
        self.target_y: float = 0.87
        self._arrive_action: str = "idle"
        self.facing: int = -1                  # -1 esquerda, +1 direita
        self.walk_speed: float = 0.135
        self.walk_phase: float = 0.0
        self._step_emit_accum: float = 0.0
        self.pending_footstep: tuple[float, float] | None = None

        # Temporizador para micro-animações complexas (alongar, acenar, admirar)
        self.time: float = 0.0
        self.action_timer: float = 0.0
        self.look_x: float = 0.0
        self.look_y: float = 0.0
        self.target_look_x: float = 0.0
        self.target_look_y: float = 0.0

        # Física de pulo / mola
        self.bounce_y: float = 0.0
        self.bounce_vy: float = 0.0
        self.tilt_deg: float = 0.0
        self.tilt_v: float = 0.0

        # Piscar natural
        self._blink_timer: float = 2.6
        self.blink_amount: float = 0.0

        # Balão de emote estilo Ragnarok Online / Pokémon NDS
        self.emote_kind: str = ""
        self.emote_life: float = 0.0
        self.emote_max: float = 2.6

        # Carinho & hitboxes
        self.caress_glow: float = 0.0
        self.head_rect = QRectF()
        self.body_rect = QRectF()

        # Cache de sprites RGBA já recortados nos pés + crossfade
        self._sprites: dict[str, QPixmap] = {}
        self._tint_cache: dict[tuple, QPixmap] = {}
        self._current_sprite_key: str | None = None
        self._prev_sprite: QPixmap | None = None
        self._sprite_fade_t: float = 1.0
        self.reload_sprites()

    @staticmethod
    def _normalize_dirs(dirs: list[Path] | Path | None) -> list[Path]:
        if dirs is None:
            return []
        if isinstance(dirs, (list, tuple)):
            return [Path(d) for d in dirs if d is not None]
        return [Path(dirs)]

    def set_persona(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None) -> None:
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self._current_sprite_key = None
        self._prev_sprite = None
        self._sprite_fade_t = 1.0
        self.reload_sprites()

    def reload_sprites(self) -> None:
        """Carrega sprites RGBA e recorta automaticamente a margem inferior nos pés (zero flutuação!)."""
        self._sprites.clear()
        self._tint_cache.clear()
        for folder in self.sprite_dirs:
            if not folder.exists():
                continue
            for png in folder.glob("*.png"):
                pm = QPixmap(str(png))
                if not pm.isNull():
                    key = png.stem.lower()
                    self._sprites[key] = trim_sprite_pixmap(pm) if key.startswith("sprite_") else pm

    def available_sprite_keys(self) -> set[str]:
        return set(self._sprites.keys())

    def has_world_sprites(self) -> bool:
        return any(k.startswith("sprite_") for k in self._sprites)

    def walk_to(self, tx: float, ty: float, arrive_action: str = "idle") -> None:
        cx, cy = WorldStage.clamp_walkable(tx, ty)
        self.target_x = cx
        self.target_y = cy
        self._arrive_action = arrive_action
        dist = math.hypot(cx - self.pos_x, cy - self.pos_y)
        if dist > 0.015:
            self.action = "walk"
            if abs(cx - self.pos_x) > 0.005:
                self.facing = 1 if cx > self.pos_x else -1
        else:
            self.action = arrive_action
            self.action_timer = 0.0

    def trigger_action(self, action: str) -> None:
        self.action = action
        self.action_timer = 0.0

    def show_emote(self, kind: str, duration: float = 2.6) -> None:
        self.emote_kind = kind
        self.emote_life = 0.0
        self.emote_max = max(0.8, duration)

    def impulse(self, vy: float = -210.0, tilt: float = 0.0) -> None:
        self.bounce_vy += vy
        self.tilt_v += tilt

    def set_look_target(self, nx: float, ny: float) -> None:
        self.target_look_x = clamp(nx, -1.0, 1.0)
        self.target_look_y = clamp(ny, -1.0, 1.0)

    def hit_test(self, x: float, y: float) -> str | None:
        if self.head_rect.contains(QPointF(x, y)):
            return "head"
        if self.body_rect.contains(QPointF(x, y)):
            return "body"
        return None

    def _resolve_world_sprite_key(self, mood: str, asleep: bool) -> str | None:
        candidates: list[str] = []
        if asleep or self.action == "sleep":
            candidates.extend([f"sprite_{self.outfit}_sleep", "sprite_sleep", "sprite_sit", "sprite_idle"])
        elif self.action == "walk":
            frame = "walk1" if int(self.walk_phase / math.pi) % 2 == 0 else "walk2"
            candidates.extend([f"sprite_{self.outfit}_{frame}", f"sprite_{frame}", "sprite_walk1", f"sprite_{self.outfit}", "sprite_idle"])
        elif self.action in ("sit_work", "sit_relax"):
            candidates.extend([f"sprite_{self.outfit}_sit", "sprite_sit", f"sprite_{self.outfit}", "sprite_idle"])
        elif self.action in ("wave", "stretch") or mood in ("happy", "affectionate"):
            candidates.extend([f"sprite_{self.outfit}_happy", "sprite_happy", f"sprite_{self.outfit}", "sprite_idle"])
        elif mood in ("shy", "pouty", "sleepy"):
            candidates.extend([f"sprite_{self.outfit}_{mood}", f"sprite_{mood}", f"sprite_{self.outfit}", "sprite_idle"])
        else:
            candidates.extend([f"sprite_{self.outfit}", "sprite_idle"])
        for k in candidates:
            if k in self._sprites:
                return k
        return None

    def _resolve_portrait_sprite_key(self, mood: str) -> str | None:
        mood_aliases = [mood]
        if mood == "affectionate":
            mood_aliases.append("happy")
        elif mood == "cozy":
            mood_aliases.append("calm")
        for m in mood_aliases:
            k = f"{self.outfit}_{m}"
            if k in self._sprites:
                return k
        if self.outfit in self._sprites:
            return self.outfit
        for m in mood_aliases:
            for base_k in (f"casual_{m}", m):
                if base_k in self._sprites:
                    return base_k
        for fallback in ("casual", "default", "base"):
            if fallback in self._sprites:
                return fallback
        return None

    def _get_tinted_sprite(self, sprite: QPixmap, atmosphere: AtmospherePalette) -> QPixmap:
        tr, tg, tb = atmosphere.avatar_tint
        tint_alpha = int(atmosphere.avatar_tint_alpha * 105)
        cache_key = (id(sprite), tr // 8, tg // 8, tb // 8, tint_alpha // 6)
        cached = self._tint_cache.get(cache_key)
        if cached is not None:
            return cached
        tinted = QPixmap(sprite.size())
        tinted.fill(Qt.transparent)
        tp = QPainter(tinted)
        tp.setRenderHint(QPainter.SmoothPixmapTransform, True)
        tp.drawPixmap(0, 0, sprite)
        tp.setCompositionMode(QPainter.CompositionMode_SourceAtop)
        tp.fillRect(tinted.rect(), QColor(tr, tg, tb, tint_alpha))
        tp.end()
        if len(self._tint_cache) >= 16:
            self._tint_cache.clear()
        self._tint_cache[cache_key] = tinted
        return tinted

    def update(self, dt: float, emotion: EmotionState, caressing: bool = False, asleep: bool = False) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.action_timer += dt
        self.pending_footstep = None

        dx = self.target_x - self.pos_x
        dy = self.target_y - self.pos_y
        dist = math.hypot(dx, dy)
        if dist > 0.008 and not caressing:
            self.action = "walk"
            # Desaceleração suave ao chegar no destino (ease-out)
            speed_mul = clamp(dist / 0.06, 0.35, 1.0)
            step_dist = min(dist, self.walk_speed * speed_mul * dt)
            self.pos_x += (dx / dist) * step_dist
            self.pos_y += (dy / dist) * step_dist
            if abs(dx) > 0.004:
                self.facing = 1 if dx > 0 else -1
            self.walk_phase += dt * (10.5 * speed_mul + 2.0)
            self._step_emit_accum += dt
            if self._step_emit_accum >= 0.30:
                self._step_emit_accum = 0.0
                self.pending_footstep = (self.pos_x, self.pos_y)
        else:
            if self.action == "walk":
                self.action = self._arrive_action
                self.action_timer = 0.0
            if asleep:
                self.action = "sleep"
            elif self.action in ("stretch", "wave") and self.action_timer > 4.2:
                self.action = "idle"
                self.action_timer = 0.0
            if abs(self.look_x) > 0.42 and self.action not in ("sleep", "sit_work"):
                self.facing = 1 if self.look_x > 0 else -1

        follow = clamp(dt * 6.5, 0.0, 1.0)
        self.look_x += (self.target_look_x - self.look_x) * follow
        self.look_y += (self.target_look_y - self.look_y) * follow

        self.bounce_vy += (-165.0 * self.bounce_y - 12.5 * self.bounce_vy) * dt
        self.bounce_y = clamp(self.bounce_y + self.bounce_vy * dt, -48.0, 16.0)
        self.tilt_v += (-85.0 * self.tilt_deg - 9.0 * self.tilt_v) * dt
        self.tilt_deg = clamp(self.tilt_deg + self.tilt_v * dt, -11.0, 11.0)

        target_glow = 1.0 if caressing else 0.0
        self.caress_glow += (target_glow - self.caress_glow) * clamp(dt * 5.0, 0.0, 1.0)

        if self._sprite_fade_t < 1.0:
            self._sprite_fade_t = min(1.0, self._sprite_fade_t + dt / 0.36)
            if self._sprite_fade_t >= 1.0:
                self._prev_sprite = None

        if self.emote_kind:
            self.emote_life += dt
            if self.emote_life >= self.emote_max:
                self.emote_kind = ""

        if asleep or self.action == "sleep":
            self.blink_amount = lerp(self.blink_amount, 1.0, clamp(dt * 4.0, 0.0, 1.0))
        elif caressing:
            self.blink_amount = lerp(self.blink_amount, 0.9, clamp(dt * 7.0, 0.0, 1.0))
        else:
            self._blink_timer -= dt
            if self._blink_timer <= 0.0:
                if self._blink_timer > -0.14:
                    self.blink_amount = math.sin((-self._blink_timer / 0.14) * math.pi)
                else:
                    self.blink_amount = 0.0
                    self._blink_timer = 2.4 + abs(math.sin(self.time * 1.9)) * 3.0
            else:
                self.blink_amount = max(0.0, self.blink_amount - dt * 8.0)

    def paint(
        self,
        painter: QPainter,
        canvas_w: int,
        canvas_h: int,
        x_ratio: float,
        scale: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        parallax_x: float = 0.0,
        parallax_y: float = 0.0,
        wind: float = 0.0,
        asleep: bool = False,
        raining: bool = False,
        stage: WorldStage | None = None,
        sun_x_norm: float = 0.5,
    ) -> None:
        if self.render_style == "portrait":
            self._paint_portrait_mode(
                painter, canvas_w, canvas_h, x_ratio, scale, emotion, atmosphere, parallax_x, parallax_y, asleep
            )
            return

        depth = WorldStage.depth_scale(self.pos_y)
        if stage is not None:
            foot_x, foot_y = stage.screen_pos(self.pos_x, self.pos_y, canvas_w, canvas_h, parallax_x, parallax_y)
        else:
            foot_x = self.pos_x * canvas_w - parallax_x * 14.0
            foot_y = self.pos_y * canvas_h - parallax_y * 5.0

        u = (canvas_h / 1080.0) * scale * depth
        is_walking = self.action == "walk"
        stride_hop = abs(math.sin(self.walk_phase)) * 8.5 * u if is_walking else 0.0
        music_bob = abs(math.sin(self.time * 5.2)) * 5.5 * u if self.action == "music_sway" else 0.0
        breath = math.sin(self.time * (1.35 if asleep else 2.25))
        lift = stride_hop + music_bob + max(0.0, -self.bounce_y)

        # 1. Sombra dupla aterrada EXATAMENTE sob a sola dos pés (oclusão de contato + sombra direcional)
        self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)

        draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
        sprite_key = self._resolve_world_sprite_key("sleepy" if asleep else emotion.mood, asleep)
        if sprite_key is not None:
            if sprite_key != self._current_sprite_key:
                if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                    self._prev_sprite = self._sprites[self._current_sprite_key]
                    self._sprite_fade_t = 0.0
                self._current_sprite_key = sprite_key
            self._paint_multiband_ai_sprite(
                painter, self._sprites[sprite_key], foot_x, foot_y, draw_y, u, breath, is_walking, emotion, atmosphere, wind, raining
            )
        else:
            self._paint_procedural_fallback(
                painter, foot_x, draw_y, u, breath, is_walking, emotion, atmosphere, wind, asleep, raining
            )

        if self.emote_kind:
            self._paint_ro_emote_balloon(painter, self.head_rect.center().x(), self.head_rect.top() - 8 * u, u)

    def _paint_grounded_shadow(self, painter: QPainter, foot_x: float, foot_y: float, u: float, lift: float, sun_x_norm: float) -> None:
        """Sombra de contato colada aos pés + sombra direcional projetada no chão (elimina sensação de flutuação!)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        sh_scale = clamp(1.0 - lift / (125.0 * max(u, 0.1)), 0.55, 1.0)
        dir_shift = (0.5 - sun_x_norm) * 52.0 * u

        # Sombra direcional longa e suave no chão
        cast_g = QRadialGradient(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 78 * u * sh_scale)
        cast_g.setColorAt(0.0, QColor(6, 10, 22, int(105 * sh_scale)))
        cast_g.setColorAt(0.65, QColor(6, 10, 22, int(45 * sh_scale)))
        cast_g.setColorAt(1.0, QColor(6, 10, 22, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(cast_g)
        painter.drawEllipse(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 74 * u * sh_scale, 18 * u * sh_scale)

        # Sombra de oclusão densa colada exatamente sob a sola dos sapatos
        ao_g = QRadialGradient(QPointF(foot_x, foot_y + 1 * u), 44 * u * sh_scale)
        ao_g.setColorAt(0.0, QColor(4, 6, 16, int(175 * sh_scale)))
        ao_g.setColorAt(0.65, QColor(4, 6, 16, int(90 * sh_scale)))
        ao_g.setColorAt(1.0, QColor(4, 6, 16, 0))
        painter.setBrush(ao_g)
        painter.drawEllipse(QPointF(foot_x, foot_y + 1 * u), 42 * u * sh_scale, 10.5 * u * sh_scale)
        painter.restore()

    def _draw_multiband_pixmap(
        self,
        painter: QPainter,
        tinted: QPixmap,
        target_w: float,
        target_h: float,
        u: float,
        breath: float,
        is_walking: bool,
        wind: float,
        opacity: float = 1.0,
    ) -> None:
        """Renderiza o sprite em 3 bandas anatômicas sobrepostas (pernas, tronco/quadril, cabeça/busto) com movimento Live2D."""
        sw, sh = tinted.width(), tinted.height()
        t = self.time
        breeze = math.sin(t * 2.1) * (1.2 + wind * 0.08) * u

        # Parâmetros de movimento por ação complexa
        if is_walking:
            hip_x = math.sin(self.walk_phase) * 3.8 * u
            torso_rot = math.sin(self.walk_phase) * 3.6 + 2.5
            head_rot = math.sin(self.walk_phase - 0.55) * 4.2
            leg_shear = math.sin(self.walk_phase) * 0.055
            stretch_y = 1.0
        elif self.action == "music_sway":
            hip_x = math.sin(t * 5.2) * 5.2 * u
            torso_rot = math.sin(t * 5.2) * 4.8
            head_rot = -math.sin(t * 5.2 - 0.4) * 5.5
            leg_shear = math.sin(t * 5.2) * 0.025
            stretch_y = 1.0
        elif self.action == "stretch":
            arch = math.sin(clamp(self.action_timer / 4.0, 0.0, 1.0) * math.pi)
            hip_x = 0.0
            torso_rot = -arch * 3.2
            head_rot = -arch * 4.5
            leg_shear = 0.0
            stretch_y = 1.0 + arch * 0.048
        elif self.action == "wave":
            wave_s = math.sin(t * 8.5)
            hip_x = math.sin(t * 3.0) * 2.5 * u
            torso_rot = wave_s * 3.4
            head_rot = wave_s * 4.8 + self.look_x * 3.0
            leg_shear = 0.0
            stretch_y = 1.0 + 0.015 * abs(wave_s)
        else:
            # Idle orgânico maduro: pés fixos no chão, quadril e busto respirando, cabeça olhando o cursor
            hip_x = math.sin(t * 1.15) * 1.6 * u
            torso_rot = math.sin(t * 1.15) * 1.3 + breeze * 0.15
            head_rot = self.look_x * 4.0 + math.sin(t * 1.5 - 0.6) * 1.6
            leg_shear = 0.0
            stretch_y = 1.0

        # 3 bandas sobrepostas (com overlap de 4% para zero fissura!)
        # Banda 0: Pernas / Sapatos (0.60 .. 1.00) — ancorada na sola dos pés (y=0)!
        # Banda 1: Quadril / Tronco (0.31 .. 0.64) — respira e balança suavemente!
        # Banda 2: Busto / Cabeça / Cabelo (0.00 .. 0.35) — inclina olhando o cursor!
        bands = [
            (0.60, 1.00, 0.0,           0.0,       leg_shear, 1.0),
            (0.31, 0.64, hip_x,         torso_rot, 0.0,       (1.0 + breath * 0.014) * stretch_y),
            (0.00, 0.35, hip_x * 1.35 + breeze * 0.35, torso_rot * 0.6 + head_rot, 0.0, (1.0 + breath * 0.010) * stretch_y),
        ]

        painter.setOpacity(opacity)
        for v0, v1, ox, rot_deg, shear_x, sy_mul in bands:
            painter.save()
            pivot_y = -target_h * (1.0 - v1)
            painter.translate(ox, pivot_y)
            if rot_deg != 0.0:
                painter.rotate(rot_deg)
            if shear_x != 0.0:
                painter.shear(shear_x, 0.0)
            painter.scale(1.0, sy_mul)
            band_h = target_h * (v1 - v0)
            dst = QRectF(-target_w * 0.5, -band_h, target_w, band_h)
            src = QRectF(0.0, sh * v0, sw, sh * (v1 - v0))
            painter.drawPixmap(dst, tinted, src)
            painter.restore()
        painter.setOpacity(1.0)

    def _paint_multiband_ai_sprite(
        self,
        painter: QPainter,
        sprite: QPixmap,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        breath: float,
        is_walking: bool,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        wind: float,
        raining: bool,
    ) -> None:
        # Proporção madura elegante (mais alta e esguia que chibi, bem integrada ao cenário 2.5D)
        target_h = 395.0 * u
        aspect = sprite.width() / max(sprite.height(), 1)
        target_w = target_h * aspect

        # Reflexo sutil no piso molhado quando está chovendo!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(-1.0 if self.facing < 0 else 1.0, -0.34)
            painter.setOpacity(0.18)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-target_w * 0.5, -target_h, target_w, target_h), sprite, QRectF(sprite.rect()))
            painter.restore()

        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.55), target_h * 0.55)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(95 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.55), target_h * 0.42, target_h * 0.55)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        sx = -1.0 if self.facing < 0 else 1.0
        sy = 0.94 if self.action in ("sit_work", "sit_relax") else 1.0
        painter.scale(sx, sy)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(sprite, atmosphere)
        if self._prev_sprite is not None and self._sprite_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._sprite_fade_t)
            tinted_prev = self._get_tinted_sprite(self._prev_sprite, atmosphere)
            self._draw_multiband_pixmap(painter, tinted_prev, target_w, target_h, u, breath, is_walking, wind, opacity=1.0 - ease)
            self._draw_multiband_pixmap(painter, tinted_curr, target_w, target_h, u, breath, is_walking, wind, opacity=ease)
        else:
            self._draw_multiband_pixmap(painter, tinted_curr, target_w, target_h, u, breath, is_walking, wind, opacity=1.0)
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 12 * u, draw_y - target_h * 1.05, u, atmosphere)

        self.body_rect = QRectF(foot_x - target_w * 0.40, draw_y - target_h * 0.96, target_w * 0.80, target_h * 0.96)
        self.head_rect = QRectF(foot_x - target_w * 0.34, draw_y - target_h * 0.98, target_w * 0.68, target_h * 0.28)

    def _paint_procedural_fallback(
        self,
        painter: QPainter,
        foot_x: float,
        draw_y: float,
        u: float,
        breath: float,
        is_walking: bool,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        wind: float,
        asleep: bool,
        raining: bool,
    ) -> None:
        """Avatar anime maduro procedural de corpo inteiro (usado apenas quando não há PNG gerado)."""
        outfit_cfg = self.persona.outfits.get(self.outfit) or self.persona.outfits["casual"]
        hair = QColor(*self.persona.hair_color)
        hair_hi = QColor(*self.persona.hair_highlight)
        eye_c = QColor(*self.persona.eye_color)
        skin = QColor(*self.persona.skin_color)
        c_prim = QColor(*outfit_cfg["primary"])
        c_trim = QColor(*outfit_cfg["trim"])
        rim_c = QColor(*atmosphere.rim_light)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg + (math.sin(self.walk_phase) * 4.0 if is_walking else 0.0))
        if self.facing < 0:
            painter.scale(-1.0, 1.0)
        painter.scale(1.0 - breath * 0.01, 1.0 + breath * 0.015)

        leg_sw = math.sin(self.walk_phase) * 14.0 * u if is_walking else 0.0

        # Cabelo longo fluido
        bh = QPainterPath()
        bh.moveTo(-34 * u, -295 * u)
        bh.cubicTo(-64 * u, -190 * u, -66 * u, -100 * u, -44 * u, -62 * u)
        bh.lineTo(44 * u, -62 * u)
        bh.cubicTo(66 * u, -100 * u, 64 * u, -190 * u, 34 * u, -295 * u)
        bh.closeSubpath()
        painter.setBrush(hair.darker(112))
        painter.setPen(QPen(rim_c, 1.6 * u))
        painter.drawPath(bh)

        # Pernas longas elegantes + saltos
        painter.setPen(QPen(QColor(46, 38, 58), 1.4 * u))
        for sign, sw in ((-1, leg_sw), (1, -leg_sw)):
            lx = sign * 12 * u + sw * 0.5
            painter.setBrush(skin)
            painter.drawRoundedRect(QRectF(lx - 6 * u, -135 * u, 12 * u, 125 * u), 5 * u, 5 * u)
            painter.setBrush(c_prim.darker(145))
            painter.drawRoundedRect(QRectF(lx - 7 * u, -16 * u, 16 * u, 16 * u), 4 * u, 4 * u)

        # Vestido ajustado elegante
        dress = QPainterPath()
        dress.moveTo(-26 * u, -125 * u)
        dress.cubicTo(-28 * u, -165 * u, -16 * u, -190 * u, -22 * u, -238 * u)
        dress.lineTo(22 * u, -238 * u)
        dress.cubicTo(16 * u, -190 * u, 28 * u, -165 * u, 26 * u, -125 * u)
        dress.closeSubpath()
        painter.setBrush(c_prim)
        painter.setPen(QPen(c_trim, 1.6 * u))
        painter.drawPath(dress)

        # Cabeça proporcional adulta
        painter.save()
        painter.translate(0, -280 * u + breath * 2.0 * u)
        painter.setBrush(skin)
        painter.setPen(QPen(QColor(82, 60, 68, 150), 1.4 * u))
        painter.drawEllipse(QPointF(0, 0), 32 * u, 34 * u)

        for sign in (-1, 1):
            ex = sign * 13 * u + 2 * u
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QPointF(ex, 2 * u), 7.5 * u, 8.5 * u * (1.0 - self.blink_amount))
            if self.blink_amount < 0.7:
                painter.setBrush(eye_c)
                painter.drawEllipse(QPointF(ex + 1 * u, 2 * u), 5.5 * u, 6.5 * u * (1.0 - self.blink_amount))

        bangs = QPainterPath()
        bangs.moveTo(-34 * u, -6 * u)
        bangs.cubicTo(-36 * u, -46 * u, 36 * u, -46 * u, 34 * u, -6 * u)
        bangs.lineTo(24 * u, 10 * u)
        bangs.lineTo(0, -10 * u)
        bangs.lineTo(-24 * u, 10 * u)
        bangs.closeSubpath()
        painter.setBrush(hair_hi)
        painter.setPen(QPen(rim_c, 1.2 * u))
        painter.drawPath(bangs)
        painter.restore()
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 8 * u, draw_y - 335 * u, u, atmosphere)

        self.head_rect = QRectF(foot_x - 42 * u, draw_y - 325 * u, 84 * u, 78 * u)
        self.body_rect = QRectF(foot_x - 48 * u, draw_y - 325 * u, 96 * u, 325 * u)

    def _paint_umbrella(self, painter: QPainter, cx: float, cy: float, u: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(cx, cy)
        painter.rotate(-8 * self.facing)
        painter.setPen(QPen(QColor(225, 232, 245, 215), 2.4 * u))
        painter.drawLine(QPointF(0, -6 * u), QPointF(0, 76 * u))
        dome = QPainterPath()
        dome.moveTo(-66 * u, 8 * u)
        dome.cubicTo(-54 * u, -44 * u, 54 * u, -44 * u, 66 * u, 8 * u)
        dome.quadTo(32 * u, -2 * u, 0, 6 * u)
        dome.quadTo(-32 * u, -2 * u, -66 * u, 8 * u)
        g = QLinearGradient(0, -36 * u, 0, 10 * u)
        g.setColorAt(0.0, QColor(175, 224, 255, 215))
        g.setColorAt(1.0, QColor(115, 178, 242, 165))
        painter.setBrush(g)
        painter.setPen(QPen(QColor(235, 248, 255, 220), 1.8 * u))
        painter.drawPath(dome)
        painter.restore()

    def _paint_ro_emote_balloon(self, painter: QPainter, cx: float, cy: float, u: float) -> None:
        t = clamp(self.emote_life / max(self.emote_max, 0.01))
        pop = smoothstep(0.0, 0.14, t) * (1.0 - smoothstep(0.82, 1.0, t))
        if pop <= 0.02:
            return
        sc = (0.75 + 0.30 * pop) * u
        bob = math.sin(self.time * 6.5) * 3.0 * u

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(pop)
        painter.translate(cx, cy - 26 * u + bob)

        bw, bh = 54 * sc, 42 * sc
        rect = QRectF(-bw * 0.5, -bh * 0.5, bw, bh)
        painter.setBrush(QColor(255, 255, 255, 242))
        painter.setPen(QPen(QColor(62, 74, 112, 230), 2.0 * sc))
        painter.drawRoundedRect(rect, 12 * sc, 12 * sc)
        tail = QPainterPath()
        tail.moveTo(-6 * sc, bh * 0.5 - 1)
        tail.lineTo(0, bh * 0.5 + 9 * sc)
        tail.lineTo(6 * sc, bh * 0.5 - 1)
        painter.drawPath(tail)

        k = self.emote_kind
        if k == "heart":
            s = 14 * sc
            hp = QPainterPath()
            hp.moveTo(0, s * 0.45)
            hp.cubicTo(-s * 0.75, -s * 0.15, -s * 0.6, -s * 0.75, 0, -s * 0.25)
            hp.cubicTo(s * 0.6, -s * 0.75, s * 0.75, -s * 0.15, 0, s * 0.45)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 86, 146))
            painter.drawPath(hp)
        elif k == "exclamation":
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 110, 68))
            painter.drawRoundedRect(QRectF(-3 * sc, -13 * sc, 6 * sc, 16 * sc), 3 * sc, 3 * sc)
            painter.drawEllipse(QPointF(0, 9 * sc), 3.4 * sc, 3.4 * sc)
        elif k == "music":
            painter.setPen(QPen(QColor(68, 152, 255), 2.4 * sc))
            painter.setBrush(QColor(68, 152, 255))
            painter.drawEllipse(QPointF(-5 * sc, 7 * sc), 4.5 * sc, 3.5 * sc)
            painter.drawLine(QPointF(-1 * sc, 6 * sc), QPointF(-1 * sc, -10 * sc))
            painter.drawLine(QPointF(-1 * sc, -10 * sc), QPointF(8 * sc, -7 * sc))
        elif k == "sparkle":
            s = 13 * sc
            sp = QPainterPath()
            sp.moveTo(0, -s)
            sp.quadTo(0, 0, s, 0)
            sp.quadTo(0, 0, 0, s)
            sp.quadTo(0, 0, -s, 0)
            sp.quadTo(0, 0, 0, -s)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 198, 46))
            painter.drawPath(sp)
        else:
            font = QFont("Segoe UI", max(9, int(12 * sc)))
            font.setBold(True)
            painter.setFont(font)
            txt = "Zzz" if k == "zzz" else ("?" if k == "question" else "...")
            painter.setPen(QColor(72, 92, 168))
            painter.drawText(rect, Qt.AlignCenter, txt)
        painter.restore()

    def _paint_portrait_mode(
        self,
        painter: QPainter,
        canvas_w: int,
        canvas_h: int,
        x_ratio: float,
        scale: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        parallax_x: float,
        parallax_y: float,
        asleep: bool,
    ) -> None:
        breath = math.sin(self.time * (1.45 if asleep else 2.25))
        sway = math.sin(self.time * 1.1) * (1.2 if not asleep else 0.4)
        anchor_x = canvas_w * x_ratio + parallax_x * 18.0
        anchor_y = canvas_h * 0.985 + self.bounce_y + parallax_y * 8.0
        key = self._resolve_portrait_sprite_key("sleepy" if asleep else emotion.mood)
        if key is None:
            self._paint_procedural_fallback(
                painter, anchor_x, anchor_y - 20, (canvas_h / 1080.0) * scale * 1.3, breath, False, emotion, atmosphere, 0.0, asleep, False
            )
            return
        if key != self._current_sprite_key:
            if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                self._prev_sprite = self._sprites[self._current_sprite_key]
                self._sprite_fade_t = 0.0
            self._current_sprite_key = key
        sprite = self._sprites[key]
        target_h = canvas_h * 0.76 * scale
        target_w = target_h * (sprite.width() / max(sprite.height(), 1))
        painter.save()
        painter.translate(anchor_x, anchor_y)
        painter.rotate(self.tilt_deg + sway * 0.45 + self.look_x * 1.8)
        painter.scale(1.0 - breath * 0.006, 1.0 + breath * 0.011)
        draw_rect = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(draw_rect, self._get_tinted_sprite(sprite, atmosphere), QRectF(sprite.rect()))
        painter.restore()
        self.body_rect = QRectF(anchor_x - target_w * 0.36, anchor_y - target_h * 0.94, target_w * 0.72, target_h * 0.92)
        self.head_rect = QRectF(anchor_x - target_w * 0.28, anchor_y - target_h * 0.96, target_w * 0.56, target_h * 0.30)
