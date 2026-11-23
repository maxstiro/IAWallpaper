"""Camada render: motor visual 2.5D do wallpaper vivo, atmosfera, partículas, avatar animado e canvas Qt."""

from .atmosphere import AtmospherePalette, compute_atmosphere
from .avatar import AvatarRig
from .canvas import WallpaperCanvas
from .particles import ParticleEngine
from .rig_cutter import AutoRiggedCharacter, RigPart, build_rig_from_apose
from .scene import SceneCompositor
from .skeleton import BoneWorld, CharacterSkeleton, PoseTargets, RigProportions
from .sprite_clip import SpriteClip, load_clips_from_dirs, load_sprite_clip
from .world_stage import WorldStage

__all__ = [
    "AtmospherePalette",
    "compute_atmosphere",
    "AvatarRig",
    "WallpaperCanvas",
    "ParticleEngine",
    "AutoRiggedCharacter",
    "RigPart",
    "build_rig_from_apose",
    "SceneCompositor",
    "BoneWorld",
    "CharacterSkeleton",
    "PoseTargets",
    "RigProportions",
    "SpriteClip",
    "load_clips_from_dirs",
    "load_sprite_clip",
    "WorldStage",
]
