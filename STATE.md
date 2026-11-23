# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-23 (Milestone 17 — Pivô para Motor 2.5D Live2D / Spine2D em GPU `live2d_mesh.py`: Arte 2D Pura do ComfyUI + Malha Elástica Geodésica Contínua + Expressões 1:1 + Vista Costas + Outfits em Camadas)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão `sky_sanctuary` + `render_style="live2d_25d"` (`elfa_loira`) com fallback automático para `vrm_3d` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Presets `sky_sanctuary` (padrão) e `dark_sanctuary` + geração de rigs Live2D 2.5D (`base.png`, `base_blink.png`, `base_happy.png`, `base_back.png`) via Qwen Image 2.1 Edit |
| Render 2.5D & 3D (`render/`) | `live2d_mesh.py`, `vrm_sculptor.py`, `dungeon_avatar.py`, `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | **Motor 2.5D Live2D / Spine2D próprio na GPU (`live2d_mesh.py`)**: arte 2D pura (ZERO aspecto 3D!), detecção automática de marcos anatômicos, malha triangular elástica contínua (~7.000 tris) com skinning geodésico sem pontes/cortes, *Head Parallax Turn 2.5D*, mola *soft-body* no busto/respiração, cabelo fluido e micro-twitch nas orelhas élficas, expressões 2D reais 1:1 (`base_blink.png`, `base_happy.png`), vista costas (`base_back.png`) e suporte nativo a camadas modulares de roupas (`outfit_*.png`) |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça `sky_sanctuary`, poses fluidas (`idle`, `walk`, `wave`, `dance`, `stretch`, `sit_work`, `sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio com seletor **✨ Motor 2.5D Live2D / Spine2D (Arte 2D Pura)** + fallback 3D VRM / Wan 2.2 |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 32/32 Verdes | `pytest` completo + `render_showcase.py --style live2d_25d --scene sky_sanctuary --vrm elfa_loira` |

---

## 2. Assets Locais (fora do Git)
- **4 Arquétipos Base HD (`vrm_sculptor.py` sobre malhas studio em `assets/generated/vrm/`)**:
  1. `elfa_loira` (**Lyra — Elfa Loira**, padrão ativo de refinamento): orelhas élficas longas em 3D, pele bronzeada dourada, olhos esmeralda, cabelo loiro longo e roupa de baixo branca simples.
  2. `humana_ruiva` (**Freya — Humana Ruiva**): cabelo ruivo-cobre, olhos verde-oliva, roupa de baixo preta com borda dourada.
  3. `androide_rosa` (**Airi — Androide Rosa**): cabelo rosa-pastel longo, olhos safira, roupa de baixo rosa-pérola.
  4. `vampira_negra` (**Lilith — Vampira**): rabo lateral preto-esmeralda, sardas sutis, olhos jade, roupa de baixo preta/carmesim.
- **Cenário Padrão — Observatório Celeste (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**: Praça aberta ensolarada estilo Tree of Savior reiluminada 1:1 via Qwen 2.1 (`day`, `sunset`, `night`, `rain`).
- **Rig Live2D 2.5D Ativo (`assets/generated/live2d/elfa_loira/`)**:
  - `base.png` (Elfa Loira fiel 1:1 à referência Rapscallion × Tree of Savior em roupa de baixo marrom/creme), `base_blink.png` (piscar 1:1 pintado à mão), `base_happy.png` (sorriso radiante 1:1) e `base_back.png` (vista de costas 180°).
- **Prévias & GIFs Validados**: `m17_l2d_sheet.png`, `m17_l2d_sky_showcase.png` e `m17_l2d_sky_demo_tg.gif` (20 FPS enviados ao Telegram).

---

## 3. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF HD da Elfa Loira**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --scene sky_sanctuary --style vrm_3d --vrm elfa_loira --mode gif --out demo_elfa.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).

---

## 4. Progresso do Refinamento Direcionado (Milestone 16)
1. **Aparência Geral (Em Refinamento — Base HD concluída)**: resolução elevada para `640×800` MSAA 4x estilo *Tree of Savior*, rosto 100% legível, malha studio sem costuras em roupa de baixo simples para facilitar incrementação de outfits e 4 arquétipos base prontos.
2. **Identidade do Avatar (Próximo)**: lapidar traços faciais individuais, penteados exclusivos (ex.: trança lateral da ruiva, franja assimétrica da androide) e primeiros outfits em camadas.
3. **Ritmo & Movimentos (Em seguida)**: lapidar cadência, *timing* de respiração/idle, física secundária de cabelo/busto e expressividade 360°.
