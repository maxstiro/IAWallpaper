"""WORLD STAGE — Palco 2.5D caminhável estilo Ragnarok Online / Tree of Savior / Pokémon NDS.

Fornece plano de chão com perspectiva de profundidade (escala por Y), pontos de interesse
interativos (escrivaninha com notebook, almofada/tapete de descanso, lanterna, mirante,
cantinho de música), respingos de chuva no piso, poeira de passos e ordenação por profundidade (Y-sort).
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
    y: float           # coordenada normalizada 0.64..0.90 (profundidade no chão)
    arrive_action: str # idle | sit_work | sit_relax | sleep | music_sway
    label_pt: str


DEFAULT_HOTSPOTS: dict[str, WorldHotspot] = {
    "desk":       WorldHotspot("desk",       0.38, 0.86, "sit_work",   "Cantinho de Estudo"),
    "music_spot": WorldHotspot("music_spot", 0.48, 0.84, "music_sway", "Cantinho Musical"),
    "overlook":   WorldHotspot("overlook",   0.56, 0.82, "idle",       "Praça Central"),
    "lantern":    WorldHotspot("lantern",    0.66, 0.85, "idle",       "Mirante da Lanterna"),
    "cushion":    WorldHotspot("cushion",    0.78, 0.88, "sleep",      "Tapete & Almofada"),
    "garden_l":   WorldHotspot("garden_l",   0.36, 0.91, "idle",       "Terraço Oeste"),
    "garden_r":   WorldHotspot("garden_r",   0.82, 0.91, "idle",       "Terraço Leste"),
}

WALK_MIN_X, WALK_MAX_X = 0.28, 0.88
WALK_MIN_Y, WALK_MAX_Y = 0.78, 0.93


@dataclass
class GroundStepFx:
    x: float
    y: float
    life: float
    max_life: float
    kind: str  # dust | splash


@dataclass
class RainPuddleRipple:
    x: float
    y: float
    life: float
    max_life: float


class WorldStage:
    """Gerencia o terreno caminhável 2.5D, props interativos ordenados por Y e efeitos no piso."""

    def __init__(self, seed: int = 2026):
        self.rng = random.Random(seed + 88)
        self.hotspots = dict(DEFAULT_HOTSPOTS)
        self.time: float = 0.0
        self.step_fx: list[GroundStepFx] = []
        self.ripples: list[RainPuddleRipple] = []
        self._next_ripple: float = 0.2

        # Tufos de grama e florzinhas decorativas determinísticas no chão (x, y, size, phase)
        self._flora = [
            (self.rng.uniform(0.06, 0.94), self.rng.uniform(0.66, 0.93), self.rng.uniform(0.7, 1.3), self.rng.uniform(0, math.tau))
            for _ in range(38)
        ]

    @staticmethod
    def clamp_walkable(x: float, y: float) -> tuple[float, float]:
        return clamp(x, WALK_MIN_X, WALK_MAX_X), clamp(y, WALK_MIN_Y, WALK_MAX_Y)

    @staticmethod
    def depth_scale(y_norm: float) -> float:
        """Perspectiva 2.5D estilo RO/ToS: menor no fundo (y=0.65), maior na frente (y=0.89)."""
        t = clamp((y_norm - WALK_MIN_Y) / max(WALK_MAX_Y - WALK_MIN_Y, 0.01), 0.0, 1.0)
        return lerp(0.84, 1.15, t)

    def screen_pos(self, x_norm: float, y_norm: float, w: int, h: int, parallax_x: float = 0.0, parallax_y: float = 0.0) -> tuple[float, float]:
        depth = self.depth_scale(y_norm)
        sx = x_norm * w - parallax_x * (16.0 * depth)
        sy = y_norm * h - parallax_y * (6.0 * depth)
        return sx, sy

    def spawn_footstep(self, x_norm: float, y_norm: float, raining: bool = False) -> None:
        self.step_fx.append(
            GroundStepFx(
                x=x_norm,
                y=y_norm,
                life=0.0,
                max_life=0.48 if raining else 0.42,
                kind="splash" if raining else "dust",
            )
        )
        if len(self.step_fx) > 28:
            self.step_fx = self.step_fx[-28:]

    def update(self, dt: float, condition: str = "clear") -> None:
        dt = clamp(dt, 0.0, 0.1)
        self.time += dt

        self.step_fx = [f for f in self.step_fx if (setattr(f, "life", f.life + dt) or True) and f.life < f.max_life]
        self.ripples = [r for r in self.ripples if (setattr(r, "life", r.life + dt) or True) and r.life < r.max_life]

        if condition in ("rain", "storm"):
            self._next_ripple -= dt
            if self._next_ripple <= 0.0:
                self.ripples.append(
                    RainPuddleRipple(
                        x=self.rng.uniform(0.08, 0.92),
                        y=self.rng.uniform(WALK_MIN_Y, 0.93),
                        life=0.0,
                        max_life=self.rng.uniform(0.55, 0.95),
                    )
                )
                self._next_ripple = 0.07 if condition == "storm" else 0.14
                if len(self.ripples) > 30:
                    self.ripples = self.ripples[-30:]

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
        """Desenha o chão 2.5D de pedra/gramado estilo Tree of Savior / Ragnarok Online quando não há PNG de fundo."""
        floor_top = h * 0.625 - parallax_y * 4.0
        painter.save()

        # Balaustrada de pedra do mirante separando céu/vale do chão caminhável
        rail_c = QColor(*atmo.mountain_near)
        rim = QColor(*atmo.rim_light)
        painter.setPen(Qt.NoPen)
        painter.setBrush(rail_c.lighter(115))
        painter.drawRect(QRectF(0, floor_top - 12, w, 16))
        painter.setPen(QPen(QColor(rim.red(), rim.green(), rim.blue(), 120), 1.8))
        painter.drawLine(QPointF(0, floor_top - 12), QPointF(w, floor_top - 12))

        # Piso de prado + praça de pedras 2.5D em gradiente de profundidade
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

        # Caminho central de paralelepípedos / praça circular 2.5D (perspectiva isométrica suave)
        plaza_cx = w * 0.50 - parallax_x * 16.0
        plaza_cy = h * 0.77 - parallax_y * 6.0
        stone_g = QRadialGradient(QPointF(plaza_cx, plaza_cy), w * 0.36)
        stone = QColor(
            int(lerp(atmo.sky_horizon[0], 112, 0.55)),
            int(lerp(atmo.sky_horizon[1], 116, 0.55)),
            int(lerp(atmo.sky_horizon[2], 132, 0.55)),
        )
        stone_g.setColorAt(0.0, QColor(stone.red(), stone.green(), stone.blue(), 155))
        stone_g.setColorAt(0.75, QColor(stone.red(), stone.green(), stone.blue(), 95))
        stone_g.setColorAt(1.0, QColor(stone.red(), stone.green(), stone.blue(), 0))
        painter.setBrush(stone_g)
        painter.drawEllipse(QPointF(plaza_cx, plaza_cy), w * 0.38, h * 0.145)

        # Linhas sutis de ladrilhos em perspectiva
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1.2))
        for ring in (0.14, 0.25, 0.35):
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(plaza_cx, plaza_cy), w * ring, h * ring * 0.36)

        # Tufos de grama e florzinhas balançando com o vento
        sway_amp = 2.5 + wind_speed * 0.25
        for fx, fy, fsz, ph in self._flora:
            if 0.30 < fx < 0.70 and 0.70 < fy < 0.85:
                continue  # deixa o centro de pedra limpo
            sx, sy = self.screen_pos(fx, fy, w, h, parallax_x, parallax_y)
            sway = math.sin(self.time * 2.4 + ph) * sway_amp
            grass_c = base_meadow.lighter(135)
            painter.setPen(QPen(grass_c, 1.8 * fsz))
            painter.drawLine(QPointF(sx, sy), QPointF(sx - 4 * fsz + sway, sy - 11 * fsz))
            painter.drawLine(QPointF(sx, sy), QPointF(sx + 4 * fsz + sway, sy - 9 * fsz))
            if int(ph * 10) % 4 == 0:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 226, 238, 195))
                painter.drawEllipse(QPointF(sx + sway, sy - 11 * fsz), 2.5 * fsz, 2.5 * fsz)

        painter.restore()

    def paint_ground_fx(self, painter: QPainter, w: int, h: int, atmo: AtmospherePalette, parallax_x: float, parallax_y: float) -> None:
        """Desenha ondas de chuva no piso e poeira/respingos sob os passos da avatar."""
        painter.save()
        for r in self.ripples:
            t = clamp(r.life / max(r.max_life, 0.01))
            sx, sy = self.screen_pos(r.x, r.y, w, h, parallax_x, parallax_y)
            d = self.depth_scale(r.y)
            rx = (6.0 + 22.0 * t) * d
            ry = rx * 0.34
            alpha = int(135 * (1.0 - t))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(200, 232, 255, alpha), 1.3))
            painter.drawEllipse(QPointF(sx, sy), rx, ry)

        for fx in self.step_fx:
            t = clamp(fx.life / max(fx.max_life, 0.01))
            sx, sy = self.screen_pos(fx.x, fx.y, w, h, parallax_x, parallax_y)
            d = self.depth_scale(fx.y)
            alpha = int(165 * (1.0 - t))
            if fx.kind == "splash":
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(190, 230, 255, alpha), 1.5))
                painter.drawEllipse(QPointF(sx, sy), (5 + 16 * t) * d, (2 + 5.5 * t) * d)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(240, 238, 228, alpha))
                rad = (3.0 + 4.5 * t) * d
                painter.drawEllipse(QPointF(sx - 6 * t * d, sy - 3 * t * d), rad, rad * 0.75)
                painter.drawEllipse(QPointF(sx + 6 * t * d, sy - 2 * t * d), rad * 0.8, rad * 0.65)
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
        """Desenha props interativos do cenário com Y-sort real (atrás ou à frente da avatar)."""
        props = [
            ("cushion", self.hotspots["cushion"].x, self.hotspots["cushion"].y),
            ("desk", self.hotspots["desk"].x, self.hotspots["desk"].y + 0.018),
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
        # Tapete estrelado macio no chão
        painter.setPen(QPen(QColor(*atmo.rim_light, 120), 2.0 * sc))
        painter.setBrush(QColor(54, 52, 98, 205))
        painter.drawEllipse(QPointF(sx, sy), 78 * sc, 28 * sc)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(82, 76, 138, 190))
        painter.drawEllipse(QPointF(sx, sy), 62 * sc, 21 * sc)
        # Almofada fofa
        painter.setBrush(QColor(228, 214, 248, 235))
        painter.setPen(QPen(QColor(138, 118, 178, 180), 1.6 * sc))
        painter.drawRoundedRect(QRectF(sx - 28 * sc, sy - 20 * sc, 56 * sc, 24 * sc), 11 * sc, 11 * sc)
        painter.restore()

    def _draw_study_desk(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette, active: bool) -> None:
        painter.save()
        # Sombra no chão
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 95))
        painter.drawEllipse(QPointF(sx, sy + 6 * sc), 66 * sc, 18 * sc)

        # Pernas e tampo de madeira acolhedora
        wood = QColor(112, 78, 58)
        painter.setBrush(wood.darker(125))
        painter.drawRect(QRectF(sx - 50 * sc, sy - 34 * sc, 8 * sc, 38 * sc))
        painter.drawRect(QRectF(sx + 42 * sc, sy - 34 * sc, 8 * sc, 38 * sc))
        painter.setBrush(wood)
        painter.setPen(QPen(QColor(68, 44, 32), 1.6 * sc))
        painter.drawRoundedRect(QRectF(sx - 58 * sc, sy - 46 * sc, 116 * sc, 16 * sc), 5 * sc, 5 * sc)

        # Mini notebook com brilho ciano quando o usuário está programando
        painter.setBrush(QColor(42, 48, 68))
        painter.setPen(QPen(QColor(120, 155, 200), 1.2 * sc))
        painter.drawRoundedRect(QRectF(sx - 20 * sc, sy - 72 * sc, 40 * sc, 26 * sc), 4 * sc, 4 * sc)
        screen_glow = 230 if active else 90
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(115, 225, 255, screen_glow))
        painter.drawRoundedRect(QRectF(sx - 16 * sc, sy - 68 * sc, 32 * sc, 18 * sc), 2 * sc, 2 * sc)
        if active:
            rg = QRadialGradient(QPointF(sx, sy - 60 * sc), 58 * sc)
            rg.setColorAt(0.0, QColor(110, 220, 255, 115))
            rg.setColorAt(1.0, QColor(110, 220, 255, 0))
            painter.setBrush(rg)
            painter.drawEllipse(QPointF(sx, sy - 60 * sc), 58 * sc, 42 * sc)
        painter.restore()

    def _draw_lantern_post(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette) -> None:
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 90))
        painter.drawEllipse(QPointF(sx, sy + 2 * sc), 22 * sc, 8 * sc)

        # Poste delicado estilo Tree of Savior
        painter.setBrush(QColor(54, 58, 76))
        painter.drawRect(QRectF(sx - 3.5 * sc, sy - 118 * sc, 7 * sc, 120 * sc))
        painter.drawRoundedRect(QRectF(sx - 12 * sc, sy - 122 * sc, 24 * sc, 7 * sc), 3 * sc, 3 * sc)

        ly = sy - 108 * sc
        glow_a = max(0.18, atmo.window_glow_alpha)
        halo = QRadialGradient(QPointF(sx, ly), 92 * sc)
        halo.setColorAt(0.0, QColor(255, 226, 148, int(190 * glow_a)))
        halo.setColorAt(0.45, QColor(255, 182, 95, int(75 * glow_a)))
        halo.setColorAt(1.0, QColor(255, 160, 80, 0))
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(sx, ly), 92 * sc, 92 * sc)

        painter.setBrush(QColor(255, 242, 192, int(245 * min(1.0, glow_a + 0.35))))
        painter.setPen(QPen(QColor(70, 62, 74), 1.4 * sc))
        painter.drawRoundedRect(QRectF(sx - 9 * sc, ly - 10 * sc, 18 * sc, 22 * sc), 5 * sc, 5 * sc)
        painter.restore()

    def _draw_music_player(self, painter: QPainter, sx: float, sy: float, sc: float, atmo: AtmospherePalette, active: bool) -> None:
        painter.save()
        pulse = 1.0 + (0.06 * math.sin(self.time * 8.0) if active else 0.0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(8, 12, 24, 85))
        painter.drawEllipse(QPointF(sx, sy + 4 * sc), 30 * sc, 10 * sc)

        # Caixa retrô / vitrola aconchegante
        painter.setBrush(QColor(92, 66, 78))
        painter.setPen(QPen(QColor(220, 185, 155, 175), 1.4 * sc))
        painter.drawRoundedRect(QRectF(sx - 24 * sc * pulse, sy - 34 * sc * pulse, 48 * sc * pulse, 34 * sc * pulse), 7 * sc, 7 * sc)
        painter.setBrush(QColor(30, 32, 46))
        painter.drawEllipse(QPointF(sx, sy - 17 * sc), 11 * sc * pulse, 11 * sc * pulse)
        if active:
            painter.setPen(QPen(QColor(130, 230, 255, 185), 1.6 * sc))
            painter.setBrush(Qt.NoBrush)
            r = (16 + 18 * ((self.time * 1.4) % 1.0)) * sc
            painter.drawEllipse(QPointF(sx, sy - 17 * sc), r, r)
        painter.restore()
