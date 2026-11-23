# PROJETO.md — IAWallpaper (Living Waifu Dynamic Wallpaper)

> **Regra Permanente de Agente**: Mantenha este arquivo (`PROJETO.md`), [`STATE.md`](STATE.md) e [`roadmap.md`](roadmap.md) sempre atualizados e referenciados a cada marco concluído. São a fonte única de verdade sobre a arquitetura, decisões de engenharia e evolução do projeto.
> **Repositório Oficial**: `https://github.com/maxstiro/IAWallpaper.git`
> **Última atualização**: 2026-11-22 (Milestone 12 — Locomoção & Orientação 4-Vias Real via Qwen 2.1 Turnaround + Wan 2.2 Direcional)

---

## 1. Objetivo Geral

Criar um **wallpaper dinâmico interativo** (inspirado em **Wallpaper Engine** e na arquitetura cognitiva/comportamental de [**Pestinha**](https://github.com/mille-okws/pestinha)) estrelado por um **avatar estilo waifu** ciente de contexto, reativo, animado, com aparência dinâmica e capaz de aprendizado contínuo, vivendo dentro de um **cenário de papel de parede vivo** que responde em tempo real ao ciclo dia/noite, clima real, atividade do usuário no PC, carga do sistema e interações diretas com o mouse na área de trabalho.

### Pilares Implementados
1. **Wallpaper Vivo Nativo (Estilo Wallpaper Engine)**:
   - Renderização 2.5D em 30/60 FPS com auto-pausa automática em jogos/vídeos em tela cheia.
   - Ancoragem Win32 dual atrás dos ícones do desktop (`Progman` + `SHELLDLL_DefView` em **Windows 11 24H2+ Raised Desktop** e `WorkerW` clássico em **Windows 10/11**), com desacoplamento limpo ao encerrar e modo `--preview` interativo.
2. **Cérebro Cognitivo com Aprendizado Real (Inspirado em Pestinha)**:
   - **Rede Neural Pulsada (LIF)** de **438 neurônios** em NumPy puro (`core/nervous_system.py`), sem acoplamento com Qt ou SO.
   - **23 canais sensoriais** (atividade no PC, digitação, silêncio, carga do sistema, luz solar/noturna, chuva/tempestade, carinho, cutucada, mimo, dispensa, cansaço, tédio, carência, antecipação) com **habituação sináptica** e recuperação exponencial.
   - **12 populações de interneurônios** e **14 motores** (9 de expressão + 5 de decisão com inibição lateral).
   - **Plasticidade de Três Fatores (`learn`)**, **Condicionamento Rescorla-Wagner (`conditioning.py`)**, **Bandit Contextual Episódico com consolidação durante o sono (`episodic.py`)** e **Homeostase Circadiana + Afinidade (`homeostasis.py`)**.
3. **Cenário & Aparência Dinâmica**:
   - **Ciclo Circadiano 24h**: 7 períodos (Alvorada, Manhã, Tarde, Pôr do Sol, Crepúsculo, Noite, Madrugada) com paleta contínua, astros, estrelas, luzes urbanas e iluminação de borda (*rim-light*).
   - **Clima Real (Open-Meteo)**: Limpo, Nublado, Chuva, Tempestade com relâmpagos, Neve e Neblina via API gratuita sem chave, cache local e override manual.
   - **Avatar 2.5D Animado**: Suporta tanto sprites PNG RGBA transparentes gerados pelo ComfyUI (`isnet-anime` RemBG) com harmonização de cor por silhueta (`CompositionMode_SourceAtop` em buffer com cache) quanto avatar anime procedural nativo; inclui respiração, piscar, olhar/paralaxe seguindo cursor, física de mola, carinho na cabeça com corações vetoriais e troca automática de traje (`casual`, `focus`, `rainy`, `cozy`, `nightwear`, `starlight`).
4. **Ponte ComfyUI Read-Only (`comfy/`)**:
   - Consome exclusivamente a API HTTP local (`http://127.0.0.1:8188`) para gerar sprites RGBA da avatar e cenários multi-horário (Dia/Pôr do Sol/Noite/Chuva) via `waiIllustriousSDXL_v170` + `PerturbedAttentionGuidance` + `Image Rembg (isnet-anime)` sem alterar nenhum arquivo do ComfyUI Studio.
5. **Central de Controle, Monitor Neural & Privacidade**:
   - Interface Dark Glassmorphic em 4 abas, Monitor Neural em tempo real, ícone na bandeja do sistema, atalho global de pânico (`Ctrl+Alt+Shift+W`), persistência JSON atômica anti-NaN e privacidade estrita (nunca lê conteúdo de janela nem digitação).

---

## 2. Arquitetura em Camadas (Verificada por `tests/test_arquitetura.py`)

```text
core  <  plataforma  <  sense  <  comfy  <  render  <  mind  <  ui  <  app.py
```

| Camada | Diretório | Módulos Implementados | Usa Qt | Usa API SO |
|---|---|---|:-:|:-:|
| **Shared** | `iawallpaper/` | `paths.py`, `store.py`, `mathutil.py`, `config.py`, `log.py` | não | não |
| **Core** | `iawallpaper/core/` | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | não | não |
| **Plataforma** | `iawallpaper/plataforma/` | `desktop_host.py`, `windows.py` | não | sim |
| **Sense** | `iawallpaper/sense/` | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | não | não |
| **Comfy** | `iawallpaper/comfy/` | `presets.py`, `bridge.py`, `workflows.py` | não | não |
| **Render** | `iawallpaper/render/` | `sprite_clip.py`, `avatar.py`, `world_stage.py`, `skeleton.py`, `rig_cutter.py`, `atmosphere.py`, `particles.py`, `scene.py`, `canvas.py` | sim | não |
| **Mind** | `iawallpaper/mind/` | `director.py` | não | não |
| **UI** | `iawallpaper/ui/` | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | sim | não |
| **App** | `iawallpaper/app.py`, `main.py` | Orquestração principal, trava de instância única, ciclos 16ms/100ms/500ms/15m/30s, launcher `start_iawallpaper.ps1` | sim | sim |

---

## 3. Histórico de Marcos Concluídos
- **Milestone 1** (2026-11-22): Inicialização do repositório `IAWallpaper`, `venv` isolado com PySide6/NumPy/Pillow/psutil/pywin32/pytest, e documentação dedicada (`PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`).
- **Milestone 2** (2026-11-22): Infraestrutura atômica anti-NaN (`store.py`, `paths.py`, `config.py`, `mathutil.py`, `log.py`) + núcleo cognitivo completo (`WaifuSpikingBrain` 438 neurônios LIF, `Drives` circadiano + afinidade, `Conditioning` Rescorla-Wagner, `EpisodicMemory` contextual bandit, `EmotionDecoder`, personas `Mira` e `Nyx`). Validado com 9 testes unitários.
- **Milestone 3** (2026-11-22): Plataforma Windows 10/11 (`desktop_host.py` com suporte Win11 24H2+ Raised Desktop + WorkerW clássico; `windows.py` para processo ativo, ociosidade, tela cheia, cursor, telemetria, autostart e atalho `Ctrl+Alt+Shift+W`) e sensores (`circadian.py`, `weather.py` Open-Meteo com cache/override, `senses.py`, `routine.py`). Validado com 5 testes unitários.
- **Milestone 4** (2026-11-22): Motor visual 2.5D em 60 FPS (`atmosphere.py`, `particles.py`, `avatar.py`, `scene.py`, `canvas.py`) com sprites RGBA + fallback procedural anime, partículas vetoriais (corações, estrelas, notas, chuva, neve, pétalas, vaga-lumes, relâmpagos, estrelas cadentes), paralaxe, rim-light cacheado sem artefato retangular e HUD ambiental glassmórfico. Validado visualmente por renderização offscreen.
- **Milestone 5** (2026-11-22): Diretor comportamental (`mind/director.py`) e cliente HTTP read-only para ComfyUI (`comfy/bridge.py`, `comfy/workflows.py`). Geração validada ponta-a-ponta do pacote inicial local (`mira/casual.png` RGBA via `isnet-anime`, `sky_sanctuary/sunset.png` e `sky_sanctuary/night.png`).
- **Milestone 6** (2026-11-22): Central de Controle Dark Studio (`control_center.py`), Monitor Neural ao Vivo (`neural_monitor.py`), Bandeja do Sistema (`tray.py`), composição `app.py` / `main.py` / `start_iawallpaper.ps1`, testes de invariantes arquiteturais (`test_arquitetura.py`) e integração (`test_app_integration.py` — 21/21 verdes) + publicação no GitHub via SSH (`git@github.com:maxstiro/IAWallpaper.git`).
- **Milestone 7** (2026-11-22): Crossfade suave (`smoothstep`) em `AvatarRig` (0.55s entre expressões/trajes) e `SceneCompositor` (1.5s entre horários/clima); workflows img2img consistentes em `comfy/workflows.py` + upload sobre fundo branco via `/upload/image` + gerador em lote `generate_full_pack_sync/async` (`alpha_matting=False` no `isnet-anime` eliminando pico de memória do `pymatting`); Criador de Waifu Personalizada (`CustomPersonaDialog`, `create_custom_persona`, `save_persona`) e painel de cobertura de assets na Central de Controle; ferramentas CLI `tools/generate_pack.py` e `tools/render_showcase.py`; geração validada do pack completo da **Mira** (11 sprites RGBA consistentes: base + 5 expressões + 5 trajes) + 4 horários do **Observatório Celeste** (`day`, `sunset`, `night`, `rain`) com **23/23 testes verdes**.
- **Milestone 8** (2026-11-22): Transformação para **Mundo Vivo 2.5D estilo Ragnarok Online / Tree of Savior / Pokémon NDS** como padrão (`render_style="world_sprite"`, mantendo `"portrait"` como opção na Central de Controle). Criado `render/world_stage.py` (`WorldStage`, `WorldHotspot`, perspectiva de profundidade por Y, Y-sort de props interativos, ondas de chuva no piso e poeira/respingos sob os passos); atualizado `render/avatar.py` para sprite full-body caminhável (locomoção 2D com flip horizontal, pulo de passo, sombra de contato, guarda-chuva translúcido automático em chuva/tempestade, balões de emote RO/Pokémon `♥`, `!`, `♪`, `✦`, `Zzz`, `?` e fallback chibi full-body animado); adicionado *click-to-move* no chão do desktop (`ground_clicked`) e navegação autônoma em `mind/director.py`; adicionados workflows ComfyUI `build_diorama_scene_workflow` + `build_world_sprite_workflow` + `generate_world_pack_sync/async` e gerado o pack completo 2.5D da **Mira** (6 sprites full-body RGBA + 4 dioramas `diorama_day/sunset/night/rain`) validado visualmente com **24/24 testes verdes**.
- **Milestone 9** (2026-11-22): Resolução definitiva de flutuação, variação excessiva de cenário, complexidade de animação e estilo maduro via preset `(TOP)` do ComfyUI:
  - **Ancoragem Real & Animação Multi-Banda (`render/avatar.py`)**: `trim_sprite_pixmap()` remove margens transparentes sob os pés para encostar exatamente na sola dos sapatos; sombra dupla (oclusão de contato + sombra direcional oposta ao sol/lua) + reflexo no piso molhado na chuva; deformação esquelética 2.5D em 3 bandas anatômicas sobrepostas (pernas fixas no chão, quadril/tronco respirando/balançando, busto/cabeça acompanhando cursor) + ações `stretch`, `wave`, `admire_view`, `music_sway`, `sit_work` e `sleep`.
  - **Dinâmica Própria dos Locais (`render/world_stage.py`, `render/scene.py`)**: Raios solares volumétricos (*god rays*), caustics/reflexos cintilantes no piso, névoa deslizante, luzes de lanternas pulsando à noite, pássaros/borboletas diurnos e anel luminoso interativo no clique do chão.
  - **Leitor Read-Only de Presets `(TOP)` & Reiluminação 1:1 Qwen 2.1 (`comfy/presets.py`, `workflows.py`, `bridge.py`, `control_center.py`)**: Lê `approved_combos.json` (read-only) permitindo escolher qualquer preset do ComfyUI Studio (padrão `RawSexyGlowingGemPencil(TOP)` com `arthemyComics_v80` + 5 LoRAs para waifu adulta, madura e glamorosa) e reilumina o **mesmo cenário base** (`diorama_day.png`) em `sunset`, `night` e `rain` via **Qwen Image 2.1 Edit** (`NoctQ_V3_turbo_int8_convrot` + `qwen3vl_8b_int8_convrot` + `qwen-anime-Illustration-1`) preservando 100% da arquitetura. Validado visualmente com **25/25 testes verdes**.
- **Milestone 10** (2026-11-22): **Esqueleto Real 2D de 18 Ossos (`CharacterSkeleton`), AutoRigger Spine2D (`rig_cutter.py`) & Cenário Eye-Level em Escala Humana 1:1**:
  - **Motor Esquelético FK (`render/skeleton.py`)**: Hierarquia anatômica real de 18 ossos com convenção articular humana (joelhos dobrando apenas para trás na caminhada, coxas/canelas dobrando à frente ao sentar, braços erguidos no aceno e alongamento, guarda-chuva ancorado na mão direita `forearm_r.end`), física de mola para cabelo/saia e auto-aterramento matemático (`max(foot_y) == 0.0`).
  - **AutoRigger Guiado por Silhueta (`render/rig_cutter.py`)**: Recorta automaticamente um sprite frontal A-pose (`rig_base.png`) em 10 peças RGBA (`head`, `torso`, `upper_arm_l/r`, `forearm_l/r`, `thigh_l/r`, `shin_l/r`) usando detecção exata de axilas (*armpit gap detection*), juntas circulares sobrepostas e calibração 1:1 de `RigProportions`.
  - **Workflows A-Pose & Terraço Eye-Level 1:1 (`comfy/workflows.py`, `bridge.py`, `world_stage.py`, `director.py`)**: Novo `build_apose_rig_workflow` com preset `(TOP)` + cenário *eye-level* em escala humana (passarela de pedra com corrimãos laterais reiluminada 1:1 via Qwen Image 2.1 para dia/pôr do sol/chuva/noite) + novos modos diagnósticos `--mode rig_parts` e `--mode gif` em `tools/render_showcase.py`. Validado com **27/27 testes verdes**, inspeção visual das 10 peças + showcase + GIF animado no Telegram.
- **Milestone 11** (2026-11-22): **Animação Fluida Quadro-a-Quadro via Wan 2.2 `WanFirstLastFrameToVideo` + Praça Aberta Estilo Tree of Savior / Ragnarok Online**:
  - **Motor de Clipes RGBA (`render/sprite_clip.py`, `render/avatar.py`)**: Elimina definitivamente o aspecto de marionete 2D ao reproduzir clipes `.webp`/`.gif` RGBA transparentes quadro-a-quadro em loop infinito perfeito (`clip_idle`, `clip_walk`, `clip_wave`, `clip_dance`), com recorte de linha de pés unificada entre frames (zero flutuação/jitter), crossfade suave (0.22s) entre ações, anel mágico giratório no chão estilo Ragnarok Online / Tree of Savior, reflexo animado no piso molhado e 0% de uso de GPU durante a reprodução no desktop.
  - **Pipeline ComfyUI Wan 2.2 + Qwen 2.1 (`comfy/workflows.py`, `bridge.py`, `tools/generate_pack.py`)**: Adicionado `build_wan_sprite_clip_workflow` (`Wan2.2_Remix_NSFW_i2v_14b_high/low_lighting_fp8` + `WanFirstLastFrameToVideo` travando `start_image == end_image` + `isnet-anime` RemBG + `SaveAnimatedWEBP`) e nova praça aberta 3/4 com árvore sagrada, lanternas e piso de pedras reiluminada 1:1 sem bordas para Manhã, Pôr do Sol, Chuva e Noite. Validado visualmente (folha dos 4 clipes + mosaico 4 horários + GIF animado de 6s enviado no Telegram) com **28/28 testes verdes**.
- **Milestone 12** (2026-11-22): **Locomoção & Orientação 4-Vias Real (Estilo Ragnarok Online / Tree of Savior) via Qwen 2.1 Turnaround + Wan 2.2 Direcional**:
  - **Turnaround Fiel 1:1 (`build_qwen_turnaround_workflow`, `generate_directional_walks_sync`)**: Rotaciona a mesma personagem (`rig_base.png`) via Qwen Image 2.1 Edit para perfil 3/4 direita (`pose_side.png`) e costas 3/4 (`pose_back.png`) preservando 100% do cabelo, presilha, vestido e saltos, e anima ambos em loop infinito via Wan 2.2 (`clip_walk_side.webp`, `clip_walk_back.webp` — 25 frames RGBA cada).
  - **Motor Direcional 4-Vias & HUD Responsivo (`render/avatar.py`, `render/scene.py`)**: Seleciona automaticamente `side` (direita/esquerda com espelhamento apenas em caminhada direcional para preservar a assimetria da pose frontal), `back` (subindo para o fundo da praça) e `front` (descendo para a câmera) com limiar angular calibrado para 16:9 (`1.35`), velocidade/cadência de passo acoplada à profundidade 2.5D (zero patinação) e card HUD ambiental responsivo. Validado com **29/29 testes verdes**, folha direcional e GIF de 7.5s no Telegram.
