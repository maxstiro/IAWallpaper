"""PRESETS — Leitor estritamente READ-ONLY dos presets aprovados do ComfyUI Studio (approved_combos.json).

Nunca altera nenhum arquivo em D:\\IA\\ComfyUI; apenas lê Checkpoint + LoRAs dos presets
para que o IAWallpaper possa reproduzir os estilos favoritos (TOP) do usuário.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path

DEFAULT_COMFY_PRESETS_PATH = Path(r"D:\IA\ComfyUI\user\default\approved_combos.json")


@dataclass(frozen=True)
class LoraSpec:
    lora: str
    strength_model: float = 0.7
    strength_clip: float = 0.7


@dataclass(frozen=True)
class ComfyPreset:
    name: str
    checkpoint: str
    loras: tuple[LoraSpec, ...] = field(default_factory=tuple)

    @property
    def is_top(self) -> bool:
        return "(top)" in self.name.lower()


def load_comfy_presets(presets_file: Path | None = None) -> list[ComfyPreset]:
    """Carrega presets do ComfyUI ordenando os marcados com (TOP) primeiro."""
    path = Path(presets_file) if presets_file else DEFAULT_COMFY_PRESETS_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    items = raw.get("approved_combos", []) if isinstance(raw, dict) else []
    out: list[ComfyPreset] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        ckpt = str(it.get("checkpoint") or it.get("ckpt_name") or "").strip()
        if not name or not ckpt:
            continue
        loras: list[LoraSpec] = []
        for lr in it.get("loras") or []:
            if isinstance(lr, dict) and lr.get("lora"):
                loras.append(
                    LoraSpec(
                        lora=str(lr["lora"]),
                        strength_model=float(lr.get("strength_model", lr.get("strength", 0.7))),
                        strength_clip=float(lr.get("strength_clip", lr.get("strength", 0.7))),
                    )
                )
        out.append(ComfyPreset(name=name, checkpoint=ckpt, loras=tuple(loras)))

    # Coloca os presets (TOP) no topo da lista!
    out.sort(key=lambda p: (0 if p.is_top else 1, p.name.lower()))
    return out


def find_comfy_preset(name_query: str = "", presets_file: Path | None = None) -> ComfyPreset | None:
    """Encontra um preset por nome exato/parcial ou retorna o primeiro (TOP) disponível."""
    presets = load_comfy_presets(presets_file)
    if not presets:
        return None
    q = (name_query or "").strip().lower()
    if q:
        for p in presets:
            if p.name.lower() == q:
                return p
        for p in presets:
            if q in p.name.lower():
                return p
    for p in presets:
        if p.is_top:
            return p
    return presets[0]
