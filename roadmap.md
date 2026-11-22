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
- [ ] **Milestone 8**: Suporte multi-monitor independente (cenário dedicado por monitor ou modo panorâmico estendido) + validação em tempo real de ancoragem Win11 26300 com múltiplos DPIs.
- [ ] **Milestone 9**: Áudio ambiente reativo opcional (chuva suave, vento, lareira) e visualizador/reatividade a áudio do sistema (WASAPI loopback) sincronizando ritmo da avatar com músicas no Spotify/YouTube.
- [ ] **Milestone 10**: Diálogo interativo leve opcional (LLM local via Ollama/llama.cpp) condicionado ao humor da rede LIF, afinidade e memória episódica.
- [ ] **Milestone 11**: Animação avançada de rosto/cabelo (malha deformável 2.5D / piscar dinâmico em sprites AI / loops curtos de vídeo WebM gerados por I2V).
