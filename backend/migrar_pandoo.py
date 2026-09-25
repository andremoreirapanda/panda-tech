"""
Migração não-destrutiva do Pandoo fase 1 (25/09/2026): colunas de cenário em
`organizacoes`, `modulos_clinica.liberado_admin` e as tabelas `pandoo_jogos`
e `pandoo_resultados`. Em produção (Postgres) aplica
`migracoes/migracao_pandoo.sql`; local (SQLite) usa o DDL equivalente.

    cd backend && python3 migrar_pandoo.py

Confira que a saída termina com (Postgres) em produção (ver CLAUDE.md, seção
7.2). Seguro rodar mais de uma vez.
"""
import os
import db

COLUNAS = [
    ("organizacoes", "pandoo_cenario_padrao", "TEXT DEFAULT 'bambu'"),
    ("organizacoes", "pandoo_cenario_imagem", "TEXT"),
    ("organizacoes", "pandoo_cenario_tom", "TEXT"),
    ("modulos_clinica", "liberado_admin", "INTEGER DEFAULT 0"),
]

DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS pandoo_jogos (
    exercicio_id INTEGER PRIMARY KEY REFERENCES exercicios(id), modelo TEXT NOT NULL,
    conteudo_json TEXT NOT NULL, regras_json TEXT NOT NULL DEFAULT '{}', cenario TEXT,
    total_itens INTEGER DEFAULT 0, atualizado_em TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS pandoo_resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT, organizacao_id INTEGER NOT NULL REFERENCES organizacoes(id),
    paciente_id INTEGER NOT NULL REFERENCES pacientes(id), exercicio_id INTEGER NOT NULL REFERENCES exercicios(id),
    missao_id INTEGER REFERENCES missoes(id), atividade_id INTEGER REFERENCES atividades(id), modelo TEXT NOT NULL,
    iniciado_em TEXT, finalizado_em TEXT, encerrado_antes INTEGER DEFAULT 0, total_rodadas INTEGER DEFAULT 0,
    acertos INTEGER DEFAULT 0, a_treinar INTEGER DEFAULT 0, detalhes_json TEXT NOT NULL DEFAULT '[]',
    usuario_id INTEGER REFERENCES usuarios(id), data_local TEXT NOT NULL, criado_em TEXT DEFAULT (datetime('now')));
CREATE INDEX IF NOT EXISTS idx_pandoo_res_paciente ON pandoo_resultados(paciente_id);
CREATE INDEX IF NOT EXISTS idx_pandoo_res_missao ON pandoo_resultados(missao_id, atividade_id, data_local);
UPDATE exercicios SET tipo = 'atividade' WHERE tipo = 'jogo' AND id NOT IN (SELECT exercicio_id FROM pandoo_jogos);
"""


def migrar():
    if db.USANDO_POSTGRES:
        caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_pandoo.sql")
        sql = open(caminho, encoding="utf-8").read()
        linhas = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        for comando in "\n".join(linhas).split(";"):
            if comando.strip():
                db.execute(comando)
        print("✅ Pandoo: colunas, tabelas e índices conferidos (Postgres)")
        return
    conn = db.get_db()
    for tabela, coluna, tipo in COLUNAS:
        existentes = {l["name"] for l in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}
        if coluna in existentes:
            print(f"↷  {tabela}.{coluna} já existia (SQLite), pulei")
            continue
        conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        print(f"✅ {tabela}.{coluna} adicionada (SQLite)")
    conn.executescript(DDL_SQLITE)
    conn.commit()
    print("✅ Pandoo: tabelas e índices conferidos (SQLite)")


if __name__ == "__main__":
    migrar()
