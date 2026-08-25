"""
Teste de fumaça (smoke) do caminho principal dos 4 perfis (gestor,
profissional, responsável, admin), rodando contra Postgres REAL -- não o
SQLite do resto da suíte (ver conftest.py deste diretório para o motivo).

Cenário único e encadeado (mais representativo de uso real do que 4 testes
isolados): uma clínica é criada do zero e percorremos exatamente a cadeia de
eventos descrita no Documento 08 e citada no README como o fluxo de
referência da arquitetura: "missão concluída -> evento -> gamificação ->
notificação -> indicadores". O objetivo não é cobertura exaustiva (isso é
papel da suíte de IDOR e das demais em tests/) -- é pegar, antes do piloto,
qualquer coisa que só quebra no dialeto SQL do Postgres (RETURNING id,
tradução `?` -> `%s`, tipos) e nunca aparece rodando só contra SQLite.

## Como rodar localmente

    docker run -d --rm -p 5432:5432 \\
        -e POSTGRES_USER=panda -e POSTGRES_PASSWORD=panda -e POSTGRES_DB=panda_smoke \\
        postgres:16

    psql postgresql://panda:panda@localhost:5432/panda_smoke -v ON_ERROR_STOP=1 \\
        -f backend/schema_postgres.sql
    psql postgresql://panda:panda@localhost:5432/panda_smoke -v ON_ERROR_STOP=1 \\
        -f backend/migracao_integracoes_plataforma.sql

    cd backend && DATABASE_URL=postgresql://panda:panda@localhost:5432/panda_smoke \\
        ENCANTO_SECRET=x ENCANTO_CRYPTO_KEY=tXk_jawA-xaVDvpOfgcrao05C3ZQ-lsDr2gmQQ9Eq-k= \\
        python -m pytest tests_postgres -v

No CI isso roda automaticamente contra um serviço Postgres efêmero (job
"smoke-postgres" em .github/workflows/tests.yml) -- nunca contra o Supabase
de produção.
"""
from conftest import autenticado, REQUER_POSTGRES

pytestmark = REQUER_POSTGRES


def _nova_organizacao(db_ctx, nome, plano="pro"):
    return db_ctx.execute("INSERT INTO organizacoes (nome, plano) VALUES (?, ?)", (nome, plano))


def _novo_usuario(db_ctx, org_id, nome, email, papel):
    import auth
    senha_hash, salt = auth.hash_senha("senhateste123")
    uid = db_ctx.execute(
        "INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel) VALUES (?, ?, ?, ?, ?, ?)",
        (org_id, nome, email, senha_hash, salt, papel),
    )
    return db_ctx.query_one("SELECT * FROM usuarios WHERE id = ?", (uid,))


def _vincular_responsavel(db_ctx, responsavel_id, paciente_id):
    db_ctx.execute(
        "INSERT INTO responsaveis_pacientes (usuario_id, paciente_id, parentesco) VALUES (?, ?, ?)",
        (responsavel_id, paciente_id, "Responsável"),
    )


def test_fluxo_principal_dos_4_perfis_contra_postgres(client, db_ctx):
    # ---- Setup: uma clínica nova, do zero, com os 4 papéis ----
    org = _nova_organizacao(db_ctx, "Clínica Smoke Postgres")
    gestor = _novo_usuario(db_ctx, org, "Gestora Smoke", "gestora@smoke-postgres.com", "gestor")
    prof = _novo_usuario(db_ctx, org, "Profissional Smoke", "prof@smoke-postgres.com", "profissional")
    resp = _novo_usuario(db_ctx, org, "Família Smoke", "familia@smoke-postgres.com", "responsavel")
    admin = _novo_usuario(db_ctx, None, "Admin Smoke", "admin@smoke-postgres.com", "admin_master")

    # ================= Perfil: GESTOR =================
    # Cadastra paciente já vinculando o profissional (RETURNING id do INSERT
    # em pacientes/usuarios precisa funcionar certo no Postgres aqui).
    r = autenticado(client, gestor).post("/api/pessoas/pacientes", json={
        "nome": "Paciente Smoke", "data_nascimento": "2019-01-01",
        "profissionais_ids": [prof["id"]],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    paciente_id = r.get_json()["id"]
    _vincular_responsavel(db_ctx, resp["id"], paciente_id)

    r = autenticado(client, gestor).post("/api/agenda", json={
        "paciente_id": paciente_id, "profissional_id": prof["id"], "data_hora": "2026-09-01 10:00:00",
    })
    assert r.status_code == 201, r.get_data(as_text=True)

    r = autenticado(client, gestor).get("/api/indicadores/gestor")
    assert r.status_code == 200, r.get_data(as_text=True)

    # ================= Perfil: PROFISSIONAL =================
    r = autenticado(client, prof).post(f"/api/jornada/paciente/{paciente_id}/criar-jornada", json={
        "objetivo_principal": "Objetivo geral do smoke test",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    jornada_id = r.get_json()["id"]

    r = autenticado(client, prof).post(f"/api/jornada/jornada/{jornada_id}/criar-plano", json={
        "titulo": "Plano Smoke", "objetivos": ["Objetivo terapêutico do smoke test"],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    plano_id = r.get_json()["id"]

    r = autenticado(client, prof).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão Smoke", "recompensa_xp": 20,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]

    r = autenticado(client, prof).post(f"/api/diario/jornada/{jornada_id}", json={
        "evolucao_clinica": "Evolução registrada no smoke test",
    })
    assert r.status_code == 201, r.get_data(as_text=True)

    # ================= Perfil: RESPONSÁVEL =================
    # Vê a jornada do próprio filho...
    r = autenticado(client, resp).get(f"/api/jornada/paciente/{paciente_id}")
    assert r.status_code == 200, r.get_data(as_text=True)

    # ...e fecha a cadeia completa do Documento 08:
    # missão concluída -> evento -> gamificação -> notificação.
    r = autenticado(client, resp).post(f"/api/jornada/missao/{missao_id}/concluir")
    assert r.status_code == 200, r.get_data(as_text=True)
    gam_resultado = r.get_json()["gamificacao"]
    assert gam_resultado["xp_total"] == 20
    assert gam_resultado["xp_ganho"] == 20

    # A gamificação persistida bate com o que o endpoint de conclusão devolveu
    # (prova que o UPDATE com RETURNING/commit no Postgres funcionou de verdade,
    # não só que a resposta HTTP "pareceu" certa).
    r = autenticado(client, resp).get(f"/api/gamificacao/paciente/{paciente_id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["gamificacao"]["xp_total"] == 20

    # A notificação "Missão concluída!" chegou pro responsável.
    r = autenticado(client, resp).get("/api/notificacoes")
    assert r.status_code == 200, r.get_data(as_text=True)
    titulos = [n["titulo"] for n in r.get_json()]
    assert any("Missão concluída" in t for t in titulos), titulos

    # ================= Perfil: ADMIN (admin_master) =================
    r = autenticado(client, admin).get("/api/admin/clinicas")
    assert r.status_code == 200, r.get_data(as_text=True)
    nomes_clinicas = [c["nome"] for c in r.get_json()]
    assert "Clínica Smoke Postgres" in nomes_clinicas
