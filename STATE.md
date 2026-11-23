# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-23 (Milestone 16 · Etapa 1d — Shader Aquarela Fosco Tree of Savior sem brilho 3D, Câmera Teleobjetiva 15.5°, Cabelo Fluido por Vertex Shader & Animação com Ação Sobreposta em 20 FPS)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão `sky_sanctuary` + `vrm_model="elfa_loira"` + `render_style="vrm_3d"` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Presets `sky_sanctuary` (padrão) e `dark_sanctuary` com Qwen 2.1 relighting 1:1 + Wan 2.2 opcional |
| Render 3D & 2.5D (`render/`) | `vrm_sculptor.py`, `dungeon_avatar.py`, `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Pipeline **Aquarela/Guache Tree of Savior** (`960×1200` MRT + Sobel sépia-café -> `640×800`): ZERO brilho plástico 3D na pele, rosto 92% plano com olhos grandes abertos, câmera teleobjetiva quase ortográfica (`FOV 15.5°`), textura sutil de papel, **física fluida de cabelo no vertex shader** (rastro de caminhada, brisa e abertura em giro 360°) e **animação em cascata (*overlapping action*)** em `VrmAnimator` (quadril -> coluna -> peito -> cabeça -> braços -> pulsos) |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça `sky_sanctuary`, poses 360° (`idle` natural, `walk`, `wave`, `dance`, `stretch`, `sit_work`, `sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio com seletor direto das **4 garotas base HD** (`Lyra`, `Freya`, `Airi`, `Lilith`) + `.VRM` externos |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 31/31 Verdes | `pytest` completo + `render_showcase.py --scene sky_sanctuary --vrm elfa_loira` |

---

## 2. Assets Locais (fora do Git)
- **4 Arquétipos Base HD (`vrm_sculptor.py` sobre malhas studio em `assets/generated/vrm/`)**:
  1. `elfa_loira` (**Lyra — Elfa Loira**, padrão ativo de refinamento): orelhas élficas longas em 3D, pele bronzeada dourada, olhos esmeralda, cabelo loiro longo e roupa de baixo branca simples.
  2. `humana_ruiva` (**Freya — Humana Ruiva**): cabelo ruivo-cobre, olhos verde-oliva, roupa de baixo preta com borda dourada.
  3. `androide_rosa` (**Airi — Androide Rosa**): cabelo rosa-pastel longo, olhos safira, roupa de baixo rosa-pérola.
  4. `vampira_negra` (**Lilith — Vampira**): rabo lateral preto-esmeralda, sardas sutis, olhos jade, roupa de baixo preta/carmesim.
- **Cenário Padrão — Observatório Celeste (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**: Praça aberta ensolarada estilo Tree of Savior reiluminada 1:1 via Qwen 2.1 (`day`, `sunset`, `night`, `rain`).
- **Prévias & GIFs Validados**: `m16_tos_fluid_sheet.png`, `m16_tos_sky_showcase.png`, `m16_tos_sky_demo_tg.gif` (20 FPS) e `m16_four_girls_base.png` (enviados ao Telegram).

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
