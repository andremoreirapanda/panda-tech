-- Migração incremental — planos configuráveis (25/09/2026). Idempotente.
ALTER TABLE planos ADD COLUMN IF NOT EXISTS plano_base_id INTEGER REFERENCES planos(id);
ALTER TABLE planos ADD COLUMN IF NOT EXISTS disponivel_ate TEXT;
CREATE TABLE IF NOT EXISTS planos_modulos (
    id SERIAL PRIMARY KEY,
    plano_id INTEGER NOT NULL REFERENCES planos(id),
    modulo_codigo TEXT NOT NULL,
    UNIQUE(plano_id, modulo_codigo)
);
-- Mesmo resultado do mapa que estava no código (só preenche se o plano ainda não tem linhas).
INSERT INTO planos_modulos (plano_id, modulo_codigo)
SELECT p.id, m.codigo FROM planos p
JOIN (VALUES ('pro','financeiro'),('pro','ia'),('pro','analytics_avancado'),('pro','integracoes'),
             ('pro','importacao_pacientes'),('enterprise','white_label')) AS m(plano, codigo) ON m.plano = p.codigo
WHERE NOT EXISTS (SELECT 1 FROM planos_modulos x WHERE x.plano_id = p.id)
ON CONFLICT (plano_id, modulo_codigo) DO NOTHING;
UPDATE planos SET plano_base_id = (SELECT id FROM planos WHERE codigo = 'pro')
WHERE codigo = 'enterprise' AND plano_base_id IS NULL;
-- Pacientes ilimitados em todos os planos (decisão do usuário, 25/09/2026).
UPDATE planos SET limite_pacientes = NULL;
