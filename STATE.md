# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-23 (Milestone 15 — Avatar 3D HD Pixel-Art estilo Dungeon Squad: Rig Esculpido Voluptuoso, Pipeline 1px Ink Outline + Nearest-Neighbor, Trajes Modulares Dinâmicos & Restauração do Cenário `sky_sanctuary`)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com PySide6, NumPy, Pillow, psutil, pywin32, moderngl, pytest |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Padrão restaurado para `sky_sanctuary` + `vrm_model="dungeon_squad"` + `render_style="vrm_3d"` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `presets.py`, `bridge.py`, `workflows.py` | 🟢 Validado E2E | Presets `sky_sanctuary` (padrão) e `dark_sanctuary` com Qwen 2.1 relighting 1:1 + Wan 2.2 opcional |
| Render 3D & 2.5D (`render/`) | `dungeon_avatar.py`, `vrm_loader.py`, `vrm_animator.py`, `vrm_renderer.py`, `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | Novo `dungeon_avatar.py` (waifu 3D esculpida ~4.2 cabeças com busto, cintura ampulheta, coxas grossas, capa escura com barra dourada, halo celestial giratório, chamas arcanas e cajado/espada modular) + pipeline **HD Pixel-Art 3D** em `vrm_renderer.py` (FBO MRT `152x190`, cel-shading 3 bandas, contorno externo exato 1px + contornos internos por profundidade + upscaling `Nearest-Neighbor`) |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Navegação autônoma pela praça `sky_sanctuary`, poses 360° (`idle` A-frame, `walk`, `wave`, `dance`, `stretch`, `sit_work`, `sleep`), emotes RO, sono e sussurros |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + opção `★ Dungeon Squad 3D Pixel-Art (Nativo · Trajes Dinâmicos)` + suporte a `.VRM` externos |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tools/`, `tests/` | 🟢 31/31 Verdes | `pytest` completo + `render_showcase.py --scene sky_sanctuary --vrm dungeon_squad` |

---

## 2. Assets Locais (fora do Git)
- **Avatar 3D Nativo (`dungeon_avatar.py`)**: Construído em memória em `< 40 ms` para qualquer Persona (`Mira`, `Nyx`, Custom) e Traje (`starlight` Astral/Titan, `focus` Sacerdotisa + Cajado Crescente, `casual` Valquíria + Espada Rúnica), sem necessidade de pré-renderizar vídeos por movimento.
- **Modelos 3D Externos (`assets/generated/vrm/`)**: `Darkness_Shibu.vrm`, `Victoria_Rubin.vrm`, `AvatarSample_A.vrm`, `vroid_sample.vrm`, `seed_san.vrm` (também compatíveis com o shader HD Pixel-Art 3D e estilização de proporções!).
- **Cenário Padrão — Observatório Celeste (`assets/generated/scenes/sky_sanctuary/diorama_*.png`)**: Praça aberta ensolarada estilo Tree of Savior reiluminada 1:1 via Qwen 2.1 (`day`, `sunset`, `night`, `rain`); `dark_sanctuary` preservado como opção extra na Central de Controle.
- **Prévias & GIFs Validados**: `m15_dungeon_squad_showcase.png` e `m15_dungeon_squad_demo.gif` (enviados ao Telegram junto à folha de close-up dos 3 trajes × 4 ângulos).

---

## 3. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Renderizar Showcase ou GIF Dungeon Squad Pixel-Art 3D**: `.\venv\Scripts\python.exe tools\render_showcase.py --persona mira --scene sky_sanctuary --style vrm_3d --vrm dungeon_squad --mode gif --out demo_ds.gif`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
- **Git / GitHub**: Remote via SSH (`git@github.com:maxstiro/IAWallpaper.git`, branch `main`).

---

## 4. Próxima Sessão Planejada (Milestone 16 — Ordem Aprovada pelo Usuário)
1. **Aparência Geral**: refinar o estilo geral HD pixel-art 3D (malha, proporções, sombreamento, roupas/acessórios e silhueta).
2. **Identidade do Avatar**: consolidar rosto, cabelo, paleta e assinatura visual única da personagem.
3. **Ritmo & Movimentos**: lapidar cadência, *timing* de respiração/idle, física secundária e animações 360°.
