"""APP — Composição principal do IAWallpaper: ciclos frame/think/sense/weather/save, host Win11 e UI."""

import os
from pathlib import Path
import time

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication

from .comfy.bridge import ComfyBridge
from .config import Settings
from .core.conditioning import Conditioning
from .core.emotion import EmotionDecoder
from .core.episodic import EpisodicMemory
from .core.homeostasis import Drives
from .core.nervous_system import WaifuSpikingBrain
from .core.persona import load_persona, save_persona
from .log import configure_log, log
from .mind.director import BehaviorDirector
from .paths import Paths
from .plataforma import (
    DesktopAttachment,
    active_process,
    attach_to_desktop,
    cursor_position,
    detach_from_desktop,
    idle_seconds,
    is_cursor_over_desktop,
    is_fullscreen,
    is_left_mouse_down,
    primary_monitor_rect,
    set_autostart,
    set_no_activate,
    start_panic_hotkey,
    system_telemetry,
)
from .render.canvas import WallpaperCanvas
from .sense.circadian import compute_circadian
from .sense.routine import RoutineTracker
from .sense.senses import ActivityTracker, ContextSenses, detect_activity
from .sense.weather import WeatherService
from .store import remove_tree
from .ui.control_center import ControlCenterWindow
from .ui.neural_monitor import NeuralMonitorWindow
from .ui.tray import WallpaperTray


class _UiBridge(QObject):
    """Ponte thread-safe para atualizar a UI a partir de threads de background (ComfyUI / Hotkey)."""

    panic_triggered = Signal()
    comfy_avatar_done = Signal(str)
    comfy_scene_done = Signal(str)
    comfy_pack_progress = Signal(int, int, str)
    comfy_pack_asset = Signal(str, str)
    comfy_error = Signal(str)


class IAWallpaperApp:
    """Orquestrador principal do wallpaper dinâmico vivo e avatar waifu cognitivo."""

    def __init__(
        self,
        paths: Paths | None = None,
        override_mode: str | None = None,
        override_hour: float | None = None,
        override_weather: str | None = None,
        test_mode: bool = False,
        enable_tray: bool = True,
        enable_hotkey: bool = True,
    ):
        self.paths = paths or Paths()
        configure_log(self.paths.log_file, echo=test_mode)

        self.settings = Settings.load(self.paths.settings_file)
        if override_mode:
            self.settings.mode = override_mode
        if override_hour is not None:
            self.settings.time_override_hour = override_hour
        if override_weather:
            self.settings.weather_mode = override_weather
        if test_mode:
            self.settings.test_mode = True
        self.settings = self.settings.sanitized()

        self.bridge = _UiBridge()
        self.bridge.panic_triggered.connect(self.toggle_panic_hide)
        self.bridge.comfy_avatar_done.connect(self._on_comfy_avatar_done)
        self.bridge.comfy_scene_done.connect(self._on_comfy_scene_done)
        self.bridge.comfy_pack_progress.connect(self._on_comfy_pack_progress)
        self.bridge.comfy_pack_asset.connect(self._on_comfy_pack_asset)
        self.bridge.comfy_error.connect(self._on_comfy_error)

        # Estado de sessão
        self.paused = False
        self.panic_hidden = False
        self.fullscreen_paused = False
        self.attachment = DesktopAttachment(False, "fallback")
        self._last_frame_t = time.monotonic()
        self._last_think_t = time.monotonic()
        self._last_comfy_poll = 0.0
        self._last_routine_tick = 0.0
        self._comfy_busy = False
        self._last_cursor = (0, 0)
        self._mouse_moving = False
        self._caress_until = 0.0
        self._active_app = "desktop"
        self._idle_s = 0.0
        self._activity = "IDLE"
        self._telemetry = {"cpu": 0.0, "ram": 0.0}

        # Carrega persona e cérebro cognitivo
        self._init_cognition(self.settings.persona_id)

        # Serviços sensoriais e ComfyUI (read-only)
        self.weather_service = WeatherService(cache_path=self.paths.weather_cache_file)
        self.routine = RoutineTracker(path=self.paths.routine_file)
        self.routine.load()
        self.activity_tracker = ActivityTracker()
        self.context_senses = ContextSenses()
        self.comfy = ComfyBridge(self.settings.comfyui_url)

        # Canvas principal do wallpaper
        self.canvas = WallpaperCanvas(
            persona=self.persona,
            sprite_dirs=[
                self.paths.persona_assets(self.persona.id),
                self.paths.persona_generated_assets(self.persona.id),
            ],
            scene_dirs=[
                self.paths.scene_assets(self.settings.scene_id),
                self.paths.scene_generated_assets(self.settings.scene_id),
            ],
            render_style=self.settings.render_style,
        )
        self.canvas.setWindowTitle(f"IAWallpaper — {self.persona.name}")
        self.canvas.caress_tick.connect(self._on_canvas_caress)
        self.canvas.avatar_poked.connect(self._on_canvas_poke)
        self.canvas.ground_clicked.connect(self._on_ground_clicked)
        self.canvas.whisper_dismissed.connect(self._on_whisper_dismissed)
        self.canvas.cursor_approaching.connect(self._on_cursor_approaching)

        # Janelas de controle & monitor neural
        self.control_center = ControlCenterWindow(self.settings, personas_dir=self.paths.personas_dir)
        self._connect_control_center()
        self._update_asset_coverage()
        self.neural_monitor = NeuralMonitorWindow()

        # Ícone de bandeja
        self.tray: WallpaperTray | None = None
        if enable_tray and WallpaperTray.isSystemTrayAvailable():
            self.tray = WallpaperTray()
            self.tray.open_studio.connect(self.show_control_center)
            self.tray.open_monitor.connect(self.show_neural_monitor)
            self.tray.toggle_pause.connect(self.toggle_pause)
            self.tray.toggle_mode.connect(self.toggle_display_mode)
            self.tray.caress_now.connect(self._trigger_caress)
            self.tray.quit_app.connect(self.shutdown)
            self.tray.show()

        # Timers principais (inspirados na cadência do Pestinha)
        self.t_frame = QTimer()
        self.t_frame.timeout.connect(self._tick_frame)

        self.t_think = QTimer()
        self.t_think.timeout.connect(self._tick_think)

        self.t_sense = QTimer()
        self.t_sense.timeout.connect(self._tick_sense)

        self.t_weather = QTimer()
        self.t_weather.timeout.connect(self._refresh_weather)

        self.t_save = QTimer()
        self.t_save.timeout.connect(self.save_all)

        self._apply_canvas_settings()
        self._apply_window_mode(self.settings.mode)

        if enable_hotkey:
            start_panic_hotkey(lambda: self.bridge.panic_triggered.emit())

        log(f"[app] IAWallpaper iniciado (persona={self.persona.id}, mode={self.settings.mode})")

    def _init_cognition(self, persona_id: str) -> None:
        self.persona = load_persona(persona_id, personas_dir=self.paths.personas_dir)
        self.mem_paths = self.paths.persona_memory(self.persona.id)

        self.brain = WaifuSpikingBrain(seed=self.persona.seed, temperament=self.persona.temperament)
        self.brain.load(self.mem_paths.brain)

        self.drives = Drives()
        self.drives.load(self.mem_paths.drives)

        self.conditioning = Conditioning(path=self.mem_paths.conditioning)
        self.conditioning.load()

        self.episodic = EpisodicMemory(self.mem_paths.episodes, self.mem_paths.preferences)
        self.episodic.load()

        self.emotion_decoder = EmotionDecoder()
        self.director = BehaviorDirector(
            persona=self.persona,
            brain=self.brain,
            drives=self.drives,
            conditioning=self.conditioning,
            episodic=self.episodic,
        )

    def _connect_control_center(self) -> None:
        cc = self.control_center
        cc.settings_changed.connect(self.apply_settings)
        cc.caress_requested.connect(self._trigger_caress)
        cc.gift_requested.connect(self._trigger_gift)
        cc.whisper_requested.connect(self._trigger_whisper)
        cc.toggle_sleep_requested.connect(self._toggle_sleep)
        cc.refresh_weather_requested.connect(self._refresh_weather)
        cc.open_monitor_requested.connect(self.show_neural_monitor)
        cc.comfy_probe_requested.connect(self._probe_comfy_ui)
        cc.comfy_gen_avatar_requested.connect(self._generate_comfy_avatar)
        cc.comfy_gen_scene_requested.connect(self._generate_comfy_scene)
        cc.comfy_gen_pack_requested.connect(self._generate_comfy_pack)
        cc.create_persona_requested.connect(self._create_custom_persona)
        cc.reload_assets_requested.connect(self._reload_assets)
        cc.clear_generated_requested.connect(self._clear_generated_assets)
        cc.clear_memory_requested.connect(self._clear_memory)

    def start(self, show_studio: bool = False, show_monitor: bool = False) -> None:
        """Inicia todos os ciclos e busca clima inicial em background."""
        self.t_frame.start(16 if self.settings.fps_cap >= 60 else 33)
        self.t_think.start(100)
        self.t_sense.start(500)
        self.t_weather.start(15 * 60 * 1000)
        self.t_save.start(30 * 1000)
        self._refresh_weather()
        self._tick_think()
        if show_studio:
            self.show_control_center()
        if show_monitor:
            self.show_neural_monitor()

    def _apply_canvas_settings(self) -> None:
        self.canvas.parallax_strength = self.settings.parallax_strength
        self.canvas.particle_density = self.settings.particle_density
        self.canvas.avatar_scale = self.settings.avatar_scale
        self.canvas.avatar_x_ratio = self.settings.avatar_x_ratio
        self.canvas.avatar.render_style = self.settings.render_style
        self.t_frame.setInterval(16 if self.settings.fps_cap >= 60 else 33)

    def _apply_window_mode(self, mode: str) -> None:
        hwnd = int(self.canvas.winId())
        if self.attachment.attached:
            detach_from_desktop(hwnd)
            self.attachment = DesktopAttachment(False, "fallback")

        if mode == "wallpaper":
            rect = primary_monitor_rect()
            self.canvas.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
            self.canvas.setGeometry(rect[0], rect[1], rect[2], rect[3])
            self.canvas.show()
            hwnd = int(self.canvas.winId())
            set_no_activate(hwnd)
            self.attachment = attach_to_desktop(hwnd, rect=rect)
            if self.attachment.attached:
                self.control_center.set_status_text(f"Wallpaper ativo ({self.attachment.mode}) · {rect[2]}×{rect[3]}")
            else:
                # Fallback limpo: janela preview interativa se Progman/WorkerW indisponível
                self.canvas.setWindowFlags(Qt.Window)
                self.canvas.resize(1280, 720)
                self.canvas.show()
                self.control_center.set_status_text("Modo Janela (fallback: Progman indisponível nesta sessão)")
        else:
            self.canvas.setWindowFlags(Qt.Window)
            self.canvas.resize(1280, 720)
            self.canvas.show()
            self.control_center.set_status_text("Modo Preview Interativo (1280×720)")

    def apply_settings(self, new_settings: Settings) -> None:
        old = self.settings
        s = new_settings.sanitized()
        self.settings = s
        self.comfy.base_url = s.comfyui_url

        if s.persona_id != old.persona_id:
            self.save_all()
            self._init_cognition(s.persona_id)
            self.canvas.avatar.set_persona(
                self.persona,
                sprite_dirs=[
                    self.paths.persona_assets(self.persona.id),
                    self.paths.persona_generated_assets(self.persona.id),
                ],
            )
            self.canvas.setWindowTitle(f"IAWallpaper — {self.persona.name}")

        if s.scene_id != old.scene_id:
            self.canvas.scene.reload_scene_images(
                [
                    self.paths.scene_assets(s.scene_id),
                    self.paths.scene_generated_assets(s.scene_id),
                ]
            )

        if s.mode != old.mode:
            self._apply_window_mode(s.mode)

        if s.weather_city != old.weather_city:
            self._refresh_weather()

        if s.start_with_windows != old.start_with_windows:
            set_autostart(s.start_with_windows)

        self._apply_canvas_settings()
        self._update_asset_coverage()
        self.settings.save(self.paths.settings_file)

    # ---------------- Ciclos principais ----------------

    def _tick_frame(self) -> None:
        now = time.monotonic()
        dt = min(0.1, max(0.001, now - self._last_frame_t))
        self._last_frame_t = now

        if self.paused or self.panic_hidden or self.fullscreen_paused:
            return

        # No modo wallpaper atrás dos ícones, fazemos polling leve do cursor sobre o desktop vazio
        if self.attachment.attached:
            cx, cy = cursor_position()
            self._mouse_moving = (cx, cy) != self._last_cursor
            self._last_cursor = (cx, cy)
            over_desktop = is_cursor_over_desktop(int(self.canvas.winId()))
            left_down = is_left_mouse_down() if over_desktop else False
            self.canvas.feed_pointer(float(cx), float(cy), left_down=left_down, interactive=over_desktop)

        self.canvas.step_animation(dt)

    def _tick_sense(self) -> None:
        if self.paused or self.panic_hidden:
            return
        now = time.monotonic()
        self._idle_s = idle_seconds()
        self._active_app = active_process()
        self._telemetry = system_telemetry()

        if self.settings.auto_pause_fullscreen:
            fs = is_fullscreen()
            if fs != self.fullscreen_paused:
                self.fullscreen_paused = fs
                log("[app] Auto-pausa em tela cheia " + ("ATIVADA" if fs else "DESATIVADA"))

        if self.settings.comfyui_enabled and (now - self._last_comfy_poll >= 6.0):
            self._last_comfy_poll = now
            self._comfy_busy = self.comfy.is_busy_fast()

        self._activity = detect_activity(self._active_app, self._idle_s, comfy_busy=self._comfy_busy)
        events = self.activity_tracker.observe(self._active_app, self._activity)
        self.context_senses.on_events(events)
        if "USER_RETURNED" in events:
            self.director.on_user_returned(now=now)
        if events:
            self.drives.stimulate("novelty" if "ACTIVITY_CHANGED" in events else "app")

        # Amostra rotina a cada 60 segundos
        if now - self._last_routine_tick >= 60.0:
            self._last_routine_tick = now
            self.routine.record(self._activity)

    def _tick_think(self) -> None:
        now = time.monotonic()
        dt = min(1.0, max(0.01, now - self._last_think_t))
        self._last_think_t = now

        if self.paused or self.panic_hidden or self.fullscreen_paused:
            return

        circadian = compute_circadian(override_hour=self.settings.time_override_hour)
        weather = self.weather_service.current(override_mode=self.settings.weather_mode)
        caressing = now < self._caress_until
        user_away = self._activity == "AWAY"
        engaged = self._activity in ("PROGRAMMING", "AI_STUDIO", "DESIGNING", "GAMING")

        self.drives.update(
            dt=dt,
            asleep=self.director.asleep,
            arousal=self.emotion_decoder.state.arousal,
            user_away=user_away,
            engaged=engaged,
            night_factor=circadian.night_factor,
        )
        self.conditioning.tick(now)
        self.episodic.tick(now)

        intensities = self.context_senses.update(
            activity=self._activity,
            idle_seconds=self._idle_s,
            drives_channels=self.drives.channels(),
            circadian=circadian,
            weather=weather,
            telemetry=self._telemetry,
            caressing=caressing,
            mouse_moving=self._mouse_moving,
            anticipate=self.conditioning.strength(),
        )
        self.brain.stimulate(intensities)
        self.brain.step(dt * 1000.0)

        emotion = self.emotion_decoder.update(self.brain.expression_rates(), dt=dt, asleep=self.director.asleep)
        out = self.director.step(
            now=now,
            activity=self._activity,
            circadian=circadian,
            weather=weather,
            emotion=emotion,
            decision_rates=self.brain.decision_rates(),
            whispers_enabled=self.settings.whispers_enabled,
            outfit_override=self.settings.outfit_override,
            test_mode=self.settings.test_mode,
        )

        # Atualiza estado visual do canvas
        self.canvas.circadian = circadian
        self.canvas.weather = weather
        self.canvas.emotion = emotion
        self.canvas.asleep = out.asleep
        self.canvas.affinity = self.drives.affinity
        self.canvas.activity = self._activity
        self.canvas.avatar.outfit = out.outfit
        self.canvas.scene.set_whisper(out.whisper_text, out.whisper_alpha)

        if out.target_hotspot and out.target_hotspot in self.canvas.scene.stage.hotspots:
            hs = self.canvas.scene.stage.hotspots[out.target_hotspot]
            self.canvas.avatar.walk_to(hs.x, hs.y, arrive_action=hs.arrive_action)
        if out.emote:
            self.canvas.avatar.show_emote(out.emote)

        if out.burst_fx:
            hc = self.canvas.avatar.head_rect.center()
            if not self.canvas.avatar.head_rect.isEmpty():
                self.canvas.particles.emit_mood_burst(out.burst_fx, hc.x(), hc.y(), count=5, accent=self.persona.accent_color)

        if self.neural_monitor.isVisible():
            self.neural_monitor.refresh(self.telemetry_snapshot(weather))

    def telemetry_snapshot(self, weather=None) -> dict:
        w = weather or self.weather_service.current(self.settings.weather_mode)
        return {
            "persona": self.persona.name,
            "mood_label": self.emotion_decoder.state.label,
            "outfit": self.director.current_outfit,
            "activity": self._activity,
            "weather": f"{w.label_pt} ({w.temperature_c:.0f}°C)",
            "energy": self.drives.energy,
            "stimulation": self.drives.stimulation,
            "contact": self.drives.contact,
            "affinity": self.drives.affinity,
            "bond_stage": self.drives.bond_stage,
            "brain": self.brain.snapshot(),
            "conditioning": dict(self.conditioning.V),
            "episodic_prefs": self.episodic.preferences(top=5),
            "routine": self.routine.summary(),
        }

    # ---------------- Interações & Ações ----------------

    def _on_canvas_caress(self, _intensity: float) -> None:
        now = time.monotonic()
        self._caress_until = now + 0.55
        self.director.on_caress(now=now)

    def _on_canvas_poke(self, _zone: str) -> None:
        self.context_senses.kick("POKE", 0.85)
        self.director.on_poke()

    def _on_ground_clicked(self, nx: float, ny: float) -> None:
        """Click-to-move estilo Ragnarok Online: chama a avatar para caminhar até o ponto clicado."""
        self.canvas.avatar.walk_to(nx, ny, arrive_action="idle")
        self.canvas.avatar.show_emote("exclamation", duration=1.8)
        self.drives.stimulate("novelty", scale=0.4)

    def _on_whisper_dismissed(self) -> None:
        self.context_senses.kick("DISMISS", 0.75)
        self.director.dismiss_whisper()

    def _on_cursor_approaching(self, near: bool) -> None:
        self.conditioning.set_cue("APPROACH", near, time.monotonic())

    def _trigger_caress(self) -> None:
        now = time.monotonic()
        self._caress_until = now + 1.8
        self.canvas.avatar.impulse(vy=-120.0, tilt=3.0)
        self.director.on_caress(now=now)

    def _trigger_gift(self) -> None:
        self.context_senses.kick("GIFT", 1.0)
        self.canvas.avatar.impulse(vy=-180.0, tilt=-3.5)
        self.director.on_gift("esse mimo especial")

    def _trigger_whisper(self) -> None:
        circ = compute_circadian(self.settings.time_override_hour)
        w = self.weather_service.current(self.settings.weather_mode)
        cat = self.director._whisper_category_for(self._activity, circ, w, self.emotion_decoder.state)
        self.director.show_whisper(self.director._pick_whisper(cat), duration=7.5)

    def _toggle_sleep(self) -> None:
        self.director.asleep = not self.director.asleep
        if self.director.asleep:
            self.episodic.consolidate()

    def _refresh_weather(self) -> None:
        self.weather_service.refresh_async(
            city=self.settings.weather_city,
            lat=self.settings.weather_lat,
            lon=self.settings.weather_lon,
        )

    # ---------------- ComfyUI Bridge (Read-Only) ----------------

    def _probe_comfy_ui(self) -> None:
        st = self.comfy.probe()
        if st.online:
            self.control_center.set_comfy_status(
                f"ONLINE · Checkpoint: {st.checkpoint} · RemBG: {'Sim' if st.has_rembg else 'Não'} · PAG: {'Sim' if st.has_pag else 'Não'}"
            )
        else:
            self.control_center.set_comfy_status("OFFLINE (usando assets locais + motor procedural)")

    def _generate_comfy_avatar(self, outfit_key: str) -> None:
        dest = self.paths.persona_generated_assets(self.persona.id)
        self.control_center.set_gen_progress(f"⏳ Gerando avatar {self.persona.name} ({outfit_key}) via ComfyUI...")
        self.comfy.generate_avatar_async(
            persona=self.persona,
            outfit_key=outfit_key,
            dest_dir=dest,
            on_done=lambda p: self.bridge.comfy_avatar_done.emit(str(p)),
            on_error=lambda e: self.bridge.comfy_error.emit(e),
        )

    def _generate_comfy_scene(self, scene_id: str, variant: str) -> None:
        dest = self.paths.scene_generated_assets(scene_id)
        self.control_center.set_gen_progress(f"⏳ Gerando cenário {scene_id} ({variant}) via ComfyUI...")
        self.comfy.generate_scene_async(
            scene_id=scene_id,
            variant=variant,
            dest_dir=dest,
            on_done=lambda p: self.bridge.comfy_scene_done.emit(str(p)),
            on_error=lambda e: self.bridge.comfy_error.emit(e),
        )

    def _generate_comfy_pack(self, scene_id: str) -> None:
        p_dest = self.paths.persona_generated_assets(self.persona.id)
        s_dest = self.paths.scene_generated_assets(scene_id)
        if self.settings.render_style == "world_sprite":
            self.control_center.set_pack_progress(0, 1, f"🚀 Gerando Pack Mundo Vivo 2.5D de {self.persona.name}...")
            self.comfy.generate_world_pack_async(
                persona=self.persona,
                scene_id=scene_id,
                persona_dest_dir=p_dest,
                scene_dest_dir=s_dest,
                preset_name=self.settings.comfyui_preset,
                skip_existing=True,
                on_progress=lambda cur, tot, lbl: self.bridge.comfy_pack_progress.emit(cur, tot, lbl),
                on_asset=lambda kind, p: self.bridge.comfy_pack_asset.emit(kind, str(p)),
                on_error=lambda e: self.bridge.comfy_error.emit(e),
            )
            return
        self.control_center.set_pack_progress(0, 1, f"🚀 Iniciando pack completo de {self.persona.name}...")
        self.comfy.generate_full_pack_async(
            persona=self.persona,
            scene_id=scene_id,
            persona_dest_dir=p_dest,
            scene_dest_dir=s_dest,
            skip_existing=True,
            on_progress=lambda cur, tot, lbl: self.bridge.comfy_pack_progress.emit(cur, tot, lbl),
            on_asset=lambda kind, p: self.bridge.comfy_pack_asset.emit(kind, str(p)),
            on_error=lambda e: self.bridge.comfy_error.emit(e),
        )

    def _on_comfy_pack_progress(self, cur: int, tot: int, label: str) -> None:
        self.control_center.set_pack_progress(cur, tot, label)

    def _on_comfy_pack_asset(self, _kind: str, _path_str: str) -> None:
        self._reload_assets()

    def _create_custom_persona(self, persona) -> None:
        save_persona(persona, self.paths.personas_dir)
        self.control_center.refresh_personas(select_id=persona.id)
        new_s = Settings(**self.settings.__dict__)
        new_s.persona_id = persona.id
        self.apply_settings(new_s)
        self.control_center.set_status_text(f"✨ Nova persona criada: {persona.name}!")

    def _update_asset_coverage(self) -> None:
        self.control_center.set_asset_coverage(
            self.canvas.avatar.available_sprite_keys(),
            self.canvas.scene.available_scene_keys(),
        )

    def _on_comfy_avatar_done(self, path_str: str) -> None:
        self._reload_assets()
        self.control_center.set_gen_progress(f"✅ Sprite da avatar pronto e aplicado: {Path(path_str).name}")
        self._trigger_gift()

    def _on_comfy_scene_done(self, path_str: str) -> None:
        self._reload_assets()
        self.control_center.set_gen_progress(f"✅ Cenário pronto e aplicado: {Path(path_str).name}")

    def _on_comfy_error(self, err: str) -> None:
        self.control_center.set_gen_progress(f"⚠️ ComfyUI: {err}")

    def _reload_assets(self) -> None:
        self.canvas.avatar.reload_sprites()
        self.canvas.scene.reload_scene_images()
        self._update_asset_coverage()
        self.canvas.update()

    def _clear_generated_assets(self) -> None:
        remove_tree(self.paths.generated_dir)
        self._reload_assets()
        self.control_center.set_gen_progress("🎨 Assets gerados limpos — renderização procedural ativa.")

    # ---------------- Sessão, Visibilidade & Persistência ----------------

    def show_control_center(self) -> None:
        self.control_center.show()
        self.control_center.raise_()
        self.control_center.activateWindow()

    def show_neural_monitor(self) -> None:
        self.neural_monitor.refresh(self.telemetry_snapshot())
        self.neural_monitor.show()
        self.neural_monitor.raise_()
        self.neural_monitor.activateWindow()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.tray:
            self.tray.set_paused_label(self.paused)
        self.control_center.set_status_text("Pausado" if self.paused else "Em execução")

    def toggle_display_mode(self) -> None:
        next_mode = "preview" if self.settings.mode == "wallpaper" else "wallpaper"
        self.settings.mode = next_mode
        self._apply_window_mode(next_mode)
        self.settings.save(self.paths.settings_file)

    def toggle_panic_hide(self) -> None:
        self.panic_hidden = not self.panic_hidden
        if self.panic_hidden:
            self.canvas.hide()
            self.control_center.hide()
            self.neural_monitor.hide()
            log("[app] Pânico ativado (Ctrl+Alt+Shift+W): wallpaper oculto.")
        else:
            self.canvas.show()
            log("[app] Pânico desativado: wallpaper restaurado.")

    def _clear_memory(self) -> None:
        remove_tree(self.paths.data_dir / "personas")
        self._init_cognition(self.settings.persona_id)
        log("[app] Memória neural zerada a pedido do usuário.")

    def save_all(self) -> None:
        self.brain.save(self.mem_paths.brain)
        self.drives.save(self.mem_paths.drives)
        self.conditioning.save()
        self.episodic.save()
        self.routine.save()
        self.settings.save(self.paths.settings_file)

    def shutdown(self) -> None:
        log("[app] Encerrando IAWallpaper com salvamento limpo...")
        for t in (self.t_frame, self.t_think, self.t_sense, self.t_weather, self.t_save):
            t.stop()
        self.save_all()
        if self.attachment.attached:
            detach_from_desktop(int(self.canvas.winId()))
            self.attachment = DesktopAttachment(False, "fallback")
        if self.tray:
            self.tray.hide()
        self.control_center.close()
        self.neural_monitor.close()
        self.canvas.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()
