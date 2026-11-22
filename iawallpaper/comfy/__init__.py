"""Camada comfy: cliente HTTP read-only opcional para geração de cenários e sprites da avatar via ComfyUI."""

from .bridge import ComfyBridge, ComfyStatus
from .presets import ComfyPreset, LoraSpec, find_comfy_preset, load_comfy_presets
from .workflows import SCENE_PRESETS, build_avatar_workflow, build_scene_workflow

__all__ = [
    "ComfyBridge",
    "ComfyStatus",
    "ComfyPreset",
    "LoraSpec",
    "find_comfy_preset",
    "load_comfy_presets",
    "SCENE_PRESETS",
    "build_avatar_workflow",
    "build_scene_workflow",
]
