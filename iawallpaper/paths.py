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
        self.live2d_dir = self.assets_dir / "live2d"
        self.live2d_generated_dir = self.generated_dir / "live2d"
        self.characters_generated_dir = self.generated_dir / "characters"

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
        """Resolve o caminho de um modelo `.vrm` ou um dos arquétipos nativos (`elfa_loira`, `humana_ruiva`, `androide_rosa`, `vampira_negra`, `dungeon_squad`)."""
        if name_or_path:
            key = str(name_or_path).strip().lower()
            if key in ("elfa_loira", "humana_ruiva", "androide_rosa", "vampira_negra", "dungeon_squad", "builtin:dungeon_squad"):
                return Path(key)
            direct = Path(name_or_path)
            if direct.is_file():
                return direct
            for folder in (self.vrm_dir, self.vrm_generated_dir):
                cand = folder / name_or_path
                if cand.is_file():
                    return cand
        models = self.list_vrm_models()
        return models[0] if models else None

    def resolve_live2d_rig(self, name_or_path: str = "elfa_loira") -> Path | None:
        """Resolve a pasta de um rig Live2D 2.5D (`base.png` + expressões/costas/outfits 1:1)."""
        key = str(name_or_path or "elfa_loira").strip()
        direct = Path(key)
        if direct.is_dir() and (direct / "base.png").is_file():
            return direct
        for root in (self.live2d_generated_dir, self.live2d_dir):
            cand = root / key.lower()
            if cand.is_dir() and (cand / "base.png").is_file():
                return cand
        for root in (self.live2d_generated_dir, self.live2d_dir):
            if root.is_dir():
                for sub in sorted(root.iterdir()):
                    if sub.is_dir() and (sub / "base.png").is_file():
                        return sub
        return None

    def list_character_packs(self) -> list[Path]:
        """Lista todas as pastas de personagens padronizadas (`assets/generated/characters/<char_id>/`)."""
        if not self.characters_generated_dir.is_dir():
            return []
        return sorted(
            sub for sub in self.characters_generated_dir.iterdir()
            if sub.is_dir() and (sub / "outfits").is_dir()
        )

    def resolve_character_dir(self, char_id: str = "arya") -> Path | None:
        """Resolve a pasta de um CharacterPack Wan 2.2 (`characters/<char_id>/`) ou o primeiro disponível."""
        key = str(char_id or "arya").strip()
        direct = Path(key)
        if direct.is_dir() and (direct / "outfits").is_dir():
            return direct
        cand = self.characters_generated_dir / key.lower()
        if cand.is_dir() and (cand / "outfits").is_dir():
            return cand
        packs = self.list_character_packs()
        return packs[0] if packs else None
