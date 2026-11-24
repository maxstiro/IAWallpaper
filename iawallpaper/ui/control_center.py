"""CONTROL CENTER — Central de Controle estilo Wallpaper Engine para configurar cenário, clima, avatar, ComfyUI e sistema."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..comfy.presets import load_comfy_presets
from ..comfy.workflows import PACK_EXPRESSIONS, PACK_OUTFITS, PACK_SCENE_VARIANTS, SCENE_PRESETS
from ..config import Settings
from ..core.persona import BUILTIN_PERSONAS, create_custom_persona, list_personas, load_persona
from .theme import DARK_STUDIO_QSS


class CustomPersonaDialog(QDialog):
    """Diálogo limpo para criar uma nova persona waifu personalizada com tags e temperamento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Criar Nova Waifu Personalizada")
        self.resize(460, 290)
        self.setStyleSheet(DARK_STUDIO_QSS)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("Ex: Luna, Aria, Yuki...")
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("Ex: Guardiã da Lua / Companheira Estelar")
        self.ed_tags = QLineEdit()
        self.ed_tags.setPlaceholderText("Ex: long_silver_hair, violet_eyes, fox_ears, gentle_smile")

        self.cb_temp = QComboBox()
        self.cb_temp.addItem("Carinhosa & Aconchegante (Cozy)", "cozy")
        self.cb_temp.addItem("Divertida & Brincalhona (Playful)", "playful")
        self.cb_temp.addItem("Focada em Código & Criação (Focused)", "focused")
        self.cb_temp.addItem("Notívaga & Cyberpunk (Night Owl)", "night_owl")

        form.addRow("Nome:", self.ed_name)
        form.addRow("Título:", self.ed_title)
        form.addRow("Tags de Aparência:", self.ed_tags)
        form.addRow("Temperamento Neural:", self.cb_temp)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def build_persona(self):
        return create_custom_persona(
            name=self.ed_name.text().strip() or "Luna",
            title=self.ed_title.text().strip() or "Companheira Personalizada",
            character_tags=self.ed_tags.text().strip() or "long_silver_hair, violet_eyes, gentle_smile",
            temperament_preset=self.cb_temp.currentData() or "cozy",
        )


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
    comfy_gen_pack_requested = Signal(str)         # scene_id
    create_persona_requested = Signal(object)      # Persona
    reload_assets_requested = Signal()
    clear_generated_requested = Signal()
    clear_memory_requested = Signal()

    def __init__(self, settings: Settings, personas_dir: Path | None = None, vrm_models: list[Path] | None = None, character_packs: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IAWallpaper — Central de Controle")
        self.resize(720, 640)
        self.setStyleSheet(DARK_STUDIO_QSS)
        self._settings = settings.sanitized()
        self._personas_dir = personas_dir
        self._vrm_models: list[Path] = list(vrm_models or [])
        self._character_packs: list[Path] = list(character_packs or [])
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

        persona_row = QHBoxLayout()
        self.cb_persona = QComboBox()
        self._populate_personas()
        self.cb_persona.currentIndexChanged.connect(self._emit_settings)
        btn_new_persona = QPushButton("+ Nova Waifu")
        btn_new_persona.clicked.connect(self._open_new_persona_dialog)
        persona_row.addWidget(self.cb_persona, 1)
        persona_row.addWidget(btn_new_persona)

        self.cb_character = QComboBox()
        self._populate_characters()
        self.cb_character.currentIndexChanged.connect(self._emit_settings)

        self.cb_render_style = QComboBox()
        self.cb_render_style.addItem("✨ Clipes 2D Wan 2.2 · 8 Direções (Arya / Erin · Máximo Reaproveitamento)", "world_sprite")
        self.cb_render_style.addItem("Motor 2.5D Live2D / Spine2D (Malha Elástica GPU)", "live2d_25d")
        self.cb_render_style.addItem("Motor 3D Cel-Shaded (VRM · Giro 360° estilo Tree of Savior)", "vrm_3d")
        self.cb_render_style.addItem("Retrato Visual Novel (Busto 2.5D)", "portrait")
        self.cb_render_style.currentIndexChanged.connect(self._emit_settings)

        vrm_row = QHBoxLayout()
        self.cb_vrm = QComboBox()
        self._populate_vrm_models()
        self.cb_vrm.currentIndexChanged.connect(self._emit_settings)
        btn_import_vrm = QPushButton("📂 Carregar .VRM")
        btn_import_vrm.clicked.connect(self._browse_vrm_file)
        vrm_row.addWidget(self.cb_vrm, 1)
        vrm_row.addWidget(btn_import_vrm)

        self.chk_vrm_recolor = QCheckBox("Adaptar cores do modelo 3D dinamicamente ao traje e persona")
        self.chk_vrm_recolor.stateChanged.connect(self._emit_settings)

        self.cb_outfit = QComboBox()
        for label, key in [
            ("Automático (Reage ao Clima, Hora e Atividade)", ""),
            ("Camisola Casual (Camisetão)", "cozy_shirt"),
            ("Roupa Base", "base"),
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

        f.addRow("Persona (Cérebro):", persona_row)
        f.addRow("Personagem (Wan 2.2):", self.cb_character)
        f.addRow("Motor Visual:", self.cb_render_style)
        f.addRow("Modelo 3D (.vrm):", vrm_row)
        f.addRow("", self.chk_vrm_recolor)
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

        self.cb_comfy_preset = QComboBox()
        self.cb_comfy_preset.addItem("Automático (Primeiro Preset TOP)", "")
        for pr in load_comfy_presets():
            tag = "★ " if pr.is_top else ""
            self.cb_comfy_preset.addItem(f"{tag}{pr.name} ({len(pr.loras)} LoRAs)", pr.name)
        self.cb_comfy_preset.currentIndexChanged.connect(self._emit_settings)

        f.addRow("Endpoint HTTP:", url_row)
        f.addRow("Preset (Read-Only):", self.cb_comfy_preset)
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

        btn_gen_pack = QPushButton("🚀 Gerar Pack Completo Consistente (6 Trajes + 5 Expressões + 4 Cenários)")
        btn_gen_pack.setObjectName("primaryBtn")
        btn_gen_pack.clicked.connect(lambda: self.comfy_gen_pack_requested.emit(self.cb_scene.currentData()))
        vg.addWidget(btn_gen_pack)

        self.pb_pack = QProgressBar()
        self.pb_pack.setRange(0, 100)
        self.pb_pack.setValue(0)
        self.pb_pack.setVisible(False)
        vg.addWidget(self.pb_pack)

        self.lbl_asset_coverage = QLabel("Cobertura de Assets: verificando...")
        self.lbl_asset_coverage.setStyleSheet("color: #9bb8e8; font-size: 12px;")
        self.lbl_asset_coverage.setWordWrap(True)
        vg.addWidget(self.lbl_asset_coverage)

        row1 = QHBoxLayout()
        self.cb_gen_outfit = QComboBox()
        for key in PACK_OUTFITS:
            self.cb_gen_outfit.addItem(f"Traje: {key}", key)
        btn_gen_av = QPushButton("✨ Gerar Traje Individual (RGBA)")
        btn_gen_av.clicked.connect(lambda: self.comfy_gen_avatar_requested.emit(self.cb_gen_outfit.currentData()))
        row1.addWidget(self.cb_gen_outfit, 1)
        row1.addWidget(btn_gen_av, 2)
        vg.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_gen_variant = QComboBox()
        for label, key in [("Dia", "day"), ("Pôr do Sol", "sunset"), ("Noite Estrelada", "night"), ("Chuva", "rain")]:
            self.cb_gen_variant.addItem(f"Cenário: {label}", key)
        btn_gen_sc = QPushButton("🌄 Gerar Horário Individual")
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
        if s.character_id and self.cb_character.findData(s.character_id) < 0:
            self.cb_character.addItem(s.character_id.capitalize(), s.character_id)
        self._set_combo(self.cb_character, s.character_id)
        self._set_combo(self.cb_render_style, s.render_style)
        if s.vrm_model and self.cb_vrm.findData(s.vrm_model) < 0:
            self.cb_vrm.addItem(Path(s.vrm_model).name, s.vrm_model)
        self._set_combo(self.cb_vrm, s.vrm_model)
        self.chk_vrm_recolor.setChecked(s.vrm_dynamic_recolor)
        self._set_combo(self.cb_outfit, s.outfit_override or "")
        self.sl_avatar_scale.setValue(int(round(s.avatar_scale * 100)))
        self.sl_avatar_x.setValue(int(round(s.avatar_x_ratio * 100)))
        self.chk_whispers.setChecked(s.whispers_enabled)

        self.ed_comfy_url.setText(s.comfyui_url)
        self._set_combo(self.cb_comfy_preset, s.comfyui_preset)
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
            character_id=self.cb_character.currentData() or self._settings.character_id or "arya",
            scene_id=self.cb_scene.currentData() or "fairy_glade",
            mode=self.cb_mode.currentData() or "wallpaper",
            render_style=self.cb_render_style.currentData() or "world_sprite",
            vrm_model=self.cb_vrm.currentData() or "",
            vrm_dynamic_recolor=self.chk_vrm_recolor.isChecked(),
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
            comfyui_preset=self.cb_comfy_preset.currentData() or "RawSexyGlowingGemPencil(TOP)",
            comfyui_enabled=True,
            start_with_windows=self.chk_autostart.isChecked(),
            test_mode=self.chk_test_mode.isChecked(),
        ).sanitized()
        self._settings = s
        self.settings_changed.emit(s)

    def _populate_characters(self) -> None:
        self.cb_character.blockSignals(True)
        self.cb_character.clear()
        seen: set[str] = set()
        labels = {
            "arya": "★ Arya — Elfa Loira (Wan 2.2)",
            "erin": "★ Erin — Humana Ruiva (Wan 2.2)",
        }
        for cp in self._character_packs:
            cid = cp.name.lower()
            seen.add(cid)
            self.cb_character.addItem(labels.get(cid, f"★ {cid.capitalize()} (Wan 2.2)"), cid)
        for cid, lbl in labels.items():
            if cid not in seen:
                self.cb_character.addItem(lbl, cid)
        self.cb_character.blockSignals(False)

    def _populate_vrm_models(self) -> None:
        self.cb_vrm.blockSignals(True)
        self.cb_vrm.clear()
        self.cb_vrm.addItem("★ Arya — Elfa Loira (Base)", "elfa_loira")
        self.cb_vrm.addItem("★ Freya — Humana Ruiva (Base 3D HD)", "humana_ruiva")
        self.cb_vrm.addItem("★ Airi — Androide Rosa (Base 3D HD)", "androide_rosa")
        self.cb_vrm.addItem("★ Lilith — Vampira Cabelos Pretos (Base 3D HD)", "vampira_negra")
        self.cb_vrm.addItem("Automático (Melhor .VRM externo disponível)", "")
        for fp in self._vrm_models:
            self.cb_vrm.addItem(fp.name, fp.name)
        self.cb_vrm.blockSignals(False)

    def _browse_vrm_file(self) -> None:
        fname, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Modelo 3D Anime (.vrm / .glb)",
            "",
            "Modelos VRM/glTF (*.vrm *.glb);;Todos os arquivos (*.*)",
        )
        if not fname:
            return
        p = Path(fname)
        if self.cb_vrm.findData(str(p)) < 0:
            self.cb_vrm.addItem(f"★ {p.name}", str(p))
        self._set_combo(self.cb_vrm, str(p))
        self._set_combo(self.cb_render_style, "vrm_3d")
        self._emit_settings()

    def _populate_personas(self) -> None:
        curr = self.cb_persona.currentData() if self.cb_persona.count() else self._settings.persona_id
        self.cb_persona.blockSignals(True)
        self.cb_persona.clear()
        for pid in list_personas(self._personas_dir):
            p = load_persona(pid, self._personas_dir) if self._personas_dir else BUILTIN_PERSONAS.get(pid)
            label = f"{p.name} — {p.title}" if p else pid.title()
            self.cb_persona.addItem(label, pid)
        self._set_combo(self.cb_persona, curr)
        self.cb_persona.blockSignals(False)

    def _open_new_persona_dialog(self) -> None:
        dlg = CustomPersonaDialog(self)
        if dlg.exec() == QDialog.Accepted:
            persona = dlg.build_persona()
            self.create_persona_requested.emit(persona)

    def refresh_personas(self, select_id: str | None = None) -> None:
        self._populate_personas()
        if select_id:
            self._building = True
            self._set_combo(self.cb_persona, select_id)
            self._building = False

    def set_asset_coverage(self, avatar_keys: set[str], scene_keys: set[str]) -> None:
        outfits_ok = [k for k in PACK_OUTFITS if k in avatar_keys]
        exprs_ok = [k for k in PACK_EXPRESSIONS if f"casual_{k}" in avatar_keys or k in avatar_keys]
        scenes_ok = [k for k in PACK_SCENE_VARIANTS if k in scene_keys]
        self.lbl_asset_coverage.setText(
            f"Trajes AI: {len(outfits_ok)}/{len(PACK_OUTFITS)} ({', '.join(outfits_ok) or 'procedural'}) · "
            f"Expressões AI: {len(exprs_ok)}/{len(PACK_EXPRESSIONS)} · "
            f"Cenários: {len(scenes_ok)}/{len(PACK_SCENE_VARIANTS)} ({', '.join(scenes_ok) or 'procedural'})"
        )

    def set_pack_progress(self, current: int, total: int, label: str) -> None:
        self.lbl_gen_progress.setText(label)
        if total > 0:
            self.pb_pack.setVisible(True)
            self.pb_pack.setValue(int((current / total) * 100))
            if current >= total:
                self.pb_pack.setFormat("100% — Concluído!")
            else:
                self.pb_pack.setFormat(f"{current}/{total}")
        else:
            self.pb_pack.setVisible(False)

    def set_status_text(self, text: str) -> None:
        self.status_lbl.setText(text)

    def set_comfy_status(self, text: str) -> None:
        self.lbl_comfy_status.setText(text)

    def set_gen_progress(self, text: str) -> None:
        self.lbl_gen_progress.setText(text)
