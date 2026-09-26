"""White Label completo — achados da revisão final (25/09/2026)."""
import base64

import db
import identidade_service
from factories import DuasClinicas
from conftest import autenticado
from modulos_service import definir_liberacao_admin
from blueprints.pessoas_bp import criar_paciente_core

GRANDE = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x01" * 300_000).decode()
OUTRA = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x02" * 300_000).decode()


def _espiar(monkeypatch, modulo):
    vistos = []
    original = identidade_service.identidade_efetiva

    def espia(org, ativo):
        vistos.append(dict(org))
        return original(org, ativo)
    monkeypatch.setattr(modulo, "identidade_efetiva", espia)
    return vistos


def _com_imagens(org_id):
    db.execute("UPDATE organizacoes SET app_icone_base64 = ?, mundo_mascote_imagem = ?, pandoo_cenario_imagem = ?, "
               "logo_base64 = ? WHERE id = ?", (GRANDE, GRANDE, GRANDE, GRANDE, org_id))


def test_auth_me_nao_carrega_as_imagens_grandes(client, db_ctx, monkeypatch):
    from blueprints import auth_bp
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "white_label", True)
    _com_imagens(cen.org_a)
    vistos = _espiar(monkeypatch, auth_bp)
    org = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()["organizacao"]
    assert vistos and all(len(v.get(c) or "") < 500 for v in vistos
                          for c in ("app_icone_base64", "mundo_mascote_imagem", "pandoo_cenario_imagem"))
    assert org["tem_icone"] and org["tem_mascote_imagem"] and org["tem_cenario_imagem"] and org["versao_imagens"]
    v1 = org["versao_imagens"]
    db.execute("UPDATE organizacoes SET app_icone_base64 = ? WHERE id = ?", (OUTRA, cen.org_a))
    org = autenticado(client, cen.gestor_a).get("/api/auth/me").get_json()["organizacao"]
    assert org["versao_imagens"] != v1


def test_mascote_padrao_nao_carrega_as_imagens(db_ctx, monkeypatch):
    from blueprints import pessoas_bp
    cen = DuasClinicas()
    definir_liberacao_admin(cen.org_a, "white_label", True)
    _com_imagens(cen.org_a)
    db.execute("UPDATE organizacoes SET mundo_mascote = 'clinica' WHERE id = ?", (cen.org_a,))
    vistos = _espiar(monkeypatch, pessoas_bp)
    pid = criar_paciente_core(cen.org_a, "Importado", "2019-01-01")
    assert db.query_one("SELECT avatar_mascote FROM pacientes WHERE id = ?", (pid,))["avatar_mascote"] == "clinica"
    assert vistos and all(len(v.get("logo_base64") or "") < 500 and len(v.get("mundo_mascote_imagem") or "") < 500
                          for v in vistos)
