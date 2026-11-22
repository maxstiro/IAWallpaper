"""THEME — Folha de estilo Dark Glassmorphic para a Central de Controle e Monitor Neural."""

DARK_STUDIO_QSS = """
QWidget {
    background-color: #0e1322;
    color: #e6eefc;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #243152;
    border-radius: 10px;
    background-color: #131a2e;
    padding: 6px;
}
QTabBar::tab {
    background-color: #151d33;
    color: #9bb0d6;
    border: 1px solid #233050;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 600;
}
QTabBar::tab:selected {
    background-color: #1d2846;
    color: #ffffff;
    border-color: #4f8cff;
}
QGroupBox {
    border: 1px solid #243152;
    border-radius: 10px;
    margin-top: 12px;
    padding: 12px 12px 10px 12px;
    background-color: #151d33;
    font-weight: 600;
    color: #a9c6ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QPushButton {
    background-color: #213054;
    color: #eef4ff;
    border: 1px solid #354c82;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2c4170;
    border-color: #63a2ff;
}
QPushButton:pressed {
    background-color: #1a2744;
}
QPushButton#primaryBtn {
    background-color: #2e66d6;
    border-color: #5a93ff;
    color: #ffffff;
}
QPushButton#primaryBtn:hover {
    background-color: #3a76eb;
}
QPushButton#dangerBtn {
    background-color: #5c1f2e;
    border-color: #a83c54;
}
QPushButton#dangerBtn:hover {
    background-color: #7c273b;
}
QComboBox, QLineEdit {
    background-color: #0f1628;
    color: #eef4ff;
    border: 1px solid #2d3e66;
    border-radius: 6px;
    padding: 5px 9px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #121a30;
    color: #eef4ff;
    selection-background-color: #2e66d6;
    border: 1px solid #334a7e;
}
QProgressBar {
    background-color: #0c1120;
    border: 1px solid #223052;
    border-radius: 5px;
    text-align: center;
    color: #dbe8ff;
    min-height: 14px;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3c7eff, stop:1 #76d4ff);
    border-radius: 4px;
}
QSlider::groove:horizontal {
    height: 6px;
    background: #0c1120;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #67a8ff;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QTextEdit, QPlainTextEdit {
    background-color: #0b101d;
    border: 1px solid #233050;
    border-radius: 8px;
    color: #cfe0ff;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}
"""
