# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 13 — Motor 3D Cel-Shaded VRM 0.x/1.0 em GPU ModernGL + Modo 2D Wan 2.2 Opcional)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Resolução de `.vrm`/`.glb`, `render_style="vrm_3d"` padrão, escrita atômica anti-NaN |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Cenários 2.5D + Qwen 2.1 relighting 1:1 + Qwen Turnaround + Wan 2.2 `WanFirstLastFrameToVideo` |
| Render 3D & 2.5D (`render/`) | `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Motor 3D MToon OpenGL 3.3 (>300 FPS, MSAA 4x, GPU bone-texture skinning, giro 360°, morphs faciais, `VRMC_node_constraint`, SpringBones) + Clipes 2D Wan 2.2 opcionais |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça 2.5D, poses (`wave`/`dance`/`stretch`/`sit_work`/`sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor de Motor Visual (`vrm_3d` / `world_sprite` / `portrait`) + seletor/importador **📂 Carregar .VRM** + tingimento dinâmico |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 30/30 Verdes | `pytest` completo (incluindo GPU VRM 3D) + `render_showcase.py --style vrm_3d` |

---

## 2. Assets Locais (fora do Git)
- **Modelos 3D Anime VRM (`assets/generated/vrm/`)** — CC0 / amostras oficiais Pixiv & VRM Consortium:
  - `Victoria_Rubin.vrm` (padrão, VRM 0.x, 54 ossos humanoides, 13 expressões faciais, 25 cadeias SpringBone — visual fantasia estilo *Tree of Savior*).
  - `AvatarSample_A.vrm` (VRM 0.x, 54 ossos, cardigã creme e meias escuras).
  - `vroid_sample.vrm` (VRM 1.0, 54 ossos, 14 expressões, 22 SpringBones, 14 `VRMC_node_constraint`).
  - `seed_san.vrm` (VRM 1.0 oficial).
  - Qualquer `.vrm` ou `.glb` customizado (VRoid Studio, Booth, etc.) pode ser carregado em 1 clique via **📂 Carregar .VRM** na Central de Controle.
- **Cenário 2.5D Reiluminado 1:1 (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**:
  - Praça aberta estilo Tree of Savior (`day`, `sunset`, `night`, `rain`) sem bordas via Qwen Image 2.1 Edit.
- **Clipes 2D Opcionais da Mira (`assets/generated/personas/mira/clip_*.webp`)**:
  - 6 clipes RGBA Wan 2.2 (`idle`, `walk`, `walk_side`, `walk_back`, `wave`, `dance`) preservados para o modo opcional `"world_sprite"`.
- **Prévias & GIFs Validados**: `m13_vrm3d_showcase.png`, `m13_vrm3d_storyboard.png` e `m13_vrm3d_360_demo.gif` (enviados ao Telegram).

---

## 3. Bugs Encontrados e Resolvidos (Milestone 13)
1. **Estrutura de `VRMC_springBone` em VRM 1.0 (`vrm_loader.py`)**: `sp["joints"]` pode conter dicts diretamente em vez de índices inteiros — suporte unificado para ambos os formatos.
2. **Mangas rígidas em modelos VRM 1.0 com twist bones (`vrm_loader.py`, `vrm_animator.py`)**: Implementado suporte completo a `VRMC_node_constraint` (`aim`, `roll`, `rotation`) com propagação recursiva para nós filhos (`_propagate`), eliminando completamente mangas levantadas na T-pose.
3. **Diferença de orientação VRM 0.x (`-Z`) vs VRM 1.0 (`+Z`) (`vrm_animator.py`)**: Adicionado fator `xz_sign = 1.0 if model.is_vrm1 else -1.0` + rotação raiz `+180°` para VRM 0.x, garantindo animações 100% idênticas em ambos os padrões.
4. **Projeção exata da sola dos pés (`vrm_renderer.py`, `avatar.py`)**: Calculada a coordenada normalizada exata `last_foot_v` de `(0, min_y, 0)` pela matriz `mvp`, travando os saltos no chão sem variação de escala ao erguer os braços.

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF 3D VRM**: `.\venv\Scripts\python.exe tools\render_showcase.py --style vrm_3d --vrm Victoria_Rubin.vrm --mode gif --out demo3d.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).
