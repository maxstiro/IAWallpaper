# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 11 — Animação Fluida Quadro-a-Quadro via Wan 2.2 FirstLastFrameToVideo + Praça Aberta Tree of Savior / Ragnarok Online)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com 12 pacotes instalados |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Escrita atômica anti-NaN e recuperação `.corrompido` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Wan 2.2 `WanFirstLastFrameToVideo` + `isnet-anime` -> `SaveAnimatedWEBP` RGBA em loop infinito + Qwen 2.1 relighting 1:1 |
| Render (`render/`) | `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Reprodutor `SpriteClip` RGBA com crossfade suave, anel mágico giratório RO/ToS no piso, sombra aterrada, reflexo animado na chuva, fallbacks esquelético e procedural |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça 2.5D (`overlook`, `lantern`, `music_spot`, `desk`, `cushion`), poses (`wave`/`dance`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor Preset ComfyUI + Mundo 2.5D/Retrato + Criador de Waifu + Monitor Neural |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 28/28 Verdes | `pytest` completo + `generate_pack.py --style world/clips` + `render_showcase.py --mode world/gif` |

---

## 2. Assets Gerados Localmente (ComfyUI Read-Only, fora do Git)
- **Mira — 4 Clipes RGBA Animados em Loop Infinito (`assets/generated/personas/mira/clip_*.webp`)**:
  - Base `rig_base.png` gerada com `RawSexyGlowingGemPencil(TOP)` (`arthemyComics_v80` + 5 LoRAs) e animada via **Wan 2.2 14B Lightning (`WanFirstLastFrameToVideo`, `start_image == end_image`) + `isnet-anime` RemBG + `SaveAnimatedWEBP`** (`25 frames`, `416x640`, `12 FPS`, RGBA transparente limpo):
    - `clip_idle.webp`: respiração orgânica, piscar, sorriso suave e brisa no cabelo.
    - `clip_walk.webp`: caminhada rítmica natural com balanço de quadris, passos, braços e vestido fluidos.
    - `clip_wave.webp`: olhos sorridentes fechando, braço erguendo com dobras reais na manga e aceno caloroso.
    - `clip_dance.webp`: giro/dança estilo Tree of Savior com saia plissada abrindo e cabelo esvoaçante.
- **Observatório Celeste — Praça Aberta 3/4 Tree of Savior Reiluminada 1:1 (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**:
  - Praça ampla de pedras com árvore sagrada, lanternas de pedra, flores e balaustrada 100% sem bordas e 100% consistente em `diorama_day.png`, `diorama_sunset.png`, `diorama_night.png` e `diorama_rain.png` via **Qwen Image 2.1 Edit**.
- **Prévia & GIF Validados**: `assets/generated/m11_clips_sheet.png`, `assets/generated/m11_world_showcase.png` e `assets/generated/m11_tree_of_savior_demo.gif` (enviados ao Telegram).

---

## 3. Bugs Encontrados e Resolvidos (Milestones 6–11)
1. **Filtro de consolidação em `core/episodic.py`**: Ajustado filtro em `preferences()` para `n >= 0.2`.
2. **Retângulo semitransparente em volta do sprite RGBA (`render/avatar.py`)**: Corrigido via buffer `QPixmap` transparente dedicado com cache.
3. **Glifos virando caixas em offscreen (`render/particles.py`)**: Substituídos por formas vetoriais `QPainterPath`.
4. **Erro `numpy._ArrayMemoryError` em `pymatting` (`comfy/workflows.py`)**: Ajustado para `alpha_matting=False` mantendo `model="isnet-anime"` e `post_processing=True`.
5. **Efeito "marionete 2D" no recorte por peças planas (Milestone 11)**: Substituído como renderizador primário por **clipes RGBA quadro-a-quadro reais via Wan 2.2 `WanFirstLastFrameToVideo`** (`sprite_clip.py`), mantendo o esqueleto 18 ossos como fallback leve caso ainda não haja clipes gerados.
6. **Borda branca de papel aquarela no cenário base (Milestone 11)**: Removida tag `watercolor`, adicionadas travas `full_bleed, borderless` (negativo `white_border, paper_border`) e harmonizados `day`/`rain` a partir da praça master sem bordas via Qwen 2.1.

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Gerar Clipes RGBA Animados Wan 2.2 via CLI**: `.\venv\Scripts\python.exe tools\generate_pack.py --persona mira --style clips --actions idle,walk,wave,dance`
- **Gerar Showcase ou GIF Animado**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --scene sky_sanctuary --mode gif --out demo.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).
