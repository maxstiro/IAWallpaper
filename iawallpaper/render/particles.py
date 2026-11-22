"""PARTICLES — Sistema de partículas 60 FPS para clima (chuva, neve, relâmpagos), natureza e reações afetivas."""

from dataclasses import dataclass
import math
import random

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient

from ..mathutil import clamp


@dataclass
class WeatherParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    alpha: float
    phase: float
    kind: str  # rain | snow | petal | firefly | mote


@dataclass
class MoodParticle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    size: float
    kind: str  # heart | sparkle | note | zzz
    color: tuple[int, int, int]


@dataclass
class ShootingStar:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float


class ParticleEngine:
    """Gerencia partículas atmosféricas contínuas, relâmpagos, estrelas cadentes e efeitos de emoção."""

    def __init__(self, seed: int = 101):
        self.rng = random.Random(seed)
        self.weather_particles: list[WeatherParticle] = []
        self.mood_particles: list[MoodParticle] = []
        self.shooting_star: ShootingStar | None = None
        self.lightning: float = 0.0
        self._next_lightning: float = 6.0
        self._next_meteor: float = 9.0
        self._current_kind: str = "mote"
        self._width = 1920
        self._height = 1080

    def _target_kind(self, condition: str, night_factor: float) -> tuple[str, int]:
        if condition == "storm":
            return "rain", 180
        if condition == "rain":
            return "rain", 130
        if condition == "snow":
            return "snow", 95
        if night_factor > 0.55:
            return "firefly", 36
        if condition == "clear":
            return "petal", 32
        return "mote", 26

    def _spawn_weather(self, kind: str, w: int, h: int, random_y: bool = False) -> WeatherParticle:
        x = self.rng.uniform(-0.1 * w, 1.1 * w)
        y = self.rng.uniform(0.0, h) if random_y else self.rng.uniform(-0.15 * h, -10.0)
        if kind == "rain":
            return WeatherParticle(
                x=x, y=y,
                vx=self.rng.uniform(-140.0, -70.0),
                vy=self.rng.uniform(760.0, 1180.0),
                size=self.rng.uniform(14.0, 28.0),
                alpha=self.rng.uniform(0.25, 0.62),
                phase=0.0,
                kind="rain",
            )
        if kind == "snow":
            return WeatherParticle(
                x=x, y=y,
                vx=self.rng.uniform(-28.0, 28.0),
                vy=self.rng.uniform(35.0, 82.0),
                size=self.rng.uniform(2.5, 6.2),
                alpha=self.rng.uniform(0.35, 0.85),
                phase=self.rng.uniform(0.0, math.tau),
                kind="snow",
            )
        if kind == "petal":
            return WeatherParticle(
                x=x, y=y,
                vx=self.rng.uniform(18.0, 58.0),
                vy=self.rng.uniform(28.0, 62.0),
                size=self.rng.uniform(5.0, 10.0),
                alpha=self.rng.uniform(0.45, 0.82),
                phase=self.rng.uniform(0.0, math.tau),
                kind="petal",
            )
        if kind == "firefly":
            return WeatherParticle(
                x=self.rng.uniform(0.05 * w, 0.95 * w),
                y=self.rng.uniform(0.35 * h, 0.95 * h),
                vx=self.rng.uniform(-16.0, 16.0),
                vy=self.rng.uniform(-14.0, 14.0),
                size=self.rng.uniform(3.0, 6.5),
                alpha=self.rng.uniform(0.4, 0.95),
                phase=self.rng.uniform(0.0, math.tau),
                kind="firefly",
            )
        return WeatherParticle(
            x=self.rng.uniform(0.0, w),
            y=self.rng.uniform(0.1 * h, 0.95 * h),
            vx=self.rng.uniform(-10.0, 14.0),
            vy=self.rng.uniform(-12.0, -4.0),
            size=self.rng.uniform(2.0, 4.5),
            alpha=self.rng.uniform(0.18, 0.50),
            phase=self.rng.uniform(0.0, math.tau),
            kind="mote",
        )

    def emit_mood_burst(self, kind: str, cx: float, cy: float, count: int = 5, accent: tuple[int, int, int] = (255, 140, 195)) -> None:
        """Emite partículas afetivas (corações, brilhos, notas musicais, Zzz)."""
        for _ in range(count):
            self.mood_particles.append(
                MoodParticle(
                    x=cx + self.rng.uniform(-45.0, 45.0),
                    y=cy + self.rng.uniform(-35.0, 20.0),
                    vx=self.rng.uniform(-24.0, 24.0),
                    vy=self.rng.uniform(-75.0, -35.0),
                    life=0.0,
                    max_life=self.rng.uniform(1.4, 2.5),
                    size=self.rng.uniform(13.0, 22.0),
                    kind=kind,
                    color=accent,
                )
            )
        if len(self.mood_particles) > 64:
            self.mood_particles = self.mood_particles[-64:]

    def update(self, dt: float, width: int, height: int, condition: str, night_factor: float, density: float = 1.0, wind_speed: float = 6.0) -> None:
        dt = clamp(dt, 0.0, 0.1)
        self._width = max(width, 320)
        self._height = max(height, 240)
        kind, base_count = self._target_kind(condition, night_factor)
        target_count = int(round(base_count * clamp(density, 0.0, 2.0)))

        if kind != self._current_kind:
            self._current_kind = kind
            self.weather_particles = [self._spawn_weather(kind, self._width, self._height, random_y=True) for _ in range(target_count)]
        else:
            while len(self.weather_particles) < target_count:
                self.weather_particles.append(self._spawn_weather(kind, self._width, self._height, random_y=True))
            if len(self.weather_particles) > target_count:
                self.weather_particles = self.weather_particles[:target_count]

        wind_bias = (wind_speed - 6.0) * 3.5

        for p in self.weather_particles:
            p.phase += dt * 2.2
            if p.kind == "rain":
                p.x += (p.vx - wind_bias * 2.2) * dt
                p.y += p.vy * dt
                if p.y > self._height + 30 or p.x < -80 or p.x > self._width + 80:
                    np_p = self._spawn_weather("rain", self._width, self._height, random_y=False)
                    p.x, p.y, p.vx, p.vy = np_p.x, np_p.y, np_p.vx, np_p.vy
            elif p.kind in ("snow", "petal"):
                sway = math.sin(p.phase) * (24.0 if p.kind == "petal" else 16.0)
                p.x += (p.vx + sway + wind_bias) * dt
                p.y += p.vy * dt
                if p.y > self._height + 20 or p.x < -60 or p.x > self._width + 60:
                    np_p = self._spawn_weather(p.kind, self._width, self._height, random_y=False)
                    p.x, p.y = np_p.x, np_p.y
            else:
                p.x += (p.vx + math.sin(p.phase) * 10.0) * dt
                p.y += (p.vy + math.cos(p.phase * 0.8) * 8.0) * dt
                if p.x < -20:
                    p.x = self._width + 10
                elif p.x > self._width + 20:
                    p.x = -10
                if p.y < 0.1 * self._height:
                    p.y = self._height * 0.92
                elif p.y > self._height + 10:
                    p.y = self._height * 0.45

        # Relâmpagos na tempestade
        if self.lightning > 0.0:
            self.lightning = max(0.0, self.lightning - dt * 3.4)
        if condition == "storm":
            self._next_lightning -= dt
            if self._next_lightning <= 0.0:
                self.lightning = self.rng.uniform(0.75, 1.0)
                self._next_lightning = self.rng.uniform(4.5, 12.0)

        # Estrela cadente em noites limpas
        if self.shooting_star is not None:
            s = self.shooting_star
            s.life += dt
            s.x += s.vx * dt
            s.y += s.vy * dt
            if s.life >= s.max_life:
                self.shooting_star = None
        elif condition == "clear" and night_factor > 0.7:
            self._next_meteor -= dt
            if self._next_meteor <= 0.0:
                self.shooting_star = ShootingStar(
                    x=self.rng.uniform(0.15 * self._width, 0.85 * self._width),
                    y=self.rng.uniform(0.05 * self._height, 0.30 * self._height),
                    vx=self.rng.uniform(420.0, 680.0),
                    vy=self.rng.uniform(160.0, 290.0),
                    life=0.0,
                    max_life=self.rng.uniform(0.6, 1.0),
                )
                self._next_meteor = self.rng.uniform(9.0, 22.0)

        # Partículas de emoção
        alive = []
        for mp in self.mood_particles:
            mp.life += dt
            if mp.life < mp.max_life:
                mp.x += (mp.vx + math.sin(mp.life * 4.5) * 14.0) * dt
                mp.y += mp.vy * dt
                alive.append(mp)
        self.mood_particles = alive

    def paint_sky_fx(self, painter: QPainter) -> None:
        """Desenha estrelas cadentes no plano do céu."""
        if self.shooting_star is None:
            return
        s = self.shooting_star
        prog = clamp(s.life / max(s.max_life, 0.01))
        alpha = int(235 * math.sin(prog * math.pi))
        pen = QPen(QColor(235, 246, 255, alpha), 2.4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(s.x, s.y), QPointF(s.x - s.vx * 0.16, s.y - s.vy * 0.16))

    def paint_weather(self, painter: QPainter) -> None:
        """Desenha partículas climáticas e ambientais em camadas."""
        painter.save()
        for p in self.weather_particles:
            if p.kind == "rain":
                pen = QPen(QColor(200, 225, 255, int(p.alpha * 255)), 1.35)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                dx = p.vx * (p.size / max(p.vy, 1.0))
                painter.drawLine(QPointF(p.x, p.y), QPointF(p.x + dx, p.y + p.size))
            elif p.kind == "snow":
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(242, 248, 255, int(p.alpha * 255)))
                painter.drawEllipse(QPointF(p.x, p.y), p.size * 0.5, p.size * 0.5)
            elif p.kind == "petal":
                painter.save()
                painter.translate(p.x, p.y)
                painter.rotate(math.degrees(p.phase) * 0.7)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 198, 220, int(p.alpha * 255)))
                painter.drawEllipse(QPointF(0, 0), p.size * 0.65, p.size * 0.34)
                painter.restore()
            elif p.kind == "firefly":
                pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(p.phase * 1.6))
                r = p.size * (1.2 + 0.5 * pulse)
                grad = QRadialGradient(QPointF(p.x, p.y), r * 2.2)
                grad.setColorAt(0.0, QColor(255, 242, 165, int(230 * p.alpha * pulse)))
                grad.setColorAt(0.45, QColor(180, 245, 175, int(110 * p.alpha * pulse)))
                grad.setColorAt(1.0, QColor(120, 220, 180, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(grad)
                painter.drawEllipse(QPointF(p.x, p.y), r * 2.2, r * 2.2)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 245, 215, int(p.alpha * 255)))
                painter.drawEllipse(QPointF(p.x, p.y), p.size * 0.5, p.size * 0.5)
        painter.restore()

    def paint_mood_fx(self, painter: QPainter) -> None:
        """Desenha corações, estrelas 4-pontas, notas musicais e Zzz vetoriais suaves."""
        if not self.mood_particles:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        for mp in self.mood_particles:
            t = clamp(mp.life / max(mp.max_life, 0.01))
            alpha = int(245 * math.sin(t * math.pi))
            r, g, b = mp.color
            s = mp.size * (0.62 + 0.22 * t)
            painter.save()
            painter.translate(mp.x, mp.y)

            if mp.kind == "heart":
                path = QPainterPath()
                path.moveTo(0, s * 0.35)
                path.cubicTo(-s * 0.65, -s * 0.15, -s * 0.55, -s * 0.72, 0, -s * 0.28)
                path.cubicTo(s * 0.55, -s * 0.72, s * 0.65, -s * 0.15, 0, s * 0.35)
                painter.setPen(QPen(QColor(255, 240, 248, int(alpha * 0.7)), 1.2))
                painter.setBrush(QColor(r, g, b, alpha))
                painter.drawPath(path)
            elif mp.kind == "sparkle":
                path = QPainterPath()
                path.moveTo(0, -s * 0.6)
                path.quadTo(0, 0, s * 0.6, 0)
                path.quadTo(0, 0, 0, s * 0.6)
                path.quadTo(0, 0, -s * 0.6, 0)
                path.quadTo(0, 0, 0, -s * 0.6)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 246, 200, alpha))
                painter.drawPath(path)
            elif mp.kind == "note":
                painter.setPen(QPen(QColor(r, g, b, alpha), 2.2))
                painter.setBrush(QColor(r, g, b, alpha))
                painter.drawEllipse(QPointF(-s * 0.15, s * 0.2), s * 0.22, s * 0.16)
                painter.drawLine(QPointF(s * 0.05, s * 0.18), QPointF(s * 0.05, -s * 0.45))
                painter.drawLine(QPointF(s * 0.05, -s * 0.45), QPointF(s * 0.35, -s * 0.30))
            else:
                font = QFont("Segoe UI", max(10, int(s * 0.85)))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(r, g, b, alpha))
                painter.drawText(QPointF(-s * 0.4, 0), "Zzz")
            painter.restore()
        painter.restore()
