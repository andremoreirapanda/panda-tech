"""
Planos configuráveis (25/09/2026): o mapa de módulos por plano saiu do
código (antes: modulos_service.MODULOS_POR_PLANO) e foi para o banco
(planos_modulos + planos.plano_base_id). Este arquivo guarda só o PONTO DE
PARTIDA dos três planos originais, usado pela migração, pelos seeds e pelos
testes. Depois disso quem manda é o Admin, pela tela.
"""
from db import query, query_one, execute

MODULOS_PADRAO = {
    "starter": [],
    "pro": ["financeiro", "ia", "analytics_avancado", "integracoes", "importacao_pacientes"],
    "enterprise": ["white_label"],
}
BASE_PADRAO = {"enterprise": "pro"}
PLANOS_PADRAO_TESTE = [("starter", "Starter", 14970, 1), ("pro", "Pro", 29970, 2), ("enterprise", "Enterprise", 149700, 3)]


def aplicar_modulos_padrao():
    """Idempotente: só preenche plano padrão que ainda não tem nenhuma linha
    em planos_modulos (não desfaz ajuste feito pelo Admin)."""
    for codigo, modulos in MODULOS_PADRAO.items():
        plano = query_one("SELECT id, plano_base_id FROM planos WHERE codigo = ?", (codigo,))
        if not plano:
            continue
        ja_tem = query_one("SELECT 1 FROM planos_modulos WHERE plano_id = ?", (plano["id"],))
        if ja_tem or (not modulos and plano.get("plano_base_id")):
            continue
        for m in modulos:
            execute("INSERT INTO planos_modulos (plano_id, modulo_codigo) VALUES (?, ?)", (plano["id"], m))
        base = BASE_PADRAO.get(codigo)
        if base and not plano.get("plano_base_id"):
            base_row = query_one("SELECT id FROM planos WHERE codigo = ?", (base,))
            if base_row:
                execute("UPDATE planos SET plano_base_id = ? WHERE id = ?", (base_row["id"], plano["id"]))
    execute("UPDATE planos SET limite_pacientes = NULL WHERE limite_pacientes IS NOT NULL")


def criar_planos_padrao_para_teste():
    for codigo, nome, preco, ordem in PLANOS_PADRAO_TESTE:
        if not query_one("SELECT 1 FROM planos WHERE codigo = ?", (codigo,)):
            execute("INSERT INTO planos (codigo, nome, preco_mensal_centavos, ordem) VALUES (?, ?, ?, ?)",
                    (codigo, nome, preco, ordem))
    aplicar_modulos_padrao()
