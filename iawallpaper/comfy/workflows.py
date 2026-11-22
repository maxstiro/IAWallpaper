"""WORKFLOWS — Construtores de grafos ComfyUI SDXL/Illustrious + PAG + RemBG + img2img consistente."""

import random

from ..core.persona import Persona
from .presets import LoraSpec

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

WORLD_SPRITE_ACTIONS: dict[str, str] = {
    "idle": "standing_elegantly, alluring_confident_smile, hand_on_hip, relaxed_glamorous_pose, facing_slightly_right",
    "walk1": "walking_gracefully, mid_stride, stepping_forward, flowing_hair, alluring_smile, facing_right",
    "walk2": "walking_pose, opposite_step, gentle_hip_sway, hair_swaying, confident_gaze, facing_right",
    "sit": "sitting_elegantly, legs_crossed, alluring_relaxed_smile, stylish_sitting_pose",
    "happy": "joyful_radiant_smile, waving_gently, playful_wink, sparkles_in_eyes, expressive_pose",
    "sleep": "sleepy_relaxed_sitting, closed_eyes, peaceful_drowsy_smile, leaning_softly",
}

DIORAMA_SCENE_PRESETS: dict[str, str] = {
    "sky_sanctuary": (
        "anime_scenery, tree_of_savior_style, ragnarok_online_style, hand_painted_2.5d_rpg_background, "
        "wide_flat_open_cobblestone_terrace_floor_filling_bottom_40_percent, elegant_stone_balustrade_midground, "
        "lush_trees_and_flowerbeds_on_edges, serene_lake_and_distant_observatory_valley_horizon, "
        "eye_level_slight_high_angle_stage_view, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper"
    ),
    "cyber_loft": (
        "anime_scenery, 2.5d_rpg_stylish_rooftop_lounge, hand_painted_anime_background, "
        "wide_flat_wooden_deck_floor_filling_bottom_40_percent, glass_railing_midground, "
        "neon_cyberpunk_cityscape_horizon, potted_plants_on_edges, masterpiece, best_quality, no_humans, wide_angle, wallpaper"
    ),
    "sakura_hill": (
        "anime_scenery, tree_of_savior_style, ragnarok_online_style, hand_painted_2.5d_rpg_background, "
        "wide_flat_stone_shrine_courtyard_filling_bottom_40_percent, blooming_cherry_blossom_trees_framing_sides, "
        "low_stone_railing, coastal_town_below, masterpiece, best_quality, no_humans, wide_angle, wallpaper"
    ),
}

QWEN_RELIGHT_INSTRUCTIONS: dict[str, str] = {
    "sunset": (
        "Keep the exact same architecture, stone balustrade, flat cobblestone terrace floor, trees, and camera angle from <image1> completely unchanged. "
        "Transform only the sky, lighting, and atmosphere into a breathtaking warm golden-hour sunset with rich amber and violet clouds, warm golden sunlight casting long soft shadows across the terrace stones, and glowing sunset reflections."
    ),
    "night": (
        "Keep the exact same architecture, stone balustrade, flat cobblestone terrace floor, trees, and camera angle from <image1> completely unchanged. "
        "Transform only the sky, lighting, and atmosphere into a serene deep starry night with a glowing crescent moon, warm amber lanterns glowing softly along the terrace railing, cool moonlight illuminating the cobblestones, and twinkling distant city lights."
    ),
    "rain": (
        "Keep the exact same architecture, stone balustrade, flat cobblestone terrace floor, trees, and camera angle from <image1> completely unchanged. "
        "Transform only the weather and lighting into a cozy overcast rainy afternoon with wet glossy reflective cobblestones, shallow rain puddles reflecting soft lantern light, gentle falling rain mist, and atmospheric cool blue-grey sky."
    ),
}

DEFAULT_NEGATIVE = (
    "lowres, bad_anatomy, bad_hands, text, watermark, signature, logo, username, "
    "blurry, jpeg_artifacts, worst_quality, low_quality, nsfw, nude, explicit, "
    "multiple_views, split_screen, comic_panel"
)


def _apply_lora_chain(
    graph: dict,
    model_src: list,
    clip_src: list,
    loras: tuple[LoraSpec, ...] | list[LoraSpec] | None,
    start_id: int = 20,
) -> tuple[list, list]:
    """Encadeia nós LoraLoader a partir de um preset do ComfyUI Studio (read-only)."""
    if not loras:
        return model_src, clip_src
    cur_m, cur_c = model_src, clip_src
    nid = start_id
    for lr in loras:
        node_key = str(nid)
        graph[node_key] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": cur_m,
                "clip": cur_c,
                "lora_name": lr.lora,
                "strength_model": float(lr.strength_model),
                "strength_clip": float(lr.strength_clip),
            },
        }
        cur_m = [node_key, 0]
        cur_c = [node_key, 1]
        nid += 1
    return cur_m, cur_c


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


def build_diorama_scene_workflow(
    checkpoint: str,
    scene_id: str = "sky_sanctuary",
    variant: str = "day",
    seed: int | None = None,
    width: int = 1344,
    height: int = 768,
    steps: int = 20,
    cfg: float = 5.5,
    use_pag: bool = True,
) -> dict:
    """Constrói grafo 2.5D estilo Tree of Savior / Ragnarok Online com chão caminhável amplo."""
    base = DIORAMA_SCENE_PRESETS.get(scene_id, DIORAMA_SCENE_PRESETS["sky_sanctuary"])
    time_tags = TIME_VARIANT_PROMPTS.get(variant, TIME_VARIANT_PROMPTS["day"])
    positive = f"{base}, {time_tags}"
    negative = (
        f"{DEFAULT_NEGATIVE}, 1girl, 1boy, person, people, character, crowd, traveler, adventurer, "
        "cloaked_figure, hooded_figure, npc, silhouette, statue_person, ui, hud, minimap, health_bar"
    )
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
        "inputs": {"images": ["7", 0], "filename_prefix": f"IAWallpaper_diorama_{scene_id}_{variant}"},
    }
    return graph


def build_qwen_relight_scene_workflow(
    base_uploaded_scene: str,
    variant: str = "sunset",
    seed: int | None = None,
    steps: int = 10,
    cfg: float = 1.5,
    unet_name: str = "NoctQ_V3_turbo_int8_convrot.safetensors",
    clip_name: str = "qwen3vl_8b_int8_convrot.safetensors",
    vae_name: str = "qwen_image_2.1_vae_bf16.safetensors",
    anime_lora: str | None = r"qwen\qwen-anime-Illustration-1.safetensors",
) -> dict:
    """Reilumina a MESMA arquitetura/cenário base para sunset/night/rain via Qwen Image 2.1 Edit (consistência 1:1)."""
    instruction = QWEN_RELIGHT_INSTRUCTIONS.get(variant, QWEN_RELIGHT_INSTRUCTIONS["sunset"])
    if anime_lora:
        instruction = f"anime-style Illustration, {instruction}"
    neg = "photorealistic, real photo, different architecture, moved railing, people, 1girl, 1boy, text, watermark, blurry"
    actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))

    graph: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "10": {"class_type": "LoadImage", "inputs": {"image": base_uploaded_scene}},
    }
    model_src = ["1", 0]
    if anime_lora:
        graph["11"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": anime_lora, "strength_model": 0.65},
        }
        model_src = ["11", 0]

    graph["4"] = {
        "class_type": "TextEncodeQwenImage21",
        "inputs": {
            "clip": ["2", 0],
            "vae": ["3", 0],
            "prompt": instruction,
            "negative_prompt": neg,
            "resolution": 1024,
            "image_1": ["10", 0],
        },
    }
    graph["5"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
            "seed": actual_seed,
            "steps": int(steps),
            "cfg": float(cfg),
            "sampler_name": "euler",
            "scheduler": "simple",
            "positive": ["4", 0],
            "negative": ["4", 1],
            "latent_image": ["4", 2],
            "denoise": 1.0,
        },
    }
    graph["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["3", 0]}}
    graph["7"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["6", 0], "filename_prefix": f"IAWallpaper_diorama_relight_{variant}"},
    }
    return graph


def build_world_sprite_workflow(
    checkpoint: str,
    persona: Persona,
    action_key: str = "idle",
    outfit_key: str = "casual",
    loras: tuple[LoraSpec, ...] | list[LoraSpec] | None = None,
    base_uploaded_image: str | None = None,
    denoise: float | None = None,
    seed: int | None = None,
    width: int = 768,
    height: int = 1216,
    steps: int = 24,
    cfg: float = 5.5,
    use_pag: bool = True,
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> dict:
    """Gera sprite full-body de waifu madura, estilosa e atraente usando um preset (TOP) do ComfyUI + isnet-anime."""
    outfit = persona.outfits.get(outfit_key) or persona.outfits["casual"]
    outfit_tags = outfit.get("prompt", "stylish_fitted_off-shoulder_knit_dress, thighhighs, high_heels")
    action_tags = WORLD_SPRITE_ACTIONS.get(action_key, WORLD_SPRITE_ACTIONS["idle"])
    char_tags = persona.comfy_character_tags.replace("upper_body", "full_body")
    positive = (
        f"1girl, solo, (mature_female:1.25), (curvaceous:1.18), (glamorous_anime_style:1.15), "
        f"tall_slender_waist, wide_hips, ({action_tags}:1.22), (full_body:1.35), complete_shoes_visible, "
        f"stylish_fitted_off-shoulder_dress, thighhighs, elegant_heels, "
        f"{char_tags}, {outfit_tags}, luminous_shading, crisp_outline, simple_background, solid_white_background"
    )
    negative = (
        f"{DEFAULT_NEGATIVE}, (chibi:1.5), (loli:1.6), (child:1.6), short_stature, flat_chest, "
        "upper_body, portrait, cowboy_shot, cropped_feet, cropped_legs, out_of_frame, "
        "complex_background, scenery, floor_shadow, sprite_sheet, character_sheet, reference_sheet, 2girls, multiple_girls"
    )
    actual_seed = int(seed if seed is not None else persona.seed + 77)
    eff_denoise = float(denoise if denoise is not None else (0.52 if base_uploaded_image else 1.0))

    graph: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
    }
    model_src, clip_src = _apply_lora_chain(graph, ["1", 0], ["1", 1], loras, start_id=20)

    graph["2"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": clip_src}}
    graph["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_src}}

    if base_uploaded_image:
        graph["10"] = {"class_type": "LoadImage", "inputs": {"image": base_uploaded_image}}
        graph["4"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}}
    else:
        graph["4"] = {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height), "batch_size": 1}}

    if use_pag:
        graph["5"] = {"class_type": "PerturbedAttentionGuidance", "inputs": {"model": model_src, "scale": 2.8}}
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
    _attach_rembg_and_save(
        graph,
        decoded_node="7",
        prefix=f"IAWallpaper_sprite_{persona.id}_{action_key}",
        use_rembg=use_rembg,
        rembg_model=rembg_model,
    )
    return graph
