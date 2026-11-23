"""Testes unitários das camadas comfy (workflows + seleção de checkpoint) e mind (BehaviorDirector)."""

from pathlib import Path

from iawallpaper.comfy.bridge import ComfyBridge
from iawallpaper.comfy.character_pipeline import (
    TIER_CLIP_CATALOG,
    CharacterPipeline,
    build_qwen_anchor_workflow,
    build_wan_transition_workflow,
)
from iawallpaper.comfy.presets import LoraSpec, find_comfy_preset, load_comfy_presets
from iawallpaper.comfy.workflows import (
    build_avatar_variant_img2img_workflow,
    build_avatar_workflow,
    build_diorama_scene_workflow,
    build_qwen_relight_scene_workflow,
    build_qwen_turnaround_workflow,
    build_scene_workflow,
    build_wan_sprite_clip_workflow,
    build_world_sprite_workflow,
)
from iawallpaper.core.conditioning import Conditioning
from iawallpaper.core.emotion import EmotionState
from iawallpaper.core.episodic import EpisodicMemory
from iawallpaper.core.homeostasis import Drives
from iawallpaper.core.nervous_system import WaifuSpikingBrain
from iawallpaper.core.persona import create_custom_persona, list_personas, load_persona, save_persona
from iawallpaper.mind.director import BehaviorDirector
from iawallpaper.sense.circadian import compute_circadian
from iawallpaper.sense.weather import WeatherState


def test_comfy_workflow_builders():
    mira = load_persona("mira")
    sc = build_scene_workflow("waiIllustriousSDXL_v170.safetensors", "sky_sanctuary", "night", seed=42)
    assert sc["1"]["inputs"]["ckpt_name"] == "waiIllustriousSDXL_v170.safetensors"
    assert "PerturbedAttentionGuidance" in {n["class_type"] for n in sc.values()}
    assert "no_humans" in sc["2"]["inputs"]["text"]

    av = build_avatar_workflow("waiIllustriousSDXL_v170.safetensors", mira, "focus", seed=42, use_rembg=True)
    assert av["8"]["class_type"] == "Image Rembg (Remove Background)"
    assert av["8"]["inputs"]["model"] == "isnet-anime"
    assert av["8"]["inputs"]["transparency"] is True

    best = ComfyBridge.pick_anime_checkpoint(["foo.safetensors", "illustrious\\waiIllustriousSDXL_v170.safetensors"])
    assert "waiIllustrious" in best

    expr_wf = build_avatar_variant_img2img_workflow(
        "waiIllustriousSDXL_v170.safetensors",
        mira,
        base_uploaded_image="iawallpaper_base_mira.png",
        outfit_key="casual",
        expression_key="shy",
        seed=42,
    )
    assert expr_wf["10"]["class_type"] == "LoadImage"
    assert expr_wf["4"]["class_type"] == "VAEEncode"
    assert expr_wf["6"]["inputs"]["denoise"] == 0.44
    assert "blushing" in expr_wf["2"]["inputs"]["text"]

    dio = build_diorama_scene_workflow("waiIllustriousSDXL_v170.safetensors", "sky_sanctuary", "day", seed=11)
    assert "tree_of_savior_style" in dio["2"]["inputs"]["text"]
    assert "no_humans" in dio["2"]["inputs"]["text"]

    ws = build_world_sprite_workflow(
        "illustrious\\arthemyComics_v80.safetensors",
        mira,
        action_key="walk1",
        loras=[LoraSpec("illustrious\\cutesexyrobutts.safetensors", 0.75, 0.75)],
        seed=12,
    )
    assert "full_body" in ws["2"]["inputs"]["text"]
    assert "mature_female" in ws["2"]["inputs"]["text"]
    assert "chibi" in ws["3"]["inputs"]["text"]
    assert "20" in ws and ws["20"]["class_type"] == "LoraLoader"
    assert ws["8"]["inputs"]["alpha_matting"] is False

    qrel = build_qwen_relight_scene_workflow("iawallpaper_diorama_day.png", variant="night", seed=7)
    assert qrel["4"]["class_type"] == "TextEncodeQwenImage21"
    assert qrel["5"]["inputs"]["denoise"] == 1.0

    wan = build_wan_sprite_clip_workflow("iawallpaper_wan_base_mira.png", action_key="dance", seed=9)
    assert wan["10"]["class_type"] == "WanFirstLastFrameToVideo"
    assert wan["10"]["inputs"]["start_image"] == wan["10"]["inputs"]["end_image"]
    assert wan["14"]["class_type"] == "Image Rembg (Remove Background)"
    assert wan["14"]["inputs"]["alpha_matting"] is False
    assert wan["15"]["class_type"] == "SaveAnimatedWEBP"

    turn = build_qwen_turnaround_workflow("iawallpaper_turn_base_mira.png", direction="side", seed=5)
    assert turn["4"]["class_type"] == "TextEncodeQwenImage21"
    assert "side-right" in turn["4"]["inputs"]["prompt"]
    assert turn["8"]["class_type"] == "Image Rembg (Remove Background)"

    top = find_comfy_preset("RawSexyGlowingGemPencil")
    if top is not None:
        assert top.is_top
        assert len(top.loras) >= 3


def test_custom_persona_creation_and_persistence(tmp_path: Path):
    p = create_custom_persona(
        name="Luna Star",
        title="Guardiã Lunar",
        character_tags="long_silver_hair, violet_eyes, fox_ears",
        temperament_preset="night_owl",
    )
    assert p.id == "luna_star"
    assert "1girl" in p.comfy_character_tags
    saved = save_persona(p, tmp_path)
    assert saved.exists()
    assert "luna_star" in list_personas(tmp_path)
    loaded = load_persona("luna_star", tmp_path)
    assert loaded.name == "Luna Star"
    assert "fox_ears" in loaded.comfy_character_tags


def test_director_outfits_whispers_and_sleep(tmp_path: Path):
    mira = load_persona("mira")
    brain = WaifuSpikingBrain(seed=42)
    drives = Drives()
    cond = Conditioning(path=tmp_path / "cond.json")
    ep = EpisodicMemory(tmp_path / "ep.jsonl", tmp_path / "prefs.json")
    director = BehaviorDirector(mira, brain, drives, cond, ep)

    # Modo programação -> coloca óculos / traje focus
    out = director.step(
        now=100.0,
        activity="PROGRAMMING",
        circadian=compute_circadian(14.0),
        weather=WeatherState(condition="clear"),
        emotion=EmotionState(mood="focused"),
        decision_rates={"WHISPER": 0.5, "PLAY_FX": 0.0, "DOZE_OFF": 0.0},
    )
    assert out.outfit == "focus"

    # Chuva -> traje rainy
    out_rain = director.step(
        now=101.0,
        activity="IDLE",
        circadian=compute_circadian(15.0),
        weather=WeatherState(condition="rain", intensity=0.8),
        emotion=EmotionState(mood="cozy"),
        decision_rates={"WHISPER": 0.0, "PLAY_FX": 0.0, "DOZE_OFF": 0.0},
    )
    assert out_rain.outfit == "rainy"

    # Carinho -> gera coração e aumenta afinidade
    aff0 = drives.affinity
    director.on_caress(now=105.0)
    assert drives.affinity > aff0
    out_pat = director.step(
        now=105.1,
        activity="IDLE",
        circadian=compute_circadian(15.0),
        weather=WeatherState(condition="clear"),
        emotion=EmotionState(mood="affectionate"),
        decision_rates={"WHISPER": 0.0, "PLAY_FX": 0.0, "DOZE_OFF": 0.0},
    )
    assert out_pat.burst_fx == "heart"
    assert out_pat.whisper_text != ""

    # Energia baixa -> dorme e veste pijama
    drives.energy = 0.10
    out_sleep = director.step(
        now=120.0,
        activity="IDLE",
        circadian=compute_circadian(2.0),
        weather=WeatherState(condition="clear"),
        emotion=EmotionState(mood="sleepy"),
        decision_rates={"WHISPER": 0.0, "PLAY_FX": 0.0, "DOZE_OFF": 12.0},
    )
    assert out_sleep.asleep is True
    assert out_sleep.outfit == "nightwear"


def test_character_pipeline_workflows_and_init(tmp_path: Path):
    from PIL import Image

    # Loop Wan 2.2 (start == end) -> sem nó 9b, 25f @ 16 FPS, isnet-anime sem alpha_matting
    g_loop = build_wan_transition_workflow(
        start_uploaded_image="arya_walk_N.png",
        end_uploaded_image="arya_walk_N.png",
        clip_key="walk_N",
        prompt="continuous back walk cycle",
        character_id="arya",
        length=25,
        fps=16.0,
    )
    assert "9b" not in g_loop
    assert g_loop["10"]["inputs"]["start_image"] == ["9", 0]
    assert g_loop["10"]["inputs"]["end_image"] == ["9", 0]
    assert g_loop["10"]["inputs"]["length"] == 25
    assert g_loop["14"]["inputs"]["alpha_matting"] is False
    assert g_loop["15"]["inputs"]["fps"] == 16.0

    # Transição Wan 2.2 (start != end) -> carrega imagem final distinta no nó 9b!
    g_trans = build_wan_transition_workflow(
        start_uploaded_image="arya_master.png",
        end_uploaded_image="arya_sit_floor.png",
        clip_key="trans_sit_floor",
        prompt="sit down transition",
        character_id="arya",
        length=25,
        fps=16.0,
    )
    assert "9b" in g_trans
    assert g_trans["10"]["inputs"]["start_image"] == ["9", 0]
    assert g_trans["10"]["inputs"]["end_image"] == ["9b", 0]

    # Âncora Qwen 2.1 Edit com LoRA Anime Illustration e RemBG
    g_qwen = build_qwen_anchor_workflow(
        base_uploaded_image="arya_master.png",
        prompt="back view walking pose",
        neg="front view",
        prefix="IAW_anchor_arya_walk_N",
    )
    assert g_qwen["4"]["class_type"] == "TextEncodeQwenImage21"
    assert g_qwen["11"]["class_type"] == "LoraLoaderModelOnly"
    assert g_qwen["7"]["inputs"]["model"] == "isnet-anime"

    # Inicialização padronizada do pack de personagem
    master = tmp_path / "master_src.png"
    Image.new("RGBA", (64, 96), (240, 210, 140, 255)).save(master)
    outfit_dir = CharacterPipeline.init_character_pack(
        tmp_path / "characters", "arya", "Arya", master, outfit_id="base"
    )
    assert (outfit_dir / "anchors" / "master.png").is_file()
    assert (outfit_dir / "manifest.json").is_file()
    assert (outfit_dir.parent.parent / "character.json").is_file()
    assert len(TIER_CLIP_CATALOG) == 18
