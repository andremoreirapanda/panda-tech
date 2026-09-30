"""Pedido do usuário (26/09/2026): o sino mostra só as 5 últimas
notificações e as mais antigas são apagadas."""
import db
from factories import DuasClinicas
from conftest import autenticado


def _qtd(uid):
    return db.query_one("SELECT COUNT(*) AS c FROM notificacoes WHERE usuario_id = ?", (uid,))["c"]


def test_lista_so_as_5_ultimas_e_apaga_as_antigas(client, db_ctx):
    cen = DuasClinicas()
    uid = cen.gestor_a["id"]
    for i in range(8):
        db.execute("INSERT INTO notificacoes (usuario_id, titulo, mensagem, tipo, criado_em) VALUES (?, ?, ?, 'info', ?)",
                   (uid, f"N{i}", "m", f"2026-09-0{i + 1} 10:00:00"))
    outro = cen.gestor_b["id"]
    db.execute("INSERT INTO notificacoes (usuario_id, titulo, mensagem, tipo) VALUES (?, 'B', 'm', 'info')", (outro,))
    r = autenticado(client, cen.gestor_a).get("/api/notificacoes").get_json()
    assert [n["titulo"] for n in r] == ["N7", "N6", "N5", "N4", "N3"]
    assert _qtd(uid) == 5
    assert _qtd(outro) == 1  # não mexe nas de outro usuário


def test_nova_notificacao_mantem_so_5(db_ctx):
    cen = DuasClinicas()
    uid = cen.gestor_a["id"]
    for i in range(7):
        db.criar_notificacao(uid, f"T{i}", "m", "info")
    assert _qtd(uid) == 5
