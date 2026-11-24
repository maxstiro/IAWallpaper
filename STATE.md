# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-24 (Milestone 18.7 Concluído — **2ª Personagem Oficial `Erin` [Humana Ruiva]**: 9 âncoras `base/` limpas + 6 retratos expressivos 2D + **14 clipes Wan 2.2 @ 16 FPS** no `casual` em algodão fininho [cropped oliva + hotpants mescla cinza-carvão] + 14 clipes extras `casual_denim`, cadeira da `fairy_glade` recalibrada `(0.338, 0.775)` sem sombra sob pés balançando e seletor **Arya / Erin** na Central de Controle · **34/34 testes verdes**)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão `scene_id="fairy_glade"`, `render_style="world_sprite"`, `character_id="arya"` (`default_outfit="cozy_shirt"`, `base` preservado) |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py`, `character_pipeline.py` | 🟢 Validado E2E | `CharacterPipeline`: inicialização padronizada `characters/<id>/outfits/<outfit>/`, geração de poses-âncora Qwen 2.1 Edit, outfits 1:1 e baking Wan 2.2 (`start == end` e transições `start != end`, 25f/41f @ 16 FPS) em 3 Tiers |
| Render 2.5D & 3D (`render/`) | `character_pack.py`, `sprite_clip.py`, `avatar.py`, `live2d_mesh.py`, `vrm_sculptor.py`, `dungeon_avatar.py`, `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | **Motor Oficial Wan 2.2 (`character_pack.py` + `sprite_clip.py` + `avatar.py`)**: 8 direções reais (`S/SE/L/NE/N/NO/O/SO`) via 5 ângulos canônicos com espelhamento instantâneo em 0 ms (`NO/O/SO`), rotas multi-waypoint (`walk_path`) com preservação de fase da passada (zero flash de `idle` nas curvas), Grafo de Poses com reversão temporal (`play_reverse=True` em `sentar <-> levantar` e `deitar <-> levantar`), acoplamento matemático `stride_ratio ↔ velocidade` (zero patinação), aceleração automática `run` (`1.45×`) e expressões 2D desacopladas |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça `sky_sanctuary`, poses fluidas (`idle`, `walk`, `run`, `sit_floor`, `sit_chair`, `lie`, `wave`, `interact`, `spin`, `sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio com **✨ Clipes 2D Wan 2.2 · 8 Direções (Arya)** como motor padrão + Live2D 2.5D / VRM 3D / Retrato |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 34/34 Verdes | `pytest -v` completo (incluindo `test_arquitetura.py`) + `render_showcase.py --style world_sprite --character arya --scene sky_sanctuary` |

---

## 2. Assets Locais (fora do Git)
- **Personagem Piloto Oficial — Arya (`assets/generated/characters/arya/`)**:
  - `character.json` (`default_outfit="cozy_shirt"`) + `master_idle_SE.png`.
  - `portraits/` (**6 retratos expressivos 2D desacoplados** no medalhão ao vivo do HUD): `happy.png`, `affectionate.png`, `shy.png`, `pouty.png`, `sleepy.png`, `focused.png`.
  - **Outfit 1:1 Oficial — `outfits/cozy_shirt/` (Camisola Casual / Camisetão)**: 9 âncoras Qwen 2.1 Edit + **14 clipes Wan 2.2 @ 16 FPS** (`idle_SE` 41f, `wave_SE` 41f, `walk_S/SE/L/NE/N` 25f, `sit_chair_SE`, `sit_floor_SE`, `lie_SE`, `interact_SE`, `trans_sit_chair`, `trans_sit_floor`, `trans_lie`).
  - **Outfit Base Estrutural — `outfits/base/`**: 9 poses-âncora Qwen 2.1 + **15 clipes Wan 2.2 @ 16 FPS** (inclui `spin_SE`).
- **2ª Personagem Oficial — Erin (`assets/generated/characters/erin/` · Humana Ruiva)**:
  - `character.json` + `master_idle_SE.png` (~4.1 cabeças estilo *Rapscallion × Tree of Savior*, orelhas humanas, cabelo ruivo acobreado, sardas e base limpa minimalista).
  - `portraits/` (**6 retratos expressivos 2D** com orelhas humanas): `happy`, `affectionate`, `shy`, `pouty`, `sleepy`, `focused`.
  - `outfits/base/anchors/`: 9 âncoras limpas (sem móvel em `sit_chair_SE`, `sit_floor_SE`/`lie_SE` alinhadas ao chão).
  - `outfits/casual_denim/`: 9 âncoras + **14 clipes Wan 2.2 @ 16 FPS** completos preservados como traje extra.
  - `outfits/casual/` (**Outfit Padrão — Algodão Fininho**): 9 âncoras (hotpants cinza-carvão mescla liso + top cropped oliva-sálvia) + **14 clipes Wan 2.2 @ 16 FPS** completos (`idle_SE` 41f, `wave_SE` 41f, `walk_S/SE/L/NE/N`, `sit_chair_SE`, `sit_floor_SE`, `lie_SE`, `interact_SE`, `trans_sit_chair`, `trans_sit_floor`, `trans_lie`).
- **Cenário Padrão Oficial — Clareira Mágica de Acampamento (`assets/generated/scenes/fairy_glade/diorama_*.png`)**: Aquarela *Tree of Savior* gerada via Qwen Image 2.1 (`1344×768`) e reiluminada 1:1 para `day`, `sunset`, `night` (vaga-lumes, lanternas e cogumelos bioluminescentes) e `rain`, com móveis reais calibrados em `world_stage.py` (`chair/desk` `(0.338, 0.775)` sem sombra sob pés balançando e `bedroll/cushion` `(0.720, 0.765)`).
- **Cenários & Motores Opcionais Preservados**: `sky_sanctuary`, `dark_sanctuary`, Rig Live2D 2.5D e 4 Arquétipos 3D VRM.
- **Prévias & GIFs Validados (Milestone 18.6)**: `m186_fairy_glade_4times.png`, `m186_arya_cozy_shirt_anchors.png`, `m186_glade_furniture_check.png` e `m186_arya_fairy_glade_tg.gif` (todos enviados e validados no Telegram).

---

## 3. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF da Arya na Clareira Mágica**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --character arya --scene fairy_glade --style world_sprite --mode gif --out demo_arya_glade.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).

---

## 4. Próximas Etapas
- **Replicação para Novas Personagens (`CharacterPipeline`)**: Criar a 2ª personagem oficial na estrutura padronizada `assets/generated/characters/<id>/` + seletor de personagem/outfit na Central de Controle.
- **Milestone 19 — Desktop Vivo Win11 & Autonomia Completa**: Ligar o `BehaviorDirector` às novas ações/móveis da `fairy_glade` (`walk_path`, `chair`, `bedroll`, `worktable`), validar ancoragem ao vivo atrás dos ícones no Windows 11 Build 26300, multi-monitor e áudio reativo opcional.
