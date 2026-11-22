"""Testes unitários do núcleo cognitivo (rede LIF, homeostase, condicionamento, memória episódica, emoção e store)."""

import math
from pathlib import Path

import pytest

from iawallpaper.config import Settings
from iawallpaper.core.conditioning import Conditioning
from iawallpaper.core.emotion import EmotionDecoder
from iawallpaper.core.episodic import EpisodicMemory
from iawallpaper.core.homeostasis import Drives
from iawallpaper.core.nervous_system import WaifuSpikingBrain
from iawallpaper.core.persona import list_personas, load_persona
from iawallpaper.paths import Paths, valid_id
from iawallpaper.store import read_json, write_json


def test_store_atomic_and_nan_rejection(tmp_path: Path):
    f = tmp_path / "data.json"
    write_json(f, {"ok": 1.5, "nome": "Mira"})
    assert read_json(f) == {"ok": 1.5, "nome": "Mira"}

    with pytest.raises(ValueError):
        write_json(f, {"bad": float("nan")})

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not valid json", encoding="utf-8")
    assert read_json(corrupt, default={"fallback": True}) == {"fallback": True}
    assert (tmp_path / "corrupt.json.corrompido").exists()


def test_paths_validation(tmp_path: Path):
    assert valid_id("mira")
    assert valid_id("nyx_01")
    assert not valid_id("../evil")
    assert not valid_id("UPPER")
    paths = Paths(base_dir=tmp_path, data_dir=tmp_path / "memory")
    pm = paths.persona_memory("mira")
    assert pm.brain.name == "brain.json"


def test_settings_roundtrip_and_sanitization(tmp_path: Path):
    s = Settings(persona_id="nyx", fps_cap=144, parallax_strength=99.0, weather_mode="invalid", time_override_hour=25.0)
    san = s.sanitized()
    assert san.fps_cap == 60
    assert san.parallax_strength == 2.0
    assert san.weather_mode == "auto"
    assert san.time_override_hour is None

    p = tmp_path / "settings.json"
    Settings(persona_id="mira", time_override_hour=21.5, weather_mode="rain").save(p)
    loaded = Settings.load(p)
    assert loaded.time_override_hour == 21.5
    assert loaded.weather_mode == "rain"


def test_spiking_brain_responds_to_caress_and_work(tmp_path: Path):
    brain = WaifuSpikingBrain(seed=123)
    # Estímulo de carinho deve elevar AFFECTIONATE e SHY/HAPPY
    for _ in range(25):
        brain.stimulate({"CARESS": 1.0, "RAIN": 0.6})
        brain.step(100.0)
    rates = brain.expression_rates()
    assert rates["AFFECTIONATE"] > 2.0
    assert rates["AFFECTIONATE"] > rates["POUTY"]

    # Aprendizado de três fatores sob contexto WORK + recompensa positiva
    for _ in range(15):
        brain.stimulate({"WORK": 1.0, "TYPING": 0.8})
        brain.step(100.0)
    brain.learn(+1.0)
    assert brain.learn_events >= 1
    assert len(brain.learned_summary()) >= 1

    # Persistência e recarga
    path = tmp_path / "brain.json"
    brain.save(path)
    brain2 = WaifuSpikingBrain(seed=123)
    assert brain2.load(path)
    assert brain2.learn_events == brain.learn_events
    assert len(brain2.learned_summary()) >= 1


def test_brain_habituation_and_recovery():
    brain = WaifuSpikingBrain(seed=77)
    start_hab = brain.habituation["POKE"]
    for _ in range(40):
        brain.stimulate({"POKE": 1.0})
        brain.step(100.0)
    after_poke = brain.habituation["POKE"]
    assert after_poke < start_hab

    # Sem estímulo, recupera gradualmente
    for _ in range(40):
        brain.stimulate({})
        brain.step(100.0)
    assert brain.habituation["POKE"] > after_poke


def test_homeostasis_circadian_and_bond(tmp_path: Path):
    d = Drives()
    e0 = d.energy
    # Madrugada cansa mais rápido que dia
    d.update(dt=10.0, asleep=False, arousal=0.4, user_away=False, night_factor=1.0, energy_span=1000.0)
    drain_night = e0 - d.energy

    d2 = Drives()
    d2.update(dt=10.0, asleep=False, arousal=0.4, user_away=False, night_factor=0.0, energy_span=1000.0)
    drain_day = e0 - d2.energy
    assert drain_night > drain_day

    aff0 = d.affinity
    d.touched("caress", scale=2.0)
    assert d.affinity > aff0
    assert d.total_caresses == 1

    p = tmp_path / "drives.json"
    d.save(p)
    d3 = Drives()
    assert d3.load(p)
    assert math.isclose(d3.affinity, d.affinity, rel_tol=1e-2)


def test_conditioning_learns_and_extinguishes(tmp_path: Path):
    c = Conditioning(path=tmp_path / "cond.json", rate=0.25)
    t = 100.0
    for _ in range(6):
        c.set_cue("APPROACH", True, t)
        c.outcome(t + 0.5, cues=("APPROACH",))
        c.set_cue("APPROACH", False, t + 0.6)
        t += 5.0
        c.tick(t)
    assert c.V["APPROACH"] > 0.65

    # Extinção quando a pista ocorre sem desfecho
    before_ext = c.V["APPROACH"]
    for _ in range(4):
        c.set_cue("APPROACH", True, t)
        c.set_cue("APPROACH", False, t + 0.4)
        t += 5.0
        c.tick(t)
    assert c.V["APPROACH"] < before_ext

    c.save()
    c2 = Conditioning(path=tmp_path / "cond.json")
    c2.load()
    assert math.isclose(c2.V["APPROACH"], c.V["APPROACH"], abs_tol=1e-4)


def test_episodic_bandit_learns_and_consolidates(tmp_path: Path):
    mem = EpisodicMemory(tmp_path / "ep.jsonl", tmp_path / "prefs.json")
    ctx = EpisodicMemory.context("PROGRAMMING", "night", "rain", "focused")

    ep1 = mem.start(ctx, "whisper", now=10.0)
    mem.on_dismiss(now=11.0)
    assert ep1 not in mem.open

    ep2 = mem.start(ctx, "quiet_company", now=20.0)
    mem.on_positive_feedback()
    mem.tick(now=40.0, window=18.0)
    assert ep2 not in mem.open

    assert mem.estimate(ctx, "quiet_company") > mem.estimate(ctx, "whisper")
    chosen = mem.choose(ctx, ["whisper", "quiet_company"], epsilon=0.0)
    assert chosen == "quiet_company"

    prefs = mem.consolidate()
    assert len(prefs) >= 2


def test_emotion_decoder_and_personas():
    dec = EmotionDecoder()
    for _ in range(12):
        st = dec.update({"AFFECTIONATE": 16.0, "SHY_BLUSH": 10.0}, dt=0.2)
    assert st.mood == "affectionate"
    assert st.blush > 0.4
    assert st.valence > 0.2

    personas = list_personas()
    assert "mira" in personas and "nyx" in personas
    mira = load_persona("mira")
    assert mira.name == "Mira"
    assert "casual" in mira.outfits and "rainy" in mira.outfits
