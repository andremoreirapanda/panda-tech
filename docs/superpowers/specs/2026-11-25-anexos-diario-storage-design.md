# Anexos do Diário no Supabase Storage (30 MB, limite por variável) — desenho (25/11/2026)

## Por quê
Profissionais mandam vídeos curtos de um momento da terapia para a família assistir pelo celular. O limite
de 4 MB (base64 no banco) dá poucos segundos de vídeo. Aprovado pelo usuário: opção B, Supabase Storage,
**30 MB**, fácil de aumentar quando a produção for para o plano Pro (sem mexer no código).

## Objetivos
- Anexo do Diário (foto, áudio, vídeo) até `DIARIO_ANEXO_LIMITE_MB` (padrão 30).
- Vídeo toca no celular sem baixar tudo (link assinado, com suporte a Range do Storage).
- Banco não incha: só metadados em `diario_anexos`.
- Sem as variáveis do Storage, tudo como hoje (base64 no banco, 4 MB): local, CI, homologação sem
  configuração.

## Não objetivos
- Prazo de expiração dos arquivos (hipótese descartada pelo usuário em 25/11/2026).
- Migrar os anexos antigos em base64 (continuam funcionando; produção não tinha nenhum em 25/11/2026).
- Chat e Biblioteca continuam no banco (4 MB).

## Como funciona
- **Variáveis** (cPanel): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (service_role ou secret key, só no
  servidor), `DIARIO_ANEXO_LIMITE_MB` (padrão 30), `DIARIO_ANEXO_BUCKET` (padrão `diario-anexos`).
  Acima de 50 MB, também subir o limite global de upload em Supabase → Storage → Settings.
- **Bucket privado**, criado pelo próprio app na primeira vez (API de Storage), sem SQL.
- **Envio direto do navegador**: `POST /api/diario/<id>/anexo/envio` (permissão, tipo, tamanho) devolve um
  link de envio de uso único; o navegador faz `PUT` do arquivo nele; `POST /api/diario/<id>/anexo/confirmar`
  lê os primeiros bytes e o tamanho real (Range), confere a assinatura (magic bytes) e o limite, grava a linha
  (`storage_path`, `mime`, `tamanho_bytes`, `conteudo_base64` NULL). Se não bater, apaga o arquivo e dá 400.
  Caminho: `clinica-<org>/diario-<id>/<uuid>.<ext>` — o confirmar só aceita o prefixo do próprio registro.
- **Exibir**: `GET /api/diario/anexo/<id>` devolve `url` assinada (1 hora) no lugar do base64.
- **Remover**: apaga a linha e o arquivo (o arquivo, em melhor esforço).
- **CSP**: a origem do `SUPABASE_URL` entra em `img-src`, `media-src` e `connect-src` quando configurado.
- **Tela**: `GET /api/diario/anexos/config` → `{storage, limite_mb}`; a orientação mostra "até N MB"; fotos
  continuam reduzidas no navegador; vídeo/áudio vão como estão, com "Enviando… N%".
- Código do Storage num módulo só (`armazenamento_service.py`), para trocar de fornecedor (ex.: Cloudflare R2)
  mexendo num arquivo.

## Abordagens consideradas
- A: limite maior no banco (~20 MB) — banco gratuito lota, família baixa tudo antes de ver.
- **B (escolhida)**: Supabase Storage, envio direto do navegador.
- B2: envio passando pelo Flask — 30 MB atravessando o Passenger/LiteSpeed do cPanel (limites de corpo e
  memória desconhecidos) e vídeo servido pelo servidor compartilhado; descartada.
- C: reduzir vídeo no aparelho — lento e falha no iPhone.

## Passos de produção
1. Migração `backend/migracoes/migracao_anexos_storage.sql` (colunas `storage_path`, `mime`;
   `conteudo_base64` passa a aceitar NULL) — antes das variáveis.
2. Variáveis no cPanel e restart.
