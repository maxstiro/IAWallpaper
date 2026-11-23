"""CANVAS — Widget Qt de renderização do wallpaper (60 FPS, captura de gestos de carinho/clique e render offscreen)."""

import math
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QWidget

from ..core.emotion import EmotionState
from ..core.persona import Persona
from ..sense.circadian import CircadianState, compute_circadian
from ..sense.weather import WeatherState
from .avatar import AvatarRig
from .particles import ParticleEngine
from .scene import SceneCompositor


class WallpaperCanvas(QWidget):
    """Canvas principal do wallpaper dinâmico (funciona tanto atrás dos ícones quanto em janela preview)."""

    caress_tick = Signal(float)        # intensidade 0..1 de carinho na cabeça
    avatar_poked = Signal(str)         # "head" | "body"
    ground_clicked = Signal(float, float)  # clique no chão caminhável (x_norm, y_norm) -> click-to-move RO!
    whisper_dismissed = Signal()
    cursor_approaching = Signal(bool)  # True quando cursor se aproxima suavemente da avatar

    def __init__(self, persona: Persona, sprite_dirs=None, scene_dirs=None, render_style: str = "world_sprite", vrm_path=None, live2d_dir=None, character_dir=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setMouseTracking(True)

        self.avatar = AvatarRig(
            persona,
            sprite_dirs=sprite_dirs,
            render_style=render_style,
            vrm_path=vrm_path,
            live2d_dir=live2d_dir,
            character_dir=character_dir,
        )
        self.scene = SceneCompositor(scene_dirs=scene_dirs, seed=persona.seed)
        self.particles = ParticleEngine(seed=persona.seed + 17)

        # Estado visual atual
        self.circadian: CircadianState = compute_circadian()
        self.weather: WeatherState = WeatherState()
        self.emotion: EmotionState = EmotionState()
        self.asleep: bool = False
        self.affinity: float = 12.0
        self.activity: str = "IDLE"
        self.parallax_strength: float = 1.0
        self.particle_density: float = 1.0
        self.avatar_x_ratio: float = 0.72
        self.avatar_scale: float = 1.0

        # Rastreamento de gestos (carinho = movimento vai-e-vem suave sobre a cabeça)
        self._last_mx: float = 0.0
        self._last_my: float = 0.0
        self._last_move_t: float = 0.0
        self._stroke_acc: float = 0.0
        self._caressing: bool = False
        self._was_mouse_down: bool = False
        self._was_approaching: bool = False

    def feed_pointer(self, local_x: float, local_y: float, left_down: bool = False, interactive: bool = True) -> None:
        """Processa posição do mouse (tanto via Qt mouseMove quanto via polling desktop atrás dos ícones)."""
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        nx = ((local_x / w) - 0.5) * 2.0
        ny = ((local_y / h) - 0.5) * 2.0

        self.scene.set_parallax_target(nx, ny, strength=self.parallax_strength)

        # Avatar olha para o cursor relativo à cabeça
        head_c = self.avatar.head_rect.center()
        if not self.avatar.head_rect.isEmpty():
            look_x = (local_x - head_c.x()) / max(w * 0.35, 1.0)
            look_y = (local_y - head_c.y()) / max(h * 0.35, 1.0)
            self.avatar.set_look_target(look_x, look_y)

        if not interactive:
            self._caressing = False
            self._was_mouse_down = left_down
            return

        now = time.monotonic()
        dx = local_x - self._last_mx
        dy = local_y - self._last_my
        dist = math.hypot(dx, dy)
        self._last_mx, self._last_my = local_x, local_y

        hit = self.avatar.hit_test(local_x, local_y)

        # Pista de aproximação para condicionamento Rescorla-Wagner
        approaching = False
        if not self.avatar.head_rect.isEmpty():
            d_head = math.hypot(local_x - head_c.x(), local_y - head_c.y())
            approaching = d_head < max(self.avatar.head_rect.width() * 1.45, 160.0)
        if approaching != self._was_approaching:
            self._was_approaching = approaching
            self.cursor_approaching.emit(approaching)

        # Detecção de carinho (movimento suave sobre a cabeça)
        if hit == "head" and 2.0 <= dist <= 65.0:
            self._stroke_acc = min(1.0, self._stroke_acc + dist / 140.0)
            self._last_move_t = now
            if self._stroke_acc >= 0.35:
                self._caressing = True
                self.caress_tick.emit(self._stroke_acc)
        else:
            if now - self._last_move_t > 0.35:
                self._stroke_acc = max(0.0, self._stroke_acc - 0.08)
                if self._stroke_acc < 0.15:
                    self._caressing = False

        # Clique (borda de subida do botão esquerdo)
        if left_down and not self._was_mouse_down:
            if not self.scene.whisper_rect.isEmpty() and self.scene.whisper_rect.contains(local_x, local_y):
                self.whisper_dismissed.emit()
            elif hit is not None:
                self.avatar.impulse(vy=-210.0, tilt=(-5.0 if local_x < head_c.x() else 5.0))
                self.avatar_poked.emit(hit)
            elif self.avatar.render_style in ("live2d_25d", "vrm_3d", "world_sprite") and (local_y / h) >= 0.65:
                self.scene.stage.spawn_cursor_ripple(local_x / w, local_y / h)
                self.ground_clicked.emit(local_x / w, local_y / h)
        self._was_mouse_down = left_down

    def mouseMoveEvent(self, event):
        pos = event.position()
        self.feed_pointer(pos.x(), pos.y(), left_down=bool(event.buttons() & Qt.LeftButton), interactive=True)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            self.feed_pointer(pos.x(), pos.y(), left_down=True, interactive=True)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._was_mouse_down = False
        super().mouseReleaseEvent(event)

    def step_animation(self, dt: float) -> None:
        """Avança um quadro da simulação visual."""
        self.scene.update(dt, wind_speed=self.weather.wind_speed, condition=self.weather.condition)
        self.particles.update(
            dt=dt,
            width=max(self.width(), 640),
            height=max(self.height(), 360),
            condition=self.weather.condition,
            night_factor=self.circadian.night_factor,
            density=self.particle_density,
            wind_speed=self.weather.wind_speed,
        )
        self.avatar.update(dt=dt, emotion=self.emotion, caressing=self._caressing, asleep=self.asleep)
        if self.avatar.pending_footstep is not None:
            fx, fy = self.avatar.pending_footstep
            self.scene.stage.spawn_footstep(fx, fy, raining=self.weather.condition in ("rain", "storm"))
            self.avatar.pending_footstep = None
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        self.scene.paint(
            painter=painter,
            width=self.width(),
            height=self.height(),
            circadian=self.circadian,
            weather=self.weather,
            emotion=self.emotion,
            avatar=self.avatar,
            particles=self.particles,
            avatar_x_ratio=self.avatar_x_ratio,
            avatar_scale=self.avatar_scale,
            asleep=self.asleep,
            affinity=self.affinity,
            activity=self.activity,
        )
        painter.end()

    def render_to_image(self, width: int = 1280, height: int = 720) -> QImage:
        """Renderiza um quadro offscreen (usado para testes automatizados e validação visual)."""
        self.resize(width, height)
        self.step_animation(0.016)
        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(img)
        self.scene.paint(
            painter=painter,
            width=width,
            height=height,
            circadian=self.circadian,
            weather=self.weather,
            emotion=self.emotion,
            avatar=self.avatar,
            particles=self.particles,
            avatar_x_ratio=self.avatar_x_ratio,
            avatar_scale=self.avatar_scale,
            asleep=self.asleep,
            affinity=self.affinity,
            activity=self.activity,
        )
        painter.end()
        return img
