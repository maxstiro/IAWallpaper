"""CHARACTER PIPELINE — Fluxo padronizado e reutilizável para gerar Personagens Novas, Poses-Âncora, Retratos, Outfits 1:1 e Baking Wan 2.2 em 3 Tiers.

Regra sagrada: consome ESTRITAMENTE a API HTTP read-only do ComfyUI local (`127.0.0.1:8188`).
Nunca altera nenhum arquivo dentro de `D:\\IA\\ComfyUI`.
"""

from dataclasses import dataclass
import io
import json
from pathlib import Path
import shutil
import threading
import time
from typing import Callable

from PIL import Image

from ..log import log
from .bridge import ComfyBridge


@dataclass(frozen=True)
class AnchorSpec:
    key: str
    prompt: str
    neg: str
    seed_offset: int


@dataclass(frozen=True)
class ClipJobSpec:
    key: str
    tier: int
    start_anchor: str
    end_anchor: str
    frames: int
    fps: float
    stride_ratio: float
    prompt: str
    seed_offset: int
    loop: bool = True


# Poses-Âncora geradas 1 única vez por personagem/outfit via Qwen Image 2.1 Edit (~20s cada)
ANCHOR_SPECS: dict[str, AnchorSpec] = {
    "walk_SE": AnchorSpec(
        key="walk_SE",
        prompt=(
            "Keep this exact curvy shortstack character, exact face, exact eyes, exact hair, exact ears, exact skin tone, "
            "exact underwear/outfit, exact ~4.1 head proportions and crisp 2D painted Rapscallion Tree of Savior art style. "
            "Repose her into a clean mid-stride WALKING pose angled three-quarter front-right (facing down-right toward viewer): "
            "front right leg stepping forward, back left leg pushing off behind with heel lifted, arms swinging naturally at her sides "
            "(NO hand on hip!), wavy hair streaming slightly behind her, full body from head to bare feet, pure solid flat white background, zero floor shadow."
        ),
        neg="hand on hip, standing still, static idle, crossed legs, cropped feet, shadow, scenery, 2girls, multiple views",
        seed_offset=101,
    ),
    "walk_L": AnchorSpec(
        key="walk_L",
        prompt=(
            "Turn this exact curvy shortstack character into a clean RIGHT SIDE PROFILE (facing right, 90 degrees) mid-stride WALKING pose: "
            "preserving her exact face in profile, exact hair, exact elf ears, exact skin tone, exact underwear/outfit, exact ~4.1 head proportions "
            "and crisp 2D painted art style. One leg extended forward and the other leg trailing behind in mid-step, arms swinging naturally, "
            "hair flowing backward, full body head to feet on pure solid flat white background, zero floor shadow."
        ),
        neg="front view, facing viewer, hand on hip, standing still, cropped feet, shadow, scenery, 2girls",
        seed_offset=102,
    ),
    "walk_NE": AnchorSpec(
        key="walk_NE",
        prompt=(
            "Turn this exact curvy shortstack character into a clean three-quarter BACK-RIGHT (facing away and to the right, 135 degrees) "
            "mid-stride WALKING pose: preserving her exact long flowing hair down her back, exact pointed ears, exact skin tone, exact underwear/outfit, "
            "exact ~4.1 head proportions and crisp 2D painted art style. Walking away diagonally toward the top-right with one leg forward and back heel lifted, "
            "arms swinging naturally, full body head to bare feet on pure solid flat white background, zero floor shadow."
        ),
        neg="front view, facing viewer, looking at camera, hand on hip, cropped feet, shadow, scenery, 2girls",
        seed_offset=103,
    ),
    "walk_N": AnchorSpec(
        key="walk_N",
        prompt=(
            "Turn this exact curvy shortstack character 180 degrees to show a clean FULL BACK VIEW (facing directly away from viewer, walking forward away) "
            "in a natural mid-stride WALKING pose: preserving her exact lush wavy hair flowing down her upper back, pointed ears visible on sides, "
            "exact skin tone, curvy hips and glutes, exact underwear/outfit back straps, exact ~4.1 head proportions and crisp 2D painted art style. "
            "One heel lifted mid-step, arms swinging slightly at sides, full body head to bare feet on pure solid flat white background, zero floor shadow."
        ),
        neg="front view, face visible, eyes visible, looking back, hand on hip, cropped feet, shadow, scenery, 2girls",
        seed_offset=104,
    ),
    "walk_S": AnchorSpec(
        key="walk_S",
        prompt=(
            "Keep this exact curvy shortstack character, exact face, hair, ears, skin tone, outfit and ~4.1 head proportions. "
            "Repose her into a clean straight FRONT-FACING (walking directly toward viewer) mid-stride WALKING pose: "
            "one knee stepping forward toward camera, other foot pushing behind, arms swinging gently at sides (NO hand on hip), "
            "warm cheerful smile, full body head to bare feet on pure solid flat white background, zero floor shadow."
        ),
        neg="hand on hip, static idle, side view, back view, cropped feet, shadow, scenery, 2girls",
        seed_offset=105,
    ),
    "sit_floor_SE": AnchorSpec(
        key="sit_floor_SE",
        prompt=(
            "Keep this exact curvy shortstack character, exact face, hair, ears, skin tone, outfit and ~4.1 head proportions. "
            "Repose her sitting comfortably on the ground in a cute relaxed three-quarter pose (legs tucked neatly to the side, "
            "one hand resting lightly near her lap/floor, warm relaxed smile, full body visible), pure solid flat white background, zero floor shadow."
        ),
        neg="standing, chair, bench, sofa, cropped legs, shadow, scenery, 2girls",
        seed_offset=106,
    ),
    "sit_chair_SE": AnchorSpec(
        key="sit_chair_SE",
        prompt=(
            "Keep this exact curvy shortstack character, exact face, hair, ears, skin tone, outfit and ~4.1 head proportions. "
            "Repose her in a cute seated pose as if perched on a stone ledge or bench (three-quarter front-right view, knees bent 90 degrees "
            "with legs hanging down cleanly, hands resting lightly on her thighs/edge, cheerful smile, NO visible chair drawn), "
            "pure solid flat white background, zero floor shadow."
        ),
        neg="standing, wooden chair, sofa, bench drawn, cropped feet, shadow, scenery, 2girls",
        seed_offset=107,
    ),
    "lie_SE": AnchorSpec(
        key="lie_SE",
        prompt=(
            "Keep this exact curvy shortstack character, exact face, hair, ears, skin tone, outfit and ~4.1 head proportions. "
            "Repose her lying down peacefully curled on her side as if napping softly with gently closed eyes and a serene sleepy smile, "
            "full body visible, pure solid flat white background, zero floor shadow."
        ),
        neg="standing, open eyes, bed, pillow, blanket, shadow, scenery, 2girls",
        seed_offset=108,
    ),
}

# Catálogo enxuto em 3 Tiers (apenas 18 clipes -> 8 direções + ~20 ações/transições com reversão temporal!)
TIER_CLIP_CATALOG: tuple[ClipJobSpec, ...] = (
    # ── Tier 0: Essencial (~6-8 min -> personagem viva e andando em 8 direções aproximadas!) ──
    ClipJobSpec(
        key="idle_SE", tier=0, start_anchor="master", end_anchor="master",
        frames=41, fps=16.0, stride_ratio=0.0, seed_offset=201,
        prompt=(
            "2D fantasy RPG character idle animation in Tree of Savior and Dungeon Squad style on pure solid white background, "
            "locked static camera. The character breathes smoothly in place with natural chest rise, subtle hip weight shift, "
            "charming blinking eyes and warm smile, wavy hair swaying gently in the breeze, seamless infinite loop."
        ),
    ),
    ClipJobSpec(
        key="walk_SE", tier=0, start_anchor="walk_SE", end_anchor="walk_SE",
        frames=25, fps=16.0, stride_ratio=0.84, seed_offset=202,
        prompt=(
            "Continuous smooth 2D fantasy RPG WALK CYCLE in three-quarter front-right view on pure solid white background, "
            "locked static camera. Keep walking continuously at steady rhythm with ZERO pause or idle pose: alternating full leg strides "
            "with feet lifting and planting cleanly, natural hip sway, swinging arms, hair flowing gently behind, crisp 2D lineart, seamless walk loop."
        ),
    ),
    ClipJobSpec(
        key="walk_NE", tier=0, start_anchor="walk_NE", end_anchor="walk_NE",
        frames=25, fps=16.0, stride_ratio=0.78, seed_offset=203,
        prompt=(
            "Continuous smooth 2D fantasy RPG WALK CYCLE in three-quarter BACK-RIGHT view (walking away diagonally) on pure solid white background, "
            "locked static camera. Keep walking continuously at steady rhythm with alternating leg strides, back heels lifting cleanly, "
            "natural hip sway, flowing hair down her back bouncing gently, never turning face to camera, seamless walk loop."
        ),
    ),
    ClipJobSpec(
        key="wave_SE", tier=0, start_anchor="master", end_anchor="master",
        frames=41, fps=16.0, stride_ratio=0.0, seed_offset=204,
        prompt=(
            "2D fantasy RPG character joyful greeting wave animation on pure solid white background, locked static camera. "
            "The character raises her hand cheerfully to wave at the viewer with a radiant happy beaming smile and playful head tilt, "
            "hair swaying softly, then smoothly returns to starting pose, seamless loop."
        ),
    ),
    # ── Tier 1: 8 Direções 100% Reais + Todas as Posturas (em background) ──
    ClipJobSpec(
        key="walk_L", tier=1, start_anchor="walk_L", end_anchor="walk_L",
        frames=25, fps=16.0, stride_ratio=0.92, seed_offset=211,
        prompt=(
            "Continuous smooth 2D fantasy RPG WALK CYCLE in pure RIGHT SIDE PROFILE view on pure solid white background, "
            "locked static camera. Steady rhythmic side-view walking stride with legs passing cleanly front and back, feet lifting and planting, "
            "arms swinging naturally, hair streaming slightly backward, crisp 2D art style, seamless walk loop."
        ),
    ),
    ClipJobSpec(
        key="walk_N", tier=1, start_anchor="walk_N", end_anchor="walk_N",
        frames=25, fps=16.0, stride_ratio=0.72, seed_offset=212,
        prompt=(
            "Continuous smooth 2D fantasy RPG WALK CYCLE in FULL BACK VIEW (walking directly away from viewer) on pure solid white background, "
            "locked static camera. Steady rhythmic back-view walking steps with alternating heels lifting, cute hip sway, "
            "long wavy hair bouncing smoothly down her back, never turning around, crisp 2D art style, seamless walk loop."
        ),
    ),
    ClipJobSpec(
        key="walk_S", tier=1, start_anchor="walk_S", end_anchor="walk_S",
        frames=25, fps=16.0, stride_ratio=0.72, seed_offset=213,
        prompt=(
            "Continuous smooth 2D fantasy RPG WALK CYCLE in straight FRONT VIEW (walking toward viewer) on pure solid white background, "
            "locked static camera. Steady rhythmic forward steps with alternating knees stepping forward, cute hip sway, "
            "arms swinging lightly, cheerful smile, hair bouncing softly, seamless walk loop."
        ),
    ),
    ClipJobSpec(
        key="sit_floor_SE", tier=1, start_anchor="sit_floor_SE", end_anchor="sit_floor_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=214,
        prompt=(
            "2D fantasy RPG character seated on ground idle animation on pure solid white background, locked static camera. "
            "Gentle relaxed breathing, blinking eyes, slight head sway and soft breeze moving her hair while sitting comfortably, seamless loop."
        ),
    ),
    ClipJobSpec(
        key="sit_chair_SE", tier=1, start_anchor="sit_chair_SE", end_anchor="sit_chair_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=215,
        prompt=(
            "2D fantasy RPG character seated on bench idle animation on pure solid white background, locked static camera. "
            "Gentle breathing, cute subtle swinging feet, blinking eyes, hair swaying lightly in breeze, seamless loop."
        ),
    ),
    ClipJobSpec(
        key="lie_SE", tier=1, start_anchor="lie_SE", end_anchor="lie_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=216,
        prompt=(
            "2D fantasy RPG character lying down sleeping animation on pure solid white background, locked static camera. "
            "Slow peaceful breathing with soft chest rise and fall, closed eyes, serene expression, gentle hair motion, seamless loop."
        ),
    ),
    ClipJobSpec(
        key="interact_SE", tier=1, start_anchor="master", end_anchor="master",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=217,
        prompt=(
            "2D fantasy RPG character curious interaction gesture on pure solid white background, locked static camera. "
            "The character leans slightly forward reaching one hand gently out to inspect or touch something with curious sparkling eyes "
            "and cute smile, then smoothly returns to start pose, seamless loop."
        ),
    ),
    # ── Tier 2: Transições Reversíveis + Corrida Dedicada + Giro (em background) ──
    ClipJobSpec(
        key="trans_sit_floor", tier=2, start_anchor="master", end_anchor="sit_floor_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=221, loop=False,
        prompt=(
            "Smooth 2D fantasy RPG character transition animation on pure solid white background, locked static camera: "
            "the character gracefully bends her knees and sits down smoothly onto the floor into the final seated pose, natural hair follow-through."
        ),
    ),
    ClipJobSpec(
        key="trans_sit_chair", tier=2, start_anchor="master", end_anchor="sit_chair_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=222, loop=False,
        prompt=(
            "Smooth 2D fantasy RPG character transition animation on pure solid white background, locked static camera: "
            "the character gracefully lowers herself into the seated bench pose with knees bent neatly, smooth organic motion."
        ),
    ),
    ClipJobSpec(
        key="trans_lie", tier=2, start_anchor="sit_floor_SE", end_anchor="lie_SE",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=223, loop=False,
        prompt=(
            "Smooth 2D fantasy RPG character transition animation on pure solid white background, locked static camera: "
            "from sitting on the floor, the character curls gently down onto her side to lie down peacefully and close her eyes."
        ),
    ),
    ClipJobSpec(
        key="run_SE", tier=2, start_anchor="walk_SE", end_anchor="walk_SE",
        frames=25, fps=16.0, stride_ratio=1.05, seed_offset=224,
        prompt=(
            "Energetic smooth 2D fantasy RPG RUNNING cycle in three-quarter front-right view on pure solid white background, locked static camera. "
            "Leaning slightly forward in lively joyful run, high knee lift, energetic arm pump, long hair flying dynamically behind, seamless run loop."
        ),
    ),
    ClipJobSpec(
        key="run_L", tier=2, start_anchor="walk_L", end_anchor="walk_L",
        frames=25, fps=16.0, stride_ratio=1.12, seed_offset=225,
        prompt=(
            "Energetic smooth 2D fantasy RPG RUNNING cycle in pure RIGHT SIDE PROFILE view on pure solid white background, locked static camera. "
            "Lively energetic run with wide stride, leaning forward, arms pumping, hair streaming straight back, seamless run loop."
        ),
    ),
    ClipJobSpec(
        key="run_NE", tier=2, start_anchor="walk_NE", end_anchor="walk_NE",
        frames=25, fps=16.0, stride_ratio=0.98, seed_offset=226,
        prompt=(
            "Energetic smooth 2D fantasy RPG RUNNING cycle in three-quarter BACK-RIGHT view (running away) on pure solid white background, "
            "locked static camera. Energetic running stride moving away diagonally, hair flying dynamically, seamless run loop."
        ),
    ),
    ClipJobSpec(
        key="spin_SE", tier=2, start_anchor="master", end_anchor="master",
        frames=25, fps=16.0, stride_ratio=0.0, seed_offset=227,
        prompt=(
            "Playful smooth 2D fantasy RPG character 360-degree twirl spin animation on pure solid white background, locked static camera. "
            "The character performs one graceful joyful spin twirl with hair flaring outward beautifully and lands back smiling in start pose, seamless loop."
        ),
    ),
)

PORTRAIT_EXPRESSIONS: dict[str, str] = {
    "happy":        "joyful radiant open-mouth beaming smile, sparkling bright eyes, cheerful energy",
    "affectionate": "warm tender loving smile, soft gentle eyes, rosy glowing cheek blush, sweet expression",
    "shy":          "bashful embarrassed blush across cheeks and nose, cute shy sidelong glance, tiny nervous smile",
    "pouty":        "cute puffed cheeks tsundere pout, furrowed brows, playful annoyed expression",
    "sleepy":       "drowsy half-closed heavy eyelids, tiny cute yawn, soft sleepy cozy expression",
    "focused":      "determined attentive expression, slight confident smirk, sharp focused gaze",
}


def build_wan_transition_workflow(
    start_uploaded_image: str,
    end_uploaded_image: str,
    clip_key: str,
    prompt: str,
    character_id: str = "arya",
    width: int = 448,
    height: int = 640,
    length: int = 25,
    fps: float = 16.0,
    seed: int = 55101,
    steps: int = 6,
    high_unet: str = "Wan2.2_Remix_NSFW_i2v_14b_high_lighting_fp8_e4m3fn_v3.0.safetensors",
    low_unet: str = "Wan2.2_Remix_NSFW_i2v_14b_low_lighting_fp8_e4m3fn_v3.0.safetensors",
    clip_name: str = "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
    vae_name: str = "wan_2.1_vae.safetensors",
    rembg_model: str = "isnet-anime",
) -> dict:
    """Constrói grafo Wan 2.2 FirstLastFrameToVideo suportando loops (`start == end`) E transições (`start != end`)!"""
    neg = (
        "camera movement, zoom, pan, tilt, background scenery, floor shadow, blurry, distorted limbs, "
        "extra arms, extra legs, extra heads, morphing clothes, 3d render, photorealistic, text, watermark"
    )
    half_steps = max(2, int(steps) // 2)
    same = (start_uploaded_image == end_uploaded_image)
    graph: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": high_unet, "weight_dtype": "fp8_e4m3fn"}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": low_unet, "weight_dtype": "fp8_e4m3fn"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": clip_name, "type": "wan", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": vae_name}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 5.0}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": prompt}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg}},
        "9": {"class_type": "LoadImage", "inputs": {"image": start_uploaded_image}},
    }
    end_ref = ["9", 0]
    if not same:
        graph["9b"] = {"class_type": "LoadImage", "inputs": {"image": end_uploaded_image}}
        end_ref = ["9b", 0]

    graph["10"] = {
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
            "end_image": end_ref,
        },
    }
    graph["11"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["5", 0],
            "add_noise": "enable",
            "noise_seed": int(seed),
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
    }
    graph["12"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "model": ["6", 0],
            "add_noise": "disable",
            "noise_seed": int(seed),
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
    }
    graph["13"] = {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}}
    graph["14"] = {
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
    }
    graph["15"] = {
        "class_type": "SaveAnimatedWEBP",
        "inputs": {
            "images": ["14", 0],
            "filename_prefix": f"IAW_char_{character_id}_{clip_key}",
            "fps": float(fps),
            "lossless": False,
            "quality": 92,
            "method": "default",
        },
    }
    return graph


def build_qwen_anchor_workflow(
    base_uploaded_image: str,
    prompt: str,
    neg: str,
    prefix: str,
    seed: int = 77101,
    steps: int = 10,
    cfg: float = 1.4,
    use_rembg: bool = True,
) -> dict:
    """Gera uma pose-âncora ou retrato fiel 1:1 a partir da arte mestra via Qwen Image 2.1 Edit."""
    graph: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "NoctQ_V3_turbo_int8_convrot.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_8b_int8_convrot.safetensors", "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
        "10": {"class_type": "LoadImage", "inputs": {"image": base_uploaded_image}},
        "11": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": r"qwen\qwen-anime-Illustration-1.safetensors", "strength_model": 0.65}},
        "4": {
            "class_type": "TextEncodeQwenImage21",
            "inputs": {
                "clip": ["2", 0],
                "vae": ["3", 0],
                "prompt": prompt,
                "negative_prompt": neg,
                "resolution": 1024,
                "image_1": ["10", 0],
            },
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["11", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["4", 0],
                "negative": ["4", 1],
                "latent_image": ["4", 2],
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["3", 0]}},
    }
    if use_rembg:
        graph["7"] = {
            "class_type": "Image Rembg (Remove Background)",
            "inputs": {
                "images": ["6", 0],
                "transparency": True,
                "model": "isnet-anime",
                "post_processing": True,
                "only_mask": False,
                "alpha_matting": False,
                "alpha_matting_foreground_threshold": 240,
                "alpha_matting_background_threshold": 10,
                "alpha_matting_erode_size": 6,
                "background_color": "none",
            },
        }
        graph["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}}
    else:
        graph["8"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": prefix}}
    return graph


class CharacterPipeline:
    """Orquestrador reutilizável para inicializar personagens, gerar âncoras Qwen 2.1, outfits 1:1 e assar Tiers Wan 2.2."""

    def __init__(self, bridge: ComfyBridge):
        self.bridge = bridge

    @staticmethod
    def init_character_pack(
        characters_root: Path,
        character_id: str,
        name: str,
        master_png: Path,
        outfit_id: str = "base",
        seed: int = 910421,
        tags: str = "",
    ) -> Path:
        """Cria a estrutura padronizada `characters/<id>/outfits/<outfit>/` + `character.json` + `manifest.json`."""
        char_dir = Path(characters_root) / character_id.lower()
        outfit_dir = char_dir / "outfits" / outfit_id.lower()
        (outfit_dir / "anchors").mkdir(parents=True, exist_ok=True)
        (outfit_dir / "clips").mkdir(parents=True, exist_ok=True)
        (char_dir / "portraits").mkdir(parents=True, exist_ok=True)

        master_dst = char_dir / "master_idle_SE.png"
        if Path(master_png).resolve() != master_dst.resolve():
            shutil.copy2(master_png, master_dst)
        anchor_master = outfit_dir / "anchors" / "master.png"
        if not anchor_master.exists():
            shutil.copy2(master_dst, anchor_master)

        cj = char_dir / "character.json"
        if not cj.exists():
            cj.write_text(
                json.dumps(
                    {
                        "id": character_id.lower(),
                        "name": name,
                        "seed": int(seed),
                        "tags": tags,
                        "default_outfit": outfit_id.lower(),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        mj = outfit_dir / "manifest.json"
        if not mj.exists():
            manifest = {
                "character_id": character_id.lower(),
                "outfit_id": outfit_id.lower(),
                "default_stride_ratio": 0.62,
                "clips": {
                    spec.key: {
                        "tier": spec.tier,
                        "fps": spec.fps,
                        "frames": spec.frames,
                        "stride_ratio": spec.stride_ratio,
                        "loop": spec.loop,
                        "status": "pending",
                    }
                    for spec in TIER_CLIP_CATALOG
                },
            }
            mj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return outfit_dir

    def _run_and_save(self, graph: dict, save_path: Path, timeout_s: float = 540.0) -> Path:
        res = self.bridge._post_json("/prompt", {"prompt": graph, "client_id": self.bridge.client_id}, timeout=20.0)
        if not res or "prompt_id" not in res:
            raise RuntimeError("Falha ao enfileirar grafo no ComfyUI")
        pid = res["prompt_id"]
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout_s:
            hist = self.bridge._get_json(f"/history/{pid}", timeout=10.0)
            if hist and pid in hist:
                item = hist[pid]
                if item.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(f"Erro no ComfyUI: {item.get('status')}")
                for node_out in (item.get("outputs") or {}).values():
                    imgs = node_out.get("images") or node_out.get("gifs") or []
                    if imgs:
                        info = imgs[0]
                        raw = self.bridge.download_output(
                            info["filename"], info.get("subfolder", ""), info.get("type", "output")
                        )
                        save_path.parent.mkdir(parents=True, exist_ok=True)
                        save_path.write_bytes(raw)
                        return save_path
            time.sleep(0.8)
        raise TimeoutError(f"Timeout aguardando {save_path.name} no ComfyUI")

    def generate_anchors_sync(
        self,
        outfit_dir: Path,
        anchor_keys: tuple[str, ...] | list[str],
        base_seed: int = 77100,
        skip_existing: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, Path]:
        """Gera poses-âncora Qwen 2.1 (`anchors/<key>.png`) a partir de `anchors/master.png`."""
        anchors_dir = Path(outfit_dir) / "anchors"
        master_p = anchors_dir / "master.png"
        if not master_p.is_file():
            raise FileNotFoundError(f"master.png ausente em {anchors_dir}")
        up_master = self.bridge.upload_image_on_white(master_p, f"iaw_master_{outfit_dir.parent.parent.name}.png")

        out: dict[str, Path] = {}
        for k in anchor_keys:
            spec = ANCHOR_SPECS.get(k)
            if spec is None:
                continue
            dst = anchors_dir / f"{k}.png"
            if skip_existing and dst.is_file():
                out[k] = dst
                continue
            if on_progress:
                on_progress(f"Gerando ancora {k}...")
            g = build_qwen_anchor_workflow(
                base_uploaded_image=up_master,
                prompt=spec.prompt,
                neg=spec.neg,
                prefix=f"IAW_anchor_{outfit_dir.parent.parent.name}_{k}",
                seed=base_seed + spec.seed_offset,
            )
            self._run_and_save(g, dst, timeout_s=300.0)
            out[k] = dst
        return out

    def generate_portraits_sync(
        self,
        char_dir: Path,
        expressions: tuple[str, ...] | list[str] | None = None,
        base_seed: int = 79100,
        skip_existing: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, Path]:
        """Gera os retratos 2D expressivos desacoplados (`portraits/<mood>.png`) via Qwen Image 2.1 Edit."""
        char_dir = Path(char_dir)
        master_p = char_dir / "master_idle_SE.png"
        if not master_p.is_file():
            master_p = char_dir / "outfits" / "base" / "anchors" / "master.png"
        if not master_p.is_file():
            raise FileNotFoundError(f"master_idle_SE.png ausente em {char_dir}")

        pdir = char_dir / "portraits"
        pdir.mkdir(parents=True, exist_ok=True)
        up_master = self.bridge.upload_image_on_white(master_p, f"iaw_portrait_master_{char_dir.name}.png")

        keys = list(expressions) if expressions is not None else list(PORTRAIT_EXPRESSIONS.keys())
        out: dict[str, Path] = {}
        for idx, expr in enumerate(keys):
            desc = PORTRAIT_EXPRESSIONS.get(expr)
            if not desc:
                continue
            dst = pdir / f"{expr}.png"
            if skip_existing and dst.is_file():
                out[expr] = dst
                continue
            if on_progress:
                on_progress(f"Gerando retrato expressivo {expr}...")
            g = build_qwen_anchor_workflow(
                base_uploaded_image=up_master,
                prompt=(
                    f"Keep this exact curvy shortstack character, exact face, exact hair, exact ears, exact skin tone, "
                    f"exact top/outfit and crisp 2D Rapscallion Tree of Savior hand-painted ink art style. "
                    f"Frame as a clean CLOSE-UP BUST PORTRAIT (head, ears, shoulders and upper chest centered, facing viewer) showing a vivid "
                    f"{desc}, pure solid flat white background, zero background scenery."
                ),
                neg="full body, legs, feet, different character, 3d render, photorealistic, shadow, scenery, text, watermark, 2girls",
                prefix=f"IAW_portrait_{char_dir.name}_{expr}",
                seed=base_seed + idx * 13,
                steps=10,
                cfg=1.45,
                use_rembg=True,
            )
            self._run_and_save(g, dst, timeout_s=300.0)
            out[expr] = dst
        return out

    def generate_outfit_anchors_sync(
        self,
        char_dir: Path,
        outfit_id: str,
        outfit_prompt: str,
        source_outfit: str = "base",
        anchor_keys: tuple[str, ...] | list[str] | None = None,
        base_seed: int = 88200,
        skip_existing: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> Path:
        """Veste cada âncora existente da `base/` com um novo traje 1:1 via Qwen Image 2.1 Edit (zero retrabalho de pose!)."""
        char_dir = Path(char_dir)
        src_anchors = char_dir / "outfits" / source_outfit / "anchors"
        dst_outfit = char_dir / "outfits" / outfit_id.lower()
        dst_anchors = dst_outfit / "anchors"
        dst_anchors.mkdir(parents=True, exist_ok=True)
        (dst_outfit / "clips").mkdir(parents=True, exist_ok=True)

        # Inicializa manifest.json do novo outfit se ainda não existir
        mj = dst_outfit / "manifest.json"
        if not mj.is_file():
            manifest = {
                "character_id": char_dir.name.lower(),
                "outfit_id": outfit_id.lower(),
                "default_stride_ratio": 0.80,
                "clips": {
                    spec.key: {
                        "tier": spec.tier,
                        "fps": spec.fps,
                        "frames": spec.frames,
                        "stride_ratio": spec.stride_ratio,
                        "loop": spec.loop,
                        "status": "pending",
                    }
                    for spec in TIER_CLIP_CATALOG
                },
            }
            mj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        files = sorted(src_anchors.glob("*.png"))
        if anchor_keys is not None:
            wanted = set(anchor_keys)
            files = [fp for fp in files if fp.stem in wanted]

        for idx, ap in enumerate(files):
            dst = dst_anchors / ap.name
            if skip_existing and dst.is_file():
                continue
            if on_progress:
                on_progress(f"Vestindo ancora {outfit_id}/{ap.stem}...")
            up = self.bridge.upload_image_on_white(ap, f"iaw_outfit_{outfit_id}_src_{ap.stem}.png")
            g = build_qwen_anchor_workflow(
                base_uploaded_image=up,
                prompt=(
                    f"Keep this exact curvy shortstack character, exact face, exact expression, exact pose, exact body framing, "
                    f"exact hair, exact pointed ears, exact proportions and pure solid flat white background 100% identical pixel-for-pixel, "
                    f"replacing ONLY her clothing so she wears {outfit_prompt}, crisp 2D hand-painted Rapscallion Tree of Savior ink art style, zero floor shadow."
                ),
                neg="different pose, moved limbs, different angle, different face, underwear visible on top, shadow, scenery, 2girls, cropped feet, 3d render",
                prefix=f"IAW_outfit_{outfit_id}_{ap.stem}",
                seed=base_seed + idx * 7,
            )
            self._run_and_save(g, dst, timeout_s=300.0)
        return dst_outfit

    def bake_clips_sync(
        self,
        outfit_dir: Path,
        clip_keys: tuple[str, ...] | list[str] | None = None,
        max_tier: int = 0,
        base_seed: int = 55100,
        skip_existing: bool = True,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, Path]:
        """Assa os clipes Wan 2.2 selecionados (ou até `max_tier`), atualizando `manifest.json` atomicamente."""
        outfit_dir = Path(outfit_dir)
        anchors_dir = outfit_dir / "anchors"
        clips_dir = outfit_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        char_id = outfit_dir.parent.parent.name

        mj = outfit_dir / "manifest.json"
        manifest = json.loads(mj.read_text(encoding="utf-8")) if mj.is_file() else {"clips": {}}

        specs = [
            s for s in TIER_CLIP_CATALOG
            if (clip_keys is not None and s.key in clip_keys) or (clip_keys is None and s.tier <= max_tier)
        ]

        # Garante que todas as âncoras necessárias já existam
        need_anchors = sorted({a for s in specs for a in (s.start_anchor, s.end_anchor) if a != "master"})
        if need_anchors:
            self.generate_anchors_sync(outfit_dir, need_anchors, skip_existing=True, on_progress=on_progress)

        uploaded_cache: dict[str, str] = {}
        results: dict[str, Path] = {}
        for spec in specs:
            dst = clips_dir / f"clip_{spec.key}.webp"
            if skip_existing and dst.is_file():
                results[spec.key] = dst
                manifest.setdefault("clips", {}).setdefault(spec.key, {})["status"] = "ready"
                continue

            start_p = anchors_dir / f"{spec.start_anchor}.png"
            end_p = anchors_dir / f"{spec.end_anchor}.png"
            if not start_p.is_file() or not end_p.is_file():
                log(f"[pipeline] Âncora ausente para {spec.key}: {start_p.name} / {end_p.name}")
                continue

            for ap in (start_p, end_p):
                if ap.name not in uploaded_cache:
                    uploaded_cache[ap.name] = self.bridge.upload_image_fitted_on_white(
                        ap, f"iaw_wan_{char_id}_{ap.stem}.png", tw=448, th=640
                    )

            if on_progress:
                on_progress(f"Assando Wan 2.2 ({spec.frames}f @ {int(spec.fps)}FPS): {spec.key}...")
            g = build_wan_transition_workflow(
                start_uploaded_image=uploaded_cache[start_p.name],
                end_uploaded_image=uploaded_cache[end_p.name],
                clip_key=spec.key,
                prompt=spec.prompt,
                character_id=char_id,
                width=448,
                height=640,
                length=spec.frames,
                fps=spec.fps,
                seed=base_seed + spec.seed_offset,
            )
            self._run_and_save(g, dst, timeout_s=600.0)
            results[spec.key] = dst
            manifest.setdefault("clips", {})[spec.key] = {
                "tier": spec.tier,
                "fps": spec.fps,
                "frames": spec.frames,
                "stride_ratio": spec.stride_ratio,
                "loop": spec.loop,
                "status": "ready",
            }
            mj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        return results

    def bake_tier_async(
        self,
        outfit_dir: Path,
        max_tier: int = 0,
        on_progress: Callable[[str], None] | None = None,
        on_done: Callable[[dict[str, Path]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> threading.Thread:
        """Executa o baking de Tier em background sem travar o desktop."""
        def _worker():
            try:
                res = self.bake_clips_sync(outfit_dir, max_tier=max_tier, on_progress=on_progress)
                if on_done:
                    on_done(res)
            except Exception as exc:
                if on_error:
                    on_error(str(exc))

        th = threading.Thread(target=_worker, name=f"IAW-Bake-T{max_tier}", daemon=True)
        th.start()
        return th
