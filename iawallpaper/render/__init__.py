"""Camada render: motor visual 2.5D do wallpaper vivo, atmosfera, partículas, avatar animado e canvas Qt."""

from .atmosphere import AtmospherePalette, compute_atmosphere
from .avatar import AvatarRig
from .canvas import WallpaperCanvas
from .particles import ParticleEngine
from .scene import SceneCompositor
from .world_stage import WorldStage

__all__ = [
    "AtmospherePalette",
    "compute_atmosphere",
    "AvatarRig",
    "WallpaperCanvas",
    "ParticleEngine",
    "SceneCompositor",
    "WorldStage",
]
