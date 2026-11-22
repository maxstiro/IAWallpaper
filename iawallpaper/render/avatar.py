"""AVATAR — Sprite vivo 2.5D de corpo inteiro (estilo Ragnarok Online / Tree of Savior / Pokémon NDS) + modo retrato opcional.

Suporta:
- Locomoção autônoma 2D no plano caminhável do cenário (andar, virar esquerda/direita, sentar, dormir, pular)
- Balão de emote estilo Ragnarok Online / Pokémon acima da cabeça (♥, !, ♪, ?, Zzz, ✦, 💢)
- Guarda-chuva translúcido automático em dias de chuva/tempestade
- Sombra de contato no chão com escala de profundidade 2.5D
- Sprites PNG RGBA full-body gerados no ComfyUI (`sprite_idle.png`, `sprite_walk1.png`, `sprite_sit.png`,
  `sprite_sleep.png`, `sprite_happy.png`) + avatar chibi anime procedural de corpo inteiro animado!
"""

import math
from pathlib import Path

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
from ..core.persona import Persona
from ..mathutil import clamp, lerp, smoothstep
from .atmosphere import AtmospherePalette
from .world_stage import WorldStage


class AvatarRig:
    """Personagem waifu viva habitando o cenário 2.5D do wallpaper."""

    def __init__(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None, render_style: str = "world_sprite"):
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self.render_style: str = render_style  # "world_sprite" (RO/ToS/Pokemon) | "portrait"
        self.outfit: str = "casual"
        self.action: str = "idle"              # idle | walk | sit_work | sit_relax | sleep | music_sway

        # Posição e navegação no chão 2.5D (coordenadas normalizadas 0..1)
        self.pos_x: float = 0.56
        self.pos_y: float = 0.84
        self.target_x: float = 0.56
        self.target_y: float = 0.84
        self._arrive_action: str = "idle"
        self.facing: int = -1                  # -1 olhando esquerda, +1 olhando direita
        self.walk_speed: float = 0.145         # largura da tela por segundo
        self.walk_phase: float = 0.0
        self._step_emit_accum: float = 0.0
        self.pending_footstep: tuple[float, float] | None = None

        # Estado cinemático suave
        self.time: float = 0.0
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

        # Balão de emote estilo Ragnarok Online / Pokémon NDS acima da cabeça
        self.emote_kind: str = ""              # heart | exclamation | music | question | zzz | sparkle | pout
        self.emote_life: float = 0.0
        self.emote_max: float = 2.6

        # Carinho & hitboxes em coordenadas do canvas
        self.caress_glow: float = 0.0
        self.head_rect = QRectF()
        self.body_rect = QRectF()

        # Cache de sprites RGBA + crossfade suave
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
        self._sprites.clear()
        self._tint_cache.clear()
        for folder in self.sprite_dirs:
            if not folder.exists():
                continue
            for png in folder.glob("*.png"):
                pm = QPixmap(str(png))
                if not pm.isNull():
                    self._sprites[png.stem.lower()] = pm

    def available_sprite_keys(self) -> set[str]:
        return set(self._sprites.keys())

    def has_world_sprites(self) -> bool:
        return any(k.startswith("sprite_") for k in self._sprites)

    def walk_to(self, tx: float, ty: float, arrive_action: str = "idle") -> None:
        """Define novo destino caminhável no mundo 2.5D."""
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

    def show_emote(self, kind: str, duration: float = 2.6) -> None:
        """Dispara balão de emote estilo Ragnarok Online / Pokémon sobre a cabeça."""
        self.emote_kind = kind
        self.emote_life = 0.0
        self.emote_max = max(0.8, duration)

    def impulse(self, vy: float = -220.0, tilt: float = 0.0) -> None:
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
        """Seleciona sprite full-body para o modo mundo 2.5D (prefixo sprite_)."""
        candidates: list[str] = []
        if asleep or self.action == "sleep":
            candidates.extend([f"sprite_{self.outfit}_sleep", "sprite_sleep", "sprite_sit", "sprite_idle"])
        elif self.action == "walk":
            frame = "walk1" if int(self.walk_phase / math.pi) % 2 == 0 else "walk2"
            candidates.extend([f"sprite_{self.outfit}_{frame}", f"sprite_{frame}", f"sprite_{self.outfit}_walk", "sprite_walk", f"sprite_{self.outfit}", "sprite_idle"])
        elif self.action in ("sit_work", "sit_relax"):
            candidates.extend([f"sprite_{self.outfit}_sit", "sprite_sit", f"sprite_{self.outfit}", "sprite_idle"])
        elif mood in ("happy", "affectionate"):
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
        self.pending_footstep = None

        # Locomoção 2D suave no chão do mundo
        dx = self.target_x - self.pos_x
        dy = self.target_y - self.pos_y
        dist = math.hypot(dx, dy)
        if dist > 0.008 and not caressing:
            self.action = "walk"
            step_dist = min(dist, self.walk_speed * dt)
            self.pos_x += (dx / dist) * step_dist
            self.pos_y += (dy / dist) * step_dist
            if abs(dx) > 0.004:
                self.facing = 1 if dx > 0 else -1
            self.walk_phase += dt * 11.5
            self._step_emit_accum += dt
            if self._step_emit_accum >= 0.28:
                self._step_emit_accum = 0.0
                self.pending_footstep = (self.pos_x, self.pos_y)
        else:
            if self.action == "walk":
                self.action = self._arrive_action
            if asleep:
                self.action = "sleep"
            # Quando parada, vira gentilmente na direção do olhar do cursor
            if abs(self.look_x) > 0.42 and self.action not in ("sleep", "sit_work"):
                self.facing = 1 if self.look_x > 0 else -1

        follow = clamp(dt * 6.5, 0.0, 1.0)
        self.look_x += (self.target_look_x - self.look_x) * follow
        self.look_y += (self.target_look_y - self.look_y) * follow

        # Física de pulo / mola
        self.bounce_vy += (-165.0 * self.bounce_y - 12.5 * self.bounce_vy) * dt
        self.bounce_y = clamp(self.bounce_y + self.bounce_vy * dt, -52.0, 18.0)
        self.tilt_v += (-85.0 * self.tilt_deg - 9.0 * self.tilt_v) * dt
        self.tilt_deg = clamp(self.tilt_deg + self.tilt_v * dt, -12.0, 12.0)

        target_glow = 1.0 if caressing else 0.0
        self.caress_glow += (target_glow - self.caress_glow) * clamp(dt * 5.0, 0.0, 1.0)

        if self._sprite_fade_t < 1.0:
            self._sprite_fade_t = min(1.0, self._sprite_fade_t + dt / 0.38)
            if self._sprite_fade_t >= 1.0:
                self._prev_sprite = None

        if self.emote_kind:
            self.emote_life += dt
            if self.emote_life >= self.emote_max:
                self.emote_kind = ""

        # Piscar natural
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
    ) -> None:
        if self.render_style == "portrait":
            self._paint_portrait_mode(
                painter, canvas_w, canvas_h, x_ratio, scale, emotion, atmosphere, parallax_x, parallax_y, asleep
            )
            return

        # Modo padrão: Sprite vivo 2.5D de corpo inteiro habitando o mundo (RO / ToS / Pokémon NDS)
        depth = WorldStage.depth_scale(self.pos_y)
        if stage is not None:
            foot_x, foot_y = stage.screen_pos(self.pos_x, self.pos_y, canvas_w, canvas_h, parallax_x, parallax_y)
        else:
            foot_x = self.pos_x * canvas_w - parallax_x * 16.0
            foot_y = self.pos_y * canvas_h - parallax_y * 6.0

        u = (canvas_h / 1080.0) * scale * depth
        is_walking = self.action == "walk"
        stride_hop = abs(math.sin(self.walk_phase)) * 11.0 * u if is_walking else 0.0
        music_bob = abs(math.sin(self.time * 5.2)) * 6.0 * u if self.action == "music_sway" else 0.0
        breath = math.sin(self.time * (1.4 if asleep else 2.5))
        lift = stride_hop + music_bob + max(0.0, -self.bounce_y)

        # 1. Sombra oval de contato no chão (encolhe conforme ela pula/anda)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        sh_scale = clamp(1.0 - lift / (120.0 * max(u, 0.1)), 0.55, 1.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 26, int(115 * sh_scale)))
        painter.drawEllipse(QPointF(foot_x, foot_y + 2 * u), 56 * u * sh_scale, 16 * u * sh_scale)
        painter.restore()

        draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.4

        sprite_key = self._resolve_world_sprite_key("sleepy" if asleep else emotion.mood, asleep)
        if sprite_key is not None:
            if sprite_key != self._current_sprite_key:
                if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                    self._prev_sprite = self._sprites[self._current_sprite_key]
                    self._sprite_fade_t = 0.0
                self._current_sprite_key = sprite_key
            self._paint_fullbody_ai_sprite(
                painter, self._sprites[sprite_key], foot_x, draw_y, u, breath, is_walking, emotion, atmosphere, raining
            )
        else:
            self._paint_procedural_chibi_sprite(
                painter, foot_x, draw_y, u, breath, is_walking, emotion, atmosphere, wind, asleep, raining
            )

        # 3. Balão de Emote estilo Ragnarok Online / Pokémon NDS acima da cabeça
        if self.emote_kind:
            self._paint_ro_emote_balloon(painter, self.head_rect.center().x(), self.head_rect.top() - 10 * u, u)

    def _paint_fullbody_ai_sprite(
        self,
        painter: QPainter,
        sprite: QPixmap,
        foot_x: float,
        draw_y: float,
        u: float,
        breath: float,
        is_walking: bool,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        raining: bool,
    ) -> None:
        target_h = 330.0 * u
        aspect = sprite.width() / max(sprite.height(), 1)
        target_w = target_h * aspect

        painter.save()
        # Aura suave no carinho
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.55)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(95 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.45, target_h * 0.55)

        painter.translate(foot_x, draw_y)
        walk_tilt = math.sin(self.walk_phase) * 5.2 if is_walking else (math.sin(self.time * 5.2) * 3.5 if self.action == "music_sway" else 0.0)
        painter.rotate(self.tilt_deg + walk_tilt)

        # Espelha horizontalmente para acompanhar direção da caminhada (esquerda/direita)
        sx = (1.0 - breath * 0.010) * (-1.0 if self.facing < 0 else 1.0)
        sy = 1.0 + breath * 0.015
        if self.action in ("sit_work", "sit_relax"):
            sy *= 0.94
        painter.scale(sx, sy)

        draw_rect = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(sprite, atmosphere)
        if self._prev_sprite is not None and self._sprite_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._sprite_fade_t)
            tinted_prev = self._get_tinted_sprite(self._prev_sprite, atmosphere)
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(draw_rect, tinted_prev, QRectF(tinted_prev.rect()))
            painter.setOpacity(ease)
            painter.drawPixmap(draw_rect, tinted_curr, QRectF(tinted_curr.rect()))
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(draw_rect, tinted_curr, QRectF(tinted_curr.rect()))
        painter.restore()

        # Guarda-chuva translúcido automático em chuva/tempestade (posicionado acima da cabeça)
        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 10 * u, draw_y - target_h * 1.06, u, atmosphere)

        # Atualiza hitboxes exatas no mundo
        self.body_rect = QRectF(foot_x - target_w * 0.38, draw_y - target_h * 0.95, target_w * 0.76, target_h * 0.95)
        self.head_rect = QRectF(foot_x - target_w * 0.34, draw_y - target_h * 0.98, target_w * 0.68, target_h * 0.42)

    def _paint_procedural_chibi_sprite(
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
        """Sprite chibi anime de corpo inteiro (estilo Ragnarok Online / Tree of Savior) com pernas/braços animados."""
        outfit_cfg = self.persona.outfits.get(self.outfit) or self.persona.outfits["casual"]
        hair = QColor(*self.persona.hair_color)
        hair_hi = QColor(*self.persona.hair_highlight)
        eye_c = QColor(*self.persona.eye_color)
        skin = QColor(*self.persona.skin_color)
        c_prim = QColor(*outfit_cfg["primary"])
        c_sec = QColor(*outfit_cfg["secondary"])
        c_trim = QColor(*outfit_cfg["trim"])
        rim_c = QColor(*atmosphere.rim_light)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, draw_y)
        walk_tilt = math.sin(self.walk_phase) * 5.5 if is_walking else 0.0
        painter.rotate(self.tilt_deg + walk_tilt)
        if self.facing < 0:
            painter.scale(-1.0, 1.0)
        painter.scale(1.0 - breath * 0.012, 1.0 + breath * 0.018)

        leg_swing = math.sin(self.walk_phase) * 16.0 * u if is_walking else 0.0
        arm_swing = -leg_swing * 0.85
        sitting = self.action in ("sit_work", "sit_relax", "sleep")
        wind_sway = math.sin(self.time * 2.4) * (4.0 + wind * 0.25) * u

        # 1. Cabelo traseiro longo balançando ao caminhar
        bh = QPainterPath()
        bh.moveTo(-46 * u, -205 * u)
        bh.cubicTo(-76 * u - leg_swing * 0.3, -130 * u, -78 * u + wind_sway, -62 * u, -52 * u + wind_sway, -26 * u)
        bh.lineTo(52 * u + wind_sway, -26 * u)
        bh.cubicTo(78 * u + wind_sway, -62 * u, 76 * u + leg_swing * 0.3, -130 * u, 46 * u, -205 * u)
        bh.closeSubpath()
        painter.setBrush(hair.darker(112))
        painter.setPen(QPen(rim_c, 1.8 * u))
        painter.drawPath(bh)

        # 2. Pernas & sapatinhos animados
        painter.setPen(QPen(QColor(52, 42, 62), 1.6 * u))
        for sign, swing in ((-1, leg_swing), (1, -leg_swing)):
            lx = sign * 15 * u + (swing * 0.55 if not sitting else sign * 8 * u)
            ly = -38 * u if not sitting else -16 * u
            painter.setBrush(skin)
            painter.drawRoundedRect(QRectF(lx - 7 * u, ly, 14 * u, 30 * u if not sitting else 16 * u), 6 * u, 6 * u)
            # Sapatinho anime
            painter.setBrush(c_prim.darker(135))
            painter.drawRoundedRect(QRectF(lx - 9 * u, -12 * u, 20 * u, 12 * u), 5 * u, 5 * u)

        # 3. Vestido / Saia & Casaco (traje dinâmico)
        skirt = QPainterPath()
        skirt.moveTo(-36 * u, -34 * u)
        skirt.lineTo(-26 * u, -112 * u)
        skirt.lineTo(26 * u, -112 * u)
        skirt.lineTo(36 * u, -34 * u)
        skirt.closeSubpath()
        painter.setBrush(c_prim)
        painter.setPen(QPen(QColor(35, 30, 52), 1.8 * u))
        painter.drawPath(skirt)

        # Blusa / gola + laço
        painter.setBrush(c_sec)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon([QPointF(-18 * u, -112 * u), QPointF(0, -82 * u), QPointF(18 * u, -112 * u)])
        painter.setBrush(c_trim)
        painter.drawEllipse(QPointF(0, -84 * u), 7 * u, 5 * u)

        # Braços balançando
        painter.setPen(QPen(QColor(42, 34, 56), 1.5 * u))
        painter.setBrush(c_prim.lighter(110))
        for sign, sw in ((-1, arm_swing), (1, -arm_swing)):
            painter.save()
            painter.translate(sign * 27 * u, -104 * u)
            painter.rotate(sw * 1.4 + (-25 if self.action == "sit_work" else 0))
            painter.drawRoundedRect(QRectF(-6 * u, 0, 12 * u, 42 * u), 6 * u, 6 * u)
            painter.setBrush(skin)
            painter.drawEllipse(QPointF(0, 44 * u), 6.5 * u, 6.5 * u)
            painter.restore()

        # 4. Cabeça chibi expressiva (proporção clássica RO / ToS)
        painter.save()
        painter.translate(0, -162 * u + breath * 2.0 * u)
        painter.setBrush(skin)
        painter.setPen(QPen(QColor(82, 60, 68, 150), 1.6 * u))
        painter.drawEllipse(QPointF(0, 0), 48 * u, 46 * u)

        # Blush
        bl = clamp(0.25 + emotion.blush * 0.75 + self.caress_glow * 0.45)
        painter.setPen(Qt.NoPen)
        for sign in (-1, 1):
            painter.setBrush(QColor(255, 118, 152, int(135 * bl)))
            painter.drawEllipse(QPointF(sign * 25 * u, 14 * u), 10 * u, 5.5 * u)

        # Olhos chibi grandes & brilhantes
        e_open = 1.0 - self.blink_amount
        for sign in (-1, 1):
            ex = sign * 19 * u + 3 * u
            ey = 3 * u
            if asleep or self.action == "sleep" or e_open < 0.2:
                pen = QPen(QColor(40, 32, 54), 2.8 * u)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawArc(QRectF(ex - 9 * u, ey - 5 * u, 18 * u, 10 * u), 0, 180 * 16 if self.caress_glow > 0.3 else -180 * 16)
            else:
                eh = 13 * u * e_open
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255))
                painter.drawEllipse(QPointF(ex, ey), 10.5 * u, eh)
                painter.setBrush(eye_c)
                painter.drawEllipse(QPointF(ex + 1.5 * u, ey), 7.8 * u, eh * 0.9)
                painter.setBrush(QColor(22, 24, 48))
                painter.drawEllipse(QPointF(ex + 1.5 * u, ey + 1 * u), 3.6 * u, eh * 0.46)
                painter.setBrush(QColor(255, 255, 255, 240))
                painter.drawEllipse(QPointF(ex - 2.2 * u, ey - 3.5 * u), 2.8 * u, 2.6 * u)

        # Óculos no traje focus
        if self.outfit == "focus":
            painter.setPen(QPen(c_trim, 1.8 * u))
            painter.setBrush(QColor(210, 245, 255, 35))
            painter.drawEllipse(QPointF(-16 * u, 3 * u), 13 * u, 11 * u)
            painter.drawEllipse(QPointF(22 * u, 3 * u), 13 * u, 11 * u)

        # Boquinha
        painter.setPen(QPen(QColor(150, 82, 96), 2.2 * u))
        painter.drawArc(QRectF(-5 * u, 21 * u, 12 * u, 8 * u), 200 * 16, 140 * 16)

        # Franja & estrela no cabelo
        bangs = QPainterPath()
        bangs.moveTo(-50 * u, -8 * u)
        bangs.cubicTo(-52 * u, -62 * u, 52 * u, -62 * u, 50 * u, -8 * u)
        bangs.lineTo(36 * u, 16 * u)
        bangs.lineTo(22 * u, -16 * u)
        bangs.lineTo(6 * u, 6 * u)
        bangs.lineTo(-10 * u, -18 * u)
        bangs.lineTo(-28 * u, 12 * u)
        bangs.closeSubpath()
        fg = QLinearGradient(0, -56 * u, 0, 12 * u)
        fg.setColorAt(0.0, hair.lighter(110))
        fg.setColorAt(0.5, hair_hi)
        fg.setColorAt(1.0, hair)
        painter.setBrush(fg)
        painter.setPen(QPen(rim_c, 1.4 * u))
        painter.drawPath(bangs)

        painter.setPen(Qt.NoPen)
        painter.setBrush(c_trim)
        painter.drawEllipse(QPointF(30 * u, -24 * u), 6 * u, 6 * u)
        painter.restore()
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 8 * u, draw_y - 235 * u, u, atmosphere)

        self.head_rect = QRectF(foot_x - 58 * u, draw_y - 225 * u, 116 * u, 110 * u)
        self.body_rect = QRectF(foot_x - 62 * u, draw_y - 225 * u, 124 * u, 228 * u)

    def _paint_umbrella(self, painter: QPainter, cx: float, cy: float, u: float, atmo: AtmospherePalette) -> None:
        """Guarda-chuva anime translúcido automático em dias chuvosos."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(cx, cy)
        painter.rotate(-8 * self.facing)
        # Cabo
        painter.setPen(QPen(QColor(225, 232, 245, 210), 2.4 * u))
        painter.drawLine(QPointF(0, -8 * u), QPointF(0, 74 * u))
        # Cúpula translúcida azul-celeste
        dome = QPainterPath()
        dome.moveTo(-64 * u, 8 * u)
        dome.cubicTo(-52 * u, -44 * u, 52 * u, -44 * u, 64 * u, 8 * u)
        dome.quadTo(32 * u, -2 * u, 0, 6 * u)
        dome.quadTo(-32 * u, -2 * u, -64 * u, 8 * u)
        g = QLinearGradient(0, -34 * u, 0, 10 * u)
        g.setColorAt(0.0, QColor(175, 224, 255, 215))
        g.setColorAt(1.0, QColor(115, 178, 242, 165))
        painter.setBrush(g)
        painter.setPen(QPen(QColor(235, 248, 255, 220), 1.8 * u))
        painter.drawPath(dome)
        painter.restore()

    def _paint_ro_emote_balloon(self, painter: QPainter, cx: float, cy: float, u: float) -> None:
        """Balãozinho clássico de emote estilo Ragnarok Online / Pokémon NDS com animação pop-in."""
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
        # Pontinha do balão
        tail = QPainterPath()
        tail.moveTo(-6 * sc, bh * 0.5 - 1)
        tail.lineTo(0, bh * 0.5 + 9 * sc)
        tail.lineTo(6 * sc, bh * 0.5 - 1)
        painter.drawPath(tail)

        # Ícone vetorial interno
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
        """Modo retrato clássico opcional (busto grande à direita)."""
        breath = math.sin(self.time * (1.45 if asleep else 2.25))
        sway = math.sin(self.time * 1.1) * (1.2 if not asleep else 0.4)
        anchor_x = canvas_w * x_ratio + parallax_x * 18.0
        anchor_y = canvas_h * 0.985 + self.bounce_y + parallax_y * 8.0
        key = self._resolve_portrait_sprite_key("sleepy" if asleep else emotion.mood)
        if key is None:
            self._paint_procedural_chibi_sprite(
                painter, anchor_x, anchor_y - 20, (canvas_h / 1080.0) * scale * 1.4, breath, False, emotion, atmosphere, 0.0, asleep, False
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
