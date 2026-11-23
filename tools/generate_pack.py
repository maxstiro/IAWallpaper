"""Ferramenta CLI para gerar packs completos de avatar (trajes + expressões) e cenários via ComfyUI."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iawallpaper.comfy.bridge import ComfyBridge
from iawallpaper.core.persona import load_persona
from iawallpaper.paths import Paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera pack completo consistente de persona + cenário via ComfyUI local.")
    parser.add_argument("--persona", default="mira", help="ID da persona (ex: mira, nyx ou personalizada).")
    parser.add_argument("--scene", default="sky_sanctuary", help="ID do cenário (sky_sanctuary, cyber_loft, sakura_hill).")
    parser.add_argument("--style", choices=("world", "clips", "directional", "portrait"), default="world", help="world = base + cenários 2.5D; clips = clipes Wan 2.2; directional = walk side/back; portrait = bustos.")
    parser.add_argument("--preset", default="RawSexyGlowingGemPencil(TOP)", help="Nome do preset do ComfyUI Studio (read-only).")
    parser.add_argument("--actions", default="idle,walk,wave,dance", help="Lista de ações para --style clips (separadas por vírgula).")
    parser.add_argument("--url", default="http://127.0.0.1:8188", help="URL da API HTTP do ComfyUI.")
    parser.add_argument("--force", action="store_true", help="Regenera inclusive arquivos já existentes.")
    args = parser.parse_args()

    paths = Paths(base_dir=ROOT)
    persona = load_persona(args.persona, personas_dir=paths.personas_dir)
    bridge = ComfyBridge(args.url)
    if args.style == "directional":
        created = bridge.generate_directional_walks_sync(
            persona=persona,
            persona_dest_dir=paths.persona_generated_assets(persona.id),
            skip_existing=not args.force,
            on_progress=lambda cur, tot, lbl: print(lbl, flush=True),
        )
    elif args.style == "clips":
        acts = tuple(a.strip() for a in args.actions.split(",") if a.strip())
        created = bridge.generate_wan_clips_sync(
            persona=persona,
            persona_dest_dir=paths.persona_generated_assets(persona.id),
            actions=acts,
            skip_existing=not args.force,
            on_progress=lambda cur, tot, lbl: print(lbl, flush=True),
        )
    elif args.style == "world":
        created = bridge.generate_world_pack_sync(
            persona=persona,
            scene_id=args.scene,
            persona_dest_dir=paths.persona_generated_assets(persona.id),
            scene_dest_dir=paths.scene_generated_assets(args.scene),
            preset_name=args.preset,
            skip_existing=not args.force,
            on_progress=lambda cur, tot, lbl: print(lbl, flush=True),
        )
    else:
        created = bridge.generate_full_pack_sync(
            persona=persona,
            scene_id=args.scene,
            persona_dest_dir=paths.persona_generated_assets(persona.id),
            scene_dest_dir=paths.scene_generated_assets(args.scene),
            skip_existing=not args.force,
            on_progress=lambda cur, tot, lbl: print(lbl, flush=True),
        )
    print(f"\nConcluído! {len(created)} novos assets salvos em assets/generated/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
