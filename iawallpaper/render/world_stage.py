"""WORLD STAGE — Palco 2.5D caminhável com dinâmica ambiental própria (raios solares, água viva, pássaros, borboletas, brisa e reflexos).

Resolve tanto a ancoragem espacial (plano de chão real sem flutuação) quanto a vida própria
de cada cenário (feixes de sol, caustics/reflexos na água, névoa deslizante, luzes pulsantes
de lanterna, pássaros/borboletas diurnos, ondas de chuva e faíscas interativas no piso).
"""

from dataclasses import dataclass
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from ..mathutil import clamp, lerp
from .atmosphere import AtmospherePalette


@dataclass(frozen=True)
class WorldHotspot:
    id: str
    x: float           # coordenada normalizada 0..1
    y: float           # coordenada normalizada no piso caminhável (0.81..0.95)
    arrive_action: str # idle | sit_work | sit_relax | sleep | music_sway | admire_view | stretch
    label_pt: str


# Hotspots distribuídos pela praça de pedra aberta estilo Tree of Savior / Ragnarok Online (livres do HUD inferior esquerdo!)
DEFAULT_HOTSPOTS: dict[str, WorldHotspot] = {
    "desk":       WorldHotspot("desk",       0.46, 0.88, "sit_work",    "Praça de Estudo"),
    "music_spot": WorldHotspot("music_spot", 0.48, 0.84, "dance",       "Praça da Música"),
    "overlook":   WorldHotspot("overlook",   0.54, 0.71, "idle",        "Árvore Sagrada"),
    "lantern":    WorldHotspot("lantern",    0.66, 0.78, "wave",        "Lanternas do Mirante"),
    "cushion":    WorldHotspot("cushion",    0.74, 0.88, "sleep",       "Recanto das Flores"),
    "garden_l":   WorldHotspot("garden_l",   0.44, 0.90, "walk",        "Pedras da Praça"),
    "garden_r":   WorldHotspot("garden_r",   0.78, 0.88, "idle",        "Terraço Leste"),
}

WALK_MIN_X, WALK_MAX_X = 0.24, 0.84
WALK_MIN_Y, WALK_MAX_Y = 0.69, 0.94


@dataclass
class GroundStepFx:
    x: float
    y: float
    life: float
    max_life: float
    kind: str  # dust | splash | cursor_spark


@dataclass
class RainPuddleRipple:
    x: float
    y: float
    life: float
    max_life: float


@dataclass
class AmbientCritter:
    x: float
    y: float
    vx: float
    vy: float
    phase: float
    scale: float
    kind: str  # bird | butterfly


class WorldStage:
    """Gerencia o plano de chão 2.5D, props ordenados por Y e dinâmica ambiental viva do local."""

    def __init__(self, seed: int = 2026):
        self.rng = random.Random(seed + 88)
        self.hotspots = dict(DEFAULT_HOTSPOTS)
        self.time: float = 0.0
        self.step_fx: list[GroundStepFx] = []
        self.ripples: list[RainPuddleRipple] = []
        self._next_ripple: float = 0.2

        # Fauna ambiental viva (pássaros distantes no céu / borboletas sobre o terraço)
        self.critters: list[AmbientCritter] = [
            AmbientCritter(
                x=self.rng.uniform(0.05, 0.95),
                y=self.rng.uniform(0.14, 0.34) if i < 4 else self.rng.uniform(0.62, 0.84),
                vx=self.rng.uniform(0.018, 0.036) * (1 if i % 2 == 0 else -1),
                vy=self.rng.uniform(-0.004, 0.004),
                phase=self.rng.uniform(0.0, math.tau),
                scale=self.rng.uniform(0.75, 1.25),
                kind="bird" if i < 4 else "butterfly",
            )
            for i in range(8)
        ]

        # Tufos de grama e florzinhas decorativas para modo procedural
        self._flora = [
            (self.rng.uniform(0.06, 0.94), self.rng.uniform(0.70, 0.95), self.rng.uniform(0.7, 1.3), self.rng.uniform(0, math.tau))
            for _ in range(38)
        ]

    @staticmethod
    def clamp_walkable(x: float, y: float) -> tuple[float, float]:
        return clamp(x, WALK_MIN_X, WALK_MAX_X), clamp(y, WALK_MIN_Y, WALK_MAX_Y)

    @staticmethod
    def depth_scale(y_norm: float) -> float:
        """Perspectiva 2.5D estilo Tree of Savior / Ragnarok Online: menor ao fundo da praça (0.64), maior à frente (0.91)."""
        t = clamp((y_norm - WALK_MIN_Y) / max(WALK_MAX_Y - WALK_MIN_Y, 0.01), 0.0, 1.0)
        return lerp(0.78, 1.08, t)

    def screen_pos(self, x_norm: float, y_norm: float, w: int, h: int, parallax_x: float = 0.0, parallax_y: float = 0.0) -> tuple[float, float]:
        depth = self.depth_scale(y_norm)
        sx = x_norm * w - parallax_x * (14.0 * depth)
        sy = y_norm * h - parallax_y * (5.0 * depth)
        return sx, sy

    def spawn_footstep(self, x_norm: float, y_norm: float, raining: bool = False) -> None:
        self.step_fx.append(
            GroundStepFx(
                x=x_norm,
                y=y_norm,
                life=0.0,
                max_life=0.52 if raining else 0.44,
                kind="splash" if raining else "dust",
            )
        )
        if len(self.step_fx) > 32:
            self.step_fx = self.step_fx[-32:]

    def spawn_cursor_ripple(self, x_norm: float, y_norm: float) -> None:
        """Faísca/onda sutil no piso ao clicar ou passar o mouse sobre o terraço."""
        self.step_fx.append(GroundStepFx(x=x_norm, y=y_norm, life=0.0, max_life=0.55, kind="cursor_spark"))
        if len(self.step_fx) > 32:
            self.step_fx = self.step_fx[-32:]

    def update(self, dt: float, condition: str = "clear", wind_speed: float = 6.0) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt

        self.step_fx = [f for f in self.step_fx if (setattr(f, "life", f.life + dt) or True) and f.life < f.max_life]
        self.ripples = [r for r in self.ripples if (setattr(r, "life", r.life + dt) or True) and r.life < r.max_life]

        # Atualiza pássaros e borboletas vivos
        wind_push = (wind_speed - 6.0) * 0.0008
        for c in self.critters:
            c.phase += dt * (7.5 if c.kind == "butterfly" else 5.2)
            c.x += (c.vx + wind_push) * dt
            c.y += (c.vy + math.sin(c.phase * 0.6) * (0.014 if c.kind == "butterfly" else 0.005)) * dt
            if c.x > 1.08:
                c.x = -0.06
            elif c.x < -0.08:
                c.x = 1.06
            if c.kind == "butterfly":
                c.y = clamp(c.y, 0.56, 0.88)
            else:
                c.y = clamp(c.y, 0.08, 0.38)

        if condition in ("rain", "storm"):
            self._next_ripple -= dt
            if self._next_ripple <= 0.0:
                self.ripples.append(
                    RainPuddleRipple(
                        x=self.rng.uniform(0.08, 0.92),
                        y=self.rng.uniform(WALK_MIN_Y - 0.04, 0.96),
                        life=0.0,
                        max_life=self.rng.uniform(0.55, 0.95),
                    )
                )
                self._next_ripple = 0.06 if condition == "storm" else 0.12
                if len(self.ripples) > 36:
                    self.ripples = self.ripples[-36:]

    def paint_location_dynamics(
        self,
        painter: QPainter,
        w: int,
        h: int,
        atmo: AtmospherePalette,
        daylight: float,
        warmth: float,
        condition: str,
        parallax_x: float,
        parallax_y: float,
    ) -> None:
        """Dinâmica ambiental própria do cenário: raios de sol, caustics/reflexos, névoa deslizante, luzes vivas e fauna."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 1. Feixes de luz solar volumétricos (God Rays) na manhã e pôr do sol
        if condition in ("clear", "cloudy") and (daylight > 0.25 or warmth > 0.35):
            ray_strength = clamp(max(daylight * 0.55, warmth * 0.95), 0.0, 1.0)
            if condition == "cloudy":
                ray_strength *= 0.45
            rr, rg, rb = atmo.celestial_glow
            for i in range(4):
                drift = math.sin(self.time * (0.28 + i * 0.07) + i * 1.7) * w * 0.045
                bx = w * (0.16 + i * 0.22) + drift - parallax_x * 10.0
                bw = w * (0.09 + (i % 2) * 0.04)
                pulse = 0.65 + 0.35 * math.sin(self.time * 0.65 + i * 1.9)
                poly = QPainterPath()
                poly.moveTo(bx, 0)
                poly.lineTo(bx + bw, 0)
                poly.lineTo(bx + bw * 2.25 + h * 0.22, h * 0.92)
                poly.lineTo(bx + bw * 0.75 + h * 0.16, h * 0.92)
                poly.closeSubpath()
                g = QLinearGradient(bx, 0, bx + h * 0.20, h * 0.90)
                a = int(38 * ray_strength * pulse)
                g.setColorAt(0.0, QColor(rr, rg, rb, a))
                g.setColorAt(0.65, QColor(rr, rg, rb, a // 3))
                g.setColorAt(1.0, QColor(rr, rg, rb, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(g)
                painter.drawPath(poly)

        # 2. Névoa leve / sombras de nuvens deslizando sobre o piso do terraço
        mist_a = 24 if condition in ("rain", "storm", "fog") else 12
        for i in range(3):
            mx = ((self.time * (0.018 + i * 0.008) + i * 0.37) % 1.4 - 0.2) * w
            my = h * (0.76 + i * 0.06)
            mg = QRadialGradient(QPointF(mx, my), w * 0.28)
            hc = QColor(*atmo.sky_horizon)
            mg.setColorAt(0.0, QColor(hc.red(), hc.green(), hc.blue(), mist_a))
            mg.setColorAt(1.0, QColor(hc.red(), hc.green(), hc.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(mg)
            painter.drawEllipse(QPointF(mx, my), w * 0.30, h * 0.09)

        # 3. Brilho cintilante / reflexos de água & piso molhado (caustics)
        shimmer_alpha = 52 if condition in ("rain", "storm") else (28 if daylight > 0.3 else 36)
        rim = QColor(*atmo.rim_light)
        painter.setPen(Qt.NoPen)
        for i in range(14):
            phase = self.time * (1.2 + (i % 4) * 0.35) + i * 1.15
            sx = ((0.08 + i * 0.065) * w) + math.sin(phase) * 18.0 - parallax_x * 12.0
            sy = h * (0.79 + (i % 5) * 0.036)
            sw = (22.0 + 26.0 * (0.5 + 0.5 * math.sin(phase * 1.4))) * (w / 1280.0)
            a = int(shimmer_alpha * (0.45 + 0.55 * math.sin(phase)))
            painter.setBrush(QColor(rim.red(), rim.green(), rim.blue(), max(0, a)))
            painter.drawRoundedRect(QRectF(sx - sw * 0.5, sy, sw, 2.2), 1.2, 1.2)

        # 4. Luzes quentes pulsantes ao anoitecer/noite (efeito lanternas respirando no cenário)
        if atmo.window_glow_alpha > 0.08:
            pulse = 0.84 + 0.16 * math.sin(self.time * 2.1)
            for lx_n, ly_n, rad in ((0.22, 0.72, 110.0), (0.68, 0.74, 130.0)):
                lx = lx_n * w - parallax_x * 14.0
                ly = ly_n * h - parallax_y * 5.0
                lg = QRadialGradient(QPointF(lx, ly), rad * (h / 720.0))
                a = int(68 * atmo.window_glow_alpha * pulse)
                lg.setColorAt(0.0, QColor(255, 214, 132, a))
                lg.setColorAt(0.55, QColor(255, 175, 92, a // 3))
                lg.setColorAt(1.0, QColor(255, 160, 80, 0))
                painter.setBrush(lg)
                painter.drawEllipse(QPointF(lx, ly), rad * (h / 720.0), rad * (h / 720.0))

        # 5. Fauna viva diurna (pássaros no horizonte & borboletas no jardim quando sem chuva)
        if condition in ("clear", "cloudy") and daylight > 0.25:
            for c in self.critters:
                cx = c.x * w - parallax_x * (6.0 if c.kind == "bird" else 14.0)
                cy = c.y * h - parallax_y * 4.0
                flap = math.sin(c.phase)
                if c.kind == "bird":
                    s = 6.5 * c.scale * (h / 720.0)
                    pen = QPen(QColor(40, 48, 72, int(145 * daylight)), 1.5)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    wy = flap * s * 0.65
                    painter.drawLine(QPointF(cx - s, cy - wy), QPointF(cx, cy))
                    painter.drawLine(QPointF(cx, cy), QPointF(cx + s, cy - wy))
                else:
                    s = 4.8 * c.scale * (h / 720.0)
                    wing_w = max(1.5, abs(flap) * s)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255, 224, 165, int(195 * daylight)))
                    painter.drawEllipse(QPointF(cx - wing_w * 0.6, cy), wing_w, s * 0.72)
                    painter.drawEllipse(QPointF(cx + wing_w * 0.6, cy), wing_w, s * 0.72)

        painter.restore()

    def paint_procedural_terrace(
        self,
        painter: QPainter,
        w: int,
        h: int,
        atmo: AtmospherePalette,
        parallax_x: float,
        parallax_y: float,
        wind_speed: float = 6.0,
    ) -> None:
        """Piso 2.5D de pedra/gramado estilo Tree of Savior / Ragnarok Online quando em modo procedural."""
        floor_top = h * 0.68 - parallax_y * 4.0
        painter.save()

        rail_c = QColor(*atmo.mountain_near)
        rim = QColor(*atmo.rim_light)
        painter.setPen(Qt.NoPen)
        painter.setBrush(rail_c.lighter(115))
        painter.drawRect(QRectF(0, floor_top - 12, w, 16))
        painter.setPen(QPen(QColor(rim.red(), rim.green(), rim.blue(), 120), 1.8))
        painter.drawLine(QPointF(0, floor_top - 12), QPointF(w, floor_top - 12))

        fg = QLinearGradient(0, floor_top, 0, h)
        base_meadow = QColor(
            int(lerp(atmo.mountain_mid[0], 56, 0.45)),
            int(lerp(atmo.mountain_mid[1], 88, 0.45)),
            int(lerp(atmo.mountain_mid[2], 74, 0.35)),
        )
        fg.setColorAt(0.0, base_meadow.lighter(112))
        fg.setColorAt(0.55, base_meadow.darker(108))
        fg.setColorAt(1.0, base_meadow.darker(142))
        painter.setPen(Qt.NoPen)
        painter.setBrush(fg)
        painter.drawRect(QRectF(0, floor_top, w, h - floor_top))

        plaza_cx = w * 0.54 - parallax_x * 16.0
        plaza_cy = h * 0.85 - parallax_y * 6.0
        stone_g = QRadialGradient(QPointF(plaza_cx, plaza_cy), w * 0.40)
        stone = QColor(
            int(lerp(atmo.sky_horizon[0], 112, 0.55)),
            int(lerp(atmo.sky_horizon[1], 116, 0.55)),
            int(lerp(atmo.sky_horizon[2], 132, 0.55)),
        )
        stone_g.setColorAt(0.0, QColor(stone.red(), stone.green(), stone.blue(), 165))
        stone_g.setColorAt(0.78, QColor(stone.red(), stone.green(), stone.blue(), 100))
        stone_g.setColorAt(1.0, QColor(stone.red(), stone.green(), stone.blue(), 0))
        painter.setBrush(stone_g)
        painter.drawEllipse(QPointF(plaza_cx, plaza_cy), w * 0.42, h * 0.14)

        sway_amp = 2.5 + wind_speed * 0.25
        for fx, fy, fsz, ph in self._flora:
            if 0.30 < fx < 0.78 and 0.78 < fy < 0.92:
                continue
            sx, sy = self.screen_pos(fx, fy, w, h, parallax_x, parallax_y)
            sway = math.sin(self.time * 2.4 + ph) * sway_amp
            grass_c = base_meadow.lighter(135)
            painter.setPen(QPen(grass_c, 1.8 * fsz))
            painter.drawLine(QPointF(sx, sy), QPointF(sx - 4 * fsz + sway, sy - 11 * fsz))
            painter.drawLine(QPointF(sx, sy), QPointF(sx + 4 * fsz + sway, sy - 9 * fsz))
        painter.restore()

    def paint_ground_fx(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette, parallax_x: float, parallax_y: float) -> None:
        """Desenha ondas de chuva no piso, poeira/respingos sob os passos e anel de clique."""
        painter.save()
        for r in self.ripples:
            t = clamp(r.life / max(r.max_life, 0.01))
            sx, sy = self.screen_pos(r.x, r.y, w, h, parallax_x, parallax_y)
            d = self.depth_scale(r.y)
            rx = (6.0 + 24.0 * t) * d
            ry = rx * 0.32
            alpha = int(145 * (1.0 - t))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(200, 232, 255, alpha), 1.35))
            painter.drawEllipse(QPointF(sx, sy), rx, ry)

        for fx in self.step_fx:
            t = clamp(fx.life / max(fx.max_life, 0.01))
            sx, sy = self.screen_pos(fx.x, fx.y, w, h, parallax_x, parallax_y)
            d = self.depth_scale(fx.y)
            alpha = int(185 * (1.0 - t))
            if fx.kind == "splash":
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(190, 230, 255, alpha), 1.6))
                painter.drawEllipse(QPointF(sx, sy), (5 + 18 * t) * d, (2 + 6 * t) * d)
            elif fx.kind == "cursor_spark":
                rim = QColor(*atmo.rim_light)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(rim.red(), rim.green(), rim.blue(), alpha), 2.0))
                painter.drawEllipse(QPointF(sx, sy), (8 + 26 * t) * d, (3 + 9 * t) * d)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(245, 240, 228, alpha))
                rad = (3.0 + 4.5 * t) * d
                painter.drawEllipse(QPointF(sx - 6 * t * d, sy - 3 * t * d), rad, rad * 0.72)
                painter.drawEllipse(QPointF(sx + 6 * t * d, sy - 2 * t * d), rad * 0.8, rad * 0.62)
        painter.restore()

    def paint_props_layer(
        self,
        painter: QPainter,
        w: int,
        h: int,
        atmo: AtmospherePalette,
        parallax_x: float,
        parallax_y: float,
        avatar_y: float,
        behind_avatar: bool,
        working_active: bool = False,
        music_active: bool = False,
    ) -> None:
        props = [
            ("cushion", self.hotspots["cushion"].x, self.hotspots["cushion"].y),
            ("desk", self.hotspots["desk"].x, self.hotspots["desk"].y + 0.015),
            ("lantern", self.hotspots["lantern"].x, self.hotspots["lantern"].y),
            ("music_spot", self.hotspots["music_spot"].x, self.hotspots["music_spot"].y - 0.01),
        ]
        props.sort(key=lambda item: item[2])
        u = h / 1080.0

        for name, px, py in props:
            is_behind = py <= avatar_y
            if is_behind != behind_avatar:
                continue
            sx, sy = self.screen_pos(px, py, w, h, parallax_x, parallax_y)
            sc = self.depth_scale(py) * u
            if name == "cushion":
                self._draw_cushion_rug(painter, sx, sy, sc, atmo)
            elif name == "desk":
                self._draw_study_desk(painter, sx, sy, sc, atmo, working_active)
            elif name == "lantern":
                self._draw_lantern_post(painter, sx, sy, sc, atmo)
            elif name == "music_spot":
                self._draw_music_player(painter, sx, sy, sc, atmo, music_active)

    def _draw_cushion_rug(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setPen(QPen(QColor(*atmo.rim_light, 110), 1.8 * sc))
        painter.setBrush(QColor(46, 44, 88, 195))
        painter.drawEllipse(QPointF(sx, sy), 76 * sc, 24 * sc)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(78, 72, 134, 175))
        painter.drawEllipse(QPointF(sx, sy), 58 * sc, 17 * sc)
        painter.restore()

    def _draw_study_desk(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette, active: bool) -> None:
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 100))
        painter.drawEllipse(QPointF(sx, sy + 6 * sc), 60 * sc, 15 * sc)
        wood = QColor(102, 70, 54)
        painter.setBrush(wood.darker(125))
        painter.drawRect(QRectF(sx - 44 * sc, sy - 32 * sc, 7 * sc, 36 * sc))
        painter.drawRect(QRectF(sx + 37 * sc, sy - 32 * sc, 7 * sc, 36 * sc))
        painter.setBrush(wood)
        painter.setPen(QPen(QColor(60, 40, 30), 1.5 * sc))
        painter.drawRoundedRect(QRectF(sx - 52 * sc, sy - 42 * sc, 104 * sc, 14 * sc), 5 * sc, 5 * sc)

        painter.setBrush(QColor(38, 44, 62))
        painter.setPen(QPen(QColor(125, 165, 215), 1.2 * sc))
        painter.drawRoundedRect(QRectF(sx - 18 * sc, sy - 66 * sc, 36 * sc, 24 * sc), 4 * sc, 4 * sc)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(115, 225, 255, 230 if active else 95))
        painter.drawRoundedRect(QRectF(sx - 14 * sc, sy - 62 * sc, 28 * sc, 16 * sc), 2 * sc, 2 * sc)
        if active:
            rg = QRadialGradient(QPointF(sx, sy - 54 * sc), 56 * sc)
            rg.setColorAt(0.0, QColor(110, 220, 255, 115))
            rg.setColorAt(1.0, QColor(110, 220, 255, 0))
            painter.setBrush(rg)
            painter.drawEllipse(QPointF(sx, sy - 54 * sc), 56 * sc, 40 * sc)
        painter.restore()

    def _draw_lantern_post(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 90))
        painter.drawEllipse(QPointF(sx, sy + 2 * sc), 20 * sc, 7 * sc)
        painter.setBrush(QColor(52, 56, 74))
        painter.drawRect(QRectF(sx - 3 * sc, sy - 110 * sc, 6 * sc, 112 * sc))
        ly = sy - 102 * sc
        glow_a = max(0.20, atmo.window_glow_alpha)
        halo = QRadialGradient(QPointF(sx, ly), 85 * sc)
        halo.setColorAt(0.0, QColor(255, 226, 148, int(185 * glow_a)))
        halo.setColorAt(1.0, QColor(255, 160, 80, 0))
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(sx, ly), 85 * sc, 85 * sc)
        painter.setBrush(QColor(255, 242, 192, int(245 * min(1.0, glow_a + 0.3))))
        painter.drawRoundedRect(QRectF(sx - 8 * sc, ly - 9 * sc, 16 * sc, 20 * sc), 5 * sc, 5 * sc)
        painter.restore()

    def _draw_music_player(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette, active: bool) -> None:
        painter.save()
        pulse = 1.0 + (0.06 * math.sin(self.time * 8.0) if active else 0.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 85))
        painter.drawEllipse(QPointF(sx, sy + 4 * sc), 28 * sc, 9 * sc)
        painter.setBrush(QColor(88, 62, 76))
        painter.drawRoundedRect(QRectF(sx - 22 * sc * pulse, sy - 32 * sc * pulse, 44 * sc * pulse, 32 * sc * pulse), 7 * sc, 7 * sc)
        painter.setBrush(QColor(28, 30, 44))
        painter.drawEllipse(QPointF(sx, sy - 16 * sc), 10 * sc * pulse, 10 * sc * pulse)
        painter.restore()
