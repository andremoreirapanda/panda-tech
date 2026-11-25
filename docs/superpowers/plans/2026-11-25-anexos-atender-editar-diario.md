# Anexos no Atender e na edição do Diário — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Campo de anexos no Atender e no "Editar registro" do Diário, com remoção de anexo.

**Architecture:** Backend ganha `DELETE /api/diario/anexo/<id>` e o Atender devolve `diario_id`/`diario.anexos`; o envio continua por `POST /api/diario/<id>/anexo`. No front, um componente único em `diario.js` (`renderCampoAnexos` / `ligarCampoAnexos`) usado pelas três telas.

**Tech Stack:** Flask, SPA JS puro, pytest, Playwright de fumaça.

**Spec:** `docs/superpowers/specs/2026-11-25-anexos-atender-editar-diario-design.md`

## Global Constraints
- Limite de 4 MB por arquivo continua (a etapa 2 muda o armazenamento).
- Texto visível em português, com o nome PandaUp onde aparecer marca.
- Acrescentar ou remover anexo não notifica a família.

## Review Focus
- Responsável ou profissional de outra clínica tentando apagar anexo → 403, anexo fica.
- Profissional que não é autor do registro tentando apagar → 403.
- Falta sem texto + arquivo escolhido no Atender → aviso antes de salvar, nada gravado.
- Upload que falha depois de salvar o atendimento → mensagem de erro, atendimento já salvo não se perde.
- Remover anexo de um registro não deixa a lista quebrada (re-renderiza).

---

### Task 1: Backend — excluir anexo e anexos no Atender

**Files:**
- Modify: `backend/blueprints/diario_bp.py` (rota nova depois de `obter_anexo`)
- Modify: `backend/blueprints/agenda_bp.py` (`_diario_da_consulta`, `salvar_atendimento`)
- Test: `backend/tests/test_anexos_diario_edicao.py`

**Interfaces:**
- Produces: `DELETE /api/diario/anexo/<id>` → `{"ok": true}`; 404 inexistente; 403 sem acesso / não autor (gestor sempre pode na própria clínica). `PUT /api/agenda/<id>/atendimento` → `{"ok": true, "diario_id": int|null}`. `GET .../atendimento` → `diario.anexos = [{id, tipo, nome_arquivo, tamanho_bytes}]`.

- [ ] Testes: `test_autor_apaga_anexo`, `test_gestor_apaga_anexo`, `test_outro_profissional_nao_apaga`, `test_responsavel_nao_apaga`, `test_outra_clinica_nao_apaga`, `test_atendimento_devolve_diario_id` (realizada com descrição → int; falta sem texto → None), `test_get_atendimento_traz_anexos`.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 2: Front — componente de anexos e uso nas três telas

**Files:**
- Modify: `frontend/js/views/diario.js` (componente + Novo Diário + edição)
- Modify: `frontend/js/views/atendimento.js`

**Interfaces:**
- `renderCampoAnexos(prefixo: string, existentes: Array) -> string` (HTML do campo, orientação `renderOrientacaoEnvio("anexo")`, lista).
- `ligarCampoAnexos(raiz: Element, prefixo: string, {existentes, podeRemover}) -> {pendentes: Array, enviar(diarioId): Promise<void>}`; o ✕ de um existente chama `DELETE /diario/anexo/<id>` após `confirm` e tira da lista.
- Atender: antes de salvar, se há pendentes, não há `diario` e não há texto algum → `Toast.erro("Escreva a descrição ou algo para a família para anexar arquivos.")`. Depois do PUT, `enviar(r.diario_id)`.

- [ ] `node --check` nos dois arquivos; suíte Node; Playwright de fumaça (Atender com anexo, editar registro: ver, remover, acrescentar); commit.
