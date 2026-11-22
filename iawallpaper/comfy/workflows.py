"""WORKFLOWS — Construtores de grafos ComfyUI SDXL/Illustrious + PAG + RemBG + img2img consistente."""

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

EXPRESSION_PROMPTS: dict[str, str] = {
    "happy": "bright_cheerful_smile, open_mouth, sparkling_eyes, joyful_expression, happy",
    "affectionate": "closed_eyes, happy_closed_eyes, gentle_warm_smile, soft_blush, affectionate_expression, blissful",
    "shy": "blushing, heavy_blush, shy_expression, looking_slightly_aside, embarrassed_cute_smile",
    "sleepy": "half-closed_eyes, sleepy_expression, drowsy_eyes, relaxed_soft_mouth, tired_cute_face",
    "pouty": "pout, puffed_cheeks, slightly_annoyed_cute_expression, furrowed_brows",
}

PACK_OUTFITS = ("casual", "focus", "rainy", "cozy", "nightwear", "starlight")
PACK_EXPRESSIONS = ("happy", "affectionate", "shy", "sleepy", "pouty")
PACK_SCENE_VARIANTS = ("day", "sunset", "night", "rain")

DEFAULT_NEGATIVE = (
    "lowres, bad_anatomy, bad_hands, text, watermark, signature, logo, username, "
    "blurry, jpeg_artifacts, worst_quality, low_quality, nsfw, nude, explicit, "
    "multiple_views, split_screen, comic_panel"
)


def _attach_rembg_and_save(
    graph: dict,
    decoded_node: str,
    prefix: str,
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> None:
    img_src = [decoded_node, 0]
    if use_rembg:
        graph["8"] = {
            "class_type": "Image Rembg (Remove Background)",
            "inputs": {
                "images": [decoded_node, 0],
                "transparency": True,
                "model": rembg_model,
                "post_processing": True,
                "only_mask": False,
                "alpha_matting": False,
                "alpha_matting_foreground_threshold": 240,
                "alpha_matting_background_threshold": 10,
                "alpha_matting_erode_size": 6,
                "background_color": "none",
            },
        }
        img_src = ["8", 0]
    graph["9"] = {
        "class_type": "SaveImage",
        "inputs": {"images": img_src, "filename_prefix": prefix},
    }


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
    """Constrói grafo txt2img SDXL/Illustrious + RemBG para gerar sprite base transparente RGBA da waifu."""
    outfit = persona.outfits.get(outfit_key) or persona.outfits["casual"]
    outfit_tags = outfit.get("prompt", "stylish_anime_outfit")
    positive = (
        f"{persona.comfy_character_tags}, {outfit_tags}, "
        "cowboy_shot, standing, clean_edges, simple_background, solid_white_background, studio_lighting"
    )
    negative = f"{DEFAULT_NEGATIVE}, complex_background, scenery, cropped_head, out_of_frame, extra_limbs"
    actual_seed = int(seed if seed is not None else persona.seed)

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
    _attach_rembg_and_save(
        graph,
        decoded_node="7",
        prefix=f"IAWallpaper_avatar_{persona.id}_{outfit_key}",
        use_rembg=use_rembg,
        rembg_model=rembg_model,
    )
    return graph


def build_avatar_variant_img2img_workflow(
    checkpoint: str,
    persona: Persona,
    base_uploaded_image: str,
    outfit_key: str = "casual",
    expression_key: str | None = None,
    denoise: float | None = None,
    seed: int | None = None,
    steps: int = 20,
    cfg: float = 5.5,
    use_pag: bool = True,
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> dict:
    """Gera variante consistente (expressão ou novo traje) via img2img a partir da base da personagem.

    - Expressões (denoise ~0.44): trava pose, enquadramento, cabelo e roupa, variando a expressão facial.
    - Trajes (denoise ~0.68): preserva enquadramento e identidade visual enquanto troca vestimenta/acessórios.
    """
    outfit = persona.outfits.get(outfit_key) or persona.outfits["casual"]
    outfit_tags = outfit.get("prompt", "stylish_anime_outfit")
    expr_tags = EXPRESSION_PROMPTS.get(expression_key, "") if expression_key else ""
    eff_denoise = float(denoise if denoise is not None else (0.44 if expression_key else 0.75))

    parts = [persona.comfy_character_tags, f"({outfit_tags}:1.22)" if not expression_key else outfit_tags]
    if expr_tags:
        parts.append(f"({expr_tags}:1.25)")
    parts.append("cowboy_shot, standing, clean_edges, simple_background, solid_white_background, studio_lighting")
    positive = ", ".join(p for p in parts if p)
    extra_neg = ", beige_cardigan, cream_cardigan, school_uniform, necktie" if (not expression_key and outfit_key != "casual") else ""
    negative = f"{DEFAULT_NEGATIVE}, complex_background, scenery, cropped_head, out_of_frame, extra_limbs{extra_neg}"
    actual_seed = int(seed if seed is not None else persona.seed)

    model_src = ["1", 0]
    graph: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "10": {"class_type": "LoadImage", "inputs": {"image": base_uploaded_image}},
        "4": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}},
    }
    if use_pag:
        graph["5"] = {"class_type": "PerturbedAttentionGuidance", "inputs": {"model": ["1", 0], "scale": 2.6}}
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
            "denoise": eff_denoise,
        },
    }
    graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    suffix = f"{outfit_key}_{expression_key}" if expression_key else outfit_key
    _attach_rembg_and_save(
        graph,
        decoded_node="7",
        prefix=f"IAWallpaper_avatar_{persona.id}_{suffix}",
        use_rembg=use_rembg,
        rembg_model=rembg_model,
    )
    return graph
