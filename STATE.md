# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 9 — Ancoragem Aterrada, Preset TOP & Reiluminação 1:1 Qwen 2.1)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com 12 pacotes instalados |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Escrita atômica anti-NaN e recuperação `.corrompido` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Leitor read-only de presets `(TOP)` (`RawSexyGlowingGemPencil(TOP)`) + Qwen 2.1 relighting 1:1 |
| Render (`render/`) | `atmosphere.py`, `particles.py`, `world_stage.py`, `avatar.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Auto-trim nos pés, sombra dupla + reflexo molhado, animação 3-bandas Live2D, god rays, fauna diurna |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma por hotspots (`desk`, `cushion`, `music_spot`, `overlook`, `lantern`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor Preset ComfyUI + Mundo 2.5D/Retrato + Criador de Waifu + Monitor Neural |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 25/25 Verdes | `pytest` completo + `generate_pack.py --preset ...` + `render_showcase.py` |

---

## 2. Assets Gerados Localmente (ComfyUI Read-Only, fora do Git)
- **Mira — Modo Mundo Vivo 2.5D Maduro (`assets/generated/personas/mira/sprite_*.png` — 6 sprites full-body RGBA)**:
  - Gerados com o preset **`RawSexyGlowingGemPencil(TOP)`** (`arthemyComics_v80` + 5 LoRAs) + `isnet-anime`: `sprite_idle.png`, `sprite_walk1.png`, `sprite_walk2.png`, `sprite_sit.png`, `sprite_happy.png`, `sprite_sleep.png` (recorte automático exato na sola dos saltos via `trim_sprite_pixmap`).
- **Observatório Celeste — Diorama Único Reiluminado 1:1 via Qwen Image 2.1 (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**:
  - `diorama_day.png` (base) + `diorama_sunset.png`, `diorama_night.png`, `diorama_rain.png` (mesma arquitetura/cúpula/ponte/árvores pixel-a-pixel nos 4 climas/horários!).
- **Mira — Modo Retrato Opcional (`casual*.png`, `focus.png`, `rainy.png`, `cozy.png`, `nightwear.png`, `starlight.png`)** + cenários `day/sunset/night/rain.png` também preservados caso o usuário alterne para o modo Retrato.
- **Fallback Procedural**: Qualquer nova persona/cenário sem PNG gerado opera 100% nativamente via render procedural.

---

## 3. Bugs Encontrados e Resolvidos (Milestones 6–7)
1. **Filtro de consolidação em `core/episodic.py`**: Episódios recém-decaídos (`n = 0.995`) eram filtrados por `n >= 1.0` em `preferences()`; ajustado para `n >= 0.2`.
2. **Retângulo semitransparente em volta do sprite RGBA (`render/avatar.py`)**: `CompositionMode_SourceAtop` aplicado no painter principal tingia toda a bounding box (pois o fundo já tinha alpha 255). Corrigido renderizando o tint em buffer `QPixmap` transparente dedicado com cache por paleta (0 artefato de borda + alta performance em 60 FPS).
3. **Glifos de coração/brilho virando caixas em ambientes sem fonte de símbolo (`render/particles.py`)**: Substituídos glifos de fonte por formas vetoriais puras (`QPainterPath`) para corações, estrelas 4-pontas e notas musicais.
4. **Sobreposição visual da lanterna com o card HUD no modo procedural (`render/scene.py`)**: Reposicionada a lanterna para `w * 0.38` e alargado o card HUD para `360x78px`.
5. **Erro `numpy._ArrayMemoryError` em `pymatting` durante `Image Rembg` em lote (`comfy/workflows.py`)**: `alpha_matting=True` acionava `pymatting.estimate_alpha_cf` alocando matriz esparsa pesada na RAM da CPU. Alterado para `alpha_matting=False` mantendo `model="isnet-anime"` e `post_processing=True` — recortes limpos em <1s sem picos de RAM.
6. **Sincronia de crossfade no gerador de mosaico (`tools/render_showcase.py`)**: O primeiro `render_to_image()` dispara o crossfade; adicionada etapa prévia de disparo + 36 passos antes da captura final.

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Gerar Pack Completo via CLI**: `.\venv\Scripts\python.exe tools\generate_pack.py --persona nyx --scene cyber_loft`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote configurado via SSH (`git@github.com:maxstiro/IAWallpaper.git`, chave `ED25519` validada) com push automático na branch `main`.
