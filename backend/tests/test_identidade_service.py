"""White Label completo (25/09/2026): regra única da identidade efetiva."""
import base64

import db
import identidade_service as ids

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
JPG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()
WEBP = base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64).decode()
GIF = base64.b64encode(b"GIF89a" + b"\x00" * 64).decode()

ORG = {"nome": "Clínica X", "logo_emoji": "🌈", "logo_base64": None, "cor_primaria": "#112233",
       "cor_secundaria": "#445566", "nome_ia": "Nina", "nome_moeda_gamificacao": "Estrelinhas",
       "nome_medalha_generico": "Troféu", "app_nome": "Clínica X App", "login_mensagem": "Oi!",
       "mundo_fonte": "baloo", "mundo_fundo": "mar", "mundo_mascote": "🦊", "mundo_comemoracao": "Arrasou!",
       "endereco_login": "clinica-x", "app_icone_base64": None, "mundo_mascote_imagem": None,
       "pandoo_cenario_padrao": "bambu", "pandoo_cenario_imagem": None, "pandoo_cenario_tom": None}


def test_com_modulo_valem_os_da_clinica():
    e = ids.identidade_efetiva(dict(ORG), True)
    assert e["cor_primaria"] == "#112233" and e["nome_moeda_gamificacao"] == "Estrelinhas"
    assert e["mundo_fundo"] == "mar" and e["app_nome"] == "Clínica X App" and e["white_label_ativo"] is True


def test_sem_modulo_valem_os_padroes_mas_logo_e_nome_passam():
    e = ids.identidade_efetiva(dict(ORG), False)
    for campo in ids.CAMPOS_GATED:
        assert e[campo] == ids.PADROES[campo], campo
    assert e["nome"] == "Clínica X" and e["logo_emoji"] == "🌈" and e["white_label_ativo"] is False
    # 26/09/2026: cores e nomes da gamificação passam sempre.
    assert e["cor_primaria"] == "#112233" and e["nome_ia"] == "Nina" and e["nome_moeda_gamificacao"] == "Estrelinhas"
    assert "cor_primaria" not in ids.CAMPOS_GATED and "app_fundo" in ids.CAMPOS_GATED


def test_null_vira_padrao_com_modulo():
    org = dict(ORG, app_nome=None, mundo_fonte=None, cor_primaria=None)
    e = ids.identidade_efetiva(org, True)
    assert e["app_nome"] == "Panda Tech" and e["mundo_fonte"] == "fredoka" and e["cor_primaria"] == "#5B4FE9"


def test_imagens_nao_vao_no_efetivo_mas_flags_sim():
    org = dict(ORG, app_icone_base64=PNG, mundo_mascote_imagem=PNG)
    e = ids.identidade_efetiva(org, True)
    assert "app_icone_base64" not in e and "mundo_mascote_imagem" not in e
    assert e["tem_icone"] is True and e["tem_mascote_imagem"] is True and e["versao_imagens"]
    e2 = ids.identidade_efetiva(org, False)
    assert e2["tem_icone"] is False and e2["tem_mascote_imagem"] is False


def test_mascote_clinica_sem_imagem_vira_padrao():
    e = ids.identidade_efetiva(dict(ORG, mundo_mascote="clinica"), True)
    assert e["mundo_mascote"] == "🐻"


def test_mime_imagem():
    assert ids.mime_imagem(PNG) == "image/png"
    assert ids.mime_imagem(JPG) == "image/jpeg"
    assert ids.mime_imagem(WEBP) == "image/webp"
    assert ids.mime_imagem(GIF) is None
    assert ids.mime_imagem("não é base64 \" onerror=") is None


def test_imagem_pequena_valida_limite():
    grande = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (501 * 1024)).decode()
    assert ids.imagem_pequena_valida(PNG) and not ids.imagem_pequena_valida(grande)


def test_validar_texto():
    assert ids.validar_texto("  Olá  ", 10, "Nome") == ("Olá", None)
    assert ids.validar_texto("", 10, "Nome") == (None, None)
    assert ids.validar_texto(None, 10, "Nome") == (None, None)
    assert ids.validar_texto("x" * 11, 10, "Nome")[1]
    assert ids.validar_texto("<b>", 10, "Nome")[1]
    assert ids.validar_texto(123, 10, "Nome")[1]


def test_slug_e_endereco(db_ctx):
    assert ids.slug_de("Clínica Ênçantar!!", lambda s: False) == "clinica-encantar"
    db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'clinica-encantar')")
    assert ids.gerar_endereco_login("Clínica Encantar") == "clinica-encantar-2"
    assert ids.gerar_endereco_login("!!") == "clinica"


def test_validar_endereco(db_ctx):
    a = db.execute("INSERT INTO organizacoes (nome, endereco_login) VALUES ('A', 'ocupado')")
    b = db.execute("INSERT INTO organizacoes (nome) VALUES ('B')")
    assert ids.validar_endereco_login("Minha-Clinica", b) == ("minha-clinica", None, 200)
    assert ids.validar_endereco_login("ab", b)[2] == 400
    assert ids.validar_endereco_login("com espaço", b)[2] == 400
    assert ids.validar_endereco_login("-abc", b)[2] == 400
    assert ids.validar_endereco_login(None, b)[2] == 400
    assert ids.validar_endereco_login("ocupado", b)[2] == 409
    assert ids.validar_endereco_login("ocupado", a) == ("ocupado", None, 200)


def test_garantir_endereco(db_ctx):
    org = db.execute("INSERT INTO organizacoes (nome) VALUES ('Clínica Sol')")
    assert ids.garantir_endereco_login(org) == "clinica-sol"
    assert ids.garantir_endereco_login(org) == "clinica-sol"
