"""AVATAR — Motor 2.5D de animação da waifu (suporte a sprites RGBA do ComfyUI + avatar anime procedural de alta fidelidade)."""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
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


class AvatarRig:
    """Controla animação 2.5D (respiração, piscar, rastreamento ocular, física de mola, roupas e rim-light)."""

    def __init__(self, persona: Persona, sprite_dirs: list[Path] | Path | None = None):
        self.persona = persona
        self.sprite_dirs = self._normalize_dirs(sprite_dirs)
        self.outfit: str = "casual"
        self.pose: str = "idle"

        # Estado cinemático suave
        self.time: float = 0.0
        self.look_x: float = 0.0      # -1..+1 direção do olhar
        self.look_y: float = 0.0
        self.target_look_x: float = 0.0
        self.target_look_y: float = 0.0

        # Física de mola (bounce ao receber carinho/cutucada)
        self.bounce_y: float = 0.0
        self.bounce_vy: float = 0.0
        self.tilt_deg: float = 0.0
        self.tilt_v: float = 0.0

        # Piscar natural
        self._blink_timer: float = 2.8
        self.blink_amount: float = 0.0  # 0 = aberto, 1 = fechado

        # Caress glow & hitboxes em coordenadas do canvas
        self.caress_glow: float = 0.0
        self.head_rect = QRectF()
        self.body_rect = QRectF()

        # Cache de sprites RGBA (ex: generated/comfyui ou assets/personas/<id>/) + crossfade suave
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
        """Carrega sprites PNG transparentes (prioridade para o último diretório na lista, ex: generated)."""
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

    def _resolve_sprite_key(self, mood: str) -> str | None:
        # Prioridade: traje+humor -> traje -> base+humor -> humor -> casual -> default -> qualquer um
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
        if self._sprites:
            return next(iter(self._sprites.keys()))
        return None

    def _get_tinted_sprite(self, sprite: QPixmap, atmosphere: AtmospherePalette) -> QPixmap:
        tr, tg, tb = atmosphere.avatar_tint
        tint_alpha = int(atmosphere.avatar_tint_alpha * 115)
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
        if len(self._tint_cache) >= 12:
            self._tint_cache.clear()
        self._tint_cache[cache_key] = tinted
        return tinted

    def impulse(self, vy: float = -180.0, tilt: float = 0.0) -> None:
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

    def update(self, dt: float, emotion: EmotionState, caressing: bool = False, asleep: bool = False) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt

        # Olhar suave em direção ao cursor
        follow = clamp(dt * 6.5, 0.0, 1.0)
        self.look_x += (self.target_look_x - self.look_x) * follow
        self.look_y += (self.target_look_y - self.look_y) * follow

        # Física de mola amortecida
        k_spring = 140.0
        damping = 12.0
        self.bounce_vy += (-k_spring * self.bounce_y - damping * self.bounce_vy) * dt
        self.bounce_y = clamp(self.bounce_y + self.bounce_vy * dt, -36.0, 24.0)

        self.tilt_v += (-80.0 * self.tilt_deg - 9.0 * self.tilt_v) * dt
        self.tilt_deg = clamp(self.tilt_deg + self.tilt_v * dt, -10.0, 10.0)

        # Brilho afetivo durante carinho
        target_glow = 1.0 if caressing else 0.0
        self.caress_glow += (target_glow - self.caress_glow) * clamp(dt * 5.0, 0.0, 1.0)

        # Crossfade suave entre expressões e trajes (0.55s)
        if self._sprite_fade_t < 1.0:
            self._sprite_fade_t = min(1.0, self._sprite_fade_t + dt / 0.55)
            if self._sprite_fade_t >= 1.0:
                self._prev_sprite = None

        # Ciclo natural de piscar
        if asleep:
            self.blink_amount = lerp(self.blink_amount, 1.0, clamp(dt * 4.0, 0.0, 1.0))
        elif caressing or emotion.mood == "affectionate":
            self.blink_amount = lerp(self.blink_amount, 0.85 if caressing else 0.0, clamp(dt * 6.0, 0.0, 1.0))
        else:
            self._blink_timer -= dt
            if self._blink_timer <= 0.0:
                if self._blink_timer > -0.14:
                    phase = -self._blink_timer / 0.14
                    self.blink_amount = math.sin(phase * math.pi)
                else:
                    self.blink_amount = 0.0
                    self._blink_timer = 2.6 + (abs(math.sin(self.time * 1.7)) * 3.2)
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
    ) -> None:
        """Desenha o avatar integrado ao cenário com respiração, rim-light e overlays emocionais."""
        breath = math.sin(self.time * (1.45 if asleep else 2.25))
        sway = math.sin(self.time * 1.1) * (1.2 if not asleep else 0.4)

        anchor_x = canvas_w * x_ratio + parallax_x * 18.0
        anchor_y = canvas_h * 0.985 + self.bounce_y + parallax_y * 8.0

        sprite_key = self._resolve_sprite_key("sleepy" if asleep else emotion.mood)
        if sprite_key is not None:
            if sprite_key != self._current_sprite_key:
                if self._current_sprite_key is not None and self._current_sprite_key in self._sprites:
                    self._prev_sprite = self._sprites[self._current_sprite_key]
                    self._sprite_fade_t = 0.0
                self._current_sprite_key = sprite_key
            sprite = self._sprites[sprite_key]
            self._paint_sprite_avatar(
                painter, sprite, anchor_x, anchor_y, canvas_h, scale, breath, sway, emotion, atmosphere, asleep
            )
        else:
            self._paint_procedural_avatar(
                painter, anchor_x, anchor_y, canvas_h, scale, breath, sway, emotion, atmosphere, wind, asleep
            )

    def _paint_sprite_avatar(
        self,
        painter: QPainter,
        sprite: QPixmap,
        anchor_x: float,
        anchor_y: float,
        canvas_h: int,
        scale: float,
        breath: float,
        sway: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        asleep: bool,
    ) -> None:
        target_h = canvas_h * 0.76 * scale
        aspect = sprite.width() / max(sprite.height(), 1)
        target_w = target_h * aspect

        # Aura de luz de borda (rim light) atrás da silhueta
        painter.save()
        aura_cx = anchor_x
        aura_cy = anchor_y - target_h * 0.54
        rim_r, rim_g, rim_b = atmosphere.rim_light
        aura = QRadialGradient(QPointF(aura_cx, aura_cy), target_h * 0.52)
        aura_alpha = int(68 + 55 * self.caress_glow)
        aura.setColorAt(0.0, QColor(rim_r, rim_g, rim_b, aura_alpha))
        aura.setColorAt(0.6, QColor(rim_r, rim_g, rim_b, aura_alpha // 3))
        aura.setColorAt(1.0, QColor(rim_r, rim_g, rim_b, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(aura)
        painter.drawEllipse(QPointF(aura_cx, aura_cy), target_h * 0.46, target_h * 0.52)

        # Transformação 2.5D (respiração + inclinação de cabeça + olhar)
        painter.translate(anchor_x, anchor_y)
        painter.rotate(self.tilt_deg + sway * 0.45 + self.look_x * 1.8)
        sx = 1.0 - breath * 0.006
        sy = 1.0 + breath * 0.011
        painter.scale(sx, sy)

        draw_rect = QRectF(-target_w * 0.5, -target_h, target_w, target_h)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Harmonização sutil + crossfade suave quando troca expressão/traje
        tinted_curr = self._get_tinted_sprite(sprite, atmosphere)
        if self._prev_sprite is not None and self._sprite_fade_t < 1.0:
            ease = smoothstep(0.0, 1.0, self._sprite_fade_t)
            tinted_prev = self._get_tinted_sprite(self._prev_sprite, atmosphere)
            prev_aspect = self._prev_sprite.width() / max(self._prev_sprite.height(), 1)
            prev_w = target_h * prev_aspect
            prev_rect = QRectF(-prev_w * 0.5, -target_h, prev_w, target_h)
            painter.setOpacity(1.0 - ease)
            painter.drawPixmap(prev_rect, tinted_prev, QRectF(tinted_prev.rect()))
            painter.setOpacity(ease)
            painter.drawPixmap(draw_rect, tinted_curr, QRectF(tinted_curr.rect()))
            painter.setOpacity(1.0)
        else:
            painter.drawPixmap(draw_rect, tinted_curr, QRectF(tinted_curr.rect()))
        painter.restore()

        # Atualiza hitboxes para carinho na cabeça e clique no corpo
        self.body_rect = QRectF(anchor_x - target_w * 0.36, anchor_y - target_h * 0.94, target_w * 0.72, target_h * 0.92)
        self.head_rect = QRectF(anchor_x - target_w * 0.28, anchor_y - target_h * 0.96, target_w * 0.56, target_h * 0.30)

        # Rubor suave se corada / recebendo carinho
        if emotion.blush > 0.25 or self.caress_glow > 0.2:
            painter.save()
            b_alpha = int(clamp(max(emotion.blush, self.caress_glow) * 90, 0, 110))
            hx = self.head_rect.center().x()
            hy = self.head_rect.center().y() + self.head_rect.height() * 0.14
            for sign in (-1.0, 1.0):
                rg = QRadialGradient(QPointF(hx + sign * self.head_rect.width() * 0.18, hy), self.head_rect.width() * 0.16)
                rg.setColorAt(0.0, QColor(255, 118, 155, b_alpha))
                rg.setColorAt(1.0, QColor(255, 118, 155, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(rg)
                painter.drawEllipse(QPointF(hx + sign * self.head_rect.width() * 0.18, hy), self.head_rect.width() * 0.16, self.head_rect.width() * 0.10)
            painter.restore()

    def _paint_procedural_avatar(
        self,
        painter: QPainter,
        anchor_x: float,
        anchor_y: float,
        canvas_h: int,
        scale: float,
        breath: float,
        sway: float,
        emotion: EmotionState,
        atmosphere: AtmospherePalette,
        wind: float,
        asleep: bool,
    ) -> None:
        """Avatar waifu anime procedural de alta estética (fallback instantâneo sem precisar de arquivos externos)."""
        u = (canvas_h / 1080.0) * scale  # unidade proporcional à resolução
        outfit_cfg = self.persona.outfits.get(self.outfit) or self.persona.outfits["casual"]
        hair = QColor(*self.persona.hair_color)
        hair_hi = QColor(*self.persona.hair_highlight)
        eye_c = QColor(*self.persona.eye_color)
        skin = QColor(*self.persona.skin_color)
        skin_sh = QColor(max(0, skin.red() - 28), max(0, skin.green() - 32), max(0, skin.blue() - 24))
        c_prim = QColor(*outfit_cfg["primary"])
        c_sec = QColor(*outfit_cfg["secondary"])
        c_trim = QColor(*outfit_cfg["trim"])
        rim_c = QColor(*atmosphere.rim_light)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Aura luminosa de integração ao cenário
        aura_cy = anchor_y - 310 * u
        aura = QRadialGradient(QPointF(anchor_x, aura_cy), 300 * u)
        aura.setColorAt(0.0, QColor(rim_c.red(), rim_c.green(), rim_c.blue(), int(78 + 60 * self.caress_glow)))
        aura.setColorAt(0.55, QColor(rim_c.red(), rim_c.green(), rim_c.blue(), 24))
        aura.setColorAt(1.0, QColor(rim_c.red(), rim_c.green(), rim_c.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(aura)
        painter.drawEllipse(QPointF(anchor_x, aura_cy), 280 * u, 310 * u)

        painter.translate(anchor_x, anchor_y)
        painter.rotate(self.tilt_deg + sway * 0.55)
        painter.scale(1.0 - breath * 0.006, 1.0 + breath * 0.012)

        wind_sway = math.sin(self.time * 2.1) * (5.0 + wind * 0.35) * u

        # 1. Cabelo traseiro longo e fluido
        back_hair = QPainterPath()
        back_hair.moveTo(-118 * u, -470 * u)
        back_hair.cubicTo(-190 * u + wind_sway, -310 * u, -205 * u + wind_sway * 1.4, -120 * u, -155 * u + wind_sway * 1.6, 10 * u)
        back_hair.lineTo(155 * u + wind_sway * 1.6, 10 * u)
        back_hair.cubicTo(205 * u + wind_sway * 1.4, -120 * u, 190 * u + wind_sway, -310 * u, 118 * u, -470 * u)
        back_hair.cubicTo(65 * u, -575 * u, -65 * u, -575 * u, -118 * u, -470 * u)
        bh_grad = QLinearGradient(0, -560 * u, 0, 10 * u)
        bh_grad.setColorAt(0.0, hair)
        bh_grad.setColorAt(0.55, hair.darker(118))
        bh_grad.setColorAt(1.0, hair.darker(145))
        painter.setBrush(bh_grad)
        painter.setPen(QPen(rim_c, 2.2 * u))
        painter.drawPath(back_hair)

        # 2. Tronco / Traje dinâmico
        torso = QPainterPath()
        torso.moveTo(-132 * u, 15 * u)
        torso.cubicTo(-125 * u, -125 * u, -102 * u, -245 * u, -66 * u, -280 * u)
        torso.lineTo(66 * u, -280 * u)
        torso.cubicTo(102 * u, -245 * u, 125 * u, -125 * u, 132 * u, 15 * u)
        torso.closeSubpath()
        t_grad = QLinearGradient(-120 * u, -280 * u, 120 * u, 10 * u)
        t_grad.setColorAt(0.0, c_prim.lighter(115))
        t_grad.setColorAt(0.65, c_prim)
        t_grad.setColorAt(1.0, c_prim.darker(128))
        painter.setBrush(t_grad)
        painter.setPen(QPen(QColor(25, 22, 42, 160), 2.0 * u))
        painter.drawPath(torso)

        # Detalhe central da roupa (gola, laço ou capuz conforme o traje)
        collar = QPainterPath()
        collar.moveTo(-54 * u, -278 * u)
        collar.lineTo(0, -188 * u)
        collar.lineTo(54 * u, -278 * u)
        collar.closeSubpath()
        painter.setBrush(c_sec)
        painter.setPen(QPen(c_trim, 2.2 * u))
        painter.drawPath(collar)

        # Laço / Broche luminoso no peito
        ribbon = QPainterPath()
        ribbon.moveTo(0, -210 * u)
        ribbon.lineTo(-26 * u, -192 * u)
        ribbon.lineTo(-18 * u, -168 * u)
        ribbon.lineTo(0, -186 * u)
        ribbon.lineTo(18 * u, -168 * u)
        ribbon.lineTo(26 * u, -192 * u)
        ribbon.closeSubpath()
        painter.setBrush(c_trim)
        painter.setPen(Qt.NoPen)
        painter.drawPath(ribbon)

        # 3. Pescoço + sombra
        painter.setBrush(skin)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(-22 * u, -335 * u, 44 * u, 68 * u), 14 * u, 14 * u)
        painter.setBrush(skin_sh)
        painter.drawEllipse(QPointF(0, -315 * u), 24 * u, 14 * u)

        # 4. Cabeça (inclina suavemente seguindo o cursor!)
        painter.save()
        head_cy = -420 * u + breath * 2.5 * u
        painter.translate(self.look_x * 9.0 * u, head_cy + self.look_y * 4.5 * u)
        painter.rotate(self.look_x * 3.8 + (2.5 if emotion.mood == "curious" else 0.0))

        # Rosto estilo anime (queixo delicado)
        face = QPainterPath()
        face.moveTo(-88 * u, -32 * u)
        face.cubicTo(-90 * u, 42 * u, -52 * u, 88 * u, 0, 98 * u)
        face.cubicTo(52 * u, 88 * u, 90 * u, 42 * u, 88 * u, -32 * u)
        face.cubicTo(86 * u, -110 * u, -86 * u, -110 * u, -88 * u, -32 * u)
        f_grad = QRadialGradient(QPointF(-10 * u, -18 * u), 125 * u)
        f_grad.setColorAt(0.0, skin.lighter(104))
        f_grad.setColorAt(0.85, skin)
        f_grad.setColorAt(1.0, skin_sh)
        painter.setBrush(f_grad)
        painter.setPen(QPen(QColor(95, 68, 72, 120), 1.8 * u))
        painter.drawPath(face)

        # Rubor nas bochechas
        blush_lvl = clamp(0.22 + emotion.blush * 0.78 + self.caress_glow * 0.45, 0.0, 1.0)
        for sign in (-1.0, 1.0):
            bg = QRadialGradient(QPointF(sign * 46 * u, 30 * u), 24 * u)
            bg.setColorAt(0.0, QColor(255, 118, 152, int(135 * blush_lvl)))
            bg.setColorAt(1.0, QColor(255, 118, 152, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawEllipse(QPointF(sign * 46 * u, 30 * u), 25 * u, 13 * u)

        # 5. Olhos expressivos com pupila rastreadora e piscar
        eye_open = 1.0 - self.blink_amount
        happy_closed = (self.caress_glow > 0.35 or emotion.mood == "affectionate") and self.blink_amount > 0.55
        for sign in (-1.0, 1.0):
            ex = sign * 39 * u
            ey = 4 * u
            if asleep or happy_closed or eye_open < 0.18:
                pen = QPen(QColor(46, 36, 58), 3.6 * u)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                arc = QPainterPath()
                if happy_closed:
                    arc.moveTo(ex - 20 * u, ey + 4 * u)
                    arc.quadTo(ex, ey - 14 * u, ex + 20 * u, ey + 4 * u)
                else:
                    arc.moveTo(ex - 20 * u, ey)
                    arc.quadTo(ex, ey + 11 * u, ex + 20 * u, ey)
                painter.drawPath(arc)
            else:
                eh = 23 * u * eye_open * (0.72 if emotion.mood == "sleepy" else 1.0)
                # Esclera
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(252, 253, 255))
                painter.drawEllipse(QPointF(ex, ey), 21 * u, eh)

                # Íris acompanhando o cursor
                px = ex + self.look_x * 6.5 * u
                py = ey + self.look_y * 4.0 * u
                iris_g = QLinearGradient(px, py - eh, px, py + eh)
                iris_g.setColorAt(0.0, eye_c.darker(145))
                iris_g.setColorAt(0.55, eye_c)
                iris_g.setColorAt(1.0, eye_c.lighter(145))
                painter.setBrush(iris_g)
                painter.drawEllipse(QPointF(px, py), 14.5 * u, min(17.5 * u, eh * 0.92))

                # Pupila
                painter.setBrush(QColor(22, 24, 48))
                painter.drawEllipse(QPointF(px, py + 1 * u), 6.2 * u, min(7.5 * u, eh * 0.48))

                # Catchlights (brilho anime vivo nos olhos)
                painter.setBrush(QColor(255, 255, 255, 240))
                painter.drawEllipse(QPointF(px - 5.2 * u, py - 5.5 * u), 4.6 * u, 4.2 * u)
                painter.setBrush(QColor(255, 255, 255, 190))
                painter.drawEllipse(QPointF(px + 5.5 * u, py + 5.0 * u), 2.3 * u, 2.3 * u)

                # Cílios superiores
                lash = QPainterPath()
                lash.moveTo(ex - 23 * u, ey - eh * 0.2)
                lash.quadTo(ex, ey - eh * 1.15, ex + 23 * u, ey - eh * 0.1)
                pen = QPen(QColor(34, 28, 48), 4.2 * u)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(lash)

        # Óculos estilosos no traje "focus" (Estúdio / Programação)
        if self.outfit == "focus":
            painter.setPen(QPen(c_trim, 2.4 * u))
            painter.setBrush(QColor(210, 240, 255, 26))
            painter.drawRoundedRect(QRectF(-66 * u, -20 * u, 52 * u, 42 * u), 12 * u, 12 * u)
            painter.drawRoundedRect(QRectF(14 * u, -20 * u, 52 * u, 42 * u), 12 * u, 12 * u)
            painter.drawLine(QPointF(-14 * u, 0), QPointF(14 * u, 0))

        # 6. Boca expressiva por emoção
        mouth_pen = QPen(QColor(155, 86, 98), 2.8 * u)
        mouth_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(mouth_pen)
        painter.setBrush(Qt.NoBrush)
        mpath = QPainterPath()
        if emotion.mood in ("happy", "affectionate"):
            mpath.moveTo(-14 * u, 54 * u)
            mpath.quadTo(0, 68 * u, 14 * u, 54 * u)
            painter.setBrush(QColor(238, 128, 146, 175))
        elif emotion.mood == "surprised":
            painter.setBrush(QColor(232, 124, 142, 180))
            painter.drawEllipse(QPointF(0, 58 * u), 7.5 * u, 9.5 * u)
        elif emotion.mood == "pouty":
            mpath.moveTo(-10 * u, 60 * u)
            mpath.quadTo(0, 53 * u, 10 * u, 60 * u)
        elif emotion.mood in ("sleepy", "cozy") or asleep:
            mpath.moveTo(-7 * u, 58 * u)
            mpath.quadTo(0, 62 * u, 7 * u, 58 * u)
        else:
            mpath.moveTo(-11 * u, 56 * u)
            mpath.quadTo(0, 63 * u, 11 * u, 56 * u)
        if not mpath.isEmpty():
            painter.drawPath(mpath)

        # 7. Franja e mechas frontais com brilho de destaque
        bangs = QPainterPath()
        bangs.moveTo(-98 * u, -30 * u)
        bangs.cubicTo(-102 * u, -125 * u, -40 * u, -148 * u, 0, -146 * u)
        bangs.cubicTo(40 * u, -148 * u, 102 * u, -125 * u, 98 * u, -30 * u)
        bangs.lineTo(82 * u, 36 * u)
        bangs.quadTo(68 * u, -24 * u, 56 * u, -48 * u)
        bangs.lineTo(36 * u, -14 * u)
        bangs.quadTo(22 * u, -45 * u, 8 * u, -52 * u)
        bangs.lineTo(-4 * u, -12 * u)
        bangs.quadTo(-20 * u, -48 * u, -38 * u, -52 * u)
        bangs.lineTo(-56 * u, -16 * u)
        bangs.quadTo(-72 * u, -30 * u, -82 * u, 36 * u)
        bangs.closeSubpath()

        fg_grad = QLinearGradient(0, -148 * u, 0, 20 * u)
        fg_grad.setColorAt(0.0, hair.lighter(115))
        fg_grad.setColorAt(0.45, hair_hi)
        fg_grad.setColorAt(0.68, hair)
        fg_grad.setColorAt(1.0, hair.darker(115))
        painter.setBrush(fg_grad)
        painter.setPen(QPen(QColor(rim_c.red(), rim_c.green(), rim_c.blue(), 170), 1.8 * u))
        painter.drawPath(bangs)

        # Ornamento luminoso no cabelo (estrela / pino)
        painter.setPen(Qt.NoPen)
        painter.setBrush(c_trim)
        painter.drawEllipse(QPointF(58 * u, -62 * u), 9 * u, 9 * u)
        painter.setBrush(QColor(255, 252, 235, 230))
        painter.drawEllipse(QPointF(58 * u, -62 * u), 4.5 * u, 4.5 * u)

        painter.restore()  # fim cabeça
        painter.restore()  # fim avatar

        # Atualiza hitboxes exatas em coordenadas do canvas
        self.head_rect = QRectF(anchor_x - 108 * u, anchor_y - 575 * u, 216 * u, 240 * u)
        self.body_rect = QRectF(anchor_x - 145 * u, anchor_y - 335 * u, 290 * u, 340 * u)
