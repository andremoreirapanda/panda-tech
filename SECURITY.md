# Politica de Seguranca - Panda Tech

O Panda Tech lida com dados sensiveis de desenvolvimento infantil de criancas reais. Se voce encontrar uma vulnerabilidade de seguranca, por favor NAO abra uma Issue publica - relate de forma privada.

## Como reportar

- Preferencial: use a aba "Security" deste repositorio no GitHub, opcao "Report a vulnerability" (relato privado, so o mantenedor ve).
- Alternativa: envie um e-mail para andreluiz.jornalismo@gmail.com com uma descricao do problema e, se possivel, os passos para reproduzir.

## O que esperar

Confirmamos o recebimento em poucos dias uteis, investigamos e corrigimos antes de qualquer divulgacao publica. Como o Panda Tech tem deploy continuo (sem versoes numeradas separadas), a correcao e aplicada direto na versao em producao assim que possivel.

## Escopo

Este repositorio contem o backend (Flask) e o frontend do Panda Tech. Nao inclui a infraestrutura de hospedagem (cPanel) nem os servicos de terceiros integrados (Supabase, Mercado Pago, Google Calendar, WhatsApp Cloud API) - vulnerabilidades nesses servicos devem ser reportadas diretamente a eles.
