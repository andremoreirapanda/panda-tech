# Anexos no Atender e na edição do Diário — desenho curto (25/11/2026)

## Por quê
Os profissionais querem mandar à família vídeos curtos de um momento da terapia
(a família assiste pelo celular). Hoje só o "+ Novo Diário" da ficha aceita
anexos; o Atender mostra o aviso "Fotos, áudios e vídeos continuam pelo + Novo
Diário" e o "Editar registro" não tem campo de anexo.

## O que muda (etapa 1, este desenho)
- **Atender** (seção "Para a família"): o aviso sai; entra o campo "📎 Anexos
  (opcional)" igual ao do Novo Diário, com os anexos que o registro já tem (✕
  para remover). Os arquivos sobem logo depois de "Salvar atendimento", para o
  registro do Diário da consulta (`PUT /agenda/<id>/atendimento` passa a devolver
  `diario_id`; o `GET` traz `diario.anexos`). Se o atendimento não vai gerar
  registro (falta sem nenhum texto) e há arquivos escolhidos, a tela avisa antes
  de salvar.
- **Editar registro do Diário**: o pop-up mostra os anexos atuais com ✕ e o
  mesmo campo para acrescentar novos.
- **Remover anexo**: rota nova `DELETE /api/diario/anexo/<id>`, com a regra de
  editar o registro (autor ou gestor, da clínica do paciente); vai para a
  auditoria.
- Acrescentar arquivo não manda outro aviso para a família.
- O campo é um componente só em `diario.js` (Novo Diário, Atender e Editar usam o
  mesmo).

## Fora deste desenho (etapa 2, próxima)
Limite maior para vídeo: escolhida a **opção B** (arquivos no Supabase Storage,
~50 MB por arquivo, vídeo tocando sem baixar tudo). O Supabase de produção ainda
está no plano gratuito (troca para o Pro na virada do mês). Terá desenho próprio.

## Abordagens consideradas para o limite
- A: subir o limite no banco (~20 MB) — rápido, mas 10–20 s de vídeo, a família
  baixa tudo antes de ver e o banco gratuito (500 MB) lota.
- **B (escolhida)**: Supabase Storage — vídeo maior, toca sem baixar tudo.
- C: reduzir o vídeo no aparelho — lento e falha no iPhone.
