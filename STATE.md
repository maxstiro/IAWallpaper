# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-23 (Milestone 14 — Refinamento Visual Dark-Fantasy estilo Dungeon Squad: Shader Alto-Contraste, Olhos Luminosos, Sigilo Rúnico & Santuário Abissal)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão `dark_sanctuary` + `Darkness_Shibu.vrm` + `render_style="vrm_3d"` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Novo preset `dark_sanctuary` (*Santuário Abissal · Dungeon Squad*) + Qwen 2.1 relighting 1:1 + Wan 2.2 opcional |
| Render 3D & 2.5D (`render/`) | `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Shader Dark-Fantasy Alto Contraste (outline escuro `0.0042`, sombras roxo-obsidiana, brilho especular anime, olhos emissivos, rim-light arcano), pose confiante de quadril e sigilo hexagrama carmesim-violeta no chão |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pelo pátio gótico 2.5D, poses (`wave`/`dance`/`stretch`/`sit_work`/`sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + seletor de Motor Visual (`vrm_3d` / `world_sprite` / `portrait`) + **📂 Carregar .VRM** + cenário `dark_sanctuary` / `sky_sanctuary` |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 30/30 Verdes | `pytest` completo + `render_showcase.py --scene dark_sanctuary --vrm Darkness_Shibu.vrm` |

---

## 2. Assets Locais (fora do Git)
- **Modelos 3D Anime VRM (`assets/generated/vrm/`)**:
  - `Darkness_Shibu.vrm` (padrão — visual gótico dark-fantasy estilo *Dungeon Squad*: cabelo vinho-carmesim, vestido gótico azul/carmesim, meias escuras e saltos plataforma).
  - `Victoria_Rubin.vrm`, `AvatarSample_A.vrm`, `vroid_sample.vrm`, `seed_san.vrm` + suporte 1-clique a qualquer `.vrm`/`.glb` do usuário.
- **Santuário Abissal (`assets/generated/scenes/dark_sanctuary/diorama_*.png`)**:
  - Pátio gótico de pedras obsidianas com runas brilhantes, braseiros acesos e balaustrada, reiluminado 1:1 via Qwen 2.1 em `day`, `sunset` (eclipse carmesim), `night` (runas magenta + lua) e `rain` (pedras molhadas reflexivas).
- **Observatório Celeste (`sky_sanctuary`) & Clipes 2D Wan 2.2 da Mira**: Preservados como opções selecionáveis na Central de Controle.
- **Prévias & GIFs Validados**: `m14_dungeon_squad_showcase.png` e `m14_dungeon_squad_demo.gif` (enviados ao Telegram).

---

## 3. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF Dungeon Squad**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona nyx --scene dark_sanctuary --style vrm_3d --vrm Darkness_Shibu.vrm --mode gif --out demo_ds.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).
