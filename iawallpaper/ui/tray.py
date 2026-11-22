"""TRAY — Ícone na bandeja do sistema (estilo Wallpaper Engine) com acesso instantâneo a todos os controles."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _make_tray_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    g = QRadialGradient(32, 32, 30)
    g.setColorAt(0.0, QColor(142, 210, 255))
    g.setColorAt(0.65, QColor(78, 112, 232))
    g.setColorAt(1.0, QColor(24, 30, 68))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(4, 4, 56, 56)
    p.setBrush(QColor(255, 250, 230))
    p.drawEllipse(22, 20, 20, 20)
    p.setBrush(QColor(78, 112, 232))
    p.drawEllipse(28, 17, 16, 16)
    p.end()
    return QIcon(pm)


class WallpaperTray(QSystemTrayIcon):
    open_studio = Signal()
    open_monitor = Signal()
    toggle_pause = Signal()
    toggle_mode = Signal()
    caress_now = Signal()
    quit_app = Signal()

    def __init__(self, parent=None):
        super().__init__(_make_tray_icon(), parent)
        self.setToolTip("IAWallpaper — Wallpaper Dinâmico Vivo")

        menu = QMenu()
        a_studio = QAction("🎛️ Central de Controle", menu)
        a_studio.triggered.connect(self.open_studio.emit)

        a_mon = QAction("🧠 Monitor Neural ao Vivo", menu)
        a_mon.triggered.connect(self.open_monitor.emit)

        a_pat = QAction("♥ Fazer Carinho", menu)
        a_pat.triggered.connect(self.caress_now.emit)

        a_mode = QAction("🖼️ Alternar Wallpaper / Preview", menu)
        a_mode.triggered.connect(self.toggle_mode.emit)

        self.act_pause = QAction("⏸️ Pausar Animação", menu)
        self.act_pause.triggered.connect(self.toggle_pause.emit)

        a_quit = QAction("❌ Sair do IAWallpaper", menu)
        a_quit.triggered.connect(self.quit_app.emit)

        menu.addAction(a_studio)
        menu.addAction(a_mon)
        menu.addSeparator()
        menu.addAction(a_pat)
        menu.addAction(a_mode)
        menu.addAction(self.act_pause)
        menu.addSeparator()
        menu.addAction(a_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_studio.emit()

    def set_paused_label(self, paused: bool) -> None:
        self.act_pause.setText("▶️ Retomar Animação" if paused else "⏸️ Pausar Animação")
