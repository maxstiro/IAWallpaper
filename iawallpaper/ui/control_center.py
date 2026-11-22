"""CONTROL CENTER — Central de Controle estilo Wallpaper Engine para configurar cenário, clima, avatar, ComfyUI e sistema."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..comfy.workflows import SCENE_PRESETS
from ..config import Settings
from ..core.persona import BUILTIN_PERSONAS, list_personas
from .theme import DARK_STUDIO_QSS


class ControlCenterWindow(QWidget):
    """Interface gráfica principal para controlar o IAWallpaper em tempo real."""

    settings_changed = Signal(object)       # emite novo Settings
    caress_requested = Signal()
    gift_requested = Signal()
    whisper_requested = Signal()
    toggle_sleep_requested = Signal()
    refresh_weather_requested = Signal()
    open_monitor_requested = Signal()
    comfy_probe_requested = Signal()
    comfy_gen_avatar_requested = Signal(str)       # outfit_key
    comfy_gen_scene_requested = Signal(str, str)   # scene_id, variant
    reload_assets_requested = Signal()
    clear_generated_requested = Signal()
    clear_memory_requested = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IAWallpaper — Central de Controle")
        self.resize(700, 560)
        self.setStyleSheet(DARK_STUDIO_QSS)
        self._settings = settings.sanitized()
        self._building = True

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel("✦ IAWallpaper Studio — Wallpaper Dinâmico & Waifu Cognitiva")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #8ec5ff;")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_scene_tab(), "🌄 Cenário & Clima")
        tabs.addTab(self._build_avatar_tab(), "✨ Avatar & Aparência")
        tabs.addTab(self._build_comfy_tab(), "🎨 ComfyUI Studio Bridge")
        tabs.addTab(self._build_system_tab(), "⚙️ Sistema & Memória")
        root.addWidget(tabs, 1)

        footer = QHBoxLayout()
        self.status_lbl = QLabel("Pronto · Modo Wallpaper Engine ativo")
        self.status_lbl.setStyleSheet("color: #9bb8e8; font-size: 12px;")
        btn_mon = QPushButton("🧠 Abrir Monitor Neural")
        btn_mon.clicked.connect(self.open_monitor_requested.emit)
        footer.addWidget(self.status_lbl, 1)
        footer.addWidget(btn_mon)
        root.addLayout(footer)

        self._load_into_widgets(self._settings)
        self._building = False

    def _build_scene_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g_mode = QGroupBox("Exibição & Performance")
        f = QFormLayout(g_mode)
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Wallpaper Nativo (Atrás dos Ícones)", "wallpaper")
        self.cb_mode.addItem("Janela Preview Interativa", "preview")
        self.cb_mode.currentIndexChanged.connect(self._emit_settings)

        self.cb_scene = QComboBox()
        for sid, info in SCENE_PRESETS.items():
            self.cb_scene.addItem(info["label"], sid)
        self.cb_scene.currentIndexChanged.connect(self._emit_settings)

        self.cb_fps = QComboBox()
        self.cb_fps.addItem("60 FPS (Fluido)", 60)
        self.cb_fps.addItem("30 FPS (Econômico)", 30)
        self.cb_fps.currentIndexChanged.connect(self._emit_settings)

        self.chk_autopause = QCheckBox("Pausar automaticamente em jogos/vídeos em tela cheia")
        self.chk_autopause.stateChanged.connect(self._emit_settings)

        f.addRow("Modo de Exibição:", self.cb_mode)
        f.addRow("Cenário Base:", self.cb_scene)
        f.addRow("Taxa de Quadros:", self.cb_fps)
        f.addRow("", self.chk_autopause)
        layout.addWidget(g_mode)

        g_atmo = QGroupBox("Ciclo Dia/Noite & Clima Dinâmico")
        fa = QFormLayout(g_atmo)

        self.chk_real_time = QCheckBox("Usar relógio real do sistema")
        self.chk_real_time.stateChanged.connect(self._on_time_mode_toggled)

        time_row = QHBoxLayout()
        self.sl_hour = QSlider(Qt.Horizontal)
        self.sl_hour.setRange(0, 48)  # passos de 0.5h
        self.sl_hour.valueChanged.connect(self._on_hour_changed)
        self.lbl_hour = QLabel("18:00")
        self.lbl_hour.setMinimumWidth(48)
        time_row.addWidget(self.sl_hour, 1)
        time_row.addWidget(self.lbl_hour)

        self.cb_weather = QComboBox()
        for label, key in [
            ("Automático (Clima Real Open-Meteo)", "auto"),
            ("Céu Limpo", "clear"),
            ("Nublado", "cloudy"),
            ("Chuva", "rain"),
            ("Tempestade com Relâmpagos", "storm"),
            ("Neve", "snow"),
            ("Neblina", "fog"),
        ]:
            self.cb_weather.addItem(label, key)
        self.cb_weather.currentIndexChanged.connect(self._emit_settings)

        city_row = QHBoxLayout()
        self.ed_city = QLineEdit()
        self.ed_city.setPlaceholderText("Cidade (vazio = geolocalização automática)")
        self.ed_city.editingFinished.connect(self._emit_settings)
        btn_weather = QPushButton("Atualizar")
        btn_weather.clicked.connect(self.refresh_weather_requested.emit)
        city_row.addWidget(self.ed_city, 1)
        city_row.addWidget(btn_weather)

        self.sl_parallax = QSlider(Qt.Horizontal)
        self.sl_parallax.setRange(0, 20)
        self.sl_parallax.valueChanged.connect(self._emit_settings)

        self.sl_particles = QSlider(Qt.Horizontal)
        self.sl_particles.setRange(0, 20)
        self.sl_particles.valueChanged.connect(self._emit_settings)

        fa.addRow("", self.chk_real_time)
        fa.addRow("Hora Simulada:", time_row)
        fa.addRow("Clima:", self.cb_weather)
        fa.addRow("Localização:", city_row)
        fa.addRow("Paralaxe do Cursor:", self.sl_parallax)
        fa.addRow("Densidade de Partículas:", self.sl_particles)
        layout.addWidget(g_atmo)
        layout.addStretch(1)
        return w

    def _build_avatar_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g_char = QGroupBox("Personalidade & Aparência Dinâmica")
        f = QFormLayout(g_char)

        self.cb_persona = QComboBox()
        for pid in list_personas():
            p = BUILTIN_PERSONAS.get(pid)
            label = f"{p.name} — {p.title}" if p else pid.title()
            self.cb_persona.addItem(label, pid)
        self.cb_persona.currentIndexChanged.connect(self._emit_settings)

        self.cb_outfit = QComboBox()
        for label, key in [
            ("Automático (Reage ao Clima, Hora e Atividade)", ""),
            ("Casual", "casual"),
            ("Estúdio / Óculos (Foco)", "focus"),
            ("Chuva / Moletom", "rainy"),
            ("Aconchegante (Cozy)", "cozy"),
            ("Pijama / Noite", "nightwear"),
            ("Astral / Gala Noturna", "starlight"),
        ]:
            self.cb_outfit.addItem(label, key)
        self.cb_outfit.currentIndexChanged.connect(self._emit_settings)

        self.sl_avatar_scale = QSlider(Qt.Horizontal)
        self.sl_avatar_scale.setRange(60, 150)
        self.sl_avatar_scale.valueChanged.connect(self._emit_settings)

        self.sl_avatar_x = QSlider(Qt.Horizontal)
        self.sl_avatar_x.setRange(20, 85)
        self.sl_avatar_x.valueChanged.connect(self._emit_settings)

        self.chk_whispers = QCheckBox("Permitir sussurros contextuais na área de trabalho")
        self.chk_whispers.stateChanged.connect(self._emit_settings)

        f.addRow("Personagem:", self.cb_persona)
        f.addRow("Traje:", self.cb_outfit)
        f.addRow("Escala do Avatar:", self.sl_avatar_scale)
        f.addRow("Posição Horizontal:", self.sl_avatar_x)
        f.addRow("", self.chk_whispers)
        layout.addWidget(g_char)

        g_int = QGroupBox("Interações Rápidas & Treino Positivo")
        row = QHBoxLayout(g_int)
        b_pat = QPushButton("♥ Fazer Carinho")
        b_pat.setObjectName("primaryBtn")
        b_pat.clicked.connect(self.caress_requested.emit)
        b_gift = QPushButton("🎁 Dar Mimo")
        b_gift.clicked.connect(self.gift_requested.emit)
        b_say = QPushButton("💬 Sussurrar")
        b_say.clicked.connect(self.whisper_requested.emit)
        b_sleep = QPushButton("💤 Cochilar / Acordar")
        b_sleep.clicked.connect(self.toggle_sleep_requested.emit)
        for b in (b_pat, b_gift, b_say, b_sleep):
            row.addWidget(b)
        layout.addWidget(g_int)
        layout.addStretch(1)
        return w

    def _build_comfy_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g_conn = QGroupBox("Conexão Read-Only com ComfyUI Local")
        f = QFormLayout(g_conn)
        url_row = QHBoxLayout()
        self.ed_comfy_url = QLineEdit()
        self.ed_comfy_url.editingFinished.connect(self._emit_settings)
        btn_probe = QPushButton("Testar Conexão")
        btn_probe.clicked.connect(self.comfy_probe_requested.emit)
        url_row.addWidget(self.ed_comfy_url, 1)
        url_row.addWidget(btn_probe)

        self.lbl_comfy_status = QLabel("Status: clique em Testar Conexão")
        self.lbl_comfy_status.setStyleSheet("color: #9ed0ff;")
        f.addRow("Endpoint HTTP:", url_row)
        f.addRow("Diagnóstico:", self.lbl_comfy_status)
        layout.addWidget(g_conn)

        g_gen = QGroupBox("Gerador de Assets Dinâmicos (Avatar RGBA + Cenários)")
        vg = QVBoxLayout(g_gen)
        info = QLabel(
            "Gera variações da avatar com recorte transparente (isnet-anime RemBG) e cenários widescreen "
            "para Dia, Pôr do Sol, Noite e Chuva usando seu ComfyUI local — sem alterar nada no ComfyUI Studio."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b8c9eb;")
        vg.addWidget(info)

        row1 = QHBoxLayout()
        self.cb_gen_outfit = QComboBox()
        for key in ("casual", "focus", "rainy", "cozy", "nightwear", "starlight"):
            self.cb_gen_outfit.addItem(f"Traje: {key}", key)
        btn_gen_av = QPushButton("✨ Gerar Sprite da Waifu (RGBA)")
        btn_gen_av.setObjectName("primaryBtn")
        btn_gen_av.clicked.connect(lambda: self.comfy_gen_avatar_requested.emit(self.cb_gen_outfit.currentData()))
        row1.addWidget(self.cb_gen_outfit, 1)
        row1.addWidget(btn_gen_av, 2)
        vg.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_gen_variant = QComboBox()
        for label, key in [("Dia", "day"), ("Pôr do Sol", "sunset"), ("Noite Estrelada", "night"), ("Chuva", "rain")]:
            self.cb_gen_variant.addItem(f"Cenário: {label}", key)
        btn_gen_sc = QPushButton("🌄 Gerar Fundo do Cenário Atual")
        btn_gen_sc.clicked.connect(
            lambda: self.comfy_gen_scene_requested.emit(self.cb_scene.currentData(), self.cb_gen_variant.currentData())
        )
        row2.addWidget(self.cb_gen_variant, 1)
        row2.addWidget(btn_gen_sc, 2)
        vg.addLayout(row2)

        row3 = QHBoxLayout()
        btn_reload = QPushButton("🔄 Recarregar Assets do Disco")
        btn_reload.clicked.connect(self.reload_assets_requested.emit)
        btn_clear_gen = QPushButton("🎨 Voltar ao Render Procedural")
        btn_clear_gen.clicked.connect(self.clear_generated_requested.emit)
        row3.addWidget(btn_reload)
        row3.addWidget(btn_clear_gen)
        vg.addLayout(row3)

        self.lbl_gen_progress = QLabel("")
        self.lbl_gen_progress.setStyleSheet("color: #7ee787; font-weight: 600;")
        vg.addWidget(self.lbl_gen_progress)

        layout.addWidget(g_gen)
        layout.addStretch(1)
        return w

    def _build_system_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        g_sys = QGroupBox("Sistema, Atalhos & Privacidade")
        v = QVBoxLayout(g_sys)

        self.chk_autostart = QCheckBox("Iniciar IAWallpaper automaticamente ao entrar no Windows")
        self.chk_autostart.stateChanged.connect(self._emit_settings)

        self.chk_test_mode = QCheckBox("Modo Teste (decisões e sussurros acelerados)")
        self.chk_test_mode.stateChanged.connect(self._emit_settings)

        priv = QLabel(
            "Privacidade estrita: o IAWallpaper lê apenas o nome do processo ativo, tempo ocioso, "
            "tela cheia e carga básica da CPU. Nunca lê títulos de janela, conteúdo de tela nem teclas.\n"
            "Atalho global de pânico: Ctrl + Alt + Shift + W (oculta/pausa instantaneamente)."
        )
        priv.setWordWrap(True)
        priv.setStyleSheet("color: #aebfe0; padding: 6px 0;")

        btn_reset = QPushButton("🗑️ Apagar Memória Neural & Aprendizado")
        btn_reset.setObjectName("dangerBtn")
        btn_reset.clicked.connect(self._confirm_clear_memory)

        v.addWidget(self.chk_autostart)
        v.addWidget(self.chk_test_mode)
        v.addWidget(priv)
        v.addWidget(btn_reset)
        layout.addWidget(g_sys)
        layout.addStretch(1)
        return w

    def _confirm_clear_memory(self) -> None:
        ans = QMessageBox.question(
            self,
            "Apagar Memória Neural",
            "Isso apagará todas as sinapses aprendidas, afinidade e rotina salva. Continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            self.clear_memory_requested.emit()

    def _load_into_widgets(self, s: Settings) -> None:
        self._set_combo(self.cb_mode, s.mode)
        self._set_combo(self.cb_scene, s.scene_id)
        self._set_combo(self.cb_fps, s.fps_cap)
        self.chk_autopause.setChecked(s.auto_pause_fullscreen)

        real_t = s.time_override_hour is None
        self.chk_real_time.setChecked(real_t)
        self.sl_hour.setEnabled(not real_t)
        hr = 18.0 if real_t else float(s.time_override_hour)
        self.sl_hour.setValue(int(round(hr * 2)))
        self._update_hour_label(hr)

        self._set_combo(self.cb_weather, s.weather_mode)
        self.ed_city.setText(s.weather_city)
        self.sl_parallax.setValue(int(round(s.parallax_strength * 10)))
        self.sl_particles.setValue(int(round(s.particle_density * 10)))

        self._set_combo(self.cb_persona, s.persona_id)
        self._set_combo(self.cb_outfit, s.outfit_override or "")
        self.sl_avatar_scale.setValue(int(round(s.avatar_scale * 100)))
        self.sl_avatar_x.setValue(int(round(s.avatar_x_ratio * 100)))
        self.chk_whispers.setChecked(s.whispers_enabled)

        self.ed_comfy_url.setText(s.comfyui_url)
        self.chk_autostart.setChecked(s.start_with_windows)
        self.chk_test_mode.setChecked(s.test_mode)

    @staticmethod
    def _set_combo(cb: QComboBox, value) -> None:
        idx = cb.findData(value)
        if idx >= 0:
            cb.setCurrentIndex(idx)

    def _update_hour_label(self, hr: float) -> None:
        h = int(hr) % 24
        m = int(round((hr - int(hr)) * 60)) % 60
        self.lbl_hour.setText(f"{h:02d}:{m:02d}")

    def _on_time_mode_toggled(self) -> None:
        self.sl_hour.setEnabled(not self.chk_real_time.isChecked())
        self._emit_settings()

    def _on_hour_changed(self) -> None:
        self._update_hour_label(self.sl_hour.value() / 2.0)
        self._emit_settings()

    def _emit_settings(self) -> None:
        if self._building:
            return
        outfit_val = self.cb_outfit.currentData() or None
        time_override = None if self.chk_real_time.isChecked() else (self.sl_hour.value() / 2.0)
        s = Settings(
            persona_id=self.cb_persona.currentData() or "mira",
            scene_id=self.cb_scene.currentData() or "sky_sanctuary",
            mode=self.cb_mode.currentData() or "wallpaper",
            fps_cap=int(self.cb_fps.currentData() or 60),
            auto_pause_fullscreen=self.chk_autopause.isChecked(),
            parallax_strength=self.sl_parallax.value() / 10.0,
            particle_density=self.sl_particles.value() / 10.0,
            avatar_scale=self.sl_avatar_scale.value() / 100.0,
            avatar_x_ratio=self.sl_avatar_x.value() / 100.0,
            whispers_enabled=self.chk_whispers.isChecked(),
            weather_mode=self.cb_weather.currentData() or "auto",
            weather_city=self.ed_city.text().strip(),
            time_override_hour=time_override,
            outfit_override=outfit_val,
            comfyui_url=self.ed_comfy_url.text().strip() or "http://127.0.0.1:8188",
            comfyui_enabled=True,
            start_with_windows=self.chk_autostart.isChecked(),
            test_mode=self.chk_test_mode.isChecked(),
        ).sanitized()
        self._settings = s
        self.settings_changed.emit(s)

    def set_status_text(self, text: str) -> None:
        self.status_lbl.setText(text)

    def set_comfy_status(self, text: str) -> None:
        self.lbl_comfy_status.setText(text)

    def set_gen_progress(self, text: str) -> None:
        self.lbl_gen_progress.setText(text)
