-- ----------------------------------------------------------------------------
-- Recursos dos planos gerados automaticamente (25/09/2026): o texto livre
-- passa a guardar só "outros benefícios". Limpa os 3 planos originais SÓ se
-- ainda tiverem o texto antigo (que falava em pacientes) — ajuste feito pelo
-- Admin na tela não é tocado. Idempotente.
-- ----------------------------------------------------------------------------
UPDATE planos SET recursos_json = '["Jornada terapêutica completa", "Biblioteca de exercícios", "Chat com famílias", "Gamificação (Mundo da Criança)", "Suporte por e-mail"]'
WHERE codigo = 'starter' AND recursos_json LIKE '%pacientes%';
UPDATE planos SET recursos_json = '["Tudo do Starter", "Mural da clínica", "Suporte prioritário"]'
WHERE codigo = 'pro' AND recursos_json LIKE '%pacientes%';
UPDATE planos SET recursos_json = '["Múltiplas unidades", "Gerente de conta dedicado", "Onboarding assistido", "SLA garantido"]'
WHERE codigo = 'enterprise' AND recursos_json LIKE '%pacientes%';
