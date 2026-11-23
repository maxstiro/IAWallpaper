# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-23 (Milestone 18.5 Concluído — **Biblioteca Completa da Arya na Roupa Base**: **15 clipes Wan 2.2 @ 16 FPS** cobrindo todos os 5/5 ângulos canônicos [8 direções], todas as posturas [`sit_floor`, `sit_chair`, `lie`], ações [`wave` 41f, `interact`, `spin` 360°], **3 transições reversíveis** [`trans_sit_floor`, `trans_sit_chair`, `trans_lie`] + **6 retratos expressivos 2D** no medalhão ao vivo do HUD · **34/34 testes verdes**)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão `sky_sanctuary` + `render_style="world_sprite"` + `character_id="arya"` (`resolve_character_dir`, `list_character_packs`) com Live2D 2.5D e VRM 3D selecionáveis |
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
  - `character.json` + `master_idle_SE.png` (~4.1 cabeças estilo *Rapscallion × Dungeon Squad × Tree of Savior* em roupa base creme/marrom).
  - `portraits/` (**6 retratos expressivos 2D desacoplados** exibidos no medalhão ao vivo do HUD): `happy.png`, `affectionate.png`, `shy.png`, `pouty.png`, `sleepy.png`, `focused.png`.
  - `outfits/base/anchors/` (**9 poses-âncora Qwen 2.1 Edit**): `master.png`, `walk_SE.png`, `walk_L.png`, `walk_NE.png`, `walk_N.png`, `walk_S.png`, `sit_floor_SE.png`, `sit_chair_SE.png`, `lie_SE.png`.
  - `outfits/base/clips/` (**15 clipes Wan 2.2 @ 16 FPS assados**): `idle_SE` (41f), `wave_SE` (41f), `walk_S/SE/L/NE/N` (25f — todos os 5/5 ângulos canônicos cobrindo 8 direções + corrida acelerada `1.45×`), `sit_floor_SE` (25f), `sit_chair_SE` (25f), `lie_SE` (25f), `interact_SE` (25f), `spin_SE` (25f), e **3 transições reversíveis** `trans_sit_floor`, `trans_sit_chair`, `trans_lie` (25f — ida e volta automática via `reverse=True`!).
- **Cenário Padrão — Observatório Celeste (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**: Praça aberta ensolarada estilo Tree of Savior reiluminada 1:1 via Qwen 2.1 (`day`, `sunset`, `night`, `rain`).
- **Motores Opcionais Preservados**: Rig Live2D 2.5D (`assets/generated/live2d/elfa_loira/`) e 4 Arquétipos 3D VRM (`assets/generated/vrm/`).
- **Prévias & GIFs Validados (Milestones 18 & 18.5)**: `m18_arya_8dir_strip.png`, `m18_arya_8dir_plaza_v2_tg.gif`, `m185_arya_portraits_and_anchors.png`, `m185_arya_actions_strip.png` e `m185_arya_life_plaza_tg.gif` (todos enviados e validados no Telegram).

---

## 3. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF da Arya (Wan 2.2 · 8 Direções)**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --character arya --scene sky_sanctuary --style world_sprite --mode gif --out demo_arya.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).

---

## 4. Próximas Etapas
- **1º Outfit Completo 1:1 da Arya (`generate_outfit_anchors_sync`)**: Vestir as 9 âncoras da `base/` com o primeiro traje completo 1:1 via Qwen Image 2.1 Edit (zero retrabalho de pose!) e assar os clipes do novo traje.
- **Replicação do Fluxo para Novas Personagens**: Usar `CharacterPipeline` para criar a próxima personagem (`Humana Ruiva`, `Androide Rosa` ou `Vampira`) na estrutura padronizada `assets/generated/characters/<id>/`.
- **Milestone 19**: Ancoragem ao vivo Windows 11 Build 26300, multi-monitor independente e áudio reativo opcional.
