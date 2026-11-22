# STATE.md — Estado Operacional Vivo (`IAWallpaper`)

> **Instrução Permanente ao Agente**: Leia e atualize `STATE.md`, `PROJETO.md` e `roadmap.md` a cada módulo implementado ou corrigido.
> **Última atualização**: 2026-11-22 (Milestone 6 — MVP Completo & Validado)

---

## 1. Status Atual dos Módulos

| Módulo | Caminho | Status | Notas |
|---|---|---|---|
| Infra & Docs | `PROJETO.md`, `STATE.md`, `roadmap.md`, `AGENTS.md`, `venv/` | 🟢 Concluído | Venv Python 3.12 com 12 pacotes instalados |
| Shared Utils | `iawallpaper/store.py`, `paths.py`, `mathutil.py`, `config.py`, `log.py` | 🟢 Validado | Escrita atômica anti-NaN e recuperação `.corrompido` |
| Núcleo Neural (`core/`) | `nervous_system.py`, `homeostasis.py`, `conditioning.py`, `episodic.py`, `emotion.py`, `persona.py` | 🟢 Validado | 438 neurônios LIF, aprendizado 3 fatores, Rescorla-Wagner, Bandit, Mira & Nyx |
| Plataforma (`plataforma/`) | `desktop_host.py`, `windows.py` | 🟢 Validado | Win11 24H2+ Raised Desktop + WorkerW clássico + auto-pausa tela cheia |
| Sentidos (`sense/`) | `senses.py`, `circadian.py`, `weather.py`, `routine.py` | 🟢 Validado | Ciclo 24h contínuo, Open-Meteo sem API key, classificação de apps + ComfyUI |
| Ponte ComfyUI (`comfy/`) | `bridge.py`, `workflows.py` | 🟢 Validado E2E | Cliente read-only `127.0.0.1:8188`; gerou `mira/casual.png` + cenas `sunset.png`/`night.png` |
| Render (`render/`) | `atmosphere.py`, `particles.py`, `avatar.py`, `scene.py`, `canvas.py` | 🟢 Validado Visual | 60 FPS, rim-light cacheado sem borda, corações/estrelas vetoriais, fallback procedural |
| Mente (`mind/`) | `director.py` | 🟢 Validado | Trajes dinâmicos, sono + consolidação, sussurros por bandit, carinho/cutucada/mimo |
| Interface (`ui/`) | `theme.py`, `control_center.py`, `neural_monitor.py`, `tray.py` | 🟢 Validado | Central 4 abas Dark Studio + Monitor Neural + Bandeja |
| App & Testes | `iawallpaper/app.py`, `main.py`, `start_iawallpaper.ps1`, `tests/` | 🟢 21/21 Verdes | `pytest` completo (arquitetura + unitários + integração + offscreen render) |

---

## 2. Assets Gerados Localmente (ComfyUI Read-Only, fora do Git)
- `assets/generated/personas/mira/casual.png` — Sprite RGBA transparente via `waiIllustriousSDXL_v170.safetensors` + PAG + `Image Rembg (isnet-anime)`.
- `assets/generated/scenes/sky_sanctuary/sunset.png` — Cenário widescreen Pôr do Sol.
- `assets/generated/scenes/sky_sanctuary/night.png` — Cenário widescreen Noite Estrelada.
- **Fallback Procedural**: Qualquer persona/cenário sem PNG gerado opera 100% nativamente via render procedural.

---

## 3. Bugs Encontrados e Resolvidos na Validação Visual (Milestone 6)
1. **Filtro de consolidação em `core/episodic.py`**: Episódios recém-decaídos (`n = 0.995`) eram filtrados por `n >= 1.0` em `preferences()`; ajustado para `n >= 0.2`.
2. **Retângulo semitransparente em volta do sprite RGBA (`render/avatar.py`)**: `CompositionMode_SourceAtop` aplicado no painter principal tingia toda a bounding box (pois o fundo já tinha alpha 255). Corrigido renderizando o tint em buffer `QPixmap` transparente dedicado com cache por paleta (0 artefato de borda + alta performance em 60 FPS).
3. **Glifos de coração/brilho virando caixas em ambientes sem fonte de símbolo (`render/particles.py`)**: Substituídos glifos de fonte por formas vetoriais puras (`QPainterPath`) para corações, estrelas 4-pontas e notas musicais.
4. **Sobreposição visual da lanterna com o card HUD no modo procedural (`render/scene.py`)**: Reposicionada a lanterna para `w * 0.38` e alargado o card HUD para `360x78px`.

---

## 4. Como Executar
- **Modo Wallpaper Dinâmico (atrás dos ícones)**: `.\start_iawallpaper.ps1` ou `.\venv\Scripts\python.exe main.py`
- **Modo Preview + Central de Controle**: `.\start_iawallpaper.ps1 -Preview -Studio`
- **Com Monitor Neural ao Vivo**: `.\start_iawallpaper.ps1 -Preview -Studio -Monitor -Test`
- **Suíte de Testes**: `$env:QT_QPA_PLATFORM="offscreen"; .\venv\Scripts\python.exe -m pytest -v`
