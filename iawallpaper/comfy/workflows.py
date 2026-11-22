"""WORKFLOWS — Construtores de grafos ComfyUI SDXL/Illustrious + PAG + RemBG (100% read-only via HTTP API)."""

import random

from ..core.persona import Persona

SCENE_PRESETS: dict[str, dict[str, str]] = {
    "sky_sanctuary": {
        "label": "Observatório Celeste",
        "base": "anime_scenery, floating_sky_observatory_balcony, distant_mountains, serene_lake, makoto_shinkai_style, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper",
    },
    "cyber_loft": {
        "label": "Apartamento Cyberpunk",
        "base": "anime_scenery, cozy_futuristic_loft_window, neon_cyberpunk_cityscape_outside, glowing_skyscrapers, lo-fi_aesthetic, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper",
    },
    "sakura_hill": {
        "label": "Colina de Sakuras",
        "base": "anime_scenery, peaceful_hilltop_shrine_overlook, blooming_cherry_blossoms, distant_coastal_town, makoto_shinkai_style, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper",
    },
}

TIME_VARIANT_PROMPTS: dict[str, str] = {
    "day": "bright_blue_sky, fluffy_cumulus_clouds, crisp_sunlight, vibrant_colors, clear_day",
    "sunset": "golden_hour, dramatic_sunset_sky, orange_and_violet_clouds, warm_sunbeams, glowing_horizon",
    "night": "deep_starry_night_sky, crescent_moon, glowing_distant_city_lights, bioluminescent_fireflies, serene_moonlight",
    "rain": "rainy_atmosphere, overcast_slate_sky, wet_reflective_surfaces, soft_cyan_mist, cozy_warm_lantern_glow",
}

DEFAULT_NEGATIVE = (
    "lowres, bad_anatomy, bad_hands, text, watermark, signature, logo, username, "
    "blurry, jpeg_artifacts, worst_quality, low_quality, nsfw, nude, explicit, "
    "multiple_views, split_screen, comic_panel"
)


def build_scene_workflow(
    checkpoint: str,
    scene_id: str = "sky_sanctuary",
    variant: str = "sunset",
    seed: int | None = None,
    width: int = 1344,
    height: int = 768,
    steps: int = 20,
    cfg: float = 5.5,
    use_pag: bool = True,
) -> dict:
    """Constrói grafo SDXL/Illustrious widescreen para fundo de wallpaper (sem personagens)."""
    preset = SCENE_PRESETS.get(scene_id, SCENE_PRESETS["sky_sanctuary"])
    time_tags = TIME_VARIANT_PROMPTS.get(variant, TIME_VARIANT_PROMPTS["sunset"])
    positive = f"{preset['base']}, {time_tags}"
    negative = f"{DEFAULT_NEGATIVE}, 1girl, 1boy, person, character, silhouette_person"
    actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))

    model_src = ["1", 0]
    graph: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
    }
    if use_pag:
        graph["5"] = {"class_type": "PerturbedAttentionGuidance", "inputs": {"model": ["1", 0], "scale": 2.5}}
        model_src = ["5", 0]

    graph["6"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
            "seed": actual_seed,
            "steps": int(steps),
            "cfg": float(cfg),
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "denoise": 1.0,
        },
    }
    graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    graph["8"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["7", 0], "filename_prefix": f"IAWallpaper_scene_{scene_id}_{variant}"},
    }
    return graph


def build_avatar_workflow(
    checkpoint: str,
    persona: Persona,
    outfit_key: str = "casual",
    seed: int | None = None,
    width: int = 832,
    height: int = 1216,
    steps: int = 22,
    cfg: float = 5.5,
    use_pag: bool = True,
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> dict:
    """Constrói grafo SDXL/Illustrious + RemBG para gerar sprite transparente RGBA da waifu."""
    outfit = persona.outfits.get(outfit_key) or persona.outfits["casual"]
    outfit_tags = outfit.get("prompt", "stylish_anime_outfit")
    positive = (
        f"{persona.comfy_character_tags}, {outfit_tags}, "
        "cowboy_shot, standing, clean_edges, simple_background, solid_white_background, studio_lighting"
    )
    negative = f"{DEFAULT_NEGATIVE}, complex_background, scenery, cropped_head, out_of_frame, extra_limbs"
    actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))

    model_src = ["1", 0]
    graph: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
    }
    if use_pag:
        graph["5"] = {"class_type": "PerturbedAttentionGuidance", "inputs": {"model": ["1", 0], "scale": 2.8}}
        model_src = ["5", 0]

    graph["6"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
            "seed": actual_seed,
            "steps": int(steps),
            "cfg": float(cfg),
            "sampler_name": "dpmpp_2m",
            "scheduler": "karras",
            "positive": ["2", 0],
            "negative": ["3", 0],
            "latent_image": ["4", 0],
            "denoise": 1.0,
        },
    }
    graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}

    img_src = ["7", 0]
    if use_rembg:
        graph["8"] = {
            "class_type": "Image Rembg (Remove Background)",
            "inputs": {
                "images": ["7", 0],
                "transparency": True,
                "model": rembg_model,
                "post_processing": True,
                "only_mask": False,
                "alpha_matting": True,
                "alpha_matting_foreground_threshold": 240,
                "alpha_matting_background_threshold": 10,
                "alpha_matting_erode_size": 6,
                "background_color": "none",
            },
        }
        img_src = ["8", 0]

    graph["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": img_src, "filename_prefix": f"IAWallpaper_avatar_{persona.id}_{outfit_key}"},
    }
    return graph
