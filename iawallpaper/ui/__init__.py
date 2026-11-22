"""Camada ui: Central de Controle estilo Wallpaper Engine, Monitor Neural ao vivo e ícone de bandeja."""

from .control_center import ControlCenterWindow
from .neural_monitor import NeuralMonitorWindow
from .tray import WallpaperTray

__all__ = ["ControlCenterWindow", "NeuralMonitorWindow", "WallpaperTray"]
