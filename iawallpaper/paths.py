"""Gerenciamento centralizado de caminhos do projeto, personas, assets e memória local."""

from dataclasses import dataclass
from pathlib import Path
import re

_VALID_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


def valid_id(identifier: str) -> bool:
    """Garante identificadores seguros para nomes de pasta (evita path traversal)."""
    return isinstance(identifier, str) and bool(_VALID_ID.match(identifier))


@dataclass(frozen=True)
class PersonaMemoryPaths:
    root: Path
    brain: Path
    drives: Path
    conditioning: Path
    episodes: Path
    preferences: Path
    appearance: Path


class Paths:
    """Resolve diretórios do código, assets, personas e memória persistente."""

    def __init__(self, base_dir: str | Path | None = None, data_dir: str | Path | None = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else Path(__file__).resolve().parent.parent
        self.data_dir = Path(data_dir).resolve() if data_dir else (self.base_dir / "memory")
        self.assets_dir = self.base_dir / "assets"
        self.personas_dir = self.assets_dir / "personas"
        self.scenes_dir = self.assets_dir / "scenes"
        self.generated_dir = self.assets_dir / "generated"
        self.vrm_dir = self.assets_dir / "vrm"
        self.vrm_generated_dir = self.generated_dir / "vrm"

        self.settings_file = self.data_dir / "settings.json"
        self.routine_file = self.data_dir / "routine.json"
        self.weather_cache_file = self.data_dir / "weather_cache.json"
        self.log_file = self.data_dir / "iawallpaper.log"

    def persona_memory(self, persona_id: str) -> PersonaMemoryPaths:
        if not valid_id(persona_id):
            raise ValueError(f"persona_id inválido: {persona_id!r}")
        root = self.data_dir / "personas" / persona_id
        return PersonaMemoryPaths(
            root=root,
            brain=root / "brain.json",
            drives=root / "drives.json",
            conditioning=root / "conditioning.json",
            episodes=root / "episodes.jsonl",
            preferences=root / "preferences.json",
            appearance=root / "appearance.json",
        )

    def persona_assets(self, persona_id: str) -> Path:
        if not valid_id(persona_id):
            raise ValueError(f"persona_id inválido: {persona_id!r}")
        return self.personas_dir / persona_id

    def persona_generated_assets(self, persona_id: str) -> Path:
        if not valid_id(persona_id):
            raise ValueError(f"persona_id inválido: {persona_id!r}")
        return self.generated_dir / "personas" / persona_id

    def scene_assets(self, scene_id: str) -> Path:
        if not valid_id(scene_id):
            raise ValueError(f"scene_id inválido: {scene_id!r}")
        return self.scenes_dir / scene_id

    def scene_generated_assets(self, scene_id: str) -> Path:
        if not valid_id(scene_id):
            raise ValueError(f"scene_id inválido: {scene_id!r}")
        return self.generated_dir / "scenes" / scene_id

    def list_vrm_models(self) -> list[Path]:
        """Lista todos os modelos 3D `.vrm` / `.glb` disponíveis nas pastas de assets."""
        found: dict[str, Path] = {}
        for folder in (self.vrm_generated_dir, self.vrm_dir):
            if not folder.exists():
                continue
            for ext in ("*.vrm", "*.glb"):
                for fp in sorted(folder.glob(ext)):
                    found[fp.name.lower()] = fp
        # Ordena priorizando estética dark-fantasy (Darkness_Shibu estilo Dungeon Squad) seguida das demais VRMs femininas
        pref = {"darkness_shibu.vrm": 0, "victoria_rubin.vrm": 1, "avatarsample_a.vrm": 2, "vroid_sample.vrm": 3, "seed_san.vrm": 9}
        return sorted(found.values(), key=lambda p: (pref.get(p.name.lower(), 5), p.name.lower()))

    def resolve_vrm_model(self, name_or_path: str = "") -> Path | None:
        """Resolve o caminho de um modelo `.vrm` por nome/caminho absoluto ou escolhe o melhor padrão."""
        if name_or_path:
            direct = Path(name_or_path)
            if direct.is_file():
                return direct
            for folder in (self.vrm_dir, self.vrm_generated_dir):
                cand = folder / name_or_path
                if cand.is_file():
                    return cand
        models = self.list_vrm_models()
        return models[0] if models else None
