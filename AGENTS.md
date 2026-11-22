# AGENTS.md — Diretrizes Permanentes do Projeto `IAWallpaper`

> **OBRIGATÓRIO PARA TODOS OS AGENTES**:
> 1. **Referenciar sempre**: Leia [`PROJETO.md`](PROJETO.md), [`STATE.md`](STATE.md) e [`roadmap.md`](roadmap.md) ao iniciar qualquer tarefa em `D:\IA\IAWallpaper`.
> 2. **Atualizar sempre**: Toda alteração de código, rede neural, camadas de renderização, plataforma Windows, ponte ComfyUI ou interface **deve** ser refletida em `STATE.md`, `PROJETO.md` e `roadmap.md` antes de encerrar o turno.
> 3. **Isolamento do ComfyUI Studio**: Este projeto apenas *consome* a API HTTP do ComfyUI (`127.0.0.1:8188`) como cliente externo opcional. **Nunca** modifique arquivos dentro de `D:\IA\ComfyUI`.
> 4. **Segurança de Segredos**: Nunca versione tokens (ex: Telegram, APIs) no repositório Git.
> 5. **Camadas Arquiteturais Estritas**:
>    `core < plataforma < sense < comfy < render < mind < ui < app.py`
>    `core/` nunca importa Qt (`PySide6`) nem APIs do sistema operacional. Verificado por `tests/test_arquitetura.py`.
