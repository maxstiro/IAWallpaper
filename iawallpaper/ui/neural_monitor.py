"""NEURAL MONITOR — Painel ao vivo inspecionando a rede LIF, homeostase, condicionamento e aprendizado."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .theme import DARK_STUDIO_QSS


class NeuralMonitorWindow(QWidget):
    """Exibe em tempo real os canais sensoriais, interneurônios, motores e sinapses aprendidas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IAWallpaper — Monitor Neural & Aprendizado")
        self.resize(840, 620)
        self.setStyleSheet(DARK_STUDIO_QSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.header_lbl = QLabel("Inicializando telemetria neural...")
        self.header_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #8ec5ff;")
        root.addWidget(self.header_lbl)

        # Homeostase & Afinidade
        drives_box = QGroupBox("Homeostase & Vínculo (Drives)")
        dg = QGridLayout(drives_box)
        self.bar_energy = self._make_bar()
        self.bar_stim = self._make_bar()
        self.bar_contact = self._make_bar()
        self.bar_affinity = self._make_bar()
        dg.addWidget(QLabel("Energia"), 0, 0)
        dg.addWidget(self.bar_energy, 0, 1)
        dg.addWidget(QLabel("Estimulação"), 0, 2)
        dg.addWidget(self.bar_stim, 0, 3)
        dg.addWidget(QLabel("Carência"), 1, 0)
        dg.addWidget(self.bar_contact, 1, 1)
        dg.addWidget(QLabel("Afinidade ♥"), 1, 2)
        dg.addWidget(self.bar_affinity, 1, 3)
        root.addWidget(drives_box)

        # Colunas centrais: Motores de Expressão / Decisão e Interneurônios
        mid = QHBoxLayout()
        self.expr_bars: dict[str, QProgressBar] = {}
        self.dec_bars: dict[str, QProgressBar] = {}
        self.inter_bars: dict[str, QProgressBar] = {}

        self.expr_box, self.expr_layout = self._make_scroll_group("Motores de Expressão (Hz)")
        self.dec_box, self.dec_layout = self._make_scroll_group("Motores de Decisão (Hz)")
        self.inter_box, self.inter_layout = self._make_scroll_group("Interneurônios LIF (Hz)")
        mid.addWidget(self.expr_box, 1)
        mid.addWidget(self.dec_box, 1)
        mid.addWidget(self.inter_box, 1)
        root.addLayout(mid, 2)

        # Memória & Aprendizado
        learn_box = QGroupBox("Aprendizado Vivo (Três Fatores · Rescorla-Wagner · Bandit Episódico · Rotina)")
        ll = QVBoxLayout(learn_box)
        self.learn_text = QPlainTextEdit()
        self.learn_text.setReadOnly(True)
        self.learn_text.setMaximumHeight(165)
        ll.addWidget(self.learn_text)
        root.addWidget(learn_box, 1)

    @staticmethod
    def _make_bar() -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(True)
        return bar

    def _make_scroll_group(self, title: str):
        box = QGroupBox(title)
        outer = QVBoxLayout(box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(6)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return box, grid

    def _sync_bars(self, mapping: dict[str, QProgressBar], layout: QGridLayout, values: dict[str, float], max_hz: float) -> None:
        if not mapping:
            for row, name in enumerate(values.keys()):
                lbl = QLabel(name)
                lbl.setStyleSheet("font-size: 11px; color: #b8c9eb;")
                bar = self._make_bar()
                layout.addWidget(lbl, row, 0)
                layout.addWidget(bar, row, 1)
                mapping[name] = bar
        for name, hz in values.items():
            bar = mapping.get(name)
            if bar is not None:
                pct = int(max(0.0, min(100.0, (hz / max_hz) * 100.0)))
                bar.setValue(pct)
                bar.setFormat(f"{hz:.1f} Hz")

    def refresh(self, telemetry: dict) -> None:
        """Atualiza todos os indicadores a partir do snapshot da aplicação."""
        snap = telemetry.get("brain", {})
        self.header_lbl.setText(
            f"{telemetry.get('persona', 'Mira')} · Humor: {telemetry.get('mood_label', 'Serena')} · "
            f"Traje: {telemetry.get('outfit', 'casual')} · Atividade: {telemetry.get('activity', 'IDLE')} · "
            f"Clima: {telemetry.get('weather', 'Céu Limpo')} · Rede: {snap.get('neurons', 0)} neurônios / {snap.get('synapses', 0)} sinapses"
        )

        self.bar_energy.setValue(int(telemetry.get("energy", 0.0) * 100))
        self.bar_stim.setValue(int(telemetry.get("stimulation", 0.0) * 100))
        self.bar_contact.setValue(int(telemetry.get("contact", 0.0) * 100))
        aff = float(telemetry.get("affinity", 0.0))
        self.bar_affinity.setValue(int(aff))
        self.bar_affinity.setFormat(f"{aff:.1f}% ({telemetry.get('bond_stage', 'curiosa')})")

        self._sync_bars(self.expr_bars, self.expr_layout, snap.get("expression", {}), max_hz=22.0)
        self._sync_bars(self.dec_bars, self.dec_layout, snap.get("decision", {}), max_hz=18.0)
        self._sync_bars(self.inter_bars, self.inter_layout, snap.get("inter", {}), max_hz=28.0)

        lines = []
        active_s = [f"{k}={v:.2f}" for k, v in snap.get("sensory", {}).items() if v >= 0.08]
        lines.append("Sentidos ativos: " + (", ".join(active_s) if active_s else "(repouso)"))

        learned = snap.get("learned_top", [])
        if learned:
            l_str = ", ".join(f"{s}→{p} ({w:+.4f})" for s, p, w in learned)
            lines.append(f"Sinapses aprendidas ({snap.get('learn_events', 0)} eventos): {l_str}")
        else:
            lines.append("Sinapses aprendidas: ainda coletando experiências (faça carinho na cabeça!)")

        cond = telemetry.get("conditioning", {})
        c_str = ", ".join(f"{k}={v:.2f}" for k, v in cond.items())
        lines.append(f"Condicionamento Rescorla-Wagner: {c_str}")

        prefs = telemetry.get("episodic_prefs", [])
        if prefs:
            p_str = " | ".join(f"{ctx} ⇒ {act} ({val:+.2f}, n={n:.1f})" for ctx, act, val, n in prefs[:4])
            lines.append(f"Bandit Episódico: {p_str}")

        routine = telemetry.get("routine", {})
        if routine:
            r_str = ", ".join(f"{h}:{a}" for h, a in list(routine.items())[:8])
            lines.append(f"Rotina aprendida: {r_str}")

        self.learn_text.setPlainText("\n".join(lines))
