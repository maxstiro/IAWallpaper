"""WORKFLOWS — Construtores de grafos ComfyUI SDXL/Illustrious + PAG + RemBG + img2img consistente."""

import random

from ..core.persona import Persona
from .presets import LoraSpec

SCENE_PRESETS: dict[str, dict[str, str]] = {
    "dark_sanctuary": {
        "label": "Santuário Abissal (Dungeon Squad)",
        "base": "dark_fantasy_anime_scenery, gothic_obsidian_altar_courtyard, glowing_crimson_and_violet_runes_carved_in_stone_floor, ancient_gothic_arches_and_flaming_braziers, ominous_cathedral_ruins_horizon, high_contrast_moody_lighting, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper",
    },
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
    "dark_sanctuary": (
        "dark_fantasy_anime_scenery, dungeon_squad_style, hand_painted_2.5d_rpg_background, full_bleed, borderless, "
        "(slight_high_angle_3/4_view:1.28), wide_open_cracked_obsidian_cobblestone_courtyard_filling_bottom_55_percent, "
        "subtle_glowing_crimson_and_violet_magic_runes_inlaid_in_floor_stones, ancient_gothic_stone_pillars_and_flickering_violet_braziers_on_far_edges, "
        "low_ornate_gothic_iron_balustrade_in_background, dramatic_abyssal_cathedral_spires_and_misty_dark_fantasy_sky_horizon, "
        "bold_high_contrast_shading, rich_obsidian_and_crimson_palette, masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper"
    ),
    "sky_sanctuary": (
        "anime_scenery, (tree_of_savior_style:1.30), (ragnarok_online_style:1.25), hand_painted_anime_background, full_bleed, borderless, "
        "(slight_high_angle_3/4_view:1.25), wide_open_sunlit_cobblestone_plaza_and_lush_green_meadow_filling_bottom_55_percent, "
        "scattered_wildflowers_and_mossy_garden_stones, cozy_carved_stone_lanterns_on_edges, "
        "blooming_trees_framing_left_and_right_borders, low_ornate_stone_balustrade_in_background, "
        "bright_open_scenic_sky_and_serene_mountain_valley_horizon, luminous_warm_painterly_art, "
        "masterpiece, best_quality, ultra_detailed, no_humans, wide_angle, wallpaper"
    ),
    "cyber_loft": (
        "anime_scenery, hand_painted_2.5d_rpg_background, full_bleed, borderless, (slight_high_angle_3/4_view:1.25), "
        "wide_open_wooden_rooftop_lounge_terrace_filling_bottom_55_percent, warm_potted_plants_and_lanterns_on_edges, "
        "glass_balcony_railing_midground, glowing_cyberpunk_cityscape_horizon_behind_railing, "
        "masterpiece, best_quality, no_humans, wide_angle, wallpaper"
    ),
    "sakura_hill": (
        "anime_scenery, (tree_of_savior_style:1.30), (ragnarok_online_style:1.25), hand_painted_2.5d_rpg_background, full_bleed, borderless, "
        "(slight_high_angle_3/4_view:1.25), wide_open_stone_shrine_courtyard_and_grass_meadow_filling_bottom_55_percent, "
        "blooming_cherry_blossom_trees_framing_sides, scattered_sakura_petals_on_ground, low_stone_railing, "
        "serene_coastal_town_and_sky_horizon, masterpiece, best_quality, no_humans, wide_angle, wallpaper"
    ),
}

QWEN_RELIGHT_INSTRUCTIONS: dict[str, str] = {
    "day": (
        "Keep the exact same stone courtyard floor, architecture, pillars, lanterns, braziers, balustrade, and 3/4 camera angle from <image1> completely unchanged, full-bleed edge to edge with no white border. "
        "Transform only the sky, lighting, and atmosphere into a dramatic sunlit late morning with crisp light breaking through clouds, vibrant high-contrast anime shading, and clear daylight across the stone courtyard."
    ),
    "sunset": (
        "Keep the exact same stone courtyard floor, architecture, pillars, lanterns, braziers, balustrade, and 3/4 camera angle from <image1> completely unchanged, full-bleed edge to edge with no white border. "
        "Transform only the sky, lighting, and atmosphere into a breathtaking high-contrast crimson-and-amber blood-sunset sky with dramatic violet clouds, fiery glowing braziers, and warm dramatic shadows across the courtyard stones."
    ),
    "night": (
        "Keep the exact same stone courtyard floor, architecture, pillars, lanterns, braziers, balustrade, and 3/4 camera angle from <image1> completely unchanged, full-bleed edge to edge with no white border. "
        "Transform only the sky, lighting, and atmosphere into a deep abyssal starry night with a luminous moon, vivid glowing magenta and amber light radiating from braziers and inlaid floor runes, and dramatic moonlight across the dark obsidian stones."
    ),
    "rain": (
        "Keep the exact same stone courtyard floor, architecture, pillars, lanterns, braziers, balustrade, and 3/4 camera angle from <image1> completely unchanged, full-bleed edge to edge with no white border. "
        "Transform only the weather and lighting into a moody rainy gothic storm with glossy wet reflective obsidian cobblestones, shallow rain puddles reflecting glowing crimson/violet flames and runes, falling rain mist, and dark stormy clouds."
    ),
}

WAN_CLIP_PROMPTS: dict[str, str] = {
    "idle": (
        "2D anime game character sprite animation on a pure solid white background, static locked camera, "
        "the stylish mature anime woman stands gracefully breathing gently, shifting her weight softly from hip to hip, "
        "blinking naturally with a warm alluring smile, her glowing hair and pleated mini-dress swaying softly in a gentle breeze, "
        "smooth 2D RPG game idle animation loop, clean solid white background."
    ),
    "walk": (
        "2D anime game character sprite animation on a pure solid white background, static locked camera, "
        "the stylish mature anime woman walks forward toward the viewer in a smooth rhythmic stepping cycle, alternating legs stepping naturally "
        "with gentle hip sway, arms swinging smoothly, glowing hair and pleated mini-dress flowing naturally with each step, "
        "smooth 2D RPG front walking loop animation, clean solid white background."
    ),
    "walk_side": (
        "2D anime RPG game character walk cycle animation on a pure solid white background, static locked camera, "
        "strictly 3/4 side view facing right, the stylish mature anime woman walks steadily to the right in place in a clear continuous "
        "walking stride cycle, left and right legs alternating forward and backward with knees bending naturally and high heels stepping, "
        "arms swinging smoothly in opposition to legs, glowing blue-purple hair and pleated mini-dress flowing back with forward momentum, "
        "head looking forward to the right, seamless looping 2D RPG side-profile walk animation, clean solid white background."
    ),
    "walk_back": (
        "2D anime RPG game character walk cycle animation on a pure solid white background, static locked camera, "
        "strictly 3/4 back view facing away from the viewer, the stylish mature anime woman walks away from the camera in a smooth continuous "
        "rhythmic walking stride cycle, left and right heels lifting and stepping alternately, hips swaying naturally, arms swinging gently, "
        "long glowing blue-purple hair and pleated mini-dress swaying smoothly from behind, seamless looping 2D RPG back walk animation, clean solid white background."
    ),
    "wave": (
        "2D anime game character sprite animation on a pure solid white background, static locked camera, "
        "the stylish mature anime woman cheerfully raises her hand and waves warmly at the viewer, shifting her weight gracefully, "
        "her glowing hair and pleated mini-dress swaying gently, blinking with a radiant happy smile, "
        "then smoothly returning to her standing pose, smooth 2D RPG emote animation, clean solid white background."
    ),
    "dance": (
        "2D anime game character sprite animation on a pure solid white background, static locked camera, "
        "the stylish mature anime woman performs a playful graceful Tree of Savior style rhythmic sway and gentle twirl, "
        "pleated mini-dress flaring and glowing hair flowing dynamically, arms opening gracefully with a joyful radiant smile, "
        "then returning smoothly to her standing pose, smooth 2D RPG emote animation, clean solid white background."
    ),
}

QWEN_TURNAROUND_INSTRUCTIONS: dict[str, str] = {
    "side": (
        "anime-style Illustration, rotate the exact same mature anime woman from <image1> into a full-body 3/4 side-right walking pose "
        "facing to the right and looking to the right, mid-stride stepping gracefully to the right with one leg forward and one leg back, "
        "arms swinging naturally at her sides. Keep her exact same face, glowing blue-purple wavy hair, star hairclip, off-shoulder cream knitted "
        "pleated mini-dress with waist ribbon, white thigh-high stockings with garters, white high heels, proportions, and anime art style "
        "completely unchanged. Full body with complete shoes visible, centered on a pure solid white background with no floor shadow."
    ),
    "back": (
        "anime-style Illustration, rotate the exact same mature anime woman from <image1> into a full-body 3/4 back view walking away from the viewer, "
        "facing away from the camera mid-stride with one heel stepping forward and one back. Show the back of her glowing blue-purple wavy hair, "
        "star hairclip, off-shoulder cream knitted pleated mini-dress, white thigh-high stockings, and white high heels, keeping her exact same outfit, "
        "colors, proportions, and anime art style completely unchanged. Full body with complete shoes visible, centered on a pure solid white background with no floor shadow."
    ),
}

WAN_DEFAULT_CLIPS = ("idle", "walk", "wave", "dance")

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
        f"{DEFAULT_NEGATIVE}, white_border, paper_border, frame, vignette_border, "
        "dark_tunnel, narrow_corridor, roof_blocking_sky, dark_pillars_in_center, "
        "bridge, stairs, cliff_edge_without_floor, top-down_90_degrees, "
        "1girl, 1boy, person, people, character, crowd, traveler, adventurer, "
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


def build_apose_rig_workflow(
    checkpoint: str,
    persona: Persona,
    outfit_key: str = "casual",
    loras: tuple[LoraSpec, ...] | list[LoraSpec] | None = None,
    seed: int | None = None,
    width: int = 832,
    height: int = 1216,
    steps: int = 26,
    cfg: float = 5.5,
    use_pag: bool = True,
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> dict:
    """Gera sprite frontal simétrico em A-pose (braços afastados do tronco, pernas separadas) para AutoRigger Spine2D.

    Usa o preset `(TOP)` do ComfyUI Studio (Checkpoint + LoRAs) + `isnet-anime` RemBG para gerar
    uma waifu madura, estilosa e nítida pronta para recorte automático nas 10 peças do esqueleto.
    """
    outfit = persona.outfits.get(outfit_key) or persona.outfits["casual"]
    outfit_tags = outfit.get("prompt", "stylish_fitted_off-shoulder_mini_dress, thighhighs, elegant_heels")
    char_tags = persona.comfy_character_tags.replace("upper_body", "full_body")
    positive = (
        f"1girl, solo, (mature_female:1.25), (curvaceous:1.18), (glamorous_anime_style:1.15), "
        f"tall_slender_waist, wide_hips, (front_view:1.35), (straight-on:1.30), (a-pose:1.35), "
        f"standing_straight, (arms_slightly_away_from_body:1.32), open_hands, (legs_slightly_apart:1.25), "
        f"symmetrical_standing_pose, (full_body:1.40), complete_shoes_visible, facing_viewer, looking_at_viewer, "
        f"warm_alluring_smile, stylish_fitted_off-shoulder_mini_dress, thighhighs, elegant_heels, "
        f"{char_tags}, {outfit_tags}, luminous_shading, crisp_outline, "
        f"(simple_background:1.30), (solid_white_background:1.40)"
    )
    negative = (
        f"{DEFAULT_NEGATIVE}, (chibi:1.6), (loli:1.6), (child:1.6), short_stature, flat_chest, "
        "hand_on_hip, crossed_arms, crossed_legs, arms_behind_back, hands_together, sitting, crouching, "
        "side_view, profile, back_view, turned_around, dynamic_angle, dutch_angle, "
        "upper_body, portrait, cowboy_shot, cropped_feet, cropped_legs, out_of_frame, "
        "complex_background, scenery, floor_shadow, cast_shadow, "
        "sprite_sheet, character_sheet, reference_sheet, multiple_views, turnaround, 2girls, multiple_girls"
    )
    actual_seed = int(seed if seed is not None else persona.seed + 1024)

    graph: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
    }
    model_src, clip_src = _apply_lora_chain(graph, ["1", 0], ["1", 1], loras, start_id=20)

    graph["2"] = {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": clip_src}}
    graph["3"] = {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_src}}
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
            "denoise": 1.0,
        },
    }
    graph["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}}
    _attach_rembg_and_save(
        graph,
        decoded_node="7",
        prefix=f"IAWallpaper_rig_{persona.id}_apose",
        use_rembg=use_rembg,
        rembg_model=rembg_model,
    )
    return graph


def build_qwen_turnaround_workflow(
    base_uploaded_sprite: str,
    direction: str = "side",
    persona_id: str = "mira",
    seed: int | None = None,
    steps: int = 12,
    cfg: float = 1.5,
    unet_name: str = "NoctQ_V3_turbo_int8_convrot.safetensors",
    clip_name: str = "qwen3vl_8b_int8_convrot.safetensors",
    vae_name: str = "qwen_image_2.1_vae_bf16.safetensors",
    anime_lora: str | None = r"qwen\qwen-anime-Illustration-1.safetensors",
    use_rembg: bool = True,
    rembg_model: str = "isnet-anime",
) -> dict:
    """Rotaciona a MESMA personagem (`rig_base.png`) para perfil 3/4 direita (`side`) ou costas (`back`) via Qwen Image 2.1."""
    instruction = QWEN_TURNAROUND_INSTRUCTIONS.get(direction, QWEN_TURNAROUND_INSTRUCTIONS["side"])
    neg = (
        "photorealistic, real photo, facing_viewer, front_view, symmetrical_front, different outfit, different hair color, "
        "cropped_feet, cropped_head, floor_shadow, scenery, complex_background, 2girls, turnaround_sheet, multiple_views, text, watermark"
    )
    actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))

    graph: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": unet_name, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "10": {"class_type": "LoadImage", "inputs": {"image": base_uploaded_sprite}},
    }
    model_src = ["1", 0]
    if anime_lora:
        graph["11"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": anime_lora, "strength_model": 0.72},
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
    _attach_rembg_and_save(
        graph,
        decoded_node="6",
        prefix=f"IAWallpaper_turn_{persona_id}_{direction}",
        use_rembg=use_rembg,
        rembg_model=rembg_model,
    )
    return graph


def build_wan_sprite_clip_workflow(
    base_uploaded_image: str,
    action_key: str = "idle",
    persona_id: str = "mira",
    width: int = 416,
    height: int = 640,
    length: int = 25,
    fps: float = 12.0,
    seed: int | None = None,
    steps: int = 6,
    high_unet: str = "Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors",
    low_unet: str = "Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors",
    clip_name: str = "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    vae_name: str = "wan_2.1_vae.safetensors",
    rembg_model: str = "isnet-anime",
) -> dict:
    """Gera clipe RGBA animado em loop infinito perfeito via Wan 2.2 FirstLastFrameToVideo + isnet-anime RemBG.

    Trava `start_image == end_image` para retorno matemático perfeito ao frame inicial (loop sem corte!),
    eliminando totalmente o aspecto rígido de marionete 2D e entregando fluidez estilo Tree of Savior / RO.
    """
    pos_text = WAN_CLIP_PROMPTS.get(action_key, WAN_CLIP_PROMPTS["idle"])
    neg_text = (
        "camera movement, zoom, pan, background scenery, floor shadows, blurry, distorted limbs, "
        "extra arms, morphing clothes, low quality, photorealistic, text, watermark"
    )
    actual_seed = int(seed if seed is not None else random.randint(1, 2**31 - 1))
    half_steps = max(2, int(steps) // 2)

    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": high_unet, "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": low_unet, "weight_dtype": "fp8_e4m3fn"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 5.0}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": pos_text}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg_text}},
        "9": {"class_type": "LoadImage", "inputs": {"image": base_uploaded_image}},
        "10": {
            "class_type": "WanFirstLastFrameToVideo",
            "inputs": {
                "positive": ["7", 0],
                "negative": ["8", 0],
                "vae": ["4", 0],
                "width": int(width),
                "height": int(height),
                "length": int(length),
                "batch_size": 1,
                "start_image": ["9", 0],
                "end_image": ["9", 0],
            },
        },
        "11": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["5", 0],
                "add_noise": "enable",
                "noise_seed": actual_seed,
                "steps": int(steps),
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["10", 2],
                "start_at_step": 0,
                "end_at_step": half_steps,
                "return_with_leftover_noise": "enable",
            },
        },
        "12": {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["6", 0],
                "add_noise": "disable",
                "noise_seed": actual_seed,
                "steps": int(steps),
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["10", 0],
                "negative": ["10", 1],
                "latent_image": ["11", 0],
                "start_at_step": half_steps,
                "end_at_step": int(steps),
                "return_with_leftover_noise": "disable",
            },
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {
            "class_type": "Image Rembg (Remove Background)",
            "inputs": {
                "images": ["13", 0],
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
        },
        "15": {
            "class_type": "SaveAnimatedWEBP",
            "inputs": {
                "images": ["14", 0],
                "filename_prefix": f"IAWallpaper_clip_{persona_id}_{action_key}",
                "fps": float(fps),
                "lossless": False,
                "quality": 92,
                "method": "default",
            },
        },
    }
