"""
Migração não-destrutiva: adiciona a coluna `senha_alterada_em` (texto) à
tabela `usuarios` — carimbo da última troca de senha, usado para invalidar
tokens JWT emitidos ANTES da troca (correção de auditoria: antes, um token
roubado continuava válido por até 12h mesmo depois da vítima redefinir a
senha para se proteger — ver auth.py `gerar_token`/`login_required` e
auth_bp.py `redefinir_senha`).

Mesmo padrão de `migrar_notificacoes_entidade.py` — usa `db.py`, funciona
tanto local (SQLite) quanto em produção (Postgres via DATABASE_URL).

Rodar uma vez, depois de atualizar o código (git pull):

    cd backend
    source /caminho/do/virtualenv/bin/activate   # em produção, o mesmo
                                                   # ambiente do passenger_wsgi
    python3 migrar_senha_alterada_em.py

É seguro rodar mais de uma vez — se a coluna já existir, o script detecta e
não faz nada. Usuários existentes ficam com o valor NULL, o que é
equivalente a "nunca trocou a senha desde que este recurso existe" — os
tokens já emitidos continuam válidos normalmente (nenhuma sessão é
derrubada pela migração em si).
"""
import db

COLUNA = ("senha_alterada_em", "TEXT")


def _coluna_existe_sqlite(conn, tabela, coluna):
    linhas = conn.execute(f"PRAGMA table_info({tabela})").fetchall()
    return any(l["name"] == coluna for l in linhas)


def _coluna_existe_postgres(coluna):
    linha = db.query_one(
        "SELECT 1 FROM information_schema.columns WHERE table_name = 'usuarios' AND column_name = ?",
        (coluna,),
    )
    return bool(linha)


def migrar():
    coluna, tipo = COLUNA
    if db.USANDO_POSTGRES:
        if _coluna_existe_postgres(coluna):
            print(f"↷  usuarios.{coluna} já existia (Postgres), pulei")
            return
        db.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {tipo}")
        print(f"✅ usuarios.{coluna} adicionada (Postgres)")
    else:
        conn = db.get_db()
        if _coluna_existe_sqlite(conn, "usuarios", coluna):
            print(f"↷  usuarios.{coluna} já existia (SQLite), pulei")
            return
        conn.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} {tipo}")
        conn.commit()
        print(f"✅ usuarios.{coluna} adicionada (SQLite)")


if __name__ == "__main__":
    migrar()
