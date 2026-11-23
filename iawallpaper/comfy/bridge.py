"""BRIDGE — Cliente HTTP read-only para o ComfyUI local (incluindo upload img2img e gerador de pack em lote)."""

from dataclasses import dataclass
import io
import json
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request
import uuid

from PIL import Image

from ..core.persona import Persona
from ..log import log
from .presets import ComfyPreset, find_comfy_preset
from .workflows import (
    PACK_EXPRESSIONS,
    PACK_OUTFITS,
    PACK_SCENE_VARIANTS,
    WORLD_SPRITE_ACTIONS,
    build_apose_rig_workflow,
    build_avatar_variant_img2img_workflow,
    build_avatar_workflow,
    build_diorama_scene_workflow,
    build_qwen_relight_scene_workflow,
    build_scene_workflow,
    build_world_sprite_workflow,
)


@dataclass
class ComfyStatus:
    online: bool = False
    busy: bool = False
    queue_remaining: int = 0
    checkpoint: str = ""
    has_rembg: bool = False
    has_pag: bool = False
    has_qwen_relight: bool = False


class ComfyBridge:
    """Interage estritamente via API HTTP pública do ComfyUI (porta 8188), sem alterar arquivos do Studio."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = f"iawallpaper-{uuid.uuid4().hex[:8]}"

    def _get_json(self, endpoint: str, timeout: float = 3.0) -> dict | None:
        try:
            req = urllib.request.Request(f"{self.base_url}{endpoint}", headers={"User-Agent": "IAWallpaper/0.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return None

    def _post_json(self, endpoint: str, payload: dict, timeout: float = 10.0) -> dict | None:
        raw = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=raw,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "IAWallpaper/0.1"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def _upload_png_bytes(self, img_bytes: bytes, upload_name: str) -> str:
        boundary = f"----IAWallpaperBoundary{uuid.uuid4().hex}"
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="image"; filename="{upload_name}"\r\n'.encode())
        body.extend(b"Content-Type: image/png\r\n\r\n")
        body.extend(img_bytes)
        body.extend(b"\r\n")
        for field_name, field_val in (("type", "input"), ("overwrite", "true")):
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'.encode())
            body.extend(f"{field_val}\r\n".encode())
        body.extend(f"--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            f"{self.base_url}/upload/image",
            data=bytes(body),
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "IAWallpaper/0.1",
            },
        )
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            res = json.loads(resp.read().decode("utf-8", errors="replace"))
        return str(res.get("name") or upload_name)

    def upload_image_on_white(self, rgba_path: Path, upload_name: str) -> str:
        """Compõe um sprite RGBA sobre fundo branco em memória e envia via POST /upload/image do ComfyUI."""
        with Image.open(rgba_path) as im:
            rgba = im.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            flat = Image.alpha_composite(white, rgba).convert("RGB")
            buf = io.BytesIO()
            flat.save(buf, format="PNG")
            img_bytes = buf.getvalue()
        return self._upload_png_bytes(img_bytes, upload_name)

    def upload_image_raw(self, image_path: Path, upload_name: str) -> str:
        """Envia uma imagem PNG de cenário diretamente via POST /upload/image para reiluminação 1:1."""
        return self._upload_png_bytes(Path(image_path).read_bytes(), upload_name)

    def probe(self) -> ComfyStatus:
        stats = self._get_json("/system_stats", timeout=2.0)
        if not isinstance(stats, dict):
            return ComfyStatus(online=False)

        q = self._get_json("/queue", timeout=2.0) or {}
        running = len(q.get("queue_running") or [])
        pending = len(q.get("queue_pending") or [])

        ckpts = self.list_checkpoints()
        best = self.pick_anime_checkpoint(ckpts)
        has_rembg = self._get_json("/object_info/" + urllib.parse.quote("Image Rembg (Remove Background)"), timeout=2.0) is not None
        has_pag = self._get_json("/object_info/PerturbedAttentionGuidance", timeout=2.0) is not None
        has_qwen = self._get_json("/object_info/TextEncodeQwenImage21", timeout=2.0) is not None

        return ComfyStatus(
            online=True,
            busy=(running + pending) > 0,
            queue_remaining=running + pending,
            checkpoint=best,
            has_rembg=has_rembg,
            has_pag=has_pag,
            has_qwen_relight=has_qwen,
        )

    def is_busy_fast(self) -> bool:
        q = self._get_json("/queue", timeout=0.8)
        if not isinstance(q, dict):
            return False
        return bool((q.get("queue_running") or []) or (q.get("queue_pending") or []))

    def list_checkpoints(self) -> list[str]:
        info = self._get_json("/object_info/CheckpointLoaderSimple", timeout=3.0)
        try:
            return list(info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0])
        except Exception:
            return []

    @staticmethod
    def pick_anime_checkpoint(checkpoints: list[str]) -> str:
        for pref in ("waiillustrious", "illustrious", "anime", "mistoon"):
            for ck in checkpoints:
                if pref in ck.lower():
                    return ck
        return checkpoints[0] if checkpoints else ""

    def run_workflow_and_save(self, graph: dict, output_path: Path, timeout: float = 180.0) -> Path:
        res = self._post_json("/prompt", {"prompt": graph, "client_id": self.client_id})
        if not isinstance(res, dict) or "prompt_id" not in res:
            raise RuntimeError(f"ComfyUI recusou o prompt: {res}")
        prompt_id = res["prompt_id"]
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            hist = self._get_json(f"/history/{prompt_id}", timeout=4.0)
            if isinstance(hist, dict) and prompt_id in hist:
                item = hist[prompt_id]
                status = item.get("status") or {}
                if status.get("status_str") == "error":
                    raise RuntimeError(f"Erro na execução do ComfyUI: {status}")
                outputs = item.get("outputs") or {}
                for node_out in outputs.values():
                    images = node_out.get("images") or []
                    if images:
                        img_meta = images[0]
                        params = urllib.parse.urlencode(
                            {
                                "filename": img_meta["filename"],
                                "subfolder": img_meta.get("subfolder", ""),
                                "type": img_meta.get("type", "output"),
                            }
                        )
                        url = f"{self.base_url}/view?{params}"
                        req = urllib.request.Request(url, headers={"User-Agent": "IAWallpaper/0.1"})
                        with urllib.request.urlopen(req, timeout=15.0) as resp:
                            raw = resp.read()
                        output_path = Path(output_path)
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        tmp = output_path.with_name(output_path.name + ".tmp")
                        tmp.write_bytes(raw)
                        tmp.replace(output_path)
                        log(f"[comfy] Asset salvo em {output_path.name} ({len(raw) // 1024} KB)")
                        return output_path
            time.sleep(1.0)
        raise TimeoutError(f"Timeout aguardando prompt {prompt_id} no ComfyUI")

    def generate_avatar_async(self, persona: Persona, outfit_key: str, dest_dir: Path, on_done=None, on_error=None) -> None:
        def worker():
            try:
                st = self.probe()
                if not st.online or not st.checkpoint:
                    raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")
                base_casual = dest_dir / "casual.png"
                if outfit_key != "casual" and base_casual.exists():
                    uploaded = self.upload_image_on_white(base_casual, f"iawallpaper_base_{persona.id}.png")
                    graph = build_avatar_variant_img2img_workflow(
                        checkpoint=st.checkpoint,
                        persona=persona,
                        base_uploaded_image=uploaded,
                        outfit_key=outfit_key,
                        denoise=0.75,
                        seed=persona.seed + abs(hash(outfit_key)) % 997,
                        use_pag=st.has_pag,
                        use_rembg=st.has_rembg,
                    )
                else:
                    graph = build_avatar_workflow(
                        checkpoint=st.checkpoint,
                        persona=persona,
                        outfit_key=outfit_key,
                        seed=persona.seed,
                        use_pag=st.has_pag,
                        use_rembg=st.has_rembg,
                    )
                out = self.run_workflow_and_save(graph, dest_dir / f"{outfit_key}.png")
                if on_done:
                    on_done(out)
            except Exception as err:
                log(f"[comfy] falha ao gerar avatar: {err}")
                if on_error:
                    on_error(str(err))

        threading.Thread(target=worker, daemon=True, name="iawallpaper-comfy-avatar").start()

    def generate_scene_async(self, scene_id: str, variant: str, dest_dir: Path, on_done=None, on_error=None) -> None:
        def worker():
            try:
                st = self.probe()
                if not st.online or not st.checkpoint:
                    raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")
                seed = 202600 + (abs(hash(f"{scene_id}_{variant}")) % 9000)
                graph = build_scene_workflow(
                    checkpoint=st.checkpoint,
                    scene_id=scene_id,
                    variant=variant,
                    seed=seed,
                    use_pag=st.has_pag,
                )
                out = self.run_workflow_and_save(graph, dest_dir / f"{variant}.png")
                if on_done:
                    on_done(out)
            except Exception as err:
                log(f"[comfy] falha ao gerar cenário: {err}")
                if on_error:
                    on_error(str(err))

        threading.Thread(target=worker, daemon=True, name="iawallpaper-comfy-scene").start()

    def generate_full_pack_sync(
        self,
        persona: Persona,
        scene_id: str,
        persona_dest_dir: Path,
        scene_dest_dir: Path,
        outfits: tuple[str, ...] = PACK_OUTFITS,
        expressions: tuple[str, ...] = PACK_EXPRESSIONS,
        scene_variants: tuple[str, ...] = PACK_SCENE_VARIANTS,
        skip_existing: bool = True,
        on_progress=None,
        on_asset=None,
    ) -> list[Path]:
        """Gera pack completo consistente (base -> expressões img2img -> trajes img2img -> cenários 4 horários)."""
        st = self.probe()
        if not st.online or not st.checkpoint:
            raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")

        persona_dest_dir.mkdir(parents=True, exist_ok=True)
        scene_dest_dir.mkdir(parents=True, exist_ok=True)

        jobs: list[tuple[str, str, Path]] = []
        base_casual = persona_dest_dir / "casual.png"
        if not (skip_existing and base_casual.exists()):
            jobs.append(("avatar_base", "casual", base_casual))
        for expr in expressions:
            p = persona_dest_dir / f"casual_{expr}.png"
            if not (skip_existing and p.exists()):
                jobs.append(("expression", expr, p))
        for outfit in outfits:
            if outfit == "casual":
                continue
            p = persona_dest_dir / f"{outfit}.png"
            if not (skip_existing and p.exists()):
                jobs.append(("outfit", outfit, p))
        for var in scene_variants:
            p = scene_dest_dir / f"{var}.png"
            if not (skip_existing and p.exists()):
                jobs.append(("scene", var, p))

        total = len(jobs)
        if total == 0:
            if on_progress:
                on_progress(0, 0, "Pack completo já existe no disco!")
            return []

        created: list[Path] = []
        uploaded_base: str | None = None

        for idx, (kind, key, out_path) in enumerate(jobs, start=1):
            if on_progress:
                on_progress(idx, total, f"[{idx}/{total}] Gerando {kind}: {key}...")

            if kind == "avatar_base":
                graph = build_avatar_workflow(
                    checkpoint=st.checkpoint,
                    persona=persona,
                    outfit_key="casual",
                    seed=persona.seed,
                    steps=20,
                    use_pag=st.has_pag,
                    use_rembg=st.has_rembg,
                )
            elif kind in ("expression", "outfit"):
                if uploaded_base is None and base_casual.exists():
                    uploaded_base = self.upload_image_on_white(base_casual, f"iawallpaper_base_{persona.id}.png")
                if uploaded_base is not None:
                    graph = build_avatar_variant_img2img_workflow(
                        checkpoint=st.checkpoint,
                        persona=persona,
                        base_uploaded_image=uploaded_base,
                        outfit_key="casual" if kind == "expression" else key,
                        expression_key=key if kind == "expression" else None,
                        denoise=0.44 if kind == "expression" else 0.75,
                        seed=persona.seed + idx * 17,
                        steps=20,
                        use_pag=st.has_pag,
                        use_rembg=st.has_rembg,
                    )
                else:
                    graph = build_avatar_workflow(
                        checkpoint=st.checkpoint,
                        persona=persona,
                        outfit_key=key if kind == "outfit" else "casual",
                        seed=persona.seed + idx * 17,
                        steps=20,
                        use_pag=st.has_pag,
                        use_rembg=st.has_rembg,
                    )
            else:
                seed = 202600 + idx * 31
                graph = build_scene_workflow(
                    checkpoint=st.checkpoint,
                    scene_id=scene_id,
                    variant=key,
                    seed=seed,
                    steps=18,
                    use_pag=st.has_pag,
                )

            saved = self.run_workflow_and_save(graph, out_path, timeout=180.0)
            created.append(saved)
            if on_asset:
                on_asset(kind, saved)

        if on_progress:
            on_progress(total, total, f"✅ Pack completo concluído ({len(created)} assets gerados)!")
        return created

    def generate_world_pack_sync(
        self,
        persona: Persona,
        scene_id: str,
        persona_dest_dir: Path,
        scene_dest_dir: Path,
        preset: ComfyPreset | None = None,
        preset_name: str = "",
        actions: tuple[str, ...] = tuple(WORLD_SPRITE_ACTIONS.keys()),
        scene_variants: tuple[str, ...] = PACK_SCENE_VARIANTS,
        skip_existing: bool = True,
        on_progress=None,
        on_asset=None,
    ) -> list[Path]:
        """Gera pack 2.5D coerente com esqueleto articulado real:
        1. Usa preset (TOP) do ComfyUI Studio (Checkpoint + LoRAs) para gerar 1 base A-pose (`rig_base.png`)
           recortada automaticamente em 10 peças articuladas pelo AutoRigger.
        2. Gera 1 terraço eye-level 1:1 em escala humana (`diorama_day.png`) e reilumina O MESMO local
           para sunset/night/rain via Qwen Image 2.1 Edit!
        """
        st = self.probe()
        if not st.online or not st.checkpoint:
            raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")

        active_preset = preset or find_comfy_preset(preset_name)
        sprite_ckpt = active_preset.checkpoint if active_preset else st.checkpoint
        sprite_loras = active_preset.loras if active_preset else ()
        log(f"[comfy] World pack usando preset={active_preset.name if active_preset else 'padrão'} (ckpt={sprite_ckpt}, {len(sprite_loras)} LoRAs)")

        persona_dest_dir.mkdir(parents=True, exist_ok=True)
        scene_dest_dir.mkdir(parents=True, exist_ok=True)

        jobs: list[tuple[str, str, Path]] = []
        rig_base = persona_dest_dir / "rig_base.png"
        if not (skip_existing and rig_base.exists()):
            jobs.append(("rig_apose", "apose", rig_base))

        # Cenário base eye-level (day) primeiro, depois relight coerente do MESMO local para sunset/night/rain!
        base_day = scene_dest_dir / "diorama_day.png"
        if not (skip_existing and base_day.exists()):
            jobs.append(("diorama_base", "day", base_day))
        for var in scene_variants:
            if var == "day":
                continue
            p = scene_dest_dir / f"diorama_{var}.png"
            if not (skip_existing and p.exists()):
                jobs.append(("diorama_relight", var, p))

        total = len(jobs)
        if total == 0:
            if on_progress:
                on_progress(0, 0, "Pack Mundo Vivo 2.5D já existe no disco!")
            return []

        created: list[Path] = []
        uploaded_day: str | None = None

        for idx, (kind, key, out_path) in enumerate(jobs, start=1):
            if on_progress:
                on_progress(idx, total, f"[{idx}/{total}] Gerando {kind}: {key}...")

            if kind == "rig_apose":
                graph = build_apose_rig_workflow(
                    checkpoint=sprite_ckpt,
                    persona=persona,
                    loras=sprite_loras,
                    seed=persona.seed + 1024,
                    steps=26,
                    use_pag=st.has_pag,
                    use_rembg=st.has_rembg,
                )
            elif kind == "diorama_base":
                graph = build_diorama_scene_workflow(
                    checkpoint=st.checkpoint,
                    scene_id=scene_id,
                    variant="day",
                    seed=203011,
                    steps=24,
                    use_pag=st.has_pag,
                )
            else:
                # Reiluminação 1:1 da MESMA arquitetura eye-level via Qwen Image 2.1!
                if uploaded_day is None and base_day.exists():
                    uploaded_day = self.upload_image_raw(base_day, f"iawallpaper_diorama_day_{scene_id}.png")
                if st.has_qwen_relight and uploaded_day is not None:
                    graph = build_qwen_relight_scene_workflow(
                        base_uploaded_scene=uploaded_day,
                        variant=key,
                        seed=203011 + idx * 17,
                        steps=10,
                        cfg=1.5,
                    )
                else:
                    graph = build_diorama_scene_workflow(
                        checkpoint=st.checkpoint,
                        scene_id=scene_id,
                        variant=key,
                        seed=203011,
                        steps=22,
                        use_pag=st.has_pag,
                    )

            saved = self.run_workflow_and_save(graph, out_path, timeout=240.0)
            created.append(saved)
            if on_asset:
                on_asset(kind, saved)

        if on_progress:
            on_progress(total, total, f"✅ Pack Mundo Vivo 2.5D concluído ({len(created)} assets)!")
        return created

    def generate_world_pack_async(
        self,
        persona: Persona,
        scene_id: str,
        persona_dest_dir: Path,
        scene_dest_dir: Path,
        preset_name: str = "",
        skip_existing: bool = True,
        on_progress=None,
        on_asset=None,
        on_error=None,
    ) -> None:
        def worker():
            try:
                self.generate_world_pack_sync(
                    persona=persona,
                    scene_id=scene_id,
                    persona_dest_dir=persona_dest_dir,
                    scene_dest_dir=scene_dest_dir,
                    preset_name=preset_name,
                    skip_existing=skip_existing,
                    on_progress=on_progress,
                    on_asset=on_asset,
                )
            except Exception as err:
                log(f"[comfy] falha no pack mundo 2.5D: {err}")
                if on_error:
                    on_error(str(err))

        threading.Thread(target=worker, daemon=True, name="iawallpaper-comfy-world-pack").start()

    def generate_full_pack_async(
        self,
        persona: Persona,
        scene_id: str,
        persona_dest_dir: Path,
        scene_dest_dir: Path,
        skip_existing: bool = True,
        on_progress=None,
        on_asset=None,
        on_error=None,
    ) -> None:
        def worker():
            try:
                self.generate_full_pack_sync(
                    persona=persona,
                    scene_id=scene_id,
                    persona_dest_dir=persona_dest_dir,
                    scene_dest_dir=scene_dest_dir,
                    skip_existing=skip_existing,
                    on_progress=on_progress,
                    on_asset=on_asset,
                )
            except Exception as err:
                log(f"[comfy] falha no pack completo: {err}")
                if on_error:
                    on_error(str(err))

        threading.Thread(target=worker, daemon=True, name="iawallpaper-comfy-pack").start()
