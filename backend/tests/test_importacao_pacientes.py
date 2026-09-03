"""
Importação em lote de pacientes (insight do usuário, 02/09/2026): clínicas
que já têm uma base cadastrada em outro sistema podem importar de uma vez,
em vez de recadastrar um por um. Módulo opcional Pro/Enterprise (ver
modulos_service.py).

Cobre: módulo bloqueado no plano Starter, preview validando linha a linha,
confirmação criando pacientes e reaproveitando a conta do responsável por
e-mail (mesma regra de test_segundo_filho_mesmo_responsavel.py — crítico
aqui porque uma base legada quase sempre repete o e-mail entre irmãos), e
o limite de pacientes do plano sendo respeitado no lote inteiro, não só
linha a linha.
"""
import time

from factories import DuasClinicas

from conftest import autenticado
from blueprints.importacao_bp import _email_formato_valido


def _linha(nome="Filho Um", nascimento="2019-05-20", email="familia@exemplo.com", resp_nome="Familia Exemplo"):
    return {
        "nome": nome, "data_nascimento": nascimento,
        "responsavel_nome": resp_nome, "responsavel_email": email,
    }


def test_preview_bloqueado_para_plano_sem_o_modulo(client, db_ctx):
    cen = DuasClinicas()  # nasce no plano 'premium' — não libera o módulo (ver MODULOS_POR_PLANO)
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/preview", json={"linhas": [_linha()]})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_preview_libera_para_plano_pro(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/preview", json={"linhas": [_linha()]})
    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["validas"] == 1
    assert corpo["linhas"][0]["valido"] is True
    assert corpo["linhas"][0]["responsavel_status"] == "novo"


def test_preview_aponta_erros_por_linha_sem_derrubar_o_lote(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    linhas = [
        _linha(nome="", nascimento="2019-05-20"),  # sem nome
        _linha(nascimento="20/05/2019"),  # formato de data errado
        _linha(email="nao-e-email"),  # e-mail inválido
        _linha(nome="Filho Válido"),  # essa é boa
    ]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/preview", json={"linhas": linhas})
    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["total"] == 4
    assert corpo["validas"] == 1
    assert corpo["invalidas"] == 3
    assert corpo["linhas"][0]["valido"] is False
    assert any("Nome" in e for e in corpo["linhas"][0]["erros"])
    assert corpo["linhas"][1]["valido"] is False
    assert any("AAAA-MM-DD" in e for e in corpo["linhas"][1]["erros"])
    assert corpo["linhas"][2]["valido"] is False
    assert corpo["linhas"][3]["valido"] is True


def test_preview_avisa_quando_mesmo_email_do_lote_tem_nomes_diferentes(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    linhas = [
        _linha(nome="Filho Um", email="familia@exemplo.com", resp_nome="Familia Exemplo"),
        _linha(nome="Filho Dois", email="Familia@Exemplo.com", resp_nome="Familia Exemplo Com Typo"),
    ]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/preview", json={"linhas": linhas})
    corpo = r.get_json()
    assert corpo["linhas"][0]["aviso"] is None
    assert corpo["linhas"][1]["aviso"] is not None
    assert "Familia Exemplo" in corpo["linhas"][1]["aviso"]


def test_confirmar_cria_pacientes_e_reaproveita_conta_do_responsavel_por_email(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    linhas = [
        _linha(nome="Filho Um", email="duasfilhas@exemplo.com", resp_nome="Familia Dois Filhos"),
        _linha(nome="Filho Dois", email="DuasFilhas@Exemplo.com", resp_nome="Familia Dois Filhos"),
    ]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={"linhas": linhas})
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["total_criados"] == 2
    assert corpo["ignorados"] == []
    assert corpo["criados"][0]["responsavel_novo"] is True
    assert corpo["criados"][1]["responsavel_novo"] is False  # reaproveitou a conta da linha anterior

    contas = db_ctx.query(
        "SELECT id FROM usuarios WHERE organizacao_id = ? AND lower(email) = ?",
        (cen.org_a, "duasfilhas@exemplo.com"),
    )
    assert len(contas) == 1  # nunca duas contas pro mesmo e-mail nesta clínica

    pacientes = db_ctx.query("SELECT id FROM pacientes WHERE organizacao_id = ?", (cen.org_a,))
    ids_pacientes_criados = {c["paciente_id"] for c in corpo["criados"]}
    assert ids_pacientes_criados.issubset({p["id"] for p in pacientes})


def test_confirmar_reaproveita_conta_ja_existente_antes_do_lote(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    # Primeiro filho já cadastrado manualmente antes da importação (mesmo fluxo de test_segundo_filho_mesmo_responsavel.py).
    r1 = autenticado(client, cen.gestor_a).post(
        f"/api/pessoas/pacientes/{cen.paciente_a1}/vincular-responsavel",
        json={"nome": "Familia Legada", "email": "legado@exemplo.com"},
    )
    usuario_id_1 = r1.get_json()["usuario_id"]

    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={
        "linhas": [_linha(nome="Segundo Filho Importado", email="legado@exemplo.com", resp_nome="Familia Legada")],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["criados"][0]["responsavel_novo"] is False

    vinculos = db_ctx.query(
        "SELECT paciente_id FROM responsaveis_pacientes WHERE usuario_id = ?", (usuario_id_1,)
    )
    assert len(vinculos) == 2  # o filho antigo + o importado, mesma conta


def test_confirmar_ignora_linhas_invalidas_mas_cria_as_boas(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    linhas = [_linha(nome=""), _linha(nome="Filho Válido")]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={"linhas": linhas})
    assert r.status_code == 201, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["total_criados"] == 1
    assert len(corpo["ignorados"]) == 1
    assert corpo["ignorados"][0]["linha"] == 0


def test_confirmar_respeita_limite_de_pacientes_do_plano_para_o_lote_inteiro(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    db_ctx.execute(
        "INSERT INTO planos (codigo, nome, preco_mensal_centavos, limite_pacientes) VALUES ('pro', 'Pro', 19900, 3)",
    )
    # A clínica já tem 2 pacientes (paciente_a1, paciente_a2 do fixture) — só cabe mais 1.
    linhas = [_linha(nome="Filho A", email="a@x.com"), _linha(nome="Filho B", email="b@x.com")]
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={"linhas": linhas})
    assert r.status_code == 403, r.get_data(as_text=True)
    assert "limite" in r.get_json()["erro"].lower() or "Pro" in r.get_json()["erro"]

    # Nada foi criado — nem a linha que caberia sozinha.
    pacientes = db_ctx.query("SELECT id FROM pacientes WHERE organizacao_id = ?", (cen.org_a,))
    assert len(pacientes) == 2


def test_secretaria_nao_pode_importar(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id = ?", (cen.org_a,))
    from factories import novo_usuario
    sec = novo_usuario(cen.org_a, "Secretária A", "secretaria.import@a.com", "secretaria")
    r = autenticado(client, sec).post("/api/importacao/pacientes/preview", json={"linhas": [_linha()]})
    assert r.status_code == 403, r.get_data(as_text=True)


def test_confirmar_nao_vaza_reaproveitamento_de_conta_de_outra_clinica(client, db_ctx):
    cen = DuasClinicas()
    db_ctx.execute("UPDATE organizacoes SET plano = 'pro' WHERE id IN (?, ?)", (cen.org_a, cen.org_b))
    # resp_b1 (org B) usa o e-mail "familia.compartilhada@x.com" — clínica A
    # importando o MESMO e-mail não pode reaproveitar a conta de B.
    r = autenticado(client, cen.gestor_a).post("/api/importacao/pacientes/confirmar", json={
        "linhas": [_linha(email="familia.compartilhada@x.com", resp_nome="Familia Compartilhada")],
    })
    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["criados"][0]["responsavel_novo"] is True  # criou conta NOVA nesta clínica, não reaproveitou a de B


# ---------------------------------------------------------------------------
# Correção de segurança 04/09/2026: a regex antiga de e-mail
# (`^[^@\s]+@[^@\s]+\.[^@\s]+$`) foi apontada pelo CodeQL como "polynomial
# regular expression used on uncontrolled data" — o grupo do meio podia
# incluir pontos, então uma linha de planilha com e-mail malicioso (muitos
# pontos, terminando em algo que não fecha o "match") fazia o motor de regex
# testar cada ponto como candidato antes de falhar, O(n²) numa linha só.
# Trocamos por validação com string simples (`_email_formato_valido`), O(n)
# garantido. Os testes abaixo cobrem: os mesmos casos válidos/inválidos de
# antes (equivalência de comportamento) e uma entrada adversarial que
# comprovava o custo quadrático na regex antiga, com orçamento de tempo bem
# folgado (a validação por string devolve em microssegundos).
# ---------------------------------------------------------------------------

def test_email_formato_valido_aceita_formatos_comuns():
    assert _email_formato_valido("familia@exemplo.com") is True
    assert _email_formato_valido("nome.sobrenome@sub.dominio.com.br") is True


def test_email_formato_valido_rejeita_formatos_invalidos():
    assert _email_formato_valido("nao-e-email") is False          # sem @
    assert _email_formato_valido("a@b@c.com") is False             # dois @
    assert _email_formato_valido("") is False                      # vazio
    assert _email_formato_valido("a b@dominio.com") is False       # espaço
    assert _email_formato_valido("a@dominio") is False             # sem ponto no domínio
    assert _email_formato_valido("a@.dominio.com") is False        # domínio começa com ponto
    assert _email_formato_valido("a@dominio.com.") is False        # domínio termina com ponto
    assert _email_formato_valido("a@") is False                    # domínio vazio
    assert _email_formato_valido("@dominio.com") is False          # local vazio


def test_email_formato_valido_nao_trava_com_entrada_adversarial():
    # Payload clássico de ReDoS pra esse formato de regex: muitos pontos no
    # "domínio" seguidos de um caractere que nunca fecha o match (espaço,
    # que a checagem de formato rejeita de cara). Na regex antiga, cada
    # ponto virava um candidato a "." literal a testar via backtracking.
    malicioso = "a@" + ("a" * 20 + ".") * 2000 + " "
    inicio = time.monotonic()
    resultado = _email_formato_valido(malicioso)
    duracao = time.monotonic() - inicio
    assert resultado is False
    assert duracao < 0.5, f"validação de e-mail demorou {duracao:.3f}s — indício de custo não-linear"
