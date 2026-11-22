"""Testes de invariantes arquiteturais (inspirado em Pestinha/tests/test_arquitetura.py).

Garante:
1. Direção estrita das camadas: core < plataforma < sense < comfy < render < mind < ui < app.py
2. core/ nunca importa PySide6 nem APIs Win32.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "iawallpaper"
LAYERS = ["core", "plataforma", "sense", "comfy", "render", "mind", "ui"]
LAYER_RANK = {name: i for i, name in enumerate(LAYERS)}
SHARED_MODULES = {"__init__", "config", "log", "mathutil", "paths", "store"}
FORBIDDEN_IN_CORE = {"PySide6", "win32gui", "win32api", "win32con", "win32process", "ctypes", "psutil"}


def _imported_targets(py_file: Path) -> set[tuple[str, str]]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    rel = py_file.relative_to(ROOT)
    pkg_parts = list(rel.parts[:-1])

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add((alias.name.split(".")[0], alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level > 0:
                base = pkg_parts[: max(0, len(pkg_parts) - (node.level - 1))]
                full = ".".join(base + ([mod] if mod else []))
                top = full.split(".")[0] if full else ""
                out.add(("iawallpaper", f"iawallpaper.{full}" if full else "iawallpaper"))
                if top:
                    out.add((top, full))
            else:
                out.add((mod.split(".")[0], mod))
    return out


def test_core_has_no_qt_or_os_apis():
    core_dir = ROOT / "core"
    for py_file in core_dir.glob("*.py"):
        imports = _imported_targets(py_file)
        for root_mod, full_mod in imports:
            assert root_mod not in FORBIDDEN_IN_CORE, f"{py_file.name} importou módulo proibido: {full_mod}"


def test_strict_layer_ordering():
    for layer_name, rank in LAYER_RANK.items():
        layer_dir = ROOT / layer_name
        assert layer_dir.exists(), f"camada ausente: {layer_name}"
        for py_file in layer_dir.glob("*.py"):
            for _root, full in _imported_targets(py_file):
                parts = full.split(".")
                if parts and parts[0] == "iawallpaper" and len(parts) >= 2:
                    target = parts[1]
                elif parts and parts[0] in LAYER_RANK:
                    target = parts[0]
                else:
                    continue
                if target in SHARED_MODULES or target == layer_name:
                    continue
                if target in LAYER_RANK:
                    assert LAYER_RANK[target] < rank, (
                        f"Violação de camada: {layer_name}/{py_file.name} importou {target} "
                        f"(rank {LAYER_RANK[target]} >= {rank})"
                    )
                assert target != "app", f"Camada {layer_name}/{py_file.name} não pode importar app.py"
