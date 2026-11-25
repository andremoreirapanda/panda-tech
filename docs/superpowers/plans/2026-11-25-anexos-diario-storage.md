# Anexos do Diário no Supabase Storage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anexos do Diário até `DIARIO_ANEXO_LIMITE_MB` (30) no Supabase Storage, com envio direto do navegador.

**Architecture:** `armazenamento_service.py` fala com a API REST do Storage (requests). Rotas novas em
`diario_bp` (config, envio, confirmar); `obter_anexo`/`excluir_anexo` entendem `storage_path`. CSP dinâmica.
Front: `ligarCampoAnexos` escolhe o caminho pelo `/diario/anexos/config`.

**Tech Stack:** Flask, requests, JS puro (XHR para progresso), pytest, Playwright com Storage simulado.

**Spec:** `docs/superpowers/specs/2026-11-25-anexos-diario-storage-design.md`

## Global Constraints
- Padrões: limite 30 MB, bucket `diario-anexos`, link de leitura 3600 s.
- Sem `SUPABASE_URL`/`SUPABASE_SERVICE_KEY`: comportamento atual (base64, 4 MB) intacto.
- A chave nunca sai do servidor nem aparece em log/erro.

## Review Focus
- Caminho forjado no confirmar (outro registro/clínica, `..`) → 400, nada gravado.
- Arquivo enviado maior que o limite ou com assinatura errada → 400 e arquivo apagado do Storage.
- Storage fora do ar ao pedir link/confirmar → 502 com mensagem amigável, sem 500.
- Responsável vê `url` só de registro compartilhado (mesma regra de hoje).
- Código implantado antes da migração/variáveis → tudo como hoje.

---

### Task 1: Backend
**Files:** Create `backend/armazenamento_service.py`, `backend/migracoes/migracao_anexos_storage.sql`,
`backend/migrar_anexos_storage.py`, `backend/tests/test_anexos_storage.py`. Modify `backend/blueprints/diario_bp.py`,
`backend/validacao_arquivo.py` (`validar_bytes(binario, categoria)`), `backend/app.py` (CSP), `schema.sql`,
`schema_postgres.sql`, `.env.example`.

**Interfaces (armazenamento_service):** `configurado() -> bool`, `limite_anexo_bytes() -> int`,
`limite_anexo_mb() -> int|float`, `origem() -> str|None`, `criar_link_envio(caminho) -> str`,
`ler_inicio(caminho, n=64) -> (bytes, int)`, `criar_link_leitura(caminho, segundos=3600) -> str`,
`apagar(caminho) -> bool`, exceção `ErroArmazenamento`.

- [ ] Testes (com o serviço simulado por monkeypatch): config sem/com Storage; limite da variável; envio 503
  sem Storage, 400 acima do limite/tipo inválido, 403 outra clínica; confirmar grava linha, recusa caminho de
  outro registro, recusa assinatura errada (e apaga), recusa tamanho real acima do limite (e apaga),
  `ErroArmazenamento` → 502; GET devolve `url` e não `conteudo_base64`; DELETE chama `apagar`; CSP inclui a
  origem só quando configurado.
- [ ] Implementar; suíte do Diário verde; commit.

### Task 2: Front
**Files:** `frontend/js/views/diario.js`, `frontend/js/envio_arquivos.js` (perfil `anexo_diario`).
- [ ] `ligarCampoAnexos` busca a config uma vez; modo Storage: valida com `anexo_diario`, imagem reduzida vira
  Blob, vídeo/áudio vão como `File`; `enviar` faz envio → PUT (XHR com %) → confirmar. Detalhe usa `url` quando
  houver (`preload="metadata"`, `playsinline`).
- [ ] `node --check`, suíte Node, Playwright com Storage simulado local; CLAUDE.md; commit.
