"""Testes unitários das camadas comfy (workflows + seleção de checkpoint) e mind (BehaviorDirector)."""

from pathlib import Path

from iawallpaper.comfy.bridge import ComfyBridge
from iawallpaper.comfy.workflows import build_avatar_workflow, build_scene_workflow
from iawallpaper.core.conditioning import Conditioning
from iawallpaper.core.emotion import EmotionState
from iawallpaper.core.episodic import EpisodicMemory
from iawallpaper.core.homeostasis import Drives
from iawallpaper.core.nervous_system import WaifuSpikingBrain
from iawallpaper.core.persona import load_persona
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
