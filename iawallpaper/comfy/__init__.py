"""Camada comfy: cliente HTTP read-only opcional para geração de cenários e sprites da avatar via ComfyUI."""

from .bridge import ComfyBridge, ComfyStatus
from .workflows import SCENE_PRESETS, build_avatar_workflow, build_scene_workflow

__all__ = [
    "ComfyBridge",
    "ComfyStatus",
    "SCENE_PRESETS",
    "build_avatar_workflow",
    "build_scene_workflow",
]
