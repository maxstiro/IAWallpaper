"""BRIDGE — Cliente HTTP read-only para o ComfyUI local (nunca altera arquivos do ComfyUI Studio)."""

from dataclasses import dataclass
import json
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request
import uuid

from ..core.persona import Persona
from ..log import log
from .workflows import build_avatar_workflow, build_scene_workflow


@dataclass
class ComfyStatus:
    online: bool = False
    busy: bool = False
    queue_remaining: int = 0
    checkpoint: str = ""
    has_rembg: bool = False
    has_pag: bool = False


class ComfyBridge:
    """Interage estritamente via API HTTP pública do ComfyUI (porta 8188)."""

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

    def probe(self) -> ComfyStatus:
        """Verifica se o ComfyUI está online, ocupado e quais capacidades possui."""
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

        return ComfyStatus(
            online=True,
            busy=(running + pending) > 0,
            queue_remaining=running + pending,
            checkpoint=best,
            has_rembg=has_rembg,
            has_pag=has_pag,
        )

    def is_busy_fast(self) -> bool:
        """Consulta rápida de fila para o avatar perceber que o ComfyUI está renderizando."""
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

    def run_workflow_and_save(
        self,
        graph: dict,
        output_path: Path,
        timeout: float = 180.0,
    ) -> Path:
        """Envia o grafo, aguarda conclusão no /history e salva o PNG resultante em output_path."""
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
            time.sleep(1.2)
        raise TimeoutError(f"Timeout aguardando prompt {prompt_id} no ComfyUI")

    def generate_avatar_async(
        self,
        persona: Persona,
        outfit_key: str,
        dest_dir: Path,
        on_done=None,
        on_error=None,
    ) -> None:
        def worker():
            try:
                st = self.probe()
                if not st.online or not st.checkpoint:
                    raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")
                graph = build_avatar_workflow(
                    checkpoint=st.checkpoint,
                    persona=persona,
                    outfit_key=outfit_key,
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

    def generate_scene_async(
        self,
        scene_id: str,
        variant: str,
        dest_dir: Path,
        on_done=None,
        on_error=None,
    ) -> None:
        def worker():
            try:
                st = self.probe()
                if not st.online or not st.checkpoint:
                    raise RuntimeError("ComfyUI offline ou sem checkpoint disponível.")
                graph = build_scene_workflow(
                    checkpoint=st.checkpoint,
                    scene_id=scene_id,
                    variant=variant,
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
