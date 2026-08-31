"""
Seed de PRODUÇÃO — usado no piloto com clínica e clientes reais.

Diferença fundamental para `seed.py`: este script NÃO cria pacientes,
jornadas, missões nem qualquer outro dado fictício de demonstração. Ele
popula apenas o mínimo que a plataforma precisa para existir antes de
qualquer clínica real se cadastrar:

  1. Os planos comerciais (Starter/Pro/Enterprise) — exibidos no cadastro
     de clínicas e no painel comercial do Admin.
  2. Uma conta admin_master — é ela quem, pelo painel /admin, cria a
     clínica de verdade (nome, dados da clínica, e-mail do gestor). O
     gestor recebe um link de convite para definir a própria senha (mesmo
     fluxo de convite usado para profissionais e responsáveis).

Diferente de `seed.py` (que sempre recria o banco do zero via schema.sql,
só faz sentido em SQLite local), este script:
  - Funciona tanto em SQLite quanto em Postgres (usa só `db.py`, nunca
    sqlite3 diretamente).
  - É IDEMPOTENTE — pode rodar mais de uma vez sem duplicar dados nem
    apagar nada; se os planos ou o admin já existem, só avisa e segue.
  - NÃO apaga nada. Pressupõe que o schema já foi aplicado (schema.sql
    localmente via seed.py, ou schema_postgres.sql em produção via
    `psql "$DATABASE_URL" -f schema_postgres.sql`).

Uso (com DATABASE_URL apontando para o Postgres de produção):
    DATABASE_URL="postgresql://..." python3 seed_producao.py
"""
import getpass
import json
import os
import sys

from db import query, query_one, execute
from auth import hash_senha

PLANOS_PADRAO = [
    ("starter", "Starter", 29700, 8, 3, 0,
     ["Até 8 pacientes ativos", "Até 3 profissionais", "Jornada terapêutica completa",
      "Biblioteca de exercícios", "Chat com famílias", "Gamificação (Mundo da Criança)",
      "Suporte por e-mail"], "#6A6280", 1),
    ("pro", "Pro", 69700, 30, 10, 1,
     ["Tudo do Starter", "Até 30 pacientes ativos", "Até 10 profissionais", "1 secretária administrativa",
      "Indicadores avançados", "Mural da clínica", "Integrações (WhatsApp, Google Agenda)",
      "Suporte prioritário"], "#5B4FE9", 2),
    ("enterprise", "Enterprise", 149700, None, None, None,
     ["Tudo do Pro", "Pacientes e profissionais ilimitados", "Secretárias administrativas ilimitadas",
      "Múltiplas unidades", "Gerente de conta dedicado", "Onboarding assistido", "SLA garantido"], "#E8875E", 3),
]


def seed_planos():
    ja_existem = query_one("SELECT COUNT(*) as c FROM planos")["c"]
    if ja_existem:
        print(f"↷  Planos já existem ({ja_existem}), pulei.")
        return
    for codigo, nome, preco, lim_pac, lim_prof, lim_sec, recursos, cor, ordem in PLANOS_PADRAO:
        execute(
            """INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes, limite_profissionais,
                                    limite_secretarias, recursos_json, cor, ordem)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (codigo, nome, preco, lim_pac, lim_prof, lim_sec, json.dumps(recursos, ensure_ascii=False), cor, ordem),
        )
    print(f"✅ {len(PLANOS_PADRAO)} planos comerciais criados (starter/pro/enterprise).")


def seed_admin_master():
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    senha = os.environ.get("ADMIN_SENHA", "").strip()
    nome = os.environ.get("ADMIN_NOME", "Administrador da Plataforma").strip()

    existente = query_one("SELECT id FROM usuarios WHERE papel = 'admin_master' AND email = ?", (email,)) if email else None
    if not email:
        # Modo interativo — só é usado se ADMIN_EMAIL não vier via variável de ambiente.
        print("\nNenhum ADMIN_EMAIL definido — configuração interativa da conta admin_master:")
        email = input("  E-mail do admin: ").strip().lower()
        senha = getpass.getpass("  Senha (mín. 8 caracteres): ").strip()
        existente = query_one("SELECT id FROM usuarios WHERE papel = 'admin_master' AND email = ?", (email,))

    if existente:
        print(f"↷  Já existe um admin_master com o e-mail {email}, pulei.")
        return

    if not email or "@" not in email:
        print("⚠️  E-mail inválido — não criei a conta admin_master. Rode de novo com ADMIN_EMAIL/ADMIN_SENHA definidos.")
        return
    if not senha or len(senha) < 8:
        print("⚠️  Senha ausente ou curta demais (mín. 8) — não criei a conta admin_master.")
        return

    senha_hash, salt = hash_senha(senha)
    admin_id = execute(
        """INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel)
           VALUES (NULL, ?, ?, ?, ?, 'admin_master')""",
        (nome, email, senha_hash, salt),
    )
    print(f"✅ Conta admin_master criada (id={admin_id}, e-mail={email}).")
    print("   Use-a para logar e criar a clínica de verdade em Admin > Clínicas.")


if __name__ == "__main__":
    print(f"🗄️  Rodando seed de produção em: {'Postgres (DATABASE_URL)' if os.environ.get('DATABASE_URL') else 'SQLite local'}")
    seed_planos()
    seed_admin_master()
    print("\nConcluído.")
