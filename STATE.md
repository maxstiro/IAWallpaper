# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 12 — Locomoção & Orientação 4-Vias Real via Qwen 2.1 Turnaround + Wan 2.2 Direcional)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com 12 pacotes instalados |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Escrita atômica anti-NaN e recuperação `.corrompido` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Qwen 2.1 Turnaround (`pose_side`/`pose_back`) + Wan 2.2 `WanFirstLastFrameToVideo` direcional + Qwen 2.1 relighting 1:1 |
| Render (`render/`) | `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Orientação 4-vias (`side` dir/esq, `back`, `front`), velocidade/cadência acoplada à perspectiva, HUD responsivo, anel mágico RO/ToS |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça 2.5D (`overlook`, `lantern`, `music_spot`, `desk`, `cushion`), poses (`wave`/`dance`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor Preset ComfyUI + Mundo 2.5D/Retrato + Criador de Waifu + Monitor Neural |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 29/29 Verdes | `pytest` completo + `generate_pack.py --style world/clips/directional` + `render_showcase.py --mode world/gif` |

---

## 2. Assets Gerados Localmente (ComfyUI Read-Only, fora do Git)
- **Mira — 6 Clipes RGBA Animados em Loop Infinito (`assets/generated/personas/mira/clip_*.webp`)**:
  - Base `rig_base.png` (`RawSexyGlowingGemPencil(TOP)`) + turnaround fiel **Qwen 2.1** (`pose_side.png` em perfil 3/4 direita e `pose_back.png` de costas), animados via **Wan 2.2 14B Lightning (`WanFirstLastFrameToVideo`) + `isnet-anime` RemBG** (`25 frames`, `416x640`, `12 FPS`, RGBA limpo):
    - `clip_idle.webp`: respiração orgânica, piscar, sorriso suave e brisa no cabelo.
    - `clip_walk.webp`: caminhada frontal descendo em direção à câmera.
    - `clip_walk_side.webp`: caminhada em perfil 3/4 real para a direita (espelhada automaticamente para a esquerda com `facing = -1`).
    - `clip_walk_back.webp`: caminhada de costas subindo em direção à árvore sagrada.
    - `clip_wave.webp`: sorriso de olhos fechados, braço erguendo e aceno caloroso.
    - `clip_dance.webp`: dança/giro estilo Tree of Savior com saia plissada abrindo e cabelo esvoaçante.
- **Observatório Celeste — Praça Aberta 3/4 Tree of Savior Reiluminada 1:1 (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**:
  - `diorama_day.png`, `diorama_sunset.png`, `diorama_night.png`, `diorama_rain.png` (100% sem bordas e consistentes via Qwen 2.1).
- **Prévias & GIFs Validados**: `m12_dir_clips_sheet.png`, `m12_locomotion_storyboard.png` e `m12_locomotion_demo.gif` (enviados ao Telegram).

---

## 3. Bugs Encontrados e Resolvidos (Milestones 6–12)
1. **Filtro de consolidação em `core/episodic.py`**: Ajustado filtro em `preferences()` para `n >= 0.2`.
2. **Retângulo semitransparente em volta do sprite RGBA (`render/avatar.py`)**: Corrigido via buffer `QPixmap` transparente com cache.
3. **Glifos virando caixas em offscreen (`render/particles.py`)**: Substituídos por formas vetoriais `QPainterPath`.
4. **Erro `numpy._ArrayMemoryError` em `pymatting` (`comfy/workflows.py`)**: `alpha_matting=False` mantendo `model="isnet-anime"` e `post_processing=True`.
5. **Efeito "marionete 2D" (Milestone 11)**: Substituído como renderizador primário por clipes RGBA quadro-a-quadro reais via Wan 2.2 `WanFirstLastFrameToVideo`.
6. **Caminhada lateral "olhando para a câmera" e HUD grande em janelas menores (Milestone 12)**: Resolvido com turnaround direcional fiel via Qwen 2.1 (`pose_side`/`pose_back`) + clipes Wan 2.2 (`clip_walk_side`/`clip_walk_back`), seleção 4-vias compensada para 16:9 (`abs(vx_vis) >= abs(vy_vis) * 1.35`), espelhamento exclusivo nos clipes direcionais (sem inverter a presilha frontal), cadência vertical sincronizada ao passo e escala responsiva no HUD ambiental (`scene.py`).

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Gerar Caminhadas Direcionais (Qwen + Wan 2.2)**: `.\venv\Scripts\python.exe tools\generate_pack.py --persona mira --style directional`
- **Gerar Showcase ou GIF Animado**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --scene sky_sanctuary --mode gif --out demo.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).
