# roadmap.md — Cronograma de Milestones (`IAWallpaper`)

> **Diretriz**: Avançar de forma modular, verificando cada etapa com testes automatizados e registrando tudo em `PROJETO.md`, `STATE.md` e `roadmap.md`.

---

## Fase 1 — Fundação & Núcleo Cognitivo
- [x] **Milestone 1**: Repositório Git (`IAWallpaper`), `venv` dedicado, estrutura documental (`PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`) e definição de camadas.
- [x] **Milestone 2**: Infraestrutura compartilhada (`store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py`) e núcleo neural completo (`core/nervous_system.py` LIF 438 neurônios, `core/homeostasis.py`, `core/conditioning.py`, `core/episodic.py`, `core/emotion.py`, `core/persona.py`) + 9 testes unitários.

## Fase 2 — Percepção do Mundo & Host Windows 11
- [x] **Milestone 3**: Plataforma Windows (`desktop_host.py` com suporte Win11 24H2+ Raised Desktop e WorkerW clássico, `windows.py` para processo ativo, ociosidade, tela cheia, cursor, telemetria, autostart e atalho de pânico `Ctrl+Alt+Shift+W`) e camada sensorial (`senses.py`, `circadian.py`, `weather.py` via Open-Meteo, `routine.py`) + 5 testes unitários.

## Fase 3 — Motor Visual Vivo & Avatar Waifu 2.5D
- [x] **Milestone 4**: Motor de renderização 2.5D em 60 FPS (`atmosphere.py`, `particles.py`, `avatar.py`, `scene.py`, `canvas.py`) com ciclo dia/noite contínuo, clima animado (chuva, neve, vento, relâmpagos, pétalas, vaga-lumes, estrelas cadentes), paralaxe por cursor, avatar animado (sprites RGBA + fallback procedural, respiração, piscar, olhar, física de mola, rim-light cacheado) + validação visual offscreen.

## Fase 4 — Mente Comportamental & Ponte ComfyUI
- [x] **Milestone 5**: Diretor comportamental (`mind/director.py`) ligando motores neurais a trajes dinâmicos, sono com consolidação, carinho/cutucada/mimo e sussurros por bandit; e cliente read-only ComfyUI (`comfy/bridge.py`, `comfy/workflows.py`) com geração E2E validada do pacote inicial local (`mira/casual.png` + `sky_sanctuary/sunset.png` e `night.png`).

## Fase 5 — Interface Wallpaper Engine, App Principal & Entrega
- [x] **Milestone 6**: Central de Controle Dark Studio (`ui/control_center.py`), Monitor Neural ao vivo (`ui/neural_monitor.py`), Bandeja do Sistema (`ui/tray.py`), composição `app.py` / `main.py` / `start_iawallpaper.ps1`, testes de arquitetura e integração (21/21 verdes), correções visuais e publicação no repositório `https://github.com/maxstiro/IAWallpaper.git`.

## Fase 6 — Evolução Contínua
- [x] **Milestone 7**: Crossfade suave 2.5D (expressões, trajes e horários/clima), workflows img2img consistentes + gerador de pack em lote (`ComfyBridge` + `tools/generate_pack.py`), Criador de Waifu Personalizada na Central de Controle (`+ Nova Waifu`), validação visual com `tools/render_showcase.py`, pack completo da **Mira** (11 sprites RGBA) + **Observatório Celeste** (4 horários) e push via SSH no GitHub.
- [x] **Milestone 8**: **Mundo Vivo 2.5D estilo Ragnarok Online / Tree of Savior / Pokémon NDS** (`world_stage.py`, `avatar.py` full-body caminhável, guarda-chuva automático, balões de emote RO, *click-to-move* no chão, navegação autônoma pelo cérebro LIF, workflows `diorama_*` + `sprite_*` no ComfyUI e pack 2.5D da Mira validado visualmente com 24/24 testes).
- [x] **Milestone 9**: **Ancoragem Aterrada + Animação Multi-Banda 2.5D + Dinâmica Própria do Local + Preset `(TOP)` + Reiluminação 1:1 via Qwen Image 2.1**: auto-recorte nos pés (`trim_sprite_pixmap`), sombra dupla + reflexo em piso molhado, deformação esquelética 3-bandas, raios solares/caustics/fauna viva, leitor read-only de `approved_combos.json` (`RawSexyGlowingGemPencil(TOP)`), reiluminação 1:1 do mesmo diorama nos 4 horários/climas (25/25 testes verdes).
- [ ] **Milestone 10**: Suporte multi-monitor independente + validação de ancoragem ao vivo no Windows 11 Build 26300 + máscaras de profundidade/colisão de caminho (*navmesh* por cenário).
- [ ] **Milestone 9**: Áudio ambiente reativo opcional (chuva suave, vento, lareira) e visualizador/reatividade a áudio do sistema (WASAPI loopback) sincronizando ritmo da avatar com músicas no Spotify/YouTube.
- [ ] **Milestone 10**: Diálogo interativo leve opcional (LLM local via Ollama/llama.cpp) condicionado ao humor da rede LIF, afinidade e memória episódica.
- [ ] **Milestone 11**: Animação avançada de rosto/cabelo (malha deformável 2.5D / piscar dinâmico em sprites AI / loops curtos de vídeo WebM gerados por I2V).
