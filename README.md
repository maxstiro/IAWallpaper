# IAWallpaper

Wallpaper dinâmico e vivo para Windows 10/11 (inspirado em **Wallpaper Engine** e na arquitetura cognitiva de **Pestinha**), trazendo um **avatar estilo waifu** ciente de contexto, reativo, animado, com aparência dinâmica e aprendizado contínuo dentro de um cenário que responde em tempo real ao horário do dia, clima, uso do PC e interações do mouse.

## Destaques
- **Wallpaper Nativo Atrás dos Ícones**: Ancoragem Win32 com suporte a **Windows 11 24H2+ (Raised Desktop)** e **Windows 10/11 (`WorkerW`)**, além de modo janela/preview e auto-pausa automática em jogos/vídeos em tela cheia.
- **Cérebro com Rede Neural Pulsada (LIF)**: Rede de neurônios de integração e disparo com vazamento, habituação sináptica, aprendizado de três fatores por carinho/recompensa, condicionamento Rescorla-Wagner, memória episódica contextual e homeostase circadiana com sistema de afinidade.
- **Cenário Dinâmico & Clima Real**: Ciclo completo dia/noite (alvorada, manhã, tarde, golden hour, crepúsculo, noite, madrugada) + clima real via Open-Meteo (chuva, tempestade com relâmpagos, neve, neblina, vento, pétalas, vaga-lumes).
- **Avatar Waifu Animado 2.5D**: Respiração natural, piscar, olhar seguindo o cursor, física de mola ao receber carinho/cutucada, iluminação sincronizada ao cenário (*rim-light*) e troca automática de traje/expressão conforme contexto e clima.
- **Ponte ComfyUI (Opcional, Read-Only)**: Conecta-se à API local do ComfyUI (`127.0.0.1:8188`) para gerar novos cenários multi-horário e variantes de aparência da personagem sem alterar nada no ComfyUI.
- **Privacidade Total**: Roda localmente; nunca lê conteúdo de tela, títulos de janela nem digitação.

## Como Executar

```powershell
# 1. Ativar ambiente virtual
.\venv\Scripts\Activate.ps1

# 2. Instalar dependências (se ainda não instaladas)
pip install -r requirements.txt

# 3. Rodar em modo Wallpaper Dinâmico (atrás dos ícones)
python main.py

# 4. Rodar em modo Janela Preview (útil para testes e ajustes)
python main.py --preview

# 5. Abrir diretamente a Central de Controle
python main.py --studio
```

## Testes Automatizados

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest -q
```

## Documentação Viva
- [`PROJETO.md`](PROJETO.md) — Arquitetura em camadas, módulos e histórico de marcos.
- [`STATE.md`](STATE.md) — Estado operacional atual e decisões técnicas.
- [`roadmap.md`](roadmap.md) — Cronograma de Milestones e evolução futura.
