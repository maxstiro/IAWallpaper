"""AVATAR — Personagem waifu articulada com esqueleto 2D real de 18 ossos (FK + AutoRigger Spine2D), sombra aterrada e reflexo.

Camadas de realismo e integração ao cenário:
1. Esqueleto real de 18 ossos (`CharacterSkeleton`): joelhos dobram de verdade ao caminhar/sentar,
   braços erguem para acenar, alongar, digitar e segurar o guarda-chuva diretamente na mão direita (`forearm_r.end`),
   com física de mola no cabelo/saia e auto-aterramento matemático (`max(foot_y) == 0.0`).
2. `AutoRigger` (`build_rig_from_apose`): recorta automaticamente um sprite A-pose limpo (`rig_base.png`)
   em 10 peças RGBA com juntas circulares sobrepostas e proporções calibradas 1:1.
3. Sombra dupla aterrada sob a sola dos pés (oclusão de contato + sombra direcional) + reflexo articulado
   no piso molhado durante a chuva.
4. Fallbacks elegantes: multi-banda Live2D para sprites legados (`sprite_*.png`) e avatar vetorial
   também 100% guiado pelo esqueleto de 18 ossos caso nenhum PNG tenha sido gerado ainda.
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
from .rig_cutter import AutoRiggedCharacter, RigPart, build_rig_from_apose
from .skeleton import BoneWorld, CharacterSkeleton
from .sprite_clip import SpriteClip, load_clips_from_dirs
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
    rx0 = max(0, x0 - 2)
    ry0 = max(0, y0 - 2)
    rx1 = min(w - 1, x1 + 2)
    ry1 = min(h - 1, y1)
    return pm.copy(QRect(rx0, ry0, rx1 - rx0 + 1, ry1 - ry0 + 1))


# Ordem anatômica Z das 10 peças articuladas (fundo -> frente) para juntas limpas sem pop
_SKELETAL_Z_ORDER: tuple[tuple[str, str], ...] = (
    ("upper_arm_l", "upper_arm_l"),
    ("forearm_l",   "forearm_l"),
    ("thigh_l",     "thigh_l"),
    ("shin_l",      "shin_l"),
    ("thigh_r",     "thigh_r"),
    ("shin_r",      "shin_r"),
    ("torso",       "pelvis"),
    ("head",        "head"),
    ("upper_arm_r", "upper_arm_r"),
    ("forearm_r",   "forearm_r"),
)


class AvatarRig:
    """Personagem waifu madura e articulada habitando o cenário 2.5D do wallpaper."""

    def __init__(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None, render_style: str = "world_sprite"):
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self.render_style: str = render_style  # "world_sprite" | "portrait"
        self.outfit: str = "casual"
        self.action: str = "idle"              # idle | walk | sit_work | stretch | wave | admire_view | music_sway | sleep

        # Esqueleto real de 18 ossos + rig recortado + banco de clipes RGBA animados quadro-a-quadro (Wan 2.2)
        self.skeleton = CharacterSkeleton()
        self._rig: AutoRiggedCharacter | None = None
        self._clips: dict[str, SpriteClip] = {}
        self._clip_time: float = 0.0
        self._current_clip_key: str | None = None
        self._prev_clip_frame: QPixmap | None = None
        self._clip_fade_t: float = 1.0

        # Posição e navegação no chão 2.5D (ancorada no plano aberto estilo Tree of Savior / Ragnarok Online)
        self.pos_x: float = 0.52
        self.pos_y: float = 0.78
        self.target_x: float = 0.52
        self.target_y: float = 0.78
        self._arrive_action: str = "idle"
        self.facing: int = 1                   # -1 esquerda, +1 direita
        self.move_dir: str = "front"           # "side" | "back" | "front" (orientação 4-vias estilo RO/ToS!)
        self.walk_speed: float = 0.115
        self.walk_phase: float = 0.0
        self._step_emit_accum: float = 0.0
        self.pending_footstep: tuple[float, float] | None = None

        # Estado climático mais recente (alimenta esqueleto de chuva/vento)
        self._last_raining: bool = False
        self._last_wind: float = 6.0

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

        # Carinho & hitboxes dinâmicos guiados pelo esqueleto
        self.caress_glow: float = 0.0
        self.head_rect = QRectF()
        self.body_rect = QRectF()

        # Cache de sprites RGBA + peças tingidas
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
        """Carrega clipes animados RGBA (`clip_*.webp`), sprites PNG e constrói fallback esquelético."""
        self._sprites.clear()
        self._tint_cache.clear()
        self._rig = None
        self._clips = load_clips_from_dirs(self.sprite_dirs)
        self._current_clip_key = None
        self._prev_clip_frame = None
        self._clip_fade_t = 1.0

        for folder in self.sprite_dirs:
            if not folder.exists():
                continue
            for png in folder.glob("*.png"):
                pm = QPixmap(str(png))
                if not pm.isNull():
                    key = png.stem.lower()
                    if key.startswith(("sprite_", "rig_")):
                        self._sprites[key] = trim_sprite_pixmap(pm)
                    else:
                        self._sprites[key] = pm

        for rig_key in ("rig_base", "sprite_apose", "sprite_rig"):
            if rig_key in self._sprites:
                rig = build_rig_from_apose(self._sprites[rig_key])
                if rig is not None:
                    self._rig = rig
                    self.skeleton.set_proportions(rig.proportions)
                    break

        if self._rig is None:
            self.skeleton.set_proportions(None)

    def available_sprite_keys(self) -> set[str]:
        return set(self._sprites.keys())

    def available_clip_keys(self) -> set[str]:
        return set(self._clips.keys())

    def has_animated_clips(self) -> bool:
        return bool(self._clips)

    def has_world_sprites(self) -> bool:
        return bool(self._clips) or self._rig is not None or any(k.startswith("sprite_") for k in self._sprites)

    def has_skeletal_rig(self) -> bool:
        return self._rig is not None

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
        if len(self._tint_cache) >= 48:
            self._tint_cache.clear()
        self._tint_cache[cache_key] = tinted
        return tinted

    def update(
        self,
        dt: float,
        emotion: EmotionState,
        caressing: bool = False,
        asleep: bool = False,
        wind_speed: float | None = None,
        raining: bool | None = None,
    ) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt
        self.action_timer += dt
        self.pending_footstep = None

        if wind_speed is not None:
            self._last_wind = wind_speed
        if raining is not None:
            self._last_raining = raining

        prev_x = self.pos_x
        dx = self.target_x - self.pos_x
        dy = self.target_y - self.pos_y
        dist = math.hypot(dx, dy)
        clip_speed_mul = 1.0
        if dist > 0.008 and not caressing:
            self.action = "walk"
            # Desaceleração suave ao chegar no destino + escala de perspectiva (passos menores ao fundo!)
            depth_mul = WorldStage.depth_scale(self.pos_y)
            speed_mul = clamp(dist / 0.055, 0.38, 1.0)
            clip_speed_mul = clamp(0.75 + 0.35 * speed_mul, 0.72, 1.12)
            step_dist = min(dist, self.walk_speed * depth_mul * speed_mul * dt)
            self.pos_x += (dx / dist) * step_dist
            self.pos_y += (dy / dist) * step_dist

            # Orientação direcional real estilo Ragnarok Online / Tree of Savior (compensando proporção 16:9)
            # Horizontal dentro de ±36° -> perfil ("side"); mais vertical para cima -> costas ("back"); para baixo -> frente ("front")
            vx_vis = dx * 1.77
            vy_vis = dy
            if abs(vx_vis) >= abs(vy_vis) * 1.35:
                self.move_dir = "side"
                if abs(dx) > 0.002:
                    self.facing = 1 if dx > 0 else -1
            elif dy < 0.0:
                self.move_dir = "back"
                if abs(dx) > 0.004:
                    self.facing = 1 if dx > 0 else -1
            else:
                self.move_dir = "front"
                if abs(dx) > 0.004:
                    self.facing = 1 if dx > 0 else -1

            self.walk_phase += dt * (9.5 * speed_mul + 2.2)
            self._step_emit_accum += dt
            if self._step_emit_accum >= 0.34:
                self._step_emit_accum = 0.0
                self.pending_footstep = (self.pos_x, self.pos_y)
        else:
            if self.action == "walk":
                self.action = self._arrive_action
                self.action_timer = 0.0
            self.move_dir = "front"
            if asleep:
                self.action = "sleep"
            elif self.action in ("stretch", "wave", "dance") and self.action_timer > 4.2:
                self.action = "idle"
                self.action_timer = 0.0
            if not self._clips and abs(self.look_x) > 0.42 and self.action not in ("sleep", "sit_work"):
                self.facing = 1 if self.look_x > 0 else -1

        vel_x = (self.pos_x - prev_x) / max(dt, 1e-4)

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

        self._clip_time += dt * clip_speed_mul
        if self._clip_fade_t < 1.0:
            self._clip_fade_t = min(1.0, self._clip_fade_t + dt / 0.22)
            if self._clip_fade_t >= 1.0:
                self._prev_clip_frame = None

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

        # Atualiza o esqueleto real de 18 ossos (coordenadas locais no referencial do facing)
        self.skeleton.update(
            dt=dt,
            action=self.action,
            walk_phase=self.walk_phase,
            action_timer=self.action_timer,
            look_x=self.look_x * self.facing,
            look_y=self.look_y,
            vel_x=vel_x * self.facing,
            wind_speed=self._last_wind,
            asleep=asleep,
            raining=self._last_raining,
            caressing=caressing,
        )

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
        self._last_raining = raining
        self._last_wind = wind

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
        breath = math.sin(self.time * (1.35 if asleep else 2.25))

        # Prioridade 1: Clipes RGBA animados quadro-a-quadro (Wan 2.2 FirstLastFrameToVideo — estilo Tree of Savior / RO!)
        clip_key = self._resolve_clip_key("sleepy" if asleep else emotion.mood, asleep)
        if clip_key is not None:
            if clip_key != self._current_clip_key:
                if self._current_clip_key is not None and self._current_clip_key in self._clips:
                    self._prev_clip_frame = self._clips[self._current_clip_key].frame_at(self._clip_time)
                    self._clip_fade_t = 0.0
                self._current_clip_key = clip_key
                self._clip_time = 0.0
            lift = max(0.0, -self.bounce_y)
            self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
            self._paint_rpg_ground_aura(painter, foot_x, foot_y, u, atmosphere)
            draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
            self._paint_animated_clip(
                painter, self._clips[clip_key], foot_x, foot_y, draw_y, u, atmosphere, raining
            )
        elif self._rig is not None:
            lift = max(0.0, -self.bounce_y)
            self._paint_grounded_shadow(painter, foot_x, foot_y, u, lift, sun_x_norm)
            draw_y = foot_y - lift + max(0.0, self.bounce_y) * 0.35
            self._paint_skeletal_rig(
                painter, self._rig, self.skeleton.bones, foot_x, foot_y, draw_y, u, emotion, atmosphere, asleep, raining
            )
        else:
            stride_hop = abs(math.sin(self.walk_phase)) * 8.5 * u if is_walking else 0.0
            music_bob = abs(math.sin(self.time * 5.2)) * 5.5 * u if self.action == "music_sway" else 0.0
            lift = stride_hop + music_bob + max(0.0, -self.bounce_y)
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
                self._paint_skeletal_procedural(
                    painter, self.skeleton.bones, foot_x, draw_y, u, emotion, atmosphere, asleep, raining
                )

        if self.emote_kind:
            self._paint_ro_emote_balloon(painter, self.head_rect.center().x(), self.head_rect.top() - 8 * u, u)

    def _resolve_clip_key(self, mood: str, asleep: bool) -> str | None:
        if not self._clips:
            return None
        candidates: list[str] = []
        if asleep or self.action == "sleep":
            candidates.extend(["clip_sleep", "clip_sit", "clip_idle", "clip_wave"])
        elif self.action == "walk":
            if self.move_dir == "side":
                candidates.extend(["clip_walk_side", "clip_walk", "clip_idle", "clip_wave"])
            elif self.move_dir == "back":
                candidates.extend(["clip_walk_back", "clip_walk_side", "clip_walk", "clip_idle"])
            else:
                candidates.extend(["clip_walk", "clip_walk_side", "clip_idle", "clip_wave"])
        elif self.action in ("dance", "music_sway", "stretch"):
            candidates.extend(["clip_dance", "clip_wave", "clip_idle"])
        elif self.action == "wave":
            candidates.extend(["clip_wave", "clip_dance", "clip_idle"])
        elif self.action in ("sit_work", "sit_relax"):
            candidates.extend(["clip_sit", "clip_idle", "clip_wave"])
        else:
            candidates.extend(["clip_idle", "clip_wave", "clip_dance"])
        for k in candidates:
            if k in self._clips:
                return k
        return next(iter(self._clips.keys()))

    def _paint_rpg_ground_aura(self, painter: QPainter, foot_x: float, foot_y: float, u: float, atmo: AtmospherePalette) -> None:
        """Anel mágico sutil no piso estilo Ragnarok Online / Tree of Savior durante interações, dança ou aceno."""
        active = self.action in ("wave", "dance", "music_sway", "stretch") or self.caress_glow > 0.1 or bool(self.emote_kind)
        if not active:
            return
        strength = 0.85 if self.action in ("dance", "music_sway") else (0.75 if self.caress_glow > 0.1 else 0.55)
        pulse = 0.85 + 0.15 * math.sin(self.time * 4.2)
        rim = QColor(*atmo.rim_light)
        acc = QColor(*self.persona.accent_color)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, foot_y + 2 * u)

        # Anel externo suave com brilho no plano 2.5D
        rx, ry = 66 * u * pulse, 20 * u * pulse
        glow = QRadialGradient(QPointF(0, 0), rx)
        glow.setColorAt(0.0, QColor(acc.red(), acc.green(), acc.blue(), int(42 * strength)))
        glow.setColorAt(0.7, QColor(rim.red(), rim.green(), rim.blue(), int(78 * strength)))
        glow.setColorAt(1.0, QColor(rim.red(), rim.green(), rim.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(0, 0), rx, ry)

        # Círculo mágico estilizado girando lentamente sob os pés
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(225, 245, 255, int(135 * strength)), 1.6 * u))
        painter.drawEllipse(QPointF(0, 0), 54 * u, 16 * u)
        painter.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), int(115 * strength)), 1.2 * u))
        painter.drawEllipse(QPointF(0, 0), 42 * u, 12.5 * u)

        # 6 pontos orbitais luminosos sobre o anel
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 250, 225, int(190 * strength)))
        for i in range(6):
            ang = self.time * 1.4 + i * (math.tau / 6.0)
            px = math.cos(ang) * 54 * u
            py = math.sin(ang) * 16 * u
            painter.drawEllipse(QPointF(px, py), 2.6 * u, 2.6 * u)
        painter.restore()

    def _paint_animated_clip(
        self,
        painter: QPainter,
        clip: SpriteClip,
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        atmosphere: AtmospherePalette,
        raining: bool,
    ) -> None:
        """Renderiza o frame atual do clipe RGBA animado (Wan 2.2) ancorado nos pés, com crossfade e reflexo."""
        frame = clip.frame_at(self._clip_time)
        if frame.isNull():
            return

        # Proporção natural estilo Tree of Savior / Ragnarok Online no cenário aberto
        target_h = 345.0 * u
        aspect = frame.width() / max(frame.height(), 1)
        target_w = target_h * aspect
        # Espelha horizontalmente APENAS nos clipes direcionais (perfil/costas) — preserva assimetria do cabelo/presilha de frente!
        is_directional = clip.name in ("clip_walk_side", "clip_walk_back")
        sx = (-1.0 if self.facing < 0 else 1.0) if is_directional else 1.0
        # Cadência vertical sutil sincronizada ao passo durante caminhada (elimina sensação de deslizar)
        step_bob = abs(math.sin(self._clip_time * math.pi * 2.0)) * 3.5 * u if self.action == "walk" else 0.0
        draw_y = draw_y - step_bob

        # 1. Reflexo animado no piso molhado quando está chovendo!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(sx, -0.32)
            painter.setOpacity(0.18)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.drawPixmap(QRectF(-target_w * 0.5, -target_h, target_w, target_h), frame, QRectF(frame.rect()))
            painter.restore()

        # 2. Aura sutil de carinho
        painter.save()
        if self.caress_glow > 0.05:
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.52)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(foot_x, draw_y - target_h * 0.52), target_h * 0.40, target_h * 0.52)

        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        tinted_curr = self._get_tinted_sprite(frame, atmosphere)
        dst = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        if self._prev_clip_frame is not None and self._clip_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._clip_fade_t)
            prev_t = self._get_tinted_sprite(self._prev_clip_frame, atmosphere)
            prev_w = target_h * (prev_t.width() / max(prev_t.height(), 1))
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(QRectF(-prev_w * 0.5, -target_h, prev_w, target_h), prev_t, QRectF(prev_t.rect()))
            painter.setOpacity(ease)
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(dst, tinted_curr, QRectF(tinted_curr.rect()))
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            self._paint_umbrella(painter, foot_x + self.facing * 18 * u, draw_y - target_h * 1.02, u, atmosphere)

        self.body_rect = QRectF(foot_x - target_w * 0.36, draw_y - target_h * 0.96, target_w * 0.72, target_h * 0.96)
        self.head_rect = QRectF(foot_x - target_w * 0.28, draw_y - target_h * 0.98, target_w * 0.56, target_h * 0.28)

    def _draw_rig_parts(
        self,
        painter: QPainter,
        rig: AutoRiggedCharacter,
        bones: dict[str, BoneWorld],
        target_h: float,
        atmosphere: AtmospherePalette,
    ) -> None:
        """Desenha as 10 peças RGBA recortadas ligadas aos respectivos ossos FK."""
        px_scale = target_h / max(float(rig.src_height), 1.0)
        for part_name, bone_name in _SKELETAL_Z_ORDER:
            part = rig.parts.get(part_name)
            bone = bones.get(bone_name)
            if part is None or bone is None:
                continue
            tinted = self._get_tinted_sprite(part.pixmap, atmosphere)
            # Conversão de convenção de ângulo (skeleton -> Qt QPainter clockwise):
            # Ossos ascendentes (torso/cabeça): +delta; descendentes (pernas/braços): -delta!
            delta = bone.angle_deg - part.rest_angle
            rot_qt = delta if part.upward else -delta

            painter.save()
            painter.translate(bone.x * target_h, bone.y * target_h)
            painter.rotate(rot_qt)
            dst = QRectF(
                -part.pivot_x * px_scale,
                -part.pivot_y * px_scale,
                tinted.width() * px_scale,
                tinted.height() * px_scale,
            )
            painter.drawPixmap(dst, tinted, QRectF(tinted.rect()))
            painter.restore()

    def _paint_skeletal_rig(
        self,
        painter: QPainter,
        rig: AutoRiggedCharacter,
        bones: dict[str, BoneWorld],
        foot_x: float,
        foot_y: float,
        draw_y: float,
        u: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        asleep: bool,
        raining: bool,
    ) -> None:
        """Renderiza a personagem articulada pelo esqueleto de 18 ossos em escala humana 1:1 no terraço."""
        target_h = 445.0 * u
        sx = -1.0 if self.facing < 0 else 1.0

        # 1. Reflexo articulado no piso molhado durante a chuva!
        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(sx, -0.30)
            painter.setOpacity(0.16)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            self._draw_rig_parts(painter, rig, bones, target_h, atmosphere)
            painter.restore()

        # 2. Aura sutil de carinho
        painter.save()
        if self.caress_glow > 0.05:
            pelvis = bones["pelvis"]
            aura_cx = foot_x + sx * pelvis.x * target_h
            aura_cy = draw_y + (pelvis.y - 0.12) * target_h
            rim_r, rim_g, rim_b = atmosphere.rim_light
            aura = QRadialGradient(QPointF(aura_cx, aura_cy), target_h * 0.52)
            aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, int(92 * self.caress_glow)))
            aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(aura)
            painter.drawEllipse(QPointF(aura_cx, aura_cy), target_h * 0.40, target_h * 0.52)

        # 3. Corpo articulado real (10 peças ligadas aos ossos FK)
        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._draw_rig_parts(painter, rig, bones, target_h, atmosphere)

        # Rubor dinâmico acompanhando o osso da cabeça quando tímida ou recebendo carinho
        blush_a = clamp(max(emotion.blush, self.caress_glow * 0.9), 0.0, 1.0)
        if blush_a > 0.35 and "head" in bones:
            hb = bones["head"]
            cx_h = (hb.x + hb.end_x) * 0.5 * target_h
            cy_h = lerp(hb.y, hb.end_y, 0.46) * target_h
            painter.save()
            painter.translate(cx_h, cy_h)
            painter.rotate(hb.angle_deg)
            painter.setPen(Qt.NoPen)
            for sgn in (-1.0, 1.0):
                bg = QRadialGradient(QPointF(sgn * 13 * u, 0), 12 * u)
                bg.setColorAt(0.0, QColor(255, 115, 155, int(75 * blush_a)))
                bg.setColorAt(1.0, QColor(255, 115, 155, 0))
                painter.setBrush(bg)
                painter.drawEllipse(QPointF(sgn * 13 * u, 0), 12 * u, 7 * u)
            painter.restore()
        painter.restore()

        # 4. Guarda-chuva ancorado EXATAMENTE na mão direita (`forearm_r.end`) quando chove!
        if raining and self.action not in ("sleep", "sit_work") and "forearm_r" in bones:
            hr = bones["forearm_r"]
            hand_sx = foot_x + sx * hr.end_x * target_h
            hand_sy = draw_y + hr.end_y * target_h
            self._paint_umbrella(painter, hand_sx, hand_sy - 72 * u, u, atmosphere)

        # 5. Hitboxes dinâmicos seguindo os ossos da cabeça e pelve (carinho, cliques e emotes precisos!)
        hb = bones["head"]
        head_cx = foot_x + sx * ((hb.x + hb.end_x) * 0.5 * target_h)
        head_top = draw_y + min(hb.y, hb.end_y) * target_h - 14 * u
        head_h = max(68 * u, abs(hb.end_y - hb.y) * target_h + 26 * u)
        self.head_rect = QRectF(head_cx - 46 * u, head_top, 92 * u, head_h)

        pb = bones["pelvis"]
        body_cx = foot_x + sx * pb.x * target_h
        self.body_rect = QRectF(body_cx - 66 * u, head_top, 132 * u, max(120 * u, draw_y - head_top))

    def _paint_grounded_shadow(self, painter: QPainter, foot_x: float, foot_y: float, u: float, lift: float, sun_x_norm: float) -> None:
        """Sombra de contato colada aos pés + sombra direcional projetada no chão (elimina sensação de flutuação!)."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        sh_scale = clamp(1.0 - lift / (125.0 * max(u, 0.1)), 0.55, 1.0)
        dir_shift = (0.5 - sun_x_norm) * 58.0 * u

        # Sombra direcional longa e suave no chão do terraço
        cast_g = QRadialGradient(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 84 * u * sh_scale)
        cast_g.setColorAt(0.0, QColor(6, 10, 22, int(112 * sh_scale)))
        cast_g.setColorAt(0.65, QColor(6, 10, 22, int(48 * sh_scale)))
        cast_g.setColorAt(1.0, QColor(6, 10, 22, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(cast_g)
        painter.drawEllipse(QPointF(foot_x + dir_shift * 0.55, foot_y + 4 * u), 82 * u * sh_scale, 19 * u * sh_scale)

        # Sombra de oclusão densa colada exatamente sob a sola dos sapatos
        ao_g = QRadialGradient(QPointF(foot_x, foot_y + 1 * u), 48 * u * sh_scale)
        ao_g.setColorAt(0.0, QColor(4, 6, 16, int(185 * sh_scale)))
        ao_g.setColorAt(0.65, QColor(4, 6, 16, int(95 * sh_scale)))
        ao_g.setColorAt(1.0, QColor(4, 6, 16, 0))
        painter.setBrush(ao_g)
        painter.drawEllipse(QPointF(foot_x, foot_y + 1 * u), 46 * u * sh_scale, 11 * u * sh_scale)
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
        """Fallback multi-banda Live2D para sprites legados (quando ainda não existe rig_base.png)."""
        sw, sh = tinted.width(), tinted.height()
        t = self.time
        breeze = math.sin(t * 2.1) * (1.2 + wind * 0.08) * u

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
            hip_x = math.sin(t * 1.15) * 1.6 * u
            torso_rot = math.sin(t * 1.15) * 1.3 + breeze * 0.15
            head_rot = self.look_x * 4.0 + math.sin(t * 1.5 - 0.6) * 1.6
            leg_shear = 0.0
            stretch_y = 1.0

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
        target_h = 435.0 * u
        aspect = sprite.width() / max(sprite.height(), 1)
        target_w = target_h * aspect

        if raining:
            painter.save()
            painter.translate(foot_x, foot_y + 2 * u)
            painter.scale(-1.0 if self.facing < 0 else 1.0, -0.32)
            painter.setOpacity(0.16)
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

    def _draw_capsule_bone(self, painter: QPainter, bone: BoneWorld, H: float, thickness: float, fill: QColor, outline: QColor) -> None:
        p0 = QPointF(bone.x * H, bone.y * H)
        p1 = QPointF(bone.end_x * H, bone.end_y * H)
        pen = QPen(outline, thickness + 2.4, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(p0, p1)
        pen_in = QPen(fill, thickness, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_in)
        painter.drawLine(p0, p1)

    def _paint_skeletal_procedural(
        self,
        painter: QPainter,
        bones: dict[str, BoneWorld],
        foot_x: float,
        draw_y: float,
        u: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        asleep: bool,
        raining: bool,
    ) -> None:
        """Avatar anime maduro vetorial 100% guiado pelo esqueleto de 18 ossos (funciona mesmo sem PNG!)."""
        H = 390.0 * u
        sx = -1.0 if self.facing < 0 else 1.0
        outfit_cfg = self.persona.outfits.get(self.outfit) or self.persona.outfits["casual"]
        hair = QColor(*self.persona.hair_color)
        hair_hi = QColor(*self.persona.hair_highlight)
        eye_c = QColor(*self.persona.eye_color)
        skin = QColor(*self.persona.skin_color)
        c_prim = QColor(*outfit_cfg["primary"])
        c_trim = QColor(*outfit_cfg["trim"])
        rim_c = QColor(*atmosphere.rim_light)
        ink = QColor(42, 34, 54, 210)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(foot_x, draw_y)
        painter.rotate(self.tilt_deg)
        painter.scale(sx, 1.0)

        # Cabelo traseiro com física de mola (`hair_back`)
        hb_back = bones["hair_back"]
        bh = QPainterPath()
        bh.moveTo((hb_back.x - 0.08) * H, hb_back.y * H)
        bh.quadTo((hb_back.end_x - 0.14) * H, lerp(hb_back.y, hb_back.end_y, 0.6) * H, (hb_back.end_x - 0.09) * H, hb_back.end_y * H)
        bh.lineTo((hb_back.end_x + 0.09) * H, hb_back.end_y * H)
        bh.quadTo((hb_back.end_x + 0.14) * H, lerp(hb_back.y, hb_back.end_y, 0.6) * H, (hb_back.x + 0.08) * H, hb_back.y * H)
        bh.closeSubpath()
        painter.setBrush(hair.darker(112))
        painter.setPen(QPen(rim_c, 1.4 * u))
        painter.drawPath(bh)

        # Braço esquerdo (atrás do tronco)
        self._draw_capsule_bone(painter, bones["upper_arm_l"], H, 12 * u, skin.darker(104), ink)
        self._draw_capsule_bone(painter, bones["forearm_l"], H, 10.5 * u, skin.darker(104), ink)

        # Pernas articuladas (coxas + canelas + sapatos)
        for thigh_k, shin_k, shade in (("thigh_l", "shin_l", 106), ("thigh_r", "shin_r", 100)):
            tb = bones[thigh_k]
            sb = bones[shin_k]
            self._draw_capsule_bone(painter, tb, H, 19 * u, skin.darker(shade), ink)
            self._draw_capsule_bone(painter, sb, H, 14 * u, c_prim.darker(140 if shade > 100 else 128), ink)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c_prim.darker(160))
            painter.drawEllipse(QPointF(sb.end_x * H + 4 * u, sb.end_y * H - 4 * u), 10 * u, 6 * u)

        # Tronco + vestido + saia com física de mola
        pel = bones["pelvis"]
        ch = bones["chest"]
        sk = bones["skirt"]
        dress = QPainterPath()
        dress.moveTo((ch.end_x - 0.075) * H, ch.end_y * H)
        dress.lineTo((ch.end_x + 0.075) * H, ch.end_y * H)
        dress.quadTo((pel.x + 0.06) * H, pel.y * H, (sk.end_x + 0.11) * H, sk.end_y * H)
        dress.lineTo((sk.end_x - 0.11) * H, sk.end_y * H)
        dress.quadTo((pel.x - 0.06) * H, pel.y * H, (ch.end_x - 0.075) * H, ch.end_y * H)
        dress.closeSubpath()
        painter.setBrush(c_prim)
        painter.setPen(QPen(c_trim, 1.5 * u))
        painter.drawPath(dress)

        # Cabeça articulada no osso `head`
        hd = bones["head"]
        painter.save()
        painter.translate((hd.x + hd.end_x) * 0.5 * H, (hd.y + hd.end_y) * 0.5 * H)
        painter.rotate(hd.angle_deg)
        painter.setBrush(skin)
        painter.setPen(QPen(QColor(82, 60, 68, 150), 1.4 * u))
        painter.drawEllipse(QPointF(0, 0), 30 * u, 32 * u)
        for sign in (-1, 1):
            ex = sign * 11.5 * u + 2 * u
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(QPointF(ex, 2 * u), 7.0 * u, 8.0 * u * (1.0 - self.blink_amount))
            if self.blink_amount < 0.7:
                painter.setBrush(eye_c)
                painter.drawEllipse(QPointF(ex + 1 * u, 2 * u), 5.0 * u, 6.0 * u * (1.0 - self.blink_amount))
        bangs = QPainterPath()
        bangs.moveTo(-32 * u, -6 * u)
        bangs.cubicTo(-34 * u, -44 * u, 34 * u, -44 * u, 32 * u, -6 * u)
        bangs.lineTo(22 * u, 9 * u)
        bangs.lineTo(0, -10 * u)
        bangs.lineTo(-22 * u, 9 * u)
        bangs.closeSubpath()
        painter.setBrush(hair_hi)
        painter.setPen(QPen(rim_c, 1.2 * u))
        painter.drawPath(bangs)
        painter.restore()

        # Braço direito (na frente do tronco: aceno, guarda-chuva, digitação!)
        self._draw_capsule_bone(painter, bones["upper_arm_r"], H, 12.5 * u, skin, ink)
        self._draw_capsule_bone(painter, bones["forearm_r"], H, 11 * u, skin, ink)
        painter.restore()

        if raining and self.action not in ("sleep", "sit_work"):
            hr = bones["forearm_r"]
            self._paint_umbrella(painter, foot_x + sx * hr.end_x * H, draw_y + hr.end_y * H - 68 * u, u, atmosphere)

        hd = bones["head"]
        head_cx = foot_x + sx * ((hd.x + hd.end_x) * 0.5 * H)
        head_top = draw_y + min(hd.y, hd.end_y) * H - 14 * u
        self.head_rect = QRectF(head_cx - 42 * u, head_top, 84 * u, 78 * u)
        self.body_rect = QRectF(foot_x - 54 * u, head_top, 108 * u, max(120 * u, draw_y - head_top))

    def _paint_umbrella(self, painter: QPainter, cx: float, cy: float, u: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(cx, cy)
        painter.rotate(-8 * self.facing)
        painter.setPen(QPen(QColor(225, 232, 245, 220), 2.5 * u))
        painter.drawLine(QPointF(0, -6 * u), QPointF(0, 82 * u))
        dome = QPainterPath()
        dome.moveTo(-72 * u, 8 * u)
        dome.cubicTo(-58 * u, -48 * u, 58 * u, -48 * u, 72 * u, 8 * u)
        dome.quadTo(35 * u, -2 * u, 0, 6 * u)
        dome.quadTo(-35 * u, -2 * u, -72 * u, 8 * u)
        g = QLinearGradient(0, -40 * u, 0, 10 * u)
        g.setColorAt(0.0, QColor(175, 224, 255, 220))
        g.setColorAt(1.0, QColor(115, 178, 242, 170))
        painter.setBrush(g)
        painter.setPen(QPen(QColor(235, 248, 255, 225), 1.8 * u))
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
            self._paint_skeletal_procedural(
                painter, self.skeleton.bones, anchor_x, anchor_y - 20, (canvas_h / 1080.0) * scale * 1.3, emotion, atmosphere, asleep, False
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
