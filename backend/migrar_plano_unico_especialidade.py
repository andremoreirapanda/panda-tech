"""
Migração (08/10/2026): um plano ativo por especialidade garantido no banco.
Encerra duplicados (fica o mais novo) e cria o índice único parcial
`idx_plano_ativo_especialidade`. Funciona igual no SQLite e no Postgres.

    cd backend
    python3 migrar_plano_unico_especialidade.py

Confira que a saída termina com (Postgres) em produção (CLAUDE.md, 7.2).
Seguro rodar de novo.
"""
import os

import db


def _indice_existe():
    if db.USANDO_POSTGRES:
        return bool(db.query_one("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_plano_ativo_especialidade'"))
    return bool(db.get_db().execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_plano_ativo_especialidade'").fetchone())


def migrar():
    banco = "Postgres" if db.USANDO_POSTGRES else "SQLite"
    if _indice_existe():
        print(f"↷  idx_plano_ativo_especialidade já existia ({banco}), pulei")
        return
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migracoes", "migracao_plano_unico_especialidade.sql")
    linhas = [l for l in open(caminho, encoding="utf-8").read().splitlines() if not l.strip().startswith("--")]
    for comando in "\n".join(linhas).split(";"):
        if comando.strip():
            db.execute(comando)
    print(f"✅ Um plano ativo por especialidade: duplicados encerrados e índice criado ({banco})")


if __name__ == "__main__":
    migrar()
