-- ----------------------------------------------------------------------------
-- Migração incremental — Fase 3: Múltiplas mídias por exercício (decisão do
-- usuário, 09/09/2026: "eliminar esse conceito de Tipo do exercício e deixar
-- cada mídia falar por si")
--
-- 1) Nova tabela `midias_exercicio` — cada linha é UMA mídia (foto, vídeo,
--    áudio, PDF ou link) pertencente a um exercício. Um exercício passa a
--    poder ter várias ao mesmo tempo (ex.: um vídeo do YouTube + um PDF de
--    apoio no mesmo exercício), coisa que o modelo antigo (uma coluna
--    `tipo` + um `conteudo_url`/`arquivo_base64` por exercício) não permitia.
--    As colunas antigas de `exercicios` (tipo, conteudo_url, arquivo_nome,
--    arquivo_base64, arquivo_tamanho_bytes) NÃO são removidas — ficam
--    paradas, só por segurança (evita um DROP COLUMN irreversível). O código
--    novo não lê mais essas colunas pra nada além desta migração.
--
-- 2) Backfill — migra o conteúdo único de cada exercício já existente pra
--    uma primeira linha (ordem=0) em midias_exercicio. Pra arquivos, o tipo
--    é redescoberto a partir da ASSINATURA REAL do arquivo (magic bytes,
--    igual o backend faz em validacao_arquivo.py) em vez de confiar na
--    antiga coluna `tipo` — que é só um rótulo pedagógico e nunca garantiu
--    bater com o FORMATO real do arquivo (e nem tinha a opção "áudio").
--    Pra links, o tipo (youtube/vimeo/link genérico) é descoberto pelo
--    formato da própria URL.
--
-- Idempotente: cada INSERT só roda pra exercícios que AINDA não têm nenhuma
-- linha em midias_exercicio (NOT EXISTS) — seguro rodar mais de uma vez.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS midias_exercicio (
    id                    SERIAL PRIMARY KEY,
    exercicio_id          INTEGER NOT NULL REFERENCES exercicios(id),
    tipo                  TEXT NOT NULL CHECK(tipo IN ('imagem','audio','video','pdf','link','youtube','vimeo')),
    conteudo_url          TEXT,
    arquivo_nome          TEXT,
    arquivo_base64        TEXT,
    arquivo_tamanho_bytes INTEGER,
    thumbnail_base64      TEXT,
    ordem                 INTEGER DEFAULT 0,
    criado_em             TEXT DEFAULT (to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS'))
);

CREATE INDEX IF NOT EXISTS idx_midias_exercicio_exercicio_id ON midias_exercicio(exercicio_id);

-- Backfill 1/2 — exercícios cujo conteúdo é um link externo.
INSERT INTO midias_exercicio (exercicio_id, tipo, conteudo_url, ordem)
SELECT e.id,
       CASE
           WHEN e.conteudo_url ~* '(youtube\.com/(watch\?v=|embed/|shorts/)|youtu\.be/)' THEN 'youtube'
           WHEN e.conteudo_url ~* 'vimeo\.com/' THEN 'vimeo'
           ELSE 'link'
       END,
       e.conteudo_url,
       0
FROM exercicios e
WHERE e.conteudo_url IS NOT NULL AND e.conteudo_url != ''
  AND NOT EXISTS (SELECT 1 FROM midias_exercicio m WHERE m.exercicio_id = e.id);

-- Backfill 2/2 — exercícios cujo conteúdo é um arquivo (upload real). O tipo
-- é redescoberto pelos magic bytes do próprio arquivo decodificado, não pela
-- antiga coluna `tipo`.
WITH bin AS (
    SELECT e.id AS exercicio_id,
           decode(regexp_replace(e.arquivo_base64, '^data:[^;]*;base64,', ''), 'base64') AS bytes
    FROM exercicios e
    WHERE (e.arquivo_base64 IS NOT NULL AND e.arquivo_base64 != '')
      AND (e.conteudo_url IS NULL OR e.conteudo_url = '')
      AND NOT EXISTS (SELECT 1 FROM midias_exercicio m WHERE m.exercicio_id = e.id)
)
INSERT INTO midias_exercicio (exercicio_id, tipo, arquivo_nome, arquivo_base64, arquivo_tamanho_bytes, ordem)
SELECT e.id,
       CASE
           -- imagem: JPEG, PNG, GIF, WEBP
           WHEN get_byte(b.bytes, 0) = 255 AND get_byte(b.bytes, 1) = 216 THEN 'imagem'
           WHEN substring(b.bytes from 1 for 4) = '\x89504e47'::bytea THEN 'imagem'
           WHEN substring(b.bytes from 1 for 4) = 'GIF8'::bytea THEN 'imagem'
           WHEN substring(b.bytes from 1 for 4) = 'RIFF'::bytea AND substring(b.bytes from 9 for 4) = 'WEBP'::bytea THEN 'imagem'
           -- pdf
           WHEN substring(b.bytes from 1 for 5) = '%PDF-'::bytea THEN 'pdf'
           -- container ISO-BMFF (bytes 4-8 = "ftyp"): desambigua áudio (M4A/M4B) de vídeo (MP4/MOV/M4V) pela marca
           WHEN substring(b.bytes from 5 for 4) = 'ftyp'::bytea AND substring(b.bytes from 9 for 4) IN ('M4A '::bytea, 'M4B '::bytea) THEN 'audio'
           WHEN substring(b.bytes from 5 for 4) = 'ftyp'::bytea THEN 'video'
           -- vídeo: WEBM/MKV, AVI
           WHEN substring(b.bytes from 1 for 4) = '\x1a45dfa3'::bytea THEN 'video'
           WHEN substring(b.bytes from 1 for 4) = 'RIFF'::bytea AND substring(b.bytes from 9 for 4) = 'AVI '::bytea THEN 'video'
           -- áudio: MP3 (com/sem ID3), WAV, OGG
           WHEN substring(b.bytes from 1 for 3) = 'ID3'::bytea THEN 'audio'
           WHEN get_byte(b.bytes, 0) = 255 AND (get_byte(b.bytes, 1) & 224) = 224 THEN 'audio'
           WHEN substring(b.bytes from 1 for 4) = 'RIFF'::bytea AND substring(b.bytes from 9 for 4) = 'WAVE'::bytea THEN 'audio'
           WHEN substring(b.bytes from 1 for 4) = 'OggS'::bytea THEN 'audio'
           -- assinatura não reconhecida: mantém como imagem (formato mais comum na Biblioteca até aqui) em vez de travar a migração
           ELSE 'imagem'
       END,
       e.arquivo_nome,
       e.arquivo_base64,
       e.arquivo_tamanho_bytes,
       0
FROM exercicios e
JOIN bin b ON b.exercicio_id = e.id;
