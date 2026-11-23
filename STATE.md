# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 10 — Esqueleto Real 2D de 18 Ossos, AutoRigger Spine2D & Terraço Eye-Level 1:1)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com 12 pacotes instalados |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Escrita atômica anti-NaN e recuperação `.corrompido` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Workflow A-pose (`build_apose_rig_workflow`) com preset `(TOP)` + Terraço eye-level 1:1 reiluminado via Qwen 2.1 |
| Render (`render/`) | `skeleton.py`, `rig_cutter.py`, `avatar.py`, `world_stage.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Esqueleto real 18 ossos FK + `AutoRigger` (10 peças RGBA com juntas circulares), guarda-chuva na mão direita, reflexo articulado molhado, sombra dupla aterrada |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma na passarela (`desk`, `cushion`, `music_spot`, `overlook`, `lantern`), poses expressivas (`wave`/`stretch`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor Preset ComfyUI + Mundo 2.5D/Retrato + Criador de Waifu + Monitor Neural |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 27/27 Verdes | `pytest` completo + `generate_pack.py --preset ...` + `render_showcase.py --mode world/rig_parts/gif` |

---

## 2. Assets Gerados Localmente (ComfyUI Read-Only, fora do Git)
- **Mira — Rig Esquelético A-Pose (`assets/generated/personas/mira/rig_base.png`)**:
  - Gerado com o preset **`RawSexyGlowingGemPencil(TOP)`** (`arthemyComics_v80` + 5 LoRAs) + `isnet-anime` RemBG em pose frontal simétrica A-pose.
  - Recortado automaticamente em runtime pelo `AutoRigger` (`rig_cutter.py`) em **10 peças articuladas RGBA** (`head`, `torso`, `upper_arm_l/r`, `forearm_l/r`, `thigh_l/r`, `shin_l/r`) com detecção de axilas (*armpit gap detection*), juntas circulares sobrepostas e calibração 1:1 de `RigProportions` no `CharacterSkeleton`.
- **Observatório Celeste — Terraço / Passarela Eye-Level 1:1 Reiluminado via Qwen Image 2.1 (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**:
  - `diorama_day.png` (perspectiva *eye-level* em escala humana 1:1 com passarela de pedra central e corrimãos laterais) + `diorama_sunset.png`, `diorama_night.png`, `diorama_rain.png` (arquitetura 100% idêntica nos 4 climas/horários!).
- **Prévia & GIF Validados**: `assets/generated/m10_rig_parts.png`, `assets/generated/m10_world_showcase.png` e `assets/generated/m10_skeleton_demo.gif` (enviados ao canal Telegram).
- **Fallback Procedural Esquelético**: Qualquer nova persona/cenário sem PNG gerado opera nativamente com avatar vetorial também 100% guiado pelos 18 ossos do `CharacterSkeleton`.

---

## 3. Bugs Encontrados e Resolvidos (Milestones 6–10)
1. **Filtro de consolidação em `core/episodic.py`**: Episódios recém-decaídos (`n = 0.995`) eram filtrados por `n >= 1.0` em `preferences()`; ajustado para `n >= 0.2`.
2. **Retângulo semitransparente em volta do sprite RGBA (`render/avatar.py`)**: Corrigido renderizando o tint em buffer `QPixmap` transparente dedicado com cache por paleta.
3. **Glifos de coração/brilho virando caixas em offscreen (`render/particles.py`)**: Substituídos por formas vetoriais puras (`QPainterPath`).
4. **Erro `numpy._ArrayMemoryError` em `pymatting` durante `Image Rembg` (`comfy/workflows.py`)**: Ajustado para `alpha_matting=False` mantendo `model="isnet-anime"` e `post_processing=True`.
5. **Rigidez de sprites img2img e desalinhamento com fundo isométrico (Milestone 10)**: Substituído por esqueleto FK real de 18 ossos (`skeleton.py`), `AutoRigger` sobre A-pose (`rig_cutter.py`) com detecção de axilas evitando invasão da saia/cabelo nos braços, e novo cenário *eye-level* em escala humana 1:1 com hotspots centrados na passarela (`WALK_MIN_X=0.33..0.69`).

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Gerar Pack Esquelético + Terraço via CLI**: `.\venv\Scripts\python.exe tools\generate_pack.py --persona mira --scene sky_sanctuary --style world --preset "RawSexyGlowingGemPencil(TOP)"`
- **Gerar Showcase, Peças do Rig ou GIF Animado**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --scene sky_sanctuary --mode gif --out demo.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote configurado via SSH (`git@github.com:maxstiro/IAWallpaper.git`, chave `ED25519` validada) na branch `main`.
