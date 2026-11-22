"""Testes unitários das camadas plataforma e sense (ciclo solar, clima, contexto e rotina)."""

from pathlib import Path

from iawallpaper.plataforma.desktop_host import primary_monitor_rect
from iawallpaper.plataforma.windows import idle_seconds, system_telemetry
from iawallpaper.sense.circadian import compute_circadian
from iawallpaper.sense.routine import RoutineTracker
from iawallpaper.sense.senses import ActivityTracker, ContextSenses, detect_activity
from iawallpaper.sense.weather import WeatherService, map_wmo_code


def test_circadian_periods_and_daylight():
    noon = compute_circadian(override_hour=12.5)
    assert noon.period == "afternoon"
    assert noon.daylight > 0.9
    assert noon.star_visibility < 0.05

    sunset = compute_circadian(override_hour=18.0)
    assert sunset.period == "golden_hour"
    assert sunset.warmth > 0.8

    midnight = compute_circadian(override_hour=1.0)
    assert midnight.period == "late_night"
    assert midnight.night_factor > 0.9
    assert midnight.star_visibility > 0.8


def test_weather_mapping_and_overrides(tmp_path: Path):
    assert map_wmo_code(0)[0] == "clear"
    assert map_wmo_code(63)[0] == "rain"
    assert map_wmo_code(95)[0] == "storm"
    assert map_wmo_code(73)[0] == "snow"
    assert map_wmo_code(45)[0] == "fog"

    ws = WeatherService(cache_path=tmp_path / "weather.json")
    rain = ws.current(override_mode="rain")
    assert rain.condition == "rain"
    assert rain.source == "override"
    assert rain.channels()["RAIN"] > 0.5

    storm = ws.current(override_mode="storm")
    assert storm.channels()["STORM"] > 0.5


def test_activity_detection_and_context_senses():
    assert detect_activity("Code.exe", idle_seconds=1.0) == "PROGRAMMING"
    assert detect_activity("spotify.exe", idle_seconds=2.0) == "MUSIC"
    assert detect_activity("valorant.exe", idle_seconds=0.5) == "GAMING"
    assert detect_activity("Code.exe", idle_seconds=300.0, away_after=180.0) == "AWAY"
    assert detect_activity("chrome.exe", idle_seconds=1.0, comfy_busy=True) == "BROWSING"
    assert detect_activity("desktop", idle_seconds=1.0, comfy_busy=True) == "AI_STUDIO"

    tracker = ActivityTracker()
    assert tracker.observe("code.exe", "PROGRAMMING") == []
    evs = tracker.observe("spotify.exe", "MUSIC")
    assert "ACTIVITY_CHANGED" in evs and "APP_CHANGED" in evs
    assert "USER_LEFT" in tracker.observe("spotify.exe", "AWAY")
    assert "USER_RETURNED" in tracker.observe("code.exe", "PROGRAMMING")

    senses = ContextSenses()
    senses.kick("GIFT", 0.9)
    ch = senses.update(
        activity="PROGRAMMING",
        idle_seconds=0.1,
        drives_channels={"BOREDOM": 0.1, "LONELY": 0.0, "FATIGUE": 0.2},
        circadian=compute_circadian(override_hour=22.0),
        weather=WeatherService().current("rain"),
        telemetry={"cpu": 0.75, "ram": 0.5},
        caressing=True,
        mouse_moving=True,
        anticipate=0.4,
    )
    assert ch["GIFT"] > 0.5
    assert ch["NIGHT"] > 0.8
    assert ch["RAIN"] > 0.5
    assert ch["SYS_LOAD"] > 0.4
    assert ch["ANTICIPATE"] == 0.4


def test_routine_tracker_persistence(tmp_path: Path):
    p = tmp_path / "routine.json"
    rt = RoutineTracker(p)
    for _ in range(5):
        rt.record("PROGRAMMING", hour=22)
    assert rt.usual_activity(22) == "PROGRAMMING"
    rt.save()

    rt2 = RoutineTracker(p)
    rt2.load()
    assert rt2.usual_activity(22) == "PROGRAMMING"


def test_platform_basic_queries():
    rect = primary_monitor_rect()
    assert rect[2] > 0 and rect[3] > 0
    assert idle_seconds() >= 0.0
    tel = system_telemetry()
    assert 0.0 <= tel["cpu"] <= 1.0
    assert 0.0 <= tel["ram"] <= 1.0
