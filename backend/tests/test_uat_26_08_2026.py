"""
Regressão para a rodada de UAT manual de 26/08/2026 (achados reportados pelo
gestor durante testes antes do piloto):

1. E-mail em uso por conta de OUTRA clínica: bloqueado no cadastro/edição de
   profissional e na criação de clínica (gestor) — para responsável, o
   comportamento é intencionalmente diferente (ver comentário em
   pessoas_bp.py::vincular_responsavel e o teste correspondente em
   test_idor_pessoas.py).
2. Frequência configurável de missão semanal (antes fixa em 7 dias).
3. Editar/remover vínculo/reenviar convite de um responsável já vinculado —
   sempre restrito à própria clínica.
4. Envio automático do convite de responsável por WhatsApp (pedido de
   follow-up: como o projeto não tem integração de e-mail nenhuma, e o
   WhatsApp Cloud API real já está integrado — ver whatsapp_service.py —,
   o link de convite passa a tentar sair por WhatsApp em vez de depender só
   de copiar/colar manualmente).
"""
import whatsapp_service
from factories import DuasClinicas, vincular_responsavel

from conftest import autenticado


# ---------------------------------------------------------------- E-mail duplicado (staff)

def test_criar_profissional_com_email_de_outra_clinica_e_bloqueado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post("/api/pessoas/profissionais", json={
        "nome": "Fulano", "email": cen.prof_b1["email"],
    })
    assert r.status_code == 409, r.get_data(as_text=True)
    assert db_ctx.query_one(
        "SELECT 1 FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?",
        (cen.org_a, cen.prof_b1["email"].lower()),
    ) is None


def test_editar_profissional_para_email_de_outra_clinica_e_bloqueado(client, db_ctx):
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).put(f"/api/pessoas/profissionais/{cen.prof_a1['id']}", json={
        "email": cen.gestor_b["email"],
    })
    assert r.status_code == 409, r.get_data(as_text=True)


def test_criar_clinica_com_email_de_gestor_de_outra_clinica_e_bloqueado(client, db_ctx):
    cen = DuasClinicas()
    if not db_ctx.query_one("SELECT 1 FROM planos WHERE codigo = 'starter'"):
        db_ctx.execute(
            "INSERT INTO planos (codigo, nome, preco_mensal_centavos, ativo, recursos_json) VALUES ('starter', 'Starter', 9900, 1, '[]')",
        )
    admin = db_ctx.query_one("SELECT * FROM usuarios WHERE papel = 'admin_master' LIMIT 1")
    if not admin:
        import auth
        senha_hash, salt = auth.hash_senha("senhateste123")
        admin_id = db_ctx.execute(
            "INSERT INTO usuarios (organizacao_id, nome, email, senha_hash, senha_salt, papel) VALUES (NULL, ?, ?, ?, ?, 'admin_master')",
            ("Admin", "admin@plataforma.com", senha_hash, salt),
        )
        admin = db_ctx.query_one("SELECT * FROM usuarios WHERE id = ?", (admin_id,))
    r = autenticado(client, admin).post("/api/admin/clinicas", json={
        "nome": "Clínica Nova", "plano": "starter", "gestor_email": cen.gestor_a["email"],
    })
    assert r.status_code == 409, r.get_data(as_text=True)


# ---------------------------------------------------------------- Frequência configurável de missão

def test_missao_semanal_respeita_frequencia_custom_em_vez_de_7_fixo(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão de frequência custom", "tipo": "semanal", "frequencia_dias": 3,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]
    assert db_ctx.query_one("SELECT frequencia_dias FROM missoes WHERE id = ?", (missao_id,))["frequencia_dias"] == 3
    db_ctx.execute("UPDATE missoes SET status = 'iniciada' WHERE id = ?", (missao_id,))
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)

    # Simula 2 dias JÁ marcados via INSERT direto (concluir-dia sempre usa a
    # data real do servidor — não dá pra chamar o endpoint duas vezes no
    # mesmo dia de calendário, então os dois primeiros dias entram direto no
    # banco, igual a um teste real rodado em dias diferentes faria).
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-01')", (missao_id,))
    db_ctx.execute("INSERT INTO missao_dias_concluidos (missao_id, data) VALUES (?, '2026-01-02')", (missao_id,))

    # O 3º dia (hoje, de verdade, via o endpoint) precisa fechar a missão —
    # frequencia_dias=3, não o antigo fixo de 7.
    resp = autenticado(client, cen.resp_a1).post(f"/api/jornada/missao/{missao_id}/concluir-dia")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    corpo = resp.get_json()
    assert corpo["dias_concluidos"] == 3, corpo
    assert corpo["semana_completa"] is True, corpo

    missao_final = db_ctx.query_one("SELECT status FROM missoes WHERE id = ?", (missao_id,))
    assert missao_final["status"] == "concluida"


def test_missao_semanal_sem_frequencia_informada_usa_padrao_7(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão padrão", "tipo": "semanal",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]
    assert db_ctx.query_one("SELECT frequencia_dias FROM missoes WHERE id = ?", (missao_id,))["frequencia_dias"] == 7


def test_missao_semanal_frequencia_fora_do_intervalo_cai_no_padrao_7(client, db_ctx):
    cen = DuasClinicas()
    jornada_id = db_ctx.execute(
        "INSERT INTO jornadas (paciente_id, objetivo_principal) VALUES (?, ?)",
        (cen.paciente_a1, "Objetivo geral"),
    )
    plano_id = db_ctx.execute(
        "INSERT INTO planos_terapeuticos (jornada_id, profissional_id, titulo, data_inicio) VALUES (?, ?, ?, date('now'))",
        (jornada_id, cen.prof_a1["id"], "Plano"),
    )
    r = autenticado(client, cen.gestor_a).post(f"/api/jornada/plano/{plano_id}/criar-missao", json={
        "titulo": "Missão frequência inválida", "tipo": "semanal", "frequencia_dias": 999,
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    missao_id = r.get_json()["id"]
    assert db_ctx.query_one("SELECT frequencia_dias FROM missoes WHERE id = ?", (missao_id,))["frequencia_dias"] == 7


# ---------------------------------------------------------------- Editar/remover/reenviar convite de responsável

def test_editar_responsavel_de_outra_clinica_e_404(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).put(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}", json={"nome": "Hackeado"},
    )
    assert r.status_code == 404, r.get_data(as_text=True)


def test_editar_responsavel_da_propria_clinica_funciona(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).put(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}",
        json={"nome": "Nome Corrigido", "parentesco": "Mãe"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    atualizado = db_ctx.query_one("SELECT nome FROM usuarios WHERE id = ?", (cen.resp_a1["id"],))
    assert atualizado["nome"] == "Nome Corrigido"


def test_remover_vinculo_responsavel_de_outra_clinica_e_404(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).delete(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}")
    assert r.status_code == 404, r.get_data(as_text=True)
    assert db_ctx.query_one(
        "SELECT 1 FROM responsaveis_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.resp_a1["id"], cen.paciente_a1),
    ) is not None


def test_remover_vinculo_responsavel_da_propria_clinica_funciona(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).delete(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert db_ctx.query_one(
        "SELECT 1 FROM responsaveis_pacientes WHERE usuario_id = ? AND paciente_id = ?",
        (cen.resp_a1["id"], cen.paciente_a1),
    ) is None
    # A CONTA do responsável continua existindo — só o vínculo com este paciente some.
    assert db_ctx.query_one("SELECT 1 FROM usuarios WHERE id = ?", (cen.resp_a1["id"],)) is not None


def test_reenviar_convite_de_outra_clinica_e_404(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_b).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}/reenviar-convite")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_reenviar_convite_da_propria_clinica_gera_link(client, db_ctx):
    cen = DuasClinicas()
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "link_convite" in r.get_json()


# ---------------------------------------------------------------- Convite de responsável por WhatsApp

class _RespostaFalsaGraphApi:
    status_code = 200

    def json(self):
        return {"messages": [{"id": "wamid.teste"}]}


def test_convite_novo_responsavel_sem_whatsapp_configurado_nao_envia_mas_nao_quebra(client, db_ctx):
    """Sem a clínica ter configurado o WhatsApp na Central de Integrações
    (cenário padrão hoje), o cadastro continua funcionando normalmente —
    só não sai o envio automático. O link pra copiar manualmente nunca
    depende disso."""
    cen = DuasClinicas()
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel", json={
        "nome": "Novo Responsável", "email": "novo.responsavel@teste.com", "telefone": "11987654321",
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert "link_convite" in corpo
    assert corpo["enviado_whatsapp"] is False


def test_convite_com_whatsapp_configurado_mas_sem_url_app_nao_envia(client, db_ctx, monkeypatch):
    """WhatsApp configurado, mas sem URL_APP no servidor: mandar o link
    relativo (sem domínio) por WhatsApp seria pior que não mandar nada —
    a função precisa recusar o envio automático nesse caso."""
    monkeypatch.delenv("URL_APP", raising=False)
    cen = DuasClinicas()
    whatsapp_service.salvar_configuracao(cen.org_a, "token-de-teste", "id-do-numero-de-teste")
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    db_ctx.execute("UPDATE usuarios SET telefone = ? WHERE id = ?", ("11987654321", cen.resp_a1["id"]))
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["enviado_whatsapp"] is False


def test_convite_com_tudo_configurado_envia_por_whatsapp(client, db_ctx, monkeypatch):
    """Com WhatsApp configurado, telefone cadastrado e URL_APP definida, o
    reenvio de convite dispara mesmo a chamada à Graph API (aqui
    substituída por um dublê, sem sair pra internet de verdade) e reporta
    sucesso pra tela poder avisar quem está usando."""
    monkeypatch.setenv("URL_APP", "https://pandatech.exemplo.com.br")
    monkeypatch.setattr(whatsapp_service.requests, "post", lambda *a, **k: _RespostaFalsaGraphApi())
    cen = DuasClinicas()
    whatsapp_service.salvar_configuracao(cen.org_a, "token-de-teste", "id-do-numero-de-teste")
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    db_ctx.execute("UPDATE usuarios SET telefone = ? WHERE id = ?", ("11987654321", cen.resp_a1["id"]))
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["enviado_whatsapp"] is True


def test_convite_com_falha_na_graph_api_nao_derruba_o_reenvio(client, db_ctx, monkeypatch):
    """Se a Meta recusar o envio (token expirado, template não aprovado
    ainda etc.), o reenvio de convite continua devolvendo o link normalmente
    — só marca enviado_whatsapp como False."""
    def _post_com_erro(*a, **k):
        raise RuntimeError("simulando falha de rede/Graph API")
    monkeypatch.setenv("URL_APP", "https://pandatech.exemplo.com.br")
    monkeypatch.setattr(whatsapp_service, "enviar_template", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("template não aprovado")))
    cen = DuasClinicas()
    whatsapp_service.salvar_configuracao(cen.org_a, "token-de-teste", "id-do-numero-de-teste")
    vincular_responsavel(cen.resp_a1["id"], cen.paciente_a1)
    db_ctx.execute("UPDATE usuarios SET telefone = ? WHERE id = ?", ("11987654321", cen.resp_a1["id"]))
    r = autenticado(client, cen.gestor_a).post(f"/api/pessoas/pacientes/{cen.paciente_a1}/responsaveis/{cen.resp_a1['id']}/reenviar-convite")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "link_convite" in r.get_json()
    assert r.get_json()["enviado_whatsapp"] is False
